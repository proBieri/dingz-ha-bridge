import base64

import pytest
from aiohttp.test_utils import TestClient, TestServer

from dingz_ha_bridge import web
from dingz_ha_bridge.device_api import DeviceStatus, MqttResult
from dingz_ha_bridge.scan import FoundDevice

HEADERS = {"X-Dingz-UI": "1"}
DEVICE = FoundDevice("192.0.2.50", mac="AA", name="Test", mqtt_id="dingztest", sources={"mdns"})


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> list:
    calls: list = []

    async def fake_scan(**kwargs: object) -> list[FoundDevice]:
        calls.append(kwargs)
        return [DEVICE]

    async def fake_status(self: web.DeviceApi) -> DeviceStatus:
        return DeviceStatus(self.host, name="Test", mqtt_uri="mqtt://u:***@b")

    async def fake_set_mqtt(self: web.DeviceApi, uri: str, enable: bool = True) -> MqttResult:
        calls.append(("set_mqtt", self.host, uri, enable))
        return MqttResult(True, "MQTT settings applied", "mqtt://u:***@b")

    monkeypatch.setattr(web, "scan", fake_scan)
    monkeypatch.setattr(web.DeviceApi, "status", fake_status)
    monkeypatch.setattr(web.DeviceApi, "set_mqtt", fake_set_mqtt)
    return calls


async def client_for(config: web.WebConfig) -> TestClient:
    client = TestClient(TestServer(web.create_app(config)))
    await client.start_server()
    await client.app[web.SCAN_TASK_KEY]
    return client


async def test_static_and_device_list() -> None:
    client = await client_for(web.WebConfig(default_broker="192.0.2.10"))
    try:
        page = await client.get("/")
        assert page.status == 200
        assert "Content-Security-Policy" in page.headers
        assert (await client.get("/app.js")).status == 200
        data = await (await client.get("/api/devices")).json()
        assert data["default_broker"] == "192.0.2.10"
        assert [d["host"] for d in data["devices"]] == ["192.0.2.50"]
    finally:
        await client.close()


async def test_post_needs_csrf_header() -> None:
    client = await client_for(web.WebConfig())
    try:
        assert (await client.post("/api/scan", json={})).status == 403
        assert (await client.post("/api/scan", json={}, headers=HEADERS)).status == 200
    finally:
        await client.close()


async def test_only_scanned_hosts(no_network: list) -> None:
    client = await client_for(web.WebConfig())
    try:
        assert (await client.get("/api/devices/192.0.2.99/status")).status == 404
        status = await (await client.get("/api/devices/192.0.2.50/status")).json()
        assert status["name"] == "Test"
        resp = await client.post(
            "/api/devices/192.0.2.99/mqtt", json={"broker": "b"}, headers=HEADERS
        )
        assert resp.status == 404
    finally:
        await client.close()


async def test_set_mqtt_builds_uri(no_network: list) -> None:
    client = await client_for(web.WebConfig())
    try:
        body = {"broker": "b", "port": 1883, "username": "u", "password": "p w", "enable": True}
        resp = await client.post("/api/devices/192.0.2.50/mqtt", json=body, headers=HEADERS)
        data = await resp.json()
        assert data["ok"] is True
        assert "p w" not in await resp.text()
        assert ("set_mqtt", "192.0.2.50", "mqtt://u:p%20w@b", True) in no_network
        missing = await client.post("/api/devices/192.0.2.50/mqtt", json={}, headers=HEADERS)
        assert missing.status == 400
    finally:
        await client.close()


async def test_basic_auth() -> None:
    client = await client_for(web.WebConfig(password="pw"))
    try:
        assert (await client.get("/api/devices")).status == 401
        good = "Basic " + base64.b64encode(b"admin:pw").decode()
        bad = "Basic " + base64.b64encode(b"admin:nope").decode()
        assert (await client.get("/api/devices", headers={"Authorization": bad})).status == 401
        assert (await client.get("/api/devices", headers={"Authorization": good})).status == 200
    finally:
        await client.close()


async def test_ingress_only_rejects_direct_access() -> None:
    client = await client_for(web.WebConfig(ingress_only=True))
    try:
        assert (await client.get("/")).status == 403
    finally:
        await client.close()


async def test_wifi_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    from dingz_ha_bridge.device_api import WifiSignal

    calls = []

    async def fake_wifi(self: web.DeviceApi) -> WifiSignal:
        calls.append(self.host)
        return WifiSignal("IOT", -60, "excellent", 80, [-60])

    monkeypatch.setattr(web.DeviceApi, "wifi", fake_wifi)
    client = await client_for(web.WebConfig())
    try:
        first = await (await client.get("/api/devices/192.0.2.50/wifi")).json()
        await client.get("/api/devices/192.0.2.50/wifi")
        assert (first["rssi"], len(calls)) == (-60, 1)
        await client.get("/api/devices/192.0.2.50/wifi?refresh=1")
        assert len(calls) == 2
        assert (await client.get("/api/devices/192.0.2.99/wifi")).status == 404
    finally:
        await client.close()


async def test_version_endpoint_caches_and_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def fake_check() -> web.updates.UpdateInfo:
        calls.append(1)
        return web.updates.UpdateInfo(current="0.1.0", latest="0.2.0", update_available=True)

    monkeypatch.setattr(web.updates, "check", fake_check)
    client = await client_for(web.WebConfig())
    try:
        data = await (await client.get("/api/version")).json()
        await client.get("/api/version")
        assert (data["latest"], data["update_available"], len(calls)) == ("0.2.0", True, 1)
        assert data["repo_url"].startswith("https://github.com/")
    finally:
        await client.close()

    client = await client_for(web.WebConfig(update_check=False))
    try:
        data = await (await client.get("/api/version")).json()
        assert data["error_code"] == "disabled"
        assert len(calls) == 1
    finally:
        await client.close()

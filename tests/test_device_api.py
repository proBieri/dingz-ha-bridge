import json
from pathlib import Path

from dingz_ha_bridge import discovery as d
from dingz_ha_bridge.device_api import parse_enrichment

HTTP = Path(__file__).parent / "fixtures" / "http"


def load(name: str) -> object:
    return json.loads((HTTP / f"{name}.json").read_text())


def test_parse_enrichment_from_fixtures() -> None:
    e = parse_enrichment(load("system_config"), load("output_config"))
    assert e.name == "Dingz Test"
    assert e.output_names == {n: f"Output {n}" for n in range(4)}
    assert e.output_types == {0: "light", 1: "light", 2: "light", 3: "light"}
    assert e.dimmable == {0: False, 1: False, 2: False, 3: False}


def test_parse_enrichment_tolerates_garbage() -> None:
    e = parse_enrichment(None, {"outputs": [None, {"name": " ", "type": "power_socket"}]})
    assert e == d.Enrichment(output_types={1: "power_socket"})


def test_enrich_changes_config() -> None:
    dev = d.DeviceState("dingztest", model="dz1f-4b", lights={0, 1})
    e = d.Enrichment(
        name="Dingz Test",
        output_names={0: "Table lamp", 1: "Steckdose"},
        output_types={0: "light", 1: "power_socket"},
        dimmable={0: False, 1: False},
    )
    assert dev.enrich(e)
    assert not dev.enrich(e)
    config = d.build_device_config(dev)
    assert config["device"]["name"] == "Dingz Test"
    light = config["components"]["dingz_dingztest_light_0"]
    assert (light["platform"], light["name"]) == ("light", "Table lamp")
    assert "brightness_template" not in light
    socket = config["components"]["dingz_dingztest_light_1"]
    assert (socket["platform"], socket["name"]) == ("switch", "Steckdose")


def test_parse_status_from_fixtures() -> None:
    from dingz_ha_bridge.device_api import parse_status

    data = {
        name: load(name)
        for name in ("info", "device", "system_config", "services_config", "protected", "outputs")
    }
    # The fixture holds no credentials; check masking with a URI that has a password.
    data["services_config"]["mqtt"]["uri"] = "mqtt://user:secret@192.0.2.10"
    status = parse_status("192.0.2.50", data)
    assert status.mac == "246F28000001"
    assert status.mqtt_id == "dingztest"
    assert status.model == "dz1f-4b"
    assert status.fw_version == "2.4.3"
    assert status.protected is False
    assert status.mqtt_enabled is True
    assert status.mqtt_uri == "mqtt://user:***@192.0.2.10"
    assert len(status.outputs) == 4
    assert "secret" not in json.dumps(status.__dict__)


def test_build_and_mask_uri() -> None:
    from dingz_ha_bridge.device_api import build_mqtt_uri, mask_uri

    assert build_mqtt_uri("192.0.2.1") == "mqtt://192.0.2.1"
    assert build_mqtt_uri("b", 1884, "u") == "mqtt://u@b:1884"
    uri = build_mqtt_uri("b", 1883, "dingz user", "p@ss:w/rd")
    assert uri == "mqtt://dingz%20user:p%40ss%3Aw%2Frd@b"
    assert mask_uri(uri) == "mqtt://dingz%20user:***@b"
    assert mask_uri("mqtt://b:1883") == "mqtt://b:1883"


class FakeDevice:
    """Stands in for the HTTP layer of DeviceApi."""

    def __init__(self, accept: bool) -> None:
        self.config = {"mqtt": {"uri": "mqtt://old", "enable": False}, "mdns": True}
        self.accept = accept
        self.posted: list[object] = []

    async def get(self, path: str) -> object:
        assert path == "services_config"
        return json.loads(json.dumps(self.config))

    async def post_json(self, path: str, body: dict) -> None:
        self.posted.append(body)
        if self.accept:
            self.config["mqtt"].update(body["mqtt"])


async def test_set_mqtt_verifies_result(monkeypatch) -> None:
    from dingz_ha_bridge.device_api import DeviceApi

    for accept, ok in ((True, True), (False, False)):
        fake = FakeDevice(accept)
        api = DeviceApi("h")
        monkeypatch.setattr(api, "get", fake.get)
        monkeypatch.setattr(api, "post_json", fake.post_json)
        result = await api.set_mqtt("mqtt://u:pw@b", enable=True)
        assert result.ok is ok
        assert fake.posted == [{"mqtt": {"uri": "mqtt://u:pw@b", "enable": True}}]
        assert "pw" not in (result.uri or "")


def test_parse_wifi_picks_strongest_ap_of_own_ssid() -> None:
    from dingz_ha_bridge.device_api import parse_wifi

    scan = ["Home", -66, "IOT", -68, "IOT", -90, "IOT", -69, "Other", -40]
    w = parse_wifi("IOT", scan)
    assert (w.rssi, w.percent, w.quality, w.access_points) == (-68, 64, "good", [-68, -69, -90])
    assert parse_wifi("Missing", scan).rssi is None
    assert parse_wifi(None, scan).quality is None
    assert parse_wifi("IOT", {"bad": 1}).access_points == []


def test_rssi_rating() -> None:
    from dingz_ha_bridge.device_api import rate_rssi, rssi_percent

    assert [rate_rssi(v) for v in (-55, -65, -75, -85)] == ["excellent", "good", "fair", "poor"]
    assert (rssi_percent(-40), rssi_percent(-75), rssi_percent(-110)) == (100, 50, 0)


async def test_room_temperature(monkeypatch) -> None:
    from dingz_ha_bridge.device_api import DeviceApi

    api = DeviceApi("h")

    async def fake_get(path: str) -> object:
        return load("sensors") if path == "sensors" else None

    monkeypatch.setattr(api, "get", fake_get)
    assert await api.room_temperature() == load("sensors")["room_temperature"]

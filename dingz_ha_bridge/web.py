"""Optional web UI: list dingz devices, show their status, set their MQTT broker.

Needs the extra `ui` (aiohttp, zeroconf). Security:
- add-on: only requests via HA ingress (peer 172.30.32.2) are served;
- standalone: HTTP basic auth when a password is set (mandatory off localhost);
- state-changing requests need the header ``X-Dingz-UI: 1`` (blocks cross-site forms);
- device endpoints only accept hosts from the last scan (no requests to arbitrary hosts);
- broker passwords are never sent back to the browser.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import hmac
import logging
import time
from dataclasses import dataclass
from importlib import resources
from typing import TYPE_CHECKING, Any

from aiohttp import web

from . import REPO_URL, __version__, updates
from .addon import INGRESS_PEER
from .device_api import DeviceApi, DeviceApiError, WifiSignal, build_mqtt_uri
from .scan import FoundDevice, merge_devices, scan

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .bridge import Bridge, MqttConfig

log = logging.getLogger(__name__)

STATIC_FILES = {
    "": ("index.html", "text/html"),
    "app.js": ("app.js", "text/javascript"),
    "style.css": ("style.css", "text/css"),
}
CSRF_HEADER = "X-Dingz-UI"
# A WLAN measurement is a radio scan on the device: cache it and run few at a time.
WIFI_CACHE_SECONDS = 300
WIFI_CONCURRENCY = 2
UPDATE_CACHE_SECONDS = 6 * 3600
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


@dataclass
class WebConfig:
    bind: str = "127.0.0.1"
    port: int = 8099
    password: str | None = None
    ingress_only: bool = False
    # Broker host suggested in the "set MQTT" form (must be reachable from the dingz).
    default_broker: str | None = None
    # Ask GitHub for newer releases (outgoing request, cached).
    update_check: bool = True


class UiState:
    def __init__(self, config: WebConfig, mqtt: MqttConfig | None, bridge: Bridge | None) -> None:
        self.config = config
        self.mqtt = mqtt
        self.bridge = bridge
        self.devices: list[FoundDevice] = []
        self.last_scan: float | None = None
        self.scan_lock = asyncio.Lock()
        self.update_info: updates.UpdateInfo | None = None
        self.update_fetched = 0.0
        self.update_lock = asyncio.Lock()
        self.wifi_cache: dict[str, tuple[float, WifiSignal]] = {}
        self.wifi_slots = asyncio.Semaphore(WIFI_CONCURRENCY)

    async def version_info(self) -> updates.UpdateInfo:
        if not self.config.update_check:
            return updates.UpdateInfo(
                current=__version__, error_code="disabled", error="update check disabled"
            )
        async with self.update_lock:
            if self.update_info is None or time.time() - self.update_fetched > UPDATE_CACHE_SECONDS:
                self.update_info = await updates.check()
                self.update_fetched = time.time()
            return self.update_info

    async def wifi(self, host: str, refresh: bool = False) -> tuple[float, WifiSignal]:
        cached = self.wifi_cache.get(host)
        if cached and not refresh and time.time() - cached[0] < WIFI_CACHE_SECONDS:
            return cached
        async with self.wifi_slots:
            signal = await DeviceApi(host, timeout=15).wifi()
        self.wifi_cache[host] = (time.time(), signal)
        return self.wifi_cache[host]

    async def rescan(self, subnet: str | None = None) -> None:
        async with self.scan_lock:
            found = await scan(mqtt=self.mqtt, subnet=subnet)
            # Keep devices found earlier (e.g. by a subnet sweep) unless they reappear.
            self.devices = merge_devices(found, self.devices)
            self.last_scan = time.time()

    def known_host(self, host: str) -> FoundDevice | None:
        return next((d for d in self.devices if d.host == host), None)

    def device_rows(self) -> list[dict[str, Any]]:
        rows = []
        for device in self.devices:
            row = device.as_dict()
            row["bridge"] = self._bridge_info(device)
            rows.append(row)
        return rows

    def _bridge_info(self, device: FoundDevice) -> dict[str, Any] | None:
        if self.bridge is None or device.mqtt_id is None:
            return None
        registry = self.bridge.registry
        state = registry.devices.get(device.mqtt_id)
        if state is None:
            return {"seen": False, "published": False}
        from .discovery import discovery_topic

        last_time, last_topic = registry.last_message.get(device.mqtt_id, (None, None))
        prefix = f"dingz/{device.mqtt_id}/"
        return {
            "seen": True,
            "published": discovery_topic(device.mqtt_id, registry.id_prefix) in registry.published,
            "last_message": last_time,
            "last_topic": last_topic.removeprefix(prefix) if last_topic else None,
        }


STATE_KEY = web.AppKey("state", UiState)
SCAN_TASK_KEY = web.AppKey("initial_scan", asyncio.Task)


def create_app(
    config: WebConfig, mqtt: MqttConfig | None = None, bridge: Bridge | None = None
) -> web.Application:
    app = web.Application(middlewares=[_security_middleware(config)])
    state = UiState(config, mqtt, bridge)
    app[STATE_KEY] = state

    for path, (filename, content_type) in STATIC_FILES.items():
        app.router.add_get(f"/{path}", _static(filename, content_type))
    app.router.add_get("/api/devices", _list_devices)
    app.router.add_get("/api/version", _version)
    app.router.add_post("/api/scan", _scan)
    app.router.add_get("/api/devices/{host}/status", _device_status)
    app.router.add_get("/api/devices/{host}/wifi", _device_wifi)
    app.router.add_post("/api/devices/{host}/mqtt", _set_mqtt)

    async def initial_scan(app: web.Application) -> None:
        app[SCAN_TASK_KEY] = asyncio.create_task(state.rescan())

    async def stop_scan(app: web.Application) -> None:
        app[SCAN_TASK_KEY].cancel()

    app.on_startup.append(initial_scan)
    app.on_cleanup.append(stop_scan)
    return app


async def serve(
    config: WebConfig, mqtt: MqttConfig | None = None, bridge: Bridge | None = None
) -> None:
    runner = web.AppRunner(create_app(config, mqtt, bridge), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, config.bind, config.port)
    await site.start()
    log.info("web UI on http://%s:%s/", config.bind, config.port)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def _security_middleware(
    config: WebConfig,
) -> Callable[[web.Request, Callable[[web.Request], Awaitable[web.StreamResponse]]], Any]:
    @web.middleware
    async def middleware(
        request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        if config.ingress_only and request.remote != INGRESS_PEER:
            raise web.HTTPForbidden(text="only available through Home Assistant ingress")
        if config.password and not _authorized(request, config.password):
            raise web.HTTPUnauthorized(
                headers={"WWW-Authenticate": 'Basic realm="dingz HA Bridge", charset="UTF-8"'}
            )
        if request.method not in ("GET", "HEAD") and request.headers.get(CSRF_HEADER) != "1":
            raise web.HTTPForbidden(text=f"missing {CSRF_HEADER} header")
        response = await handler(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    return middleware


def _authorized(request: web.Request, password: str) -> bool:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:]).decode()
    except ValueError:
        return False
    _, _, given = decoded.partition(":")
    return hmac.compare_digest(given.encode(), password.encode())


def _static(filename: str, content_type: str) -> Callable[[web.Request], Awaitable[web.Response]]:
    body = resources.files("dingz_ha_bridge").joinpath("static", filename).read_bytes()

    async def handler(request: web.Request) -> web.Response:
        return web.Response(body=body, content_type=content_type, charset="utf-8")

    return handler


def _state(request: web.Request) -> UiState:
    return request.app[STATE_KEY]


async def _version(request: web.Request) -> web.Response:
    info = await _state(request).version_info()
    return web.json_response({**dataclasses.asdict(info), "repo_url": REPO_URL})


async def _list_devices(request: web.Request) -> web.Response:
    state = _state(request)
    return web.json_response(
        {
            "version": __version__,
            "devices": state.device_rows(),
            "scanning": state.scan_lock.locked(),
            "last_scan": state.last_scan,
            "default_broker": state.config.default_broker,
            "bridge": state.bridge is not None,
            "now": time.time(),
        }
    )


async def _scan(request: web.Request) -> web.Response:
    body = await _json_body(request)
    subnet = body.get("subnet") or None
    if subnet is not None and not isinstance(subnet, str):
        raise web.HTTPBadRequest(text="subnet must be a string")
    try:
        await _state(request).rescan(subnet)
    except ValueError as err:
        raise web.HTTPBadRequest(text=str(err)) from err
    return await _list_devices(request)


async def _device_status(request: web.Request) -> web.Response:
    host = _known_host(request)
    status = await DeviceApi(host).status()
    return web.json_response(dataclasses.asdict(status))


async def _device_wifi(request: web.Request) -> web.Response:
    host = _known_host(request)
    refresh = request.query.get("refresh") == "1"
    try:
        measured_at, signal = await _state(request).wifi(host, refresh)
    except DeviceApiError as err:
        return web.json_response({"error": str(err)}, status=502)
    return web.json_response({**dataclasses.asdict(signal), "measured_at": measured_at})


async def _set_mqtt(request: web.Request) -> web.Response:
    host = _known_host(request)
    body = await _json_body(request)
    broker = str(body.get("broker") or "").strip()
    if not broker:
        raise web.HTTPBadRequest(text="broker missing")
    try:
        port = int(body.get("port") or 1883)
    except (TypeError, ValueError) as err:
        raise web.HTTPBadRequest(text="invalid port") from err
    uri = build_mqtt_uri(
        broker,
        port,
        str(body.get("username") or "") or None,
        str(body.get("password") or "") or None,
    )
    log.info("setting MQTT broker of %s to %s:%s", host, broker, port)
    try:
        result = await DeviceApi(host).set_mqtt(uri, enable=bool(body.get("enable", True)))
    except DeviceApiError as err:
        return web.json_response({"ok": False, "message": str(err)}, status=502)
    return web.json_response(dataclasses.asdict(result))


def _known_host(request: web.Request) -> str:
    host = request.match_info["host"]
    if _state(request).known_host(host) is None:
        raise web.HTTPNotFound(text="unknown device, scan first")
    return host


async def _json_body(request: web.Request) -> dict[str, Any]:
    if not request.can_read_body:
        return {}
    try:
        body = await request.json()
    except ValueError as err:
        raise web.HTTPBadRequest(text="invalid JSON") from err
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="expected a JSON object")
    return body

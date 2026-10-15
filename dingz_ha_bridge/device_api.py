"""Minimal client for the dingz HTTP API (``http://<ip>/api/v1/``).

Uses only the standard library (blocking urllib in a worker thread) so the bridge core
needs no extra dependency.

The only write is ``set_mqtt`` (``POST services_config``). The JSON partial-update format is
not officially documented for FW 2.x but was confirmed on a device (FW 2.4.3); it always
reads back and reports whether the device really took the new settings.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .discovery import Enrichment

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5.0
MASK = "***"


class DeviceApiError(Exception):
    pass


@dataclass
class DeviceStatus:
    """Summary of one dingz as shown by `status` and the UI. Never contains secrets."""

    host: str
    mac: str | None = None
    mqtt_id: str | None = None
    name: str | None = None
    room: str | None = None
    model: str | None = None
    fw_version: str | None = None
    hw_version: str | None = None
    has_pir: bool | None = None
    protected: bool | None = None
    mqtt_enabled: bool | None = None
    mqtt_uri: str | None = None  # password masked
    outputs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class WifiSignal:
    """WLAN signal as seen by the dingz.

    The API has no field for the current connection. ``GET /api/v1/scan`` lists the
    visible access points as ``[ssid, dBm, ssid, dBm, ...]``; with several APs for the
    same SSID the strongest one is taken as the likely current one.
    """

    ssid: str | None
    rssi: int | None  # dBm
    quality: str | None  # "excellent" / "good" / "fair" / "poor" (the UI translates)
    percent: int | None
    access_points: list[int] = field(default_factory=list)  # all dBm values of the SSID


@dataclass
class MqttResult:
    ok: bool
    message: str
    uri: str | None = None  # password masked
    code: str = ""  # "applied" / "rejected" (the UI translates)


class DeviceApi:
    def __init__(self, host: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.host = host
        self.timeout = timeout

    async def get(self, path: str) -> Any:
        return await asyncio.to_thread(self._request, "GET", path, None)

    async def post_json(self, path: str, body: Any) -> Any:
        return await asyncio.to_thread(self._request, "POST", path, body)

    def _request(self, method: str, path: str, body: Any) -> Any:
        url = f"http://{self.host}/api/v1/{path}"
        data = None if body is None else json.dumps(body).encode()
        headers = {} if data is None else {"Content-Type": "application/json"}
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as err:
            raise DeviceApiError(f"{method} {url}: HTTP {err.code}") from err
        except OSError as err:
            raise DeviceApiError(f"{method} {url}: {err}") from err
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except ValueError as err:
            raise DeviceApiError(f"{method} {url}: invalid JSON") from err

    async def enrichment(self) -> Enrichment:
        system_config, output_config = await asyncio.gather(
            self.get("system_config"), self.get("output_config")
        )
        return parse_enrichment(system_config, output_config)

    async def room_temperature(self) -> float | None:
        sensors = await self.get("sensors")
        value = sensors.get("room_temperature") if isinstance(sensors, dict) else None
        return float(value) if isinstance(value, int | float) else None

    async def status(self) -> DeviceStatus:
        paths = ["info", "device", "system_config", "services_config", "protected", "outputs"]
        results = await asyncio.gather(*(self.get(p) for p in paths), return_exceptions=True)
        data: dict[str, Any] = {}
        errors = []
        for path, result in zip(paths, results, strict=True):
            if isinstance(result, BaseException):
                errors.append(str(result))
            else:
                data[path] = result
        status = parse_status(self.host, data)
        status.errors = errors
        return status

    async def wifi(self) -> WifiSignal:
        """Run a WLAN scan on the device (takes ~2 s) and rate the own SSID."""
        info = await self.get("info")
        ssid = info.get("ssid") if isinstance(info, dict) else None
        return parse_wifi(ssid, await self.get("scan"))

    async def set_mqtt(self, uri: str, enable: bool = True) -> MqttResult:
        """Set the broker URI. Reads the config first and verifies it afterwards."""
        current = await self.get("services_config")
        if not isinstance(current, dict) or not isinstance(current.get("mqtt"), dict):
            raise DeviceApiError("services_config has no mqtt section")
        await self.post_json("services_config", {"mqtt": {"uri": uri, "enable": enable}})
        after = await self.get("services_config")
        mqtt = after.get("mqtt") if isinstance(after, dict) else None
        if isinstance(mqtt, dict) and mqtt.get("uri") == uri and mqtt.get("enable") == enable:
            return MqttResult(True, "MQTT settings applied", mask_uri(uri), "applied")
        seen = mask_uri(str(mqtt.get("uri"))) if isinstance(mqtt, dict) else None
        return MqttResult(False, "device did not take the new MQTT settings", seen, "rejected")


def parse_enrichment(system_config: Any, output_config: Any) -> Enrichment:
    """Extract device name and per-output name/type/dimmability."""
    result = Enrichment()
    if isinstance(system_config, dict):
        name = system_config.get("dingz_name") or system_config.get("room_name")
        result.name = str(name).strip() or None if name else None

    outputs = output_config.get("outputs") if isinstance(output_config, dict) else None
    for index, output in enumerate(outputs or []):
        if not isinstance(output, dict):
            continue
        if name := str(output.get("name") or "").strip():
            result.output_names[index] = name
        if output_type := output.get("type"):
            result.output_types[index] = str(output_type)
        light = output.get("light")
        if isinstance(light, dict) and "dimmable" in light:
            result.dimmable[index] = bool(light["dimmable"])
    return result


def parse_status(host: str, data: dict[str, Any]) -> DeviceStatus:
    status = DeviceStatus(host)
    info = _dict(data.get("info"))
    status.mac = _opt_str(info.get("mac"))
    status.fw_version = _opt_str(info.get("version"))

    device_map = _dict(data.get("device"))
    device = _dict(next(iter(device_map.values()), None)) if device_map else {}
    status.mac = status.mac or (next(iter(device_map)) if device_map else None)
    status.model = _opt_str(device.get("front_hw_model"))
    status.fw_version = _opt_str(device.get("fw_version")) or status.fw_version
    status.hw_version = _opt_str(device.get("hw_version"))
    if "has_pir" in device:
        status.has_pir = bool(device["has_pir"])

    system = _dict(data.get("system_config"))
    status.mqtt_id = _opt_str(system.get("id"))
    status.name = _opt_str(system.get("dingz_name"))
    status.room = _opt_str(system.get("room_name"))

    mqtt = _dict(_dict(data.get("services_config")).get("mqtt"))
    if "enable" in mqtt:
        status.mqtt_enabled = bool(mqtt["enable"])
    if uri := _opt_str(mqtt.get("uri")):
        status.mqtt_uri = mask_uri(uri)

    protected = _dict(data.get("protected"))
    if "protected" in protected:
        status.protected = bool(protected["protected"])

    outputs = data.get("outputs")
    if isinstance(outputs, list):
        status.outputs = [
            {k: o.get(k) for k in ("ph_out_id", "type", "enable", "on", "value")}
            for o in outputs
            if isinstance(o, dict)
        ]
    return status


def parse_wifi(ssid: str | None, scan: Any) -> WifiSignal:
    values: list[int] = []
    if ssid and isinstance(scan, list):
        for name, rssi in zip(scan[::2], scan[1::2], strict=False):
            if name == ssid and isinstance(rssi, int | float):
                values.append(int(rssi))
    values.sort(reverse=True)
    rssi = values[0] if values else None
    return WifiSignal(ssid, rssi, rate_rssi(rssi), rssi_percent(rssi), values)


def rate_rssi(rssi: int | None) -> str | None:
    if rssi is None:
        return None
    if rssi >= -60:
        return "excellent"
    if rssi >= -70:
        return "good"
    if rssi >= -80:
        return "fair"
    return "poor"


def rssi_percent(rssi: int | None) -> int | None:
    """Common linear mapping: -100 dBm = 0 %, -50 dBm = 100 %."""
    if rssi is None:
        return None
    return max(0, min(100, 2 * (rssi + 100)))


def build_mqtt_uri(
    host: str, port: int | None = None, username: str | None = None, password: str | None = None
) -> str:
    """Build ``mqtt://user:pass@host[:port]`` with user and password percent-encoded."""
    auth = ""
    if username:
        auth = urllib.parse.quote(username, safe="")
        if password:
            auth += ":" + urllib.parse.quote(password, safe="")
        auth += "@"
    hostport = host if port in (None, 1883) else f"{host}:{port}"
    return f"mqtt://{auth}{hostport}"


def mask_uri(uri: str) -> str:
    """Replace the password in a broker URI."""
    parts = urllib.parse.urlsplit(uri)
    if parts.password is None:
        return uri
    netloc = parts.netloc.rsplit("@", 1)[1]
    user = parts.netloc.rsplit("@", 1)[0].split(":", 1)[0]
    return urllib.parse.urlunsplit(parts._replace(netloc=f"{user}:{MASK}@{netloc}"))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _opt_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None

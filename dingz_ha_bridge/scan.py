"""Find dingz devices: mDNS, retained MQTT `announce`, or an HTTP subnet sweep.

Results of all sources are merged by MAC (or IP / MQTT id where no MAC is known).
mDNS needs the optional `zeroconf` package (extra `ui`) and, in Docker, host networking.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .device_api import DeviceApi, DeviceApiError

if TYPE_CHECKING:
    from .bridge import MqttConfig

log = logging.getLogger(__name__)

MDNS_TYPE = "_http._tcp.local."
MDNS_INSTANCE_PREFIX = "DINGZ "
# Host name as announced via mDNS: DINGZ-<model>-<MAC>.local.
_MDNS_SERVER = re.compile(r"^DINGZ-(?P<model>.+)-(?P<mac>[0-9A-Fa-f]{12})\.local\.?$")


@dataclass
class FoundDevice:
    host: str
    mac: str | None = None
    mqtt_id: str | None = None
    name: str | None = None
    room: str | None = None
    model: str | None = None
    fw_version: str | None = None
    protected: bool | None = None
    has_pir: bool | None = None
    mqtt_online: bool | None = None
    sources: set[str] = field(default_factory=set)

    def merge(self, other: FoundDevice) -> None:
        for name in (
            "mac",
            "mqtt_id",
            "name",
            "room",
            "model",
            "fw_version",
            "protected",
            "has_pir",
            "mqtt_online",
        ):
            if getattr(self, name) is None:
                setattr(self, name, getattr(other, name))
        self.sources |= other.sources

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "mac": self.mac,
            "mqtt_id": self.mqtt_id,
            "name": self.name,
            "room": self.room,
            "model": self.model,
            "fw_version": self.fw_version,
            "protected": self.protected,
            "has_pir": self.has_pir,
            "mqtt_online": self.mqtt_online,
            "sources": sorted(self.sources),
        }


def parse_mdns(
    server: str | None, properties: Mapping[bytes, bytes | None], addresses: Iterable[str]
) -> FoundDevice | None:
    """Build a device from a resolved `_http._tcp` service of a dingz."""
    props = {
        k.decode(errors="replace"): (v or b"").decode(errors="replace")
        for k, v in properties.items()
    }
    host = next(iter(addresses), None)
    if host is None:
        return None
    match = _MDNS_SERVER.match(server or "")
    return FoundDevice(
        host=host,
        mac=(props.get("mac") or (match["mac"] if match else "")).upper() or None,
        mqtt_id=props.get("id") or None,
        name=props.get("name") or None,
        room=props.get("room") or None,
        model=match["model"] if match else None,
        fw_version=props.get("fw") or None,
        protected=_bool(props.get("protected")),
        has_pir=_bool(props.get("pir")),
        sources={"mdns"},
    )


def parse_device_response(host: str, data: Any) -> FoundDevice | None:
    """Confirm a host as dingz from `GET /api/v1/device` (``{"<MAC>": {"type": "dingz"}}``)."""
    if not isinstance(data, dict) or len(data) != 1:
        return None
    mac, info = next(iter(data.items()))
    if not isinstance(info, dict) or info.get("type") != "dingz":
        return None
    return FoundDevice(
        host=host,
        mac=str(mac).upper(),
        model=info.get("front_hw_model"),
        fw_version=info.get("fw_version"),
        has_pir=info.get("has_pir"),
        sources={"http"},
    )


def merge_devices(*groups: Iterable[FoundDevice]) -> list[FoundDevice]:
    merged: list[FoundDevice] = []
    for device in (d for group in groups for d in group):
        match = next((m for m in merged if _same(m, device)), None)
        if match is None:
            merged.append(device)
        else:
            match.merge(device)
    return sorted(merged, key=lambda d: (d.name or "", d.host))


def _same(a: FoundDevice, b: FoundDevice) -> bool:
    if a.mac and b.mac:
        return a.mac == b.mac
    return a.host == b.host or (a.mqtt_id is not None and a.mqtt_id == b.mqtt_id)


async def scan_mdns(timeout: float = 3.0) -> list[FoundDevice]:
    try:
        from zeroconf import ServiceStateChange
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf
    except ImportError as err:
        raise RuntimeError(
            "mDNS needs the 'zeroconf' package: pip install 'dingz-ha-bridge[ui]'"
        ) from err

    names: set[str] = set()

    def on_change(
        zeroconf: Any, service_type: str, name: str, state_change: ServiceStateChange
    ) -> None:
        if state_change is ServiceStateChange.Added and name.upper().startswith(
            MDNS_INSTANCE_PREFIX
        ):
            names.add(name)

    aiozc = AsyncZeroconf()
    try:
        browser = AsyncServiceBrowser(aiozc.zeroconf, MDNS_TYPE, handlers=[on_change])
        await asyncio.sleep(timeout)
        await browser.async_cancel()
        infos = [AsyncServiceInfo(MDNS_TYPE, name) for name in sorted(names)]
        await asyncio.gather(*(info.async_request(aiozc.zeroconf, 3000) for info in infos))
    finally:
        await aiozc.async_close()

    found = []
    for info in infos:
        device = parse_mdns(info.server, info.properties or {}, info.parsed_addresses())
        if device is not None:
            found.append(device)
    if not found:
        log.warning(
            "mDNS found no dingz. In Docker this needs host networking; "
            "try --mqtt or --subnet instead."
        )
    return found


async def scan_mqtt(mqtt: MqttConfig, timeout: float = 3.0) -> list[FoundDevice]:
    """Collect retained `dingz/<id>/announce` and `online` messages."""
    devices: dict[str, FoundDevice] = {}
    online: dict[str, bool] = {}
    async with mqtt.client(identifier=f"{mqtt.client_id}-scan") as client:
        await client.subscribe("dingz/+/announce")
        await client.subscribe("dingz/+/online")
        try:
            async with asyncio.timeout(timeout):
                async for message in client.messages:
                    _, device_id, kind = str(message.topic).split("/")
                    payload = bytes(message.payload or b"")  # type: ignore[arg-type]
                    if kind == "online":
                        online[device_id] = payload == b"true"
                    elif device := _parse_announce(device_id, payload):
                        devices[device_id] = device
        except TimeoutError:
            pass
    for device_id, device in devices.items():
        device.mqtt_online = online.get(device_id)
    return list(devices.values())


def _parse_announce(device_id: str, payload: bytes) -> FoundDevice | None:
    try:
        data = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(data, dict) or not data.get("ip"):
        return None
    return FoundDevice(
        host=str(data["ip"]),
        mqtt_id=device_id,
        model=data.get("model"),
        fw_version=data.get("fw_version"),
        sources={"mqtt"},
    )


async def scan_subnet(
    network: str, concurrency: int = 64, timeout: float = 1.5
) -> list[FoundDevice]:
    net = ipaddress.ip_network(network, strict=False)
    if net.num_addresses > 4096:
        raise ValueError(f"{network} is too large to sweep (max /20)")
    semaphore = asyncio.Semaphore(concurrency)

    async def probe(host: str) -> FoundDevice | None:
        async with semaphore:
            # Cheap async port check first; the HTTP client runs in a small thread pool.
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection(host, 80), timeout)
            except (OSError, TimeoutError):
                return None
            writer.close()
        try:
            return parse_device_response(host, await DeviceApi(host, timeout * 2).get("device"))
        except DeviceApiError:
            return None

    results = await asyncio.gather(*(probe(str(ip)) for ip in net.hosts()))
    return [r for r in results if r is not None]


async def enrich_from_http(devices: list[FoundDevice], timeout: float = 3.0) -> None:
    """Fill gaps (MAC, name, model) of devices found via MQTT only."""

    async def fill(device: FoundDevice) -> None:
        if device.mac and device.name:
            return
        try:
            status = await DeviceApi(device.host, timeout).status()
        except DeviceApiError:
            return
        device.mac = device.mac or status.mac
        device.name = device.name or status.name
        device.room = device.room or status.room
        device.model = device.model or status.model
        device.mqtt_id = device.mqtt_id or status.mqtt_id
        device.protected = status.protected if device.protected is None else device.protected

    await asyncio.gather(*(fill(d) for d in devices))


async def scan(
    *,
    mdns: bool = True,
    mqtt: MqttConfig | None = None,
    subnet: str | None = None,
    timeout: float = 3.0,
) -> list[FoundDevice]:
    tasks = []
    if mdns:
        tasks.append(scan_mdns(timeout))
    if mqtt is not None:
        tasks.append(scan_mqtt(mqtt, timeout))
    if subnet:
        tasks.append(scan_subnet(subnet))
    groups: list[list[FoundDevice]] = []
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, BaseException):
            log.warning("scan source failed: %s", result)
        else:
            groups.append(result)
    devices = merge_devices(*groups)
    await enrich_from_http(devices)
    # A MAC learned from HTTP may reveal duplicates found under different IPs.
    return merge_devices(devices)


def _bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() in ("true", "1", "yes")

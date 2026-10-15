"""MQTT loop: watch dingz topics, keep the device registry and publish discovery configs."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import ssl
import time
from dataclasses import dataclass, field
from typing import Any

import aiomqtt

from . import discovery as d
from .device_api import DeviceApi, DeviceApiError
from .filters import TemperatureFilter
from .topics import ROOT, Kind, parse_topic

log = logging.getLogger(__name__)

DISCOVERY_FILTER = f"{d.DISCOVERY_PREFIX}/device/+/config"


@dataclass
class MqttConfig:
    host: str
    port: int | None = None  # default: 8883 with TLS, 1883 without
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    client_id: str = field(default_factory=lambda: f"dingz-ha-bridge-{secrets.token_hex(3)}")
    tls: bool = False
    ca_file: str | None = None  # own CA (PEM); system CAs if empty
    client_cert: str | None = None  # optional client certificate (PEM) ...
    client_key: str | None = None  # ... and its key
    tls_insecure: bool = False  # skip certificate and host name checks (testing only)

    @property
    def effective_port(self) -> int:
        return self.port or (8883 if self.tls else 1883)

    def tls_context(self) -> ssl.SSLContext | None:
        if not self.tls:
            return None
        context = ssl.create_default_context(cafile=self.ca_file or None)
        if self.client_cert:
            context.load_cert_chain(self.client_cert, self.client_key or None)
        if self.tls_insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    def client(self, identifier: str | None = None, **kwargs: Any) -> aiomqtt.Client:
        """An aiomqtt client for this broker, with TLS if configured."""
        return aiomqtt.Client(
            self.host,
            self.effective_port,
            username=self.username,
            password=self.password,
            identifier=identifier or self.client_id,
            tls_context=self.tls_context(),
            tls_insecure=True if self.tls and self.tls_insecure else None,
            **kwargs,
        )

    def describe(self) -> str:
        scheme = "mqtts" if self.tls else "mqtt"
        return f"{scheme}://{self.host}:{self.effective_port}"


@dataclass
class BridgeConfig:
    mqtt: MqttConfig
    # Wait this long after the last structural change of a device before publishing.
    debounce: float = 2.0
    # After connecting, wait this long for retained messages before removing stale configs.
    startup_grace: float = 10.0
    # Separate set of HA devices, e.g. id_prefix="dingztest", name_prefix="TEST ".
    id_prefix: str = d.DEFAULT_ID_PREFIX
    name_prefix: str = ""
    # Log what would be published instead of publishing.
    dry_run: bool = False
    # Read names and output types from the dingz HTTP API (needs the IP from `announce`).
    http_enrichment: bool = True
    # Retry interval for failed HTTP reads, and how long a first publish waits for one.
    enrich_retry: float = 300.0
    enrich_wait: float = 15.0
    # Drop the floored temperature of the periodic status dump (see filters.py). The
    # temperature sensor then reads the bridge's own topic.
    temperature_filter: bool = True


class Registry:
    """Broker-independent state: what the dingz devices look like and what is published."""

    def __init__(
        self,
        id_prefix: str = d.DEFAULT_ID_PREFIX,
        name_prefix: str = "",
        temperature_filter: bool = False,
    ) -> None:
        if not d.ID_PREFIX_PATTERN.fullmatch(id_prefix):
            raise ValueError(f"invalid id prefix {id_prefix!r}")
        self.id_prefix = id_prefix
        self.name_prefix = name_prefix
        self.temperature_filter = temperature_filter
        self.devices: dict[str, d.DeviceState] = {}
        # Discovery topic -> retained payload currently on the broker (ours only).
        self.published: dict[str, bytes] = {}
        # device_id -> (time, topic) of the last message on any of its topics (for the UI).
        self.last_message: dict[str, tuple[float, str]] = {}

    def handle(self, topic: str, payload: bytes) -> str | None:
        """Record a message. Returns the device_id whose config needs re-evaluation."""
        if topic.startswith(f"{d.DISCOVERY_PREFIX}/"):
            self._handle_discovery(topic, payload)
            return None
        info = parse_topic(topic)
        if info is None:
            return None
        self.last_message[info.device_id] = (time.time(), topic)
        dev = self.devices.get(info.device_id)
        if dev is None:
            dev = self.devices[info.device_id] = d.DeviceState(info.device_id)
            log.info("new dingz %s", info.device_id)
        return info.device_id if dev.observe(info, payload) else None

    def _handle_discovery(self, topic: str, payload: bytes) -> None:
        parts = topic.split("/")
        own = parts[2].startswith(f"{self.id_prefix}_") if len(parts) == 4 else False
        if len(parts) != 4 or parts[1] != "device" or not own:
            return
        if payload:
            self.published[topic] = payload
        else:
            self.published.pop(topic, None)

    def render(self, device_id: str) -> tuple[str, bytes] | None:
        """Return (topic, payload) to publish for ``device_id``, or None if nothing changed."""
        dev = self.devices.get(device_id)
        if dev is None or not dev.ready:
            return None
        topic = d.discovery_topic(device_id, self.id_prefix)
        previous = self._published_platforms(topic)
        config = d.build_device_config(
            dev,
            previous,
            id_prefix=self.id_prefix,
            name_prefix=self.name_prefix,
            temperature_filter=self.temperature_filter,
        )
        payload = d.encode(config)
        if self.published.get(topic) == payload:
            return None
        return topic, payload

    def stale_topics(self) -> list[str]:
        """Our discovery topics for which no dingz device has been seen."""
        known = {d.discovery_topic(device_id, self.id_prefix) for device_id in self.devices}
        return sorted(set(self.published) - known)

    def _published_platforms(self, topic: str) -> dict[str, str]:
        raw = self.published.get(topic)
        if not raw:
            return {}
        try:
            return d.component_platforms(json.loads(raw))
        except (ValueError, AttributeError):
            return {}


class Bridge:
    def __init__(self, config: BridgeConfig, registry: Registry | None = None) -> None:
        self.config = config
        self.registry = registry or Registry(
            config.id_prefix, config.name_prefix, config.temperature_filter
        )
        self.temperatures = TemperatureFilter()
        self._status_topic = d.bridge_status_topic(config.id_prefix)
        self._pending: dict[str, asyncio.Task[None]] = {}
        self._enriching: dict[str, asyncio.Task[None]] = {}
        self._enrich_attempted: dict[str, asyncio.Event] = {}
        self._enriched_ip: dict[str, str] = {}
        self._due: list[tuple[str, float]] = []
        self._side_tasks: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        """Connect and serve forever, reconnecting with backoff."""
        mqtt = self.config.mqtt
        backoff = 1.0
        while True:
            try:
                async with mqtt.client(will=self._will()) as client:
                    log.info("connected to %s as %s", mqtt.describe(), mqtt.client_id)
                    backoff = 1.0
                    await self.serve(client)
            except aiomqtt.MqttError as err:
                log.warning("MQTT connection lost (%s), retrying in %.0f s", err, backoff)
                if "CERTIFICATE_VERIFY_FAILED" in str(err):
                    log.error(
                        "the broker certificate is not trusted: pass its CA with --ca-file "
                        "(DINGZ_MQTT_CA_FILE), or --tls-insecure for testing"
                    )
                self._cancel_pending()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    def _will(self) -> aiomqtt.Will | None:
        if not self.config.temperature_filter or self.config.dry_run:
            return None
        return aiomqtt.Will(self._status_topic, b"offline", qos=1, retain=True)

    async def serve(self, client: aiomqtt.Client) -> None:
        await client.subscribe(f"{ROOT}/#", qos=1)
        await client.subscribe(DISCOVERY_FILTER, qos=1)
        background = [asyncio.create_task(self._cleanup_after_grace(client))]
        if self.config.temperature_filter:
            own = d.filtered_temperature_topic("+", self.config.id_prefix)
            await client.subscribe(own, qos=1)
            await self._publish_value(client, self._status_topic, b"online")
            background.append(asyncio.create_task(self._flush_temperatures(client)))
        try:
            async for message in client.messages:
                payload = message.payload
                if not isinstance(payload, bytes | bytearray):
                    payload = str(payload).encode() if payload is not None else b""
                topic = str(message.topic)
                if self.config.temperature_filter:
                    self._feed_temperature(topic, bytes(payload), bool(message.retain))
                device_id = self.registry.handle(topic, bytes(payload))
                if device_id is not None:
                    self._maybe_enrich(client, device_id)
                    self._schedule(client, device_id)
        finally:
            for task in background:
                task.cancel()
            self._cancel_pending()

    def _feed_temperature(self, topic: str, payload: bytes, retained: bool) -> None:
        now = time.monotonic()
        if topic.startswith(f"{d.BRIDGE_TOPIC_ROOT}/"):
            # Our own retained value from before a restart: the last good one.
            device_id = topic.split("/")[2]
            if (value := _float(payload)) is not None:
                self.temperatures.seed(device_id, value)
            return
        info = parse_topic(topic)
        if info is None:
            return
        if info.kind is Kind.LAST_ALIVE:
            self.temperatures.dump_marker(info.device_id, now)
        elif (
            info.kind is Kind.SENSOR
            and info.component == "temperature"
            and (value := _float(payload)) is not None
        ):
            # Values that became due early are published by the flush loop.
            self._due.extend(self.temperatures.temperature(info.device_id, value, now, retained))

    async def _flush_temperatures(self, client: aiomqtt.Client) -> None:
        while True:
            await asyncio.sleep(0.25)
            due, self._due = [*self._due, *self.temperatures.due(time.monotonic())], []
            for device_id, value in due:
                topic = d.filtered_temperature_topic(device_id, self.config.id_prefix)
                log.debug("temperature %s: %s", device_id, value)
                await self._publish_value(client, topic, f"{value:g}".encode())

    async def _publish_value(self, client: aiomqtt.Client, topic: str, payload: bytes) -> None:
        """Publish a retained non-discovery value (bridge status, filtered temperature)."""
        if self.config.dry_run:
            log.info("dry run, not publishing %s: %s", topic, payload.decode())
        else:
            await client.publish(topic, payload, qos=1, retain=True)

    def _schedule(self, client: aiomqtt.Client, device_id: str) -> None:
        if task := self._pending.pop(device_id, None):
            task.cancel()
        self._pending[device_id] = asyncio.create_task(self._publish_later(client, device_id))

    async def _publish_later(self, client: aiomqtt.Client, device_id: str) -> None:
        await asyncio.sleep(self.config.debounce)
        if attempted := self._enrich_attempted.get(device_id):
            # Avoid publishing generic entities that change right after the HTTP read.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(attempted.wait(), self.config.enrich_wait)
        self._pending.pop(device_id, None)
        rendered = self.registry.render(device_id)
        if rendered is None:
            return
        topic, payload = rendered
        log.info("publishing discovery for %s", device_id)
        await self._publish(client, topic, payload)

    def _maybe_enrich(self, client: aiomqtt.Client, device_id: str) -> None:
        dev = self.registry.devices.get(device_id)
        if (
            not self.config.http_enrichment
            or dev is None
            or dev.ip is None
            or self._enriched_ip.get(device_id) == dev.ip
            or device_id in self._enriching
        ):
            return
        self._enrich_attempted[device_id] = asyncio.Event()
        self._enriching[device_id] = asyncio.create_task(self._enrich(client, device_id, dev.ip))

    async def _enrich(self, client: aiomqtt.Client, device_id: str, ip: str) -> None:
        try:
            while True:
                try:
                    enrichment = await DeviceApi(ip).enrichment()
                except DeviceApiError as err:
                    log.warning("HTTP read of %s failed (%s), retrying later", device_id, err)
                    self._enrich_attempted[device_id].set()
                    await asyncio.sleep(self.config.enrich_retry)
                    continue
                self._enriched_ip[device_id] = ip
                if self.config.temperature_filter:
                    # In parallel: must not delay the discovery config.
                    task = asyncio.create_task(self._exact_temperature(device_id, ip))
                    self._side_tasks.add(task)
                    task.add_done_callback(self._side_tasks.discard)
                dev = self.registry.devices[device_id]
                if dev.enrich(enrichment):
                    log.info("HTTP details for %s: %s", device_id, enrichment.name)
                    self._schedule(client, device_id)
                self._enrich_attempted[device_id].set()
                return
        finally:
            self._enriching.pop(device_id, None)

    async def _exact_temperature(self, device_id: str, ip: str) -> None:
        """Start from the exact HTTP value; the retained MQTT one may be a floored dump."""
        try:
            value = await DeviceApi(ip).room_temperature()
        except DeviceApiError as err:
            log.debug("no HTTP temperature for %s: %s", device_id, err)
            return
        if value is not None:
            self._due.extend(self.temperatures.exact(device_id, value))

    async def _cleanup_after_grace(self, client: aiomqtt.Client) -> None:
        await asyncio.sleep(self.config.startup_grace)
        for topic in self.registry.stale_topics():
            log.info("removing stale discovery config %s", topic)
            await self._publish(client, topic, b"")

    async def _publish(self, client: aiomqtt.Client, topic: str, payload: bytes) -> None:
        if self.config.dry_run:
            log.info("dry run, not publishing %s: %s", topic, payload.decode())
        else:
            await client.publish(topic, payload, qos=1, retain=True)
        if payload:
            self.registry.published[topic] = payload
        else:
            self.registry.published.pop(topic, None)

    def _cancel_pending(self) -> None:
        for task in [*self._pending.values(), *self._enriching.values(), *self._side_tasks]:
            task.cancel()
        self._pending.clear()
        self._enriching.clear()
        self._enrich_attempted.clear()


def _float(payload: bytes) -> float | None:
    try:
        return float(payload)
    except ValueError:
        return None

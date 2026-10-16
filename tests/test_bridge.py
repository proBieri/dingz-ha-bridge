import json

from dingz_ha_bridge import discovery as d
from dingz_ha_bridge.bridge import Registry

BASE = "dingz/dingztest/dz1f-4b"
TOPIC = "homeassistant/device/dingz_dingztest/config"


def feed(reg: Registry, *messages: tuple[str, str]) -> set[str]:
    changed = set()
    for topic, payload in messages:
        if device_id := reg.handle(topic, payload.encode()):
            changed.add(device_id)
    return changed


def test_first_messages_trigger_publish() -> None:
    reg = Registry()
    changed = feed(
        reg,
        ("dingz/dingztest/online", "true"),
        (f"{BASE}/state/light/0", '{"turn":"off","brightness":0,"exception":0}'),
    )
    assert changed == {"dingztest"}
    rendered = reg.render("dingztest")
    assert rendered is not None
    topic, payload = rendered
    assert topic == TOPIC
    assert "dingz_dingztest_light_0" in json.loads(payload)["components"]


def test_unchanged_config_is_not_republished() -> None:
    reg = Registry()
    feed(reg, (f"{BASE}/state/light/0", '{"turn":"off"}'), (f"{BASE}/sensor/light", "2"))
    topic, payload = reg.render("dingztest") or ("", b"")
    reg.published[topic] = payload
    assert reg.render("dingztest") is None
    # Value updates are not structural changes.
    assert not feed(reg, (f"{BASE}/state/light/0", '{"turn":"on"}'), (f"{BASE}/sensor/light", "3"))


def test_device_without_model_is_not_rendered() -> None:
    reg = Registry()
    feed(reg, ("dingz/dingztest/online", "true"))
    assert reg.render("dingztest") is None


def test_retained_config_is_used_as_previous() -> None:
    reg = Registry()
    dev = d.DeviceState("dingztest", model="dz1f-4b", lights={0, 1})
    reg.handle(TOPIC, d.encode(d.build_device_config(dev)))
    feed(reg, (f"{BASE}/state/light/0", '{"turn":"off"}'))
    _, payload = reg.render("dingztest") or ("", b"")
    components = json.loads(payload)["components"]
    assert components["dingz_dingztest_light_1"] == {"platform": "light"}


def test_identical_retained_config_suppresses_publish() -> None:
    reg = Registry()
    feed(reg, (f"{BASE}/state/light/0", '{"turn":"off"}'))
    topic, payload = reg.render("dingztest") or ("", b"")
    reg2 = Registry()
    reg2.handle(topic, payload)
    feed(reg2, (f"{BASE}/state/light/0", '{"turn":"off"}'))
    assert reg2.render("dingztest") is None


def test_stale_and_foreign_discovery_topics() -> None:
    reg = Registry()
    reg.handle("homeassistant/device/dingz_gone/config", b'{"components":{}}')
    reg.handle("homeassistant/device/10867816/config", b'{"cmps":{}}')
    reg.handle("homeassistant/sensor/dingz_x/config", b"{}")
    feed(reg, (f"{BASE}/state/light/0", '{"turn":"off"}'))
    reg.published[TOPIC] = b"{}"
    assert reg.stale_topics() == ["homeassistant/device/dingz_gone/config"]
    reg.handle("homeassistant/device/dingz_gone/config", b"")
    assert reg.stale_topics() == []


# --- Bridge with a fake MQTT client ---

import asyncio  # noqa: E402
from dataclasses import dataclass  # noqa: E402

import pytest  # noqa: E402

from dingz_ha_bridge import bridge as b  # noqa: E402


@dataclass
class FakeMessage:
    topic: str
    payload: bytes
    retain: bool = False


class FakeClient:
    def __init__(self, messages: list[tuple[str, str]]) -> None:
        self.queue: asyncio.Queue[FakeMessage] = asyncio.Queue()
        for topic, payload in messages:
            self.queue.put_nowait(FakeMessage(topic, payload.encode()))
        self.published: list[tuple[str, bytes, bool]] = []

    async def subscribe(self, *_: object, **__: object) -> None:
        pass

    async def publish(self, topic: str, payload: bytes, qos: int = 0, retain: bool = False) -> None:
        self.published.append((topic, payload, retain))

    @property
    def messages(self) -> "FakeClient":
        return self

    def __aiter__(self) -> "FakeClient":
        return self

    async def __anext__(self) -> FakeMessage:
        return await self.queue.get()


ANNOUNCE = ("dingz/dingztest/announce", '{"model":"dz1f-4b","ip":"192.0.2.50"}')
STALE = "homeassistant/device/dingz_gone/config"


async def serve_for(bridge: b.Bridge, client: FakeClient, seconds: float) -> None:
    task = asyncio.create_task(bridge.serve(client))  # type: ignore[arg-type]
    await asyncio.sleep(seconds)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def make_bridge(**kwargs: object) -> b.Bridge:
    config = b.BridgeConfig(
        b.MqttConfig("broker"), debounce=0.01, startup_grace=0.05, enrich_wait=1, **kwargs
    )
    return b.Bridge(config)


async def test_bridge_publishes_enriched_config_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def fake_enrichment(self: b.DeviceApi) -> d.Enrichment:
        calls.append(self.host)
        await asyncio.sleep(0.05)
        return d.Enrichment(name="Dingz Test", output_types={0: "power_socket"})

    async def fake_room_temperature(self: b.DeviceApi) -> float:
        return 22.5

    monkeypatch.setattr(b.DeviceApi, "enrichment", fake_enrichment)
    monkeypatch.setattr(b.DeviceApi, "room_temperature", fake_room_temperature)
    client = FakeClient(
        [ANNOUNCE, (f"{BASE}/state/light/0", '{"turn":"off"}'), (STALE, '{"components":{}}')]
    )
    await serve_for(make_bridge(), client, 0.3)

    assert calls == ["192.0.2.50"]
    configs = [(t, p) for t, p, _ in client.published if t == TOPIC]
    assert len(configs) == 1
    config = json.loads(configs[0][1])
    assert config["device"]["name"] == "Dingz Test"
    assert config["components"]["dingz_dingztest_light_0"]["platform"] == "switch"
    assert (STALE, b"", True) in client.published
    assert ("dingz-ha-bridge/dingz/dingztest/temperature", b"22.5", True) in client.published
    assert all(retain for _, _, retain in client.published)


async def test_bridge_publishes_without_http(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing(self: b.DeviceApi) -> d.Enrichment:
        raise b.DeviceApiError("unreachable")

    monkeypatch.setattr(b.DeviceApi, "enrichment", failing)
    client = FakeClient([ANNOUNCE, (f"{BASE}/state/light/0", '{"turn":"off"}')])
    await serve_for(make_bridge(), client, 0.2)
    configs = [p for t, p, _ in client.published if t == TOPIC]
    assert len(configs) == 1
    assert json.loads(configs[0])["components"]["dingz_dingztest_light_0"]["platform"] == "light"


async def test_dry_run_publishes_nothing() -> None:
    client = FakeClient([ANNOUNCE, (f"{BASE}/state/light/0", '{"turn":"off"}')])
    await serve_for(make_bridge(dry_run=True, http_enrichment=False), client, 0.2)
    assert client.published == []


def test_id_and_name_prefix_are_separate_namespace() -> None:
    reg = Registry(id_prefix="dingztest", name_prefix="TEST ")
    reg.handle(TOPIC, b'{"components":{}}')  # real config, not ours in this namespace
    feed(reg, (f"{BASE}/state/light/0", '{"turn":"off"}'))
    topic, payload = reg.render("dingztest") or ("", b"")
    assert topic == "homeassistant/device/dingztest_dingztest/config"
    config = json.loads(payload)
    assert config["device"]["name"].startswith("TEST ")
    assert config["device"]["identifiers"] == ["dingztest_dingztest"]
    # Entity components carry the prefixed namespace; device triggers (no unique_id) do not.
    entity_ids = [u for u, c in config["components"].items() if "unique_id" in c]
    assert entity_ids
    assert all(uid.startswith("dingztest_dingztest_") for uid in entity_ids)
    reg.published[topic] = payload
    assert reg.stale_topics() == []


def test_invalid_id_prefix() -> None:
    import pytest

    with pytest.raises(ValueError):
        Registry(id_prefix="a/b")


def test_last_message_is_tracked() -> None:
    reg = Registry()
    feed(reg, (f"{BASE}/sensor/light", "12"))
    when, topic = reg.last_message["dingztest"]
    assert topic == f"{BASE}/sensor/light"
    assert when > 0
    feed(reg, ("homeassistant/device/dingz_x/config", "{}"))
    assert set(reg.last_message) == {"dingztest"}


async def test_bridge_filters_dump_temperature() -> None:
    dump = [
        (f"{BASE}/sensor/temperature", "21.0"),
        (f"{BASE}/sensor/light", "100"),
        (f"{BASE}/last_alive", "1792052873"),
    ]
    client = FakeClient([ANNOUNCE, (f"{BASE}/sensor/temperature", "21.5"), *dump])
    bridge = make_bridge(http_enrichment=False)
    bridge.temperatures.window = 0.05
    await serve_for(bridge, client, 0.4)
    temps = [p for t, p, _ in client.published if t.endswith("/temperature")]
    assert temps == [b"21.5"]
    assert ("dingz-ha-bridge/dingz/status", b"online", True) in client.published
    config = json.loads(next(p for t, p, _ in client.published if t == TOPIC))
    assert "dingz_dingztest_sensor_temperature_raw" in config["components"]


async def test_bridge_without_temperature_filter() -> None:
    client = FakeClient([ANNOUNCE, (f"{BASE}/sensor/temperature", "21.5")])
    await serve_for(make_bridge(http_enrichment=False, temperature_filter=False), client, 0.3)
    assert not any(t.startswith("dingz-ha-bridge/") for t, _, _ in client.published)

import pytest

from dingz_ha_bridge.topics import Kind, TopicInfo, channel_topic, parse_topic

DEV = "dingztest"
BASE = f"dingz/{DEV}/dz1f-pir"


@pytest.mark.parametrize(
    ("topic", "expected"),
    [
        (f"{BASE}/state/light/0", TopicInfo(DEV, "dz1f-pir", Kind.STATE, "light", 0)),
        (f"{BASE}/command/light/3", TopicInfo(DEV, "dz1f-pir", Kind.COMMAND, "light", 3)),
        (f"{BASE}/power/light/1", TopicInfo(DEV, "dz1f-pir", Kind.POWER, "light", 1)),
        (f"{BASE}/energy/motor/1", TopicInfo(DEV, "dz1f-pir", Kind.ENERGY, "motor", 1)),
        (f"{BASE}/state/motor/0", TopicInfo(DEV, "dz1f-pir", Kind.STATE, "motor", 0)),
        (f"{BASE}/state/led", TopicInfo(DEV, "dz1f-pir", Kind.STATE, "led")),
        (f"{BASE}/command/led", TopicInfo(DEV, "dz1f-pir", Kind.COMMAND, "led")),
        (f"{BASE}/event/button/4", TopicInfo(DEV, "dz1f-pir", Kind.EVENT, "button", 4)),
        (f"{BASE}/event/pir/0", TopicInfo(DEV, "dz1f-pir", Kind.EVENT, "pir", 0)),
        (f"{BASE}/state/input/0", TopicInfo(DEV, "dz1f-pir", Kind.STATE, "input", 0)),
        (f"{BASE}/sensor/temperature", TopicInfo(DEV, "dz1f-pir", Kind.SENSOR, "temperature")),
        (f"{BASE}/sensor/light", TopicInfo(DEV, "dz1f-pir", Kind.SENSOR, "light")),
        (f"{BASE}/state/thermostat", TopicInfo(DEV, "dz1f-pir", Kind.STATE, "thermostat")),
        (f"dingz/{DEV}/online", TopicInfo(DEV, None, Kind.ONLINE)),
        (f"dingz/{DEV}/announce", TopicInfo(DEV, None, Kind.ANNOUNCE)),
        (f"dingz/{DEV}/last_alive", TopicInfo(DEV, None, Kind.LAST_ALIVE)),
        (f"{BASE}/last_alive", TopicInfo(DEV, "dz1f-pir", Kind.LAST_ALIVE)),
    ],
)
def test_parse_valid(topic: str, expected: TopicInfo) -> None:
    assert parse_topic(topic) == expected


@pytest.mark.parametrize(
    "topic",
    [
        "dingz/command",
        "dingz/groupe/a/command",
        f"dingz/{DEV}/state",
        f"dingz/{DEV}/dz1f-pir/online/x",
        f"dingz/{DEV}/dz1f-pir/online",
        f"{BASE}/state/light/x",
        f"{BASE}/state/light/0/extra",
        f"{BASE}/command/function/a/b/c",
        f"{BASE}/bogus/light/0",
        f"{BASE}/state//0",
        "homeassistant/device/dingz_x/config",
        "dingz",
        "",
    ],
)
def test_parse_invalid(topic: str) -> None:
    assert parse_topic(topic) is None


def test_channel_topic_roundtrip() -> None:
    topic = channel_topic(DEV, "dz1f-4b", Kind.STATE, "motor", 1)
    assert topic == f"dingz/{DEV}/dz1f-4b/state/motor/1"
    assert parse_topic(topic) == TopicInfo(DEV, "dz1f-4b", Kind.STATE, "motor", 1)

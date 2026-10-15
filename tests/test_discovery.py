import json
from pathlib import Path
from typing import Any

import jinja2
import pytest

from dingz_ha_bridge import discovery as d
from dingz_ha_bridge.topics import Kind, parse_topic

DEV = "dingztest"
MODEL = "dz1f-pir"
BASE = f"dingz/{DEV}/{MODEL}"

# Example messages from the iolo MQTT documentation.
DOC_MESSAGES: dict[str, str] = {
    f"dingz/{DEV}/announce": json.dumps(
        {"model": MODEL, "ip": "192.0.2.50", "hw_version": "1.0", "fw_version": "2.1.58"}
    ),
    f"dingz/{DEV}/online": "true",
    f"{BASE}/state/light/0": '{"turn":"on","brightness":100,"fadetime":20,"exception":0}',
    f"{BASE}/state/light/1": '{"turn":"off","brightness":40,"fadetime":0,"exception":0}',
    f"{BASE}/power/light/0": "12.5",
    f"{BASE}/energy/light/0": "1234",
    f"{BASE}/state/motor/1": '{"motion":0,"position":50,"lamella":30}',
    f"{BASE}/state/led": '{"on":1,"r":255,"g":0,"b":128}',
    f"{BASE}/state/input/0": "1",
    f"{BASE}/sensor/temperature": "27.21",
    f"{BASE}/sensor/light": "97.00",
    f"{BASE}/event/button/4": "m2",
}

_env = jinja2.Environment(undefined=jinja2.Undefined)


def render(template: str, **variables: Any) -> str:
    return _env.from_string(template).render(**variables)


def render_value(template: str, payload: str) -> str:
    try:
        value_json = json.loads(payload)
    except ValueError:
        value_json = None
    return render(template, value=payload, value_json=value_json)


def feed(dev: d.DeviceState, messages: dict[str, str]) -> None:
    for topic, payload in messages.items():
        info = parse_topic(topic)
        assert info is not None, topic
        dev.observe(info, payload.encode())


@pytest.fixture
def device() -> d.DeviceState:
    dev = d.DeviceState(DEV)
    feed(dev, DOC_MESSAGES)
    return dev


def test_observe_collects_channels(device: d.DeviceState) -> None:
    assert device.model == MODEL
    assert device.ip == "192.0.2.50"
    assert device.fw_version == "2.1.58"
    assert device.lights == {0, 1}
    assert device.motors == {1}
    assert device.tilt_motors == {1}
    assert device.inputs == {0}
    assert device.sensors == {"temperature", "light"}
    assert device.meters == {(Kind.POWER, "light", 0), (Kind.ENERGY, "light", 0)}
    assert device.effective_buttons() == {0, 1, 2, 3, 4}
    assert device.effective_pirs() == {0}


def test_observe_reports_changes_only(device: d.DeviceState) -> None:
    info = parse_topic(f"{BASE}/state/light/0")
    assert info is not None
    assert not device.observe(info, b'{"turn":"off","brightness":0}')
    assert device.observe(info, b"")
    assert device.lights == {1}


def test_unknown_model_is_not_ready() -> None:
    dev = d.DeviceState(DEV)
    info = parse_topic(f"dingz/{DEV}/online")
    assert info is not None
    dev.observe(info, b"true")
    assert not dev.ready
    with pytest.raises(ValueError):
        d.build_device_config(dev)


def test_device_config_shape(device: d.DeviceState) -> None:
    config = d.build_device_config(device)
    assert config["device"] == {
        "identifiers": ["dingz_dingztest"],
        "name": "dingz dingztest",
        "manufacturer": "iolo AG",
        "model": MODEL,
        "sw_version": "2.1.58",
        "hw_version": "1.0",
        "configuration_url": "http://192.0.2.50",
    }
    assert config["availability"][0]["topic"] == f"dingz/{DEV}/online"
    assert d.discovery_topic(DEV) == "homeassistant/device/dingz_dingztest/config"
    assert sorted(config["components"]) == sorted(
        [
            "dingz_dingztest_light_0",
            "dingz_dingztest_light_1",
            "dingz_dingztest_motor_1",
            "dingz_dingztest_led",
            "dingz_dingztest_button_0",
            "dingz_dingztest_button_1",
            "dingz_dingztest_button_2",
            "dingz_dingztest_button_3",
            "dingz_dingztest_button_4",
            "dingz_dingztest_pir_0",
            "dingz_dingztest_input_0",
            "dingz_dingztest_sensor_temperature",
            "dingz_dingztest_sensor_light",
            "dingz_dingztest_light_power_0",
            "dingz_dingztest_light_energy_0",
        ]
    )
    for uid, cfg in config["components"].items():
        assert cfg["unique_id"] == uid
        for key in ("state_topic", "command_topic"):
            if key in cfg:
                assert parse_topic(cfg[key]) is not None, cfg[key]
    # Round-trips through JSON.
    assert json.loads(d.encode(config)) == config


def test_unsafe_device_id_is_sanitized() -> None:
    assert d.node_id("a.b/c d") == "dingz_a_b_c_d"


def test_removed_components_become_platform_only(device: d.DeviceState) -> None:
    previous = d.component_platforms(d.build_device_config(device))
    info = parse_topic(f"{BASE}/state/light/1")
    assert info is not None
    device.observe(info, b"")
    config = d.build_device_config(device, previous)
    assert config["components"]["dingz_dingztest_light_1"] == {"platform": "light"}
    assert "dingz_dingztest_light_1" not in d.component_platforms(config)


FIXTURES = Path(__file__).parent / "fixtures"


def load_capture(name: str) -> list[tuple[str, str]]:
    messages = []
    for line in (FIXTURES / "mqtt" / name).read_text().splitlines():
        if line and not line.startswith("#"):
            _, topic, payload = line.split(" ", 2)
            messages.append((topic, payload))
    return messages


def test_real_capture_dz1f_4b() -> None:
    devices: dict[str, d.DeviceState] = {}
    changes = 0
    for topic, payload in load_capture("dz1f-4b_fw2.4.3.txt"):
        info = parse_topic(topic)
        assert info is not None, topic
        dev = devices.setdefault(info.device_id, d.DeviceState(info.device_id))
        changes += dev.observe(info, payload.encode())
    dev = devices["dingztest"]
    assert dev.model == "dz1f-4b"
    assert dev.lights == {0, 1, 2, 3}
    assert dev.buttons == {1}
    components = d.build_device_config(dev)["components"]
    assert "dingz_dingztest_led" in components
    assert {f"dingz_dingztest_button_{n}" for n in range(4)} <= components.keys()
    assert not any("pir" in uid for uid in components)
    # The periodic status dump must not look like a change once a device is known.
    pir = devices["dingztest2"]
    info = parse_topic("dingz/dingztest2/dz1f-pir/sensor/light")
    assert info is not None
    assert not pir.observe(info, b"12")


def test_led_created_without_state(device: d.DeviceState) -> None:
    dev = d.DeviceState(DEV, model="dz1f-4b")
    assert "dingz_dingztest_led" in d.build_device_config(dev)["components"]


def test_power_socket_becomes_switch(device: d.DeviceState) -> None:
    device.output_types[1] = "power_socket"
    switch = d.build_device_config(device)["components"]["dingz_dingztest_light_1"]
    assert switch["platform"] == "switch"
    payload = DOC_MESSAGES[f"{BASE}/state/light/0"]
    assert render_value(switch["value_template"], payload) == switch["state_on"]
    assert json.loads(switch["payload_on"]) == {"turn": "on"}
    assert json.loads(switch["payload_off"]) == {"turn": "off"}


def test_enrichment_names_and_relay(device: d.DeviceState) -> None:
    device.channel_names[("light", 0)] = "Table lamp"
    device.dimmable[0] = False
    light = d.build_device_config(device)["components"]["dingz_dingztest_light_0"]
    assert light["name"] == "Table lamp"
    assert light["command_on_template"] == d.RELAY_ON_TEMPLATE
    assert "brightness_template" not in light


# --- templates rendered against the documented payloads ---


def test_light_state_templates() -> None:
    on = DOC_MESSAGES[f"{BASE}/state/light/0"]
    off = DOC_MESSAGES[f"{BASE}/state/light/1"]
    assert render_value(d.LIGHT_STATE_TEMPLATE, on) == "on"
    assert render_value(d.LIGHT_STATE_TEMPLATE, off) == "off"
    assert render_value(d.LIGHT_BRIGHTNESS_TEMPLATE, on) == "255"
    assert render_value(d.LIGHT_BRIGHTNESS_TEMPLATE, off) == "102"


@pytest.mark.parametrize(
    ("variables", "expected"),
    [
        ({}, {"turn": "on"}),
        ({"brightness": 255}, {"turn": "on", "brightness": 100}),
        ({"brightness": 1}, {"turn": "on", "brightness": 1}),
        ({"brightness": 128, "transition": 2}, {"turn": "on", "brightness": 50, "fadetime": 20}),
        ({"transition": 60}, {"turn": "on", "fadetime": 100}),
    ],
)
def test_light_on_template(variables: dict[str, Any], expected: dict[str, Any]) -> None:
    assert json.loads(render(d.LIGHT_ON_TEMPLATE, **variables)) == expected


def test_light_off_template() -> None:
    assert json.loads(render(d.LIGHT_OFF_TEMPLATE)) == {"turn": "off"}
    assert json.loads(render(d.LIGHT_OFF_TEMPLATE, transition=1.5)) == {
        "turn": "off",
        "fadetime": 15,
    }


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ('{"motion":0,"position":50,"lamella":30}', "stopped"),
        ('{"motion":1,"position":50}', "opening"),
        ('{"motion":2,"position":50}', "closing"),
        ('{"motion":3,"position":50}', "stopped"),
        ('{"state":"open","position":50}', "opening"),
        ('{"state":"stop","position":50}', "stopped"),
        ('{"position":50}', "stopped"),
    ],
)
def test_cover_state_template(payload: str, expected: str) -> None:
    assert render_value(d.COVER_STATE_TEMPLATE, payload) == expected


def test_cover_commands(device: d.DeviceState) -> None:
    cover = d.build_device_config(device)["components"]["dingz_dingztest_motor_1"]
    payload = DOC_MESSAGES[f"{BASE}/state/motor/1"]
    assert render_value(cover["position_template"], payload) == "50"
    assert render_value(cover["tilt_status_template"], payload) == "30"
    assert json.loads(render(cover["set_position_template"], position=20)) == {"position": 20}
    assert json.loads(render(cover["tilt_command_template"], tilt_position=70)) == {"lamella": 70}
    for key in ("payload_open", "payload_close", "payload_stop"):
        assert set(json.loads(cover[key])) == {"motion"}


def test_led_templates() -> None:
    payload = DOC_MESSAGES[f"{BASE}/state/led"]
    assert render_value(d.LED_STATE_TEMPLATE, payload) == "on"
    assert render_value(d.LED_STATE_TEMPLATE, '{"on":0,"r":0,"g":0,"b":0}') == "off"
    assert json.loads(render(d.LED_ON_TEMPLATE, red=1, green=2, blue=3)) == {
        "on": 1,
        "r": 1,
        "g": 2,
        "b": 3,
    }
    assert json.loads(render(d.LED_ON_TEMPLATE)) == {"on": 1}


def test_button_and_pir_templates(device: d.DeviceState) -> None:
    components = d.build_device_config(device)["components"]
    button = components["dingz_dingztest_button_4"]
    assert json.loads(render_value(button["value_template"], "m2")) == {"event_type": "m2"}
    assert "m2" in button["event_types"]
    pir = components["dingz_dingztest_pir_0"]
    assert [render_value(pir["value_template"], v) for v in ("s", "ss", "n")] == [
        "ON",
        "ON",
        "OFF",
    ]


def test_energy_is_converted_from_joule_to_kwh(device: d.DeviceState) -> None:
    energy = d.build_device_config(device)["components"]["dingz_dingztest_light_energy_0"]
    assert energy["unit_of_measurement"] == "kWh"
    # Measured on FW 2.4.3: counter in Ws.
    assert float(render_value(energy["value_template"], "20479728.0")) == pytest.approx(
        5.6888, 1e-4
    )


def test_temperature_filter_components(device: d.DeviceState) -> None:
    components = d.build_device_config(device, id_prefix="dingz", temperature_filter=True)[
        "components"
    ]
    temp = components["dingz_dingztest_sensor_temperature"]
    assert temp["state_topic"] == "dingz-ha-bridge/dingz/dingztest/temperature"
    assert temp["availability_mode"] == "all"
    assert [a["topic"] for a in temp["availability"]] == [
        "dingz/dingztest/online",
        "dingz-ha-bridge/dingz/status",
    ]
    raw = components["dingz_dingztest_sensor_temperature_raw"]
    assert raw["state_topic"] == f"{BASE}/sensor/temperature"
    assert (raw["entity_category"], raw["enabled_by_default"]) == ("diagnostic", False)
    # Without the filter: one sensor on the dingz topic, no raw entity.
    plain = d.build_device_config(device)["components"]
    assert (
        plain["dingz_dingztest_sensor_temperature"]["state_topic"] == f"{BASE}/sensor/temperature"
    )
    assert "dingz_dingztest_sensor_temperature_raw" not in plain

"""Build Home Assistant MQTT device discovery payloads.

Everything here is pure: ``DeviceState`` collects what was seen on the dingz topics and
``build_device_config`` turns it into one device discovery config whose state/command
topics point straight at the original dingz topics.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from . import __version__
from .topics import Kind, TopicInfo, channel_topic, meta_topic

DISCOVERY_PREFIX = "homeassistant"
# Prefix of node ids, unique_ids and device identifiers. A different prefix gives a
# completely separate set of HA devices (e.g. for testing next to the real ones).
DEFAULT_ID_PREFIX = "dingz"
ID_PREFIX_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")
# Topics the bridge publishes itself (only used by the temperature filter).
BRIDGE_TOPIC_ROOT = "dingz-ha-bridge"
MANUFACTURER = "iolo AG"

# Front models with four built-in buttons (index 0-3).
FOUR_BUTTON_MODEL_PREFIX = "dz1f-"
BUTTON_COUNT = 4
BUTTON_EVENT_TYPES = ["p", "h", "r", "m1", "m2", "m3", "m4", "m5"]
# The PIR repeats "ss" every 3 s while somebody is present; turn off if that stops.
PIR_OFF_DELAY = 10

SENSOR_META: dict[str, dict[str, str]] = {
    "temperature": {
        "name": "Temperature",
        "device_class": "temperature",
        "unit_of_measurement": "°C",
        "state_class": "measurement",
    },
    "light": {
        "name": "Illuminance",
        "device_class": "illuminance",
        "unit_of_measurement": "lx",
        "state_class": "measurement",
    },
}
# power is W. energy is a counter in Ws (J), measured on FW 2.4.3; HA gets kWh. No
# float default in the template: a garbage value must not look like a counter reset.
METER_META: dict[Kind, dict[str, Any]] = {
    Kind.POWER: {"device_class": "power", "unit_of_measurement": "W", "state_class": "measurement"},
    Kind.ENERGY: {
        "device_class": "energy",
        "unit_of_measurement": "kWh",
        "state_class": "total_increasing",
        "value_template": "{{ (value | float / 3600000) | round(6) }}",
        "suggested_display_precision": 3,
    },
}

LIGHT_STATE_TEMPLATE = "{{ 'on' if value_json.turn == 'on' else 'off' }}"
SWITCH_STATE_TEMPLATE = LIGHT_STATE_TEMPLATE
LIGHT_BRIGHTNESS_TEMPLATE = "{{ (value_json.brightness | float(0) * 255 / 100) | round(0) | int }}"
_FADETIME = (
    '{% if transition is defined %},"fadetime":'
    "{{ [(transition * 10) | round(0) | int, 100] | min }}{% endif %}"
)
LIGHT_ON_TEMPLATE = (
    '{"turn":"on"'
    '{% if brightness is defined %},"brightness":'
    "{{ [(brightness * 100 / 255) | round(0) | int, 1] | max }}{% endif %}" + _FADETIME + "}"
)
RELAY_ON_TEMPLATE = '{"turn":"on"}'
LIGHT_OFF_TEMPLATE = '{"turn":"off"' + _FADETIME + "}"

# The docs mix {"motion": 0-3} and {"state": "stop"|"open"|...}; accept both.
COVER_STATE_TEMPLATE = (
    "{% set m = value_json.motion if value_json.motion is defined "
    "else value_json.state | default('stop') %}"
    "{{ {0: 'stopped', 1: 'opening', 2: 'closing', 3: 'stopped', "
    "'stop': 'stopped', 'open': 'opening', 'opening': 'opening', "
    "'close': 'closing', 'closing': 'closing'}.get(m, 'stopped') }}"
)

LED_STATE_TEMPLATE = "{{ 'on' if value_json.on | int(0) == 1 else 'off' }}"
LED_ON_TEMPLATE = (
    '{"on":1{% if red is defined %},"r":{{ red }},"g":{{ green }},"b":{{ blue }}{% endif %}}'
)


@dataclass
class Enrichment:
    """Details only the HTTP API knows (`system_config`, `output_config`)."""

    name: str | None = None
    output_names: dict[int, str] = field(default_factory=dict)
    output_types: dict[int, str] = field(default_factory=dict)
    dimmable: dict[int, bool] = field(default_factory=dict)


@dataclass
class DeviceState:
    """Everything the bridge knows about one dingz, as collected from its topics."""

    device_id: str
    model: str | None = None
    ip: str | None = None
    hw_version: str | None = None
    fw_version: str | None = None
    name: str | None = None
    lights: set[int] = field(default_factory=set)
    motors: set[int] = field(default_factory=set)
    tilt_motors: set[int] = field(default_factory=set)
    buttons: set[int] = field(default_factory=set)
    pirs: set[int] = field(default_factory=set)
    inputs: set[int] = field(default_factory=set)
    sensors: set[str] = field(default_factory=set)
    meters: set[tuple[Kind, str, int]] = field(default_factory=set)
    # Optional enrichment (HTTP API `output_config`): output names, whether a light output
    # dims, and the output type ("light", "power_socket", ...). Without it every output
    # is a dimmable light, since MQTT publishes all of them as `state/light/<n>`.
    channel_names: dict[tuple[str, int], str] = field(default_factory=dict)
    dimmable: dict[int, bool] = field(default_factory=dict)
    output_types: dict[int, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.model is not None

    def observe(self, info: TopicInfo, payload: bytes) -> bool:
        """Record one message. Returns True if the discovery config may have changed."""
        before = self._fingerprint()
        if info.model is not None:
            self.model = info.model
        present = bool(payload)

        match info.kind, info.component, info.index:
            case Kind.ANNOUNCE, _, _ if present:
                self._apply_announce(payload)
            case Kind.STATE, "light", int(n):
                _toggle(self.lights, n, present)
            case Kind.STATE, "motor", int(n):
                _toggle(self.motors, n, present)
                _toggle(self.tilt_motors, n, present and "lamella" in _json_obj(payload))
            case Kind.STATE, "input", int(n):
                _toggle(self.inputs, n, present)
            case Kind.EVENT, "button", int(n) if present:
                self.buttons.add(n)
            case Kind.EVENT, "pir", int(n) if present:
                self.pirs.add(n)
            case (Kind.POWER | Kind.ENERGY) as kind, str(component), int(n):
                _toggle(self.meters, (kind, component, n), present)
            case Kind.SENSOR, str(component), None if component in SENSOR_META:
                _toggle(self.sensors, component, present)

        return self._fingerprint() != before

    def enrich(self, enrichment: Enrichment) -> bool:
        """Apply HTTP API details. Returns True if the discovery config may have changed."""
        before = self._fingerprint()
        self.name = enrichment.name or self.name
        self.channel_names = {("light", n): name for n, name in enrichment.output_names.items()}
        self.output_types = dict(enrichment.output_types)
        self.dimmable = dict(enrichment.dimmable)
        return self._fingerprint() != before

    def _apply_announce(self, payload: bytes) -> None:
        data = _json_obj(payload)
        self.model = _str(data.get("model")) or self.model
        self.ip = _str(data.get("ip")) or self.ip
        self.hw_version = _str(data.get("hw_version")) or self.hw_version
        self.fw_version = _str(data.get("fw_version")) or self.fw_version

    def effective_buttons(self) -> set[int]:
        # Button events are not retained, so create the built-in ones up front.
        if self.model and self.model.startswith(FOUR_BUTTON_MODEL_PREFIX):
            return self.buttons | set(range(BUTTON_COUNT))
        return set(self.buttons)

    def effective_pirs(self) -> set[int]:
        if self.model and "pir" in self.model:
            return self.pirs | {0}
        return set(self.pirs)

    def _fingerprint(self) -> tuple[Any, ...]:
        return (
            self.model,
            self.ip,
            self.hw_version,
            self.fw_version,
            self.name,
            frozenset(self.lights),
            frozenset(self.motors),
            frozenset(self.tilt_motors),
            frozenset(self.buttons),
            frozenset(self.pirs),
            frozenset(self.inputs),
            frozenset(self.sensors),
            frozenset(self.meters),
            frozenset(self.channel_names.items()),
            frozenset(self.dimmable.items()),
            frozenset(self.output_types.items()),
        )


def node_id(device_id: str, prefix: str = DEFAULT_ID_PREFIX) -> str:
    """Device id made safe for discovery topics and unique_ids."""
    return f"{prefix}_" + re.sub(r"[^a-zA-Z0-9_-]", "_", device_id)


def discovery_topic(device_id: str, prefix: str = DEFAULT_ID_PREFIX) -> str:
    return f"{DISCOVERY_PREFIX}/device/{node_id(device_id, prefix)}/config"


def unique_id(
    device_id: str, component: str, index: int | None = None, prefix: str = DEFAULT_ID_PREFIX
) -> str:
    uid = f"{node_id(device_id, prefix)}_{component}"
    return uid if index is None else f"{uid}_{index}"


def bridge_status_topic(id_prefix: str = DEFAULT_ID_PREFIX) -> str:
    """Retained "online"/"offline" of the bridge (last will)."""
    return f"{BRIDGE_TOPIC_ROOT}/{id_prefix}/status"


def filtered_temperature_topic(device_id: str, id_prefix: str = DEFAULT_ID_PREFIX) -> str:
    return f"{BRIDGE_TOPIC_ROOT}/{id_prefix}/{device_id}/temperature"


def build_device_config(
    dev: DeviceState,
    previous: Mapping[str, str] | None = None,
    *,
    id_prefix: str = DEFAULT_ID_PREFIX,
    name_prefix: str = "",
    temperature_filter: bool = False,
) -> dict[str, Any]:
    """Return the device discovery config for ``dev``.

    ``previous`` maps unique_id -> platform of the components published last time.
    Components that disappeared are kept as ``{"platform": ...}``, which tells HA to
    remove that entity.

    With ``temperature_filter`` the temperature sensor reads the bridge's filtered topic
    (and is unavailable while the bridge is down); the raw dingz value stays available
    as a disabled diagnostic entity.
    """
    if dev.model is None:
        raise ValueError(f"model of {dev.device_id} unknown, cannot build topics")

    components = _components(dev, dev.model, id_prefix, temperature_filter)
    for uid, platform in (previous or {}).items():
        components.setdefault(uid, {"platform": platform})

    device: dict[str, Any] = {
        "identifiers": [node_id(dev.device_id, id_prefix)],
        "name": name_prefix + (dev.name or f"dingz {dev.device_id}"),
        "manufacturer": MANUFACTURER,
        "model": dev.model,
    }
    if dev.fw_version:
        device["sw_version"] = dev.fw_version
    if dev.hw_version:
        device["hw_version"] = dev.hw_version
    if dev.ip:
        device["configuration_url"] = f"http://{dev.ip}"

    return {
        "device": device,
        "origin": {"name": "dingz HA Bridge", "sw_version": __version__},
        "availability": [_device_availability(dev.device_id)],
        "qos": 1,
        "components": components,
    }


def _device_availability(device_id: str) -> dict[str, str]:
    return {
        "topic": meta_topic(device_id, Kind.ONLINE),
        "payload_available": "true",
        "payload_not_available": "false",
    }


def component_platforms(config: Mapping[str, Any]) -> dict[str, str]:
    """unique_id -> platform of all live components in a published config."""
    return {
        uid: cfg["platform"]
        for uid, cfg in config.get("components", {}).items()
        if len(cfg) > 1 and "platform" in cfg
    }


def encode(config: Mapping[str, Any]) -> bytes:
    return json.dumps(config, separators=(",", ":"), sort_keys=True).encode()


def _components(
    dev: DeviceState, model: str, id_prefix: str, temperature_filter: bool = False
) -> dict[str, dict[str, Any]]:
    did = dev.device_id
    out: dict[str, dict[str, Any]] = {}

    def add(platform: str, component: str, index: int | None, cfg: dict[str, Any]) -> None:
        uid = unique_id(did, component, index, id_prefix)
        out[uid] = {"platform": platform, "unique_id": uid, **cfg}

    def name(component: str, index: int, fallback: str) -> str:
        return dev.channel_names.get((component, index)) or f"{fallback} {index + 1}"

    for n in sorted(dev.lights):
        state = channel_topic(did, model, Kind.STATE, "light", n)
        command = channel_topic(did, model, Kind.COMMAND, "light", n)
        if dev.output_types.get(n, "light") != "light":
            add(
                "switch",
                "light",
                n,
                {
                    "name": name("light", n, "Output"),
                    "state_topic": state,
                    "command_topic": command,
                    "value_template": SWITCH_STATE_TEMPLATE,
                    "state_on": "on",
                    "state_off": "off",
                    "payload_on": RELAY_ON_TEMPLATE,
                    "payload_off": '{"turn":"off"}',
                },
            )
            continue
        cfg: dict[str, Any] = {
            "name": name("light", n, "Light"),
            "schema": "template",
            "state_topic": state,
            "command_topic": command,
            "state_template": LIGHT_STATE_TEMPLATE,
            "command_off_template": LIGHT_OFF_TEMPLATE,
        }
        if dev.dimmable.get(n, True):
            cfg["command_on_template"] = LIGHT_ON_TEMPLATE
            cfg["brightness_template"] = LIGHT_BRIGHTNESS_TEMPLATE
        else:
            cfg["command_on_template"] = RELAY_ON_TEMPLATE
        add("light", "light", n, cfg)

    for n in sorted(dev.motors):
        state = channel_topic(did, model, Kind.STATE, "motor", n)
        command = channel_topic(did, model, Kind.COMMAND, "motor", n)
        cfg = {
            "name": name("motor", n, "Cover"),
            "device_class": "blind" if n in dev.tilt_motors else "shade",
            "state_topic": state,
            "value_template": COVER_STATE_TEMPLATE,
            "command_topic": command,
            "payload_open": '{"motion":1}',
            "payload_close": '{"motion":2}',
            "payload_stop": '{"motion":0}',
            "position_topic": state,
            "position_template": "{{ value_json.position }}",
            "set_position_topic": command,
            "set_position_template": '{"position":{{ position }}}',
        }
        if n in dev.tilt_motors:
            cfg |= {
                "tilt_status_topic": state,
                "tilt_status_template": "{{ value_json.lamella }}",
                "tilt_command_topic": command,
                "tilt_command_template": '{"lamella":{{ tilt_position }}}',
            }
        add("cover", "motor", n, cfg)

    # Every front has an RGB LED. Its state is not retained (only sent with the periodic
    # status dump), so create it up front instead of waiting for it.
    add(
        "light",
        "led",
        None,
        {
            "name": "LED",
            "schema": "template",
            "state_topic": channel_topic(did, model, Kind.STATE, "led"),
            "command_topic": channel_topic(did, model, Kind.COMMAND, "led"),
            "state_template": LED_STATE_TEMPLATE,
            "red_template": "{{ value_json.r }}",
            "green_template": "{{ value_json.g }}",
            "blue_template": "{{ value_json.b }}",
            "command_on_template": LED_ON_TEMPLATE,
            "command_off_template": '{"on":0}',
        },
    )

    for n in sorted(dev.effective_buttons()):
        add(
            "event",
            "button",
            n,
            {
                "name": "External button" if n == BUTTON_COUNT else f"Button {n + 1}",
                "device_class": "button",
                "state_topic": channel_topic(did, model, Kind.EVENT, "button", n),
                "event_types": BUTTON_EVENT_TYPES,
                "value_template": '{"event_type":"{{ value }}"}',
            },
        )

    for n in sorted(dev.effective_pirs()):
        add(
            "binary_sensor",
            "pir",
            n,
            {
                "name": "Motion" if n == 0 else "External motion",
                "device_class": "motion",
                "state_topic": channel_topic(did, model, Kind.EVENT, "pir", n),
                "value_template": "{{ 'ON' if value in ['s', 'ss'] else 'OFF' }}",
                "off_delay": PIR_OFF_DELAY,
            },
        )

    for n in sorted(dev.inputs):
        add(
            "binary_sensor",
            "input",
            n,
            {
                "name": f"Input {n + 1}",
                "state_topic": channel_topic(did, model, Kind.STATE, "input", n),
                "payload_on": "1",
                "payload_off": "0",
            },
        )

    for sensor in sorted(dev.sensors):
        raw_topic = channel_topic(did, model, Kind.SENSOR, sensor)
        if sensor == "temperature" and temperature_filter:
            add(
                "sensor",
                "sensor_temperature",
                None,
                {
                    **SENSOR_META[sensor],
                    "state_topic": filtered_temperature_topic(did, id_prefix),
                    "availability": [
                        _device_availability(did),
                        {"topic": bridge_status_topic(id_prefix)},
                    ],
                    "availability_mode": "all",
                },
            )
            add(
                "sensor",
                "sensor_temperature_raw",
                None,
                {
                    **SENSOR_META[sensor],
                    "name": "Temperature (raw)",
                    "state_topic": raw_topic,
                    "entity_category": "diagnostic",
                    "enabled_by_default": False,
                },
            )
            continue
        add("sensor", f"sensor_{sensor}", None, {"state_topic": raw_topic, **SENSOR_META[sensor]})

    for kind, component, n in sorted(dev.meters):
        label = dev.channel_names.get((component, n)) or f"{component.capitalize()} {n + 1}"
        add(
            "sensor",
            f"{component}_{kind}",
            n,
            {
                "name": f"{label} {kind}",
                "state_topic": channel_topic(did, model, kind, component, n),
                **METER_META[kind],
            },
        )

    return out


def _toggle[T](items: set[T], item: T, present: bool) -> None:
    if present:
        items.add(item)
    else:
        items.discard(item)


def _json_obj(payload: bytes) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None

# Features

## What appears in Home Assistant

Each dingz becomes **one device** (manufacturer “iolo AG”, model = front, e.g. `dz1f-pir`, with firmware/hardware version and a link to the dingz web interface). It contains:

| dingz | HA entity | Details |
|---|---|---|
| Output, type `light`, dimmable | `light` with brightness | brightness 0–100 % ↔ HA 0–255, transition → `fadetime` |
| Output, type `light`, not dimmable | `light` on/off | |
| Output, other type (`power_socket`, heater, fan, …) | `switch` | |
| Blind motor | `cover` with position; slats as tilt | 0 = closed, 100 = open; *untested* |
| Front LED | `light` with RGB colour | always created |
| Buttons 1–4 | `event` | events `p`, `h`, `r`, `m1` … `m5` |
| External button on the input | `event` “External button” | appears after the first event |
| PIR (motion sensor) | `binary_sensor` motion | |
| External PIR | `binary_sensor` motion | appears after the first event |
| Temperature | `sensor` °C | filtered by the bridge (see below); raw value as disabled diagnostic entity |
| Illuminance | `sensor` lx | |
| Power per output | `sensor` W | |
| Energy per output | `sensor` kWh (`total_increasing`) | suitable for the energy dashboard |
| Input (type “state”) | `binary_sensor` | |

Names: device name from the dingz (`dingz_name`), entity names from the output names on the dingz. Without HTTP enrichment: “dingz <id>”, “Light 1” …

All entities become **unavailable** when the dingz is offline (`dingz/<id>/online` = `false`, last will).

### Button events

| Event | Meaning |
|---|---|
| `p` | pressed |
| `h` | held, repeated every second |
| `r` | released after hold |
| `m1` … `m5` | multi-click (`m2` = double click) |

In automations: trigger *Entity → State* on the event entity, condition on the attribute `event_type`.

### Motion sensor

The dingz reports `s` (somebody), `ss` (still somebody, every 3 s) and `n` (nobody). If no message arrives for 10 s the sensor turns off – even if an `n` gets lost.

### Temperature

The dingz sends its room temperature twice: on every change with 0.5 °C resolution, and every 5 minutes in a status dump that **floors the value to whole degrees** (21.5 → 21.0). Unfiltered, Home Assistant would show a saw-tooth (21.5 → 21.0 → 21.5 …) and statistics about 0.25 °C too low.

The **temperature filter** (on by default) removes this:

- A status dump is a burst of all topics of a device that always ends with `…/last_alive`. The bridge holds each temperature for 1.5 s; if a `last_alive` follows, the value came from a dump and is dropped when it is only the floored last good value (a larger difference is used as fallback).
- On start the bridge reads the exact value via HTTP (`room_temperature`), because the retained MQTT value may itself be a floored dump value.
- The filtered value is published retained on `dingz-ha-bridge/<prefix>/<id>/temperature`; the temperature entity reads from there.
- This is the only entity that needs the running bridge. If the bridge stops, its last will sets `dingz-ha-bridge/<prefix>/status` to `offline` and the temperature becomes **unavailable** instead of showing wrong values.
- The unfiltered value stays available as the disabled diagnostic entity “Temperature (raw)”.

Disable with `--no-temperature-filter`, `DINGZ_TEMPERATURE_FILTER=0` or the add-on option `temperature_filter: false`.

### Energy

The dingz counts energy in watt-seconds (joules). The bridge has Home Assistant convert it to kWh; the sensors work with the energy dashboard.

The counter on the dingz is **not persistent**: after a reboot or power loss it starts again at 0. The entity graph then drops to almost zero, but because the sensors use `state_class: total_increasing`, Home Assistant treats the drop as a meter reset – the energy dashboard and long-term statistics continue correctly. Only consumption between the last report before the reboot and the reboot itself (at most a few minutes) is missing.

## How discovery works

1. The bridge subscribes to `dingz/#` and to its own discovery topics `homeassistant/device/<prefix>_*/config`.
2. From the **retained** messages it detects devices and channels (`state/light/<n>`, `power/…`, `sensor/…`, `announce` …). Buttons and PIR are not retained and are created up front based on the model (`dz1f-*`: 4 buttons; models containing `pir`: internal PIR).
3. Using the IP from `announce` it reads, **once per device** via HTTP, the device name, output names, output types and dimmability (`system_config`, `output_config`).
4. 2 s after the last change it publishes **one** device discovery config per device – retained, QoS 1. The first config waits up to 15 s for the HTTP read so that entities do not change name or type afterwards.
5. If the config is unchanged, nothing is published. Restarting the bridge therefore causes no needless updates.

The state and command topics in the config point at the **original** dingz topics. Home Assistant does the conversion (e.g. `{"turn":"on"}` ↔ on/off, brightness, energy) with templates. That is why operation keeps working while the bridge is stopped.

### Changes and cleanup

| Situation | Behaviour |
|---|---|
| New channel (e.g. output activated) | config is extended |
| Channel disappears (retained topic cleared) | entity is removed in HA |
| dingz offline | entities “unavailable”; the device stays |
| Discovery config with the own prefix for which no dingz sends data anymore | deleted 10 s after start |
| Foreign discovery configs | never touched |

### Without HTTP

With `--no-http` (add-on: `http_enrichment: false`), or if a dingz cannot be reached via HTTP, defaults apply: all outputs are dimmable lights with generic names. After an HTTP error the bridge retries every 5 minutes and updates the config afterwards.

## Device search

The device search (web UI, `scan`) combines three sources and merges hits by MAC, IP and MQTT ID:

| Source | Finds | Requirement |
|---|---|---|
| **mDNS** (`_http._tcp`, “DINGZ …”) | all dingz on the network, even without MQTT | multicast reaches the bridge (host network, same VLAN or mDNS reflector) |
| **MQTT** (`dingz/+/announce`, `online`) | dingz already publishing to the broker | broker access |
| **Subnet** (`--subnet`, field in the web UI) | all dingz in a network up to /20 | HTTP access; confirmed via `GET /api/v1/device` |

## More

- **Web UI** with device list, status, WLAN signal, MQTT activity, broker setup and update check – see [Web UI](web-ui.md).
- **Command line** for search, status and broker setup – see [Command line](cli.md).
- **Test mode** next to an existing integration with `--id-prefix` / `--name-prefix`, **dry run** with `--dry-run`.
- **MQTT over TLS** with own CA and client certificates – see [Security](security.md#tls-to-the-broker).
- **Update check** against GitHub releases, shown in the web UI.

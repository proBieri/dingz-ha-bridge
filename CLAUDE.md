# dingz-ha-bridge

Bridge service that exposes dingz switches (iolo AG) publishing via MQTT to Home Assistant through **MQTT discovery**. Optionally it finds dingz devices on the network and sets up their MQTT connection (provisioning via CLI or a small web UI).

## Core principle

The bridge **does not translate messages**. It subscribes to `dingz/#`, detects devices and channels and publishes one **retained device discovery config** per device whose `state_topic` / `command_topic` point directly at the **original dingz topics**. HA does the conversion via `value_template` / `command_template`.

Consequences:
- The bridge does not need to run for devices to stay operable. It is only needed for discovery and cleanup.
- Runtime logic in the bridge only where HA cannot express it with templates/options. Currently one exception: the **temperature filter** (`filters.py`), because a template cannot tell a floored status-dump value from a real change. The filtered temperature is published on `dingz-ha-bridge/<prefix>/<id>/temperature`; the bridge status (`dingz-ha-bridge/<prefix>/status`, last will `offline`) is part of that entity's availability. Everything else works without the bridge.

## Environment

- Target: Home Assistant OS/Supervised with an MQTT broker (e.g. the Mosquitto add-on).
- Two modes, **one Docker image**:
  - **HA add-on** (`addon/config.yaml`, `repository.yaml`; image built by CI from the root `Dockerfile` to `ghcr.io/probieri/dingz-ha-bridge-{arch}`). `addon.py` detects add-on mode via `SUPERVISOR_TOKEN`, fetches MQTT credentials from `http://supervisor/services/mqtt` and options from `/data/options.json`. UI only via **ingress** (peer `172.30.32.2`, everything else → 403).
  - **Standalone** via `docker compose` with the prebuilt multi-arch image `ghcr.io/probieri/dingz-ha-bridge:<version>|latest` (CI job `image`, built for linux/amd64+arm64 on tags, runs as the unprivileged user `app`/UID 1000 via `USER ${RUN_AS}`; the add-on images from job `addon-image` are built with `RUN_AS=0` because the add-on reads Supervisor files below `/data`; `.env` from the `.env.example` template), or directly via CLI. `build: .` only for development. Configuration via environment variables (`DINGZ_MQTT_HOST`, `DINGZ_MQTT_PORT`, `DINGZ_MQTT_USERNAME`, `DINGZ_MQTT_PASSWORD`, …) or the matching CLI arguments; CLI wins.
- The image must build for `amd64` and `aarch64`.
- mDNS needs host networking: standalone `network_mode: host`, add-on `host_network: true`. Docker Desktop (macOS) does not pass multicast reliably → develop in a venv there.
- If the HACS integration **hass-dingz** (siku2) runs in parallel, entities are duplicated.

## Conventions

- Python **3.12+**, asyncio, `aiomqtt`. No further runtime dependencies without a reason.
- MQTT connections are created only via `MqttConfig.client()` (bridge and scan), which applies TLS (`--tls`, `--ca-file`, client certificate, `--tls-insecure`; port 8883 by default with TLS). Verified against a Mosquitto with an own CA: without CA → `CERTIFICATE_VERIFY_FAILED`, insecure → connects. The add-on takes `ssl` from the Supervisor and an optional CA from `/ssl` (`map: ssl`).
- HTTP reads of the bridge (`device_api.py`) and the update check use the standard library only (`urllib` via `asyncio.to_thread`).
- Provisioning dependencies only as extra `dingz-ha-bridge[ui]`: `aiohttp` (UI server), `zeroconf` (mDNS). Pure discovery mode must run without them (lazy imports / only in the affected modules). The Docker image installs the extra.
- Typed (type hints, `dataclass`), formatting/linting with `ruff`.
- Tests with `pytest`. Discovery payloads are built as pure functions and tested without a broker. Test cases use example messages from the iolo docs and anonymised captures of real devices (`tests/fixtures/`). Bridge, web UI and CLI are tested with fakes (MQTT client, HTTP).
- Layout:
  - `dingz_ha_bridge/topics.py`: parses topics → `(device_id, model, kind, component, index)`
  - `dingz_ha_bridge/discovery.py`: builds discovery payloads (pure functions)
  - `dingz_ha_bridge/bridge.py`: MQTT loop, device registry, publish/cleanup, last message per device (for the UI), temperature filter wiring and bridge status (last will)
  - `dingz_ha_bridge/filters.py`: temperature filter for the floored status-dump values (pure, timestamp driven)
  - `dingz_ha_bridge/device_api.py`: thin HTTP client (stdlib): enrichment (`system_config`/`output_config`), `status()` (no secrets), `wifi()` (scan-based signal), `set_mqtt()` (read → write → verify), `build_mqtt_uri`/`mask_uri`
  - `dingz_ha_bridge/scan.py`: device search (mDNS, MQTT `announce`, subnet sweep via `GET /device`) → list merged by MAC/IP/MQTT ID
  - `dingz_ha_bridge/web.py` + `dingz_ha_bridge/static/`: optional web UI (aiohttp, static HTML/JS without a build step)
  - `dingz_ha_bridge/addon.py`: add-on settings from the Supervisor
  - `dingz_ha_bridge/updates.py`: GitHub update check (`releases/latest`, falling back to tags); repo constants `GITHUB_REPO`/`REPO_URL` in `__init__.py`
  - `dingz_ha_bridge/__main__.py`: CLI with subcommands `run` (default, optional `--ui`), `scan`, `status`, `set-mqtt`, `ui`
  - `tests/`, `addon/`, `docs/en/` + `docs/de/` (user docs), `docs/PLAN.md`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`
- IDs: `unique_id = dingz_<id>_<component>_<n>`, device identifier `dingz_<id>`, discovery topic `homeassistant/device/dingz_<id>/config`. The prefix `dingz` can be changed with `--id-prefix` (test mode next to hass-dingz: `--id-prefix dingztest --name-prefix "TEST "`). Cleanup/stale detection only ever touches the own prefix.
- Discovery configs always **retained**, QoS 1.
- Repository: https://github.com/proBieri/dingz-ha-bridge. Versions as tags `vX.Y.Z`; keep `__version__`, `pyproject.toml` and `addon/config.yaml` in sync. ghcr image names are lowercase: `ghcr.io/probieri/dingz-ha-bridge-{arch}`. New ghcr packages start **private**: after the first tag, set `dingz-ha-bridge`, `dingz-ha-bridge-amd64` and `dingz-ha-bridge-aarch64` to public (GitHub → Packages → Package settings), otherwise neither Docker users nor the add-on can pull them.
- Language: code, identifiers, comments, commit messages, `CLAUDE.md`, `docs/PLAN.md` and `addon/DOCS.md` in **English**. User documentation is bilingual and must be kept in sync: `README.md` (en) / `README.de.md` (de), `docs/en/` / `docs/de/` (same chapters, same file names; `docs/README.md` is the language index). Every user-facing change goes into both languages. The web UI is bilingual (English/German by browser language): all texts live in the `I18N` table in `static/app.js`; the server returns codes (`quality`, `error_code`, `code`), never UI text.

## dingz MQTT reference (iolo docs V1.02, FW 2.1.58)

Base: `dingz/<id>/<model>/…`. According to the docs `<id>` defaults to the lowercase MAC, but it is freely configurable (`system_config.id`, e.g. `dingzlivingroom`) → never interpret it as a MAC. `<model>` is the front model, e.g. `dz1f-pir`, `dz1f-4b`. `<n>` starts at 0.

| Topic | Payload | retained |
|---|---|---|
| `…/state/light/<n>` (0–3) | `{"turn":"on","brightness":100,"fadetime":20,"exception":0}` | yes |
| `…/command/light/<n>` | `{"turn":"on"\|"off"\|"toggle","brightness":0-100,"fadetime":0-100}` (fadetime in 1/10 s) | no |
| `…/power/light/<n>`, `…/energy/light/<n>` | number (energy at most every 10 min) | yes |
| `…/state/motor/<n>` (0–1) | `{"motion":0-3,"position":0-100,"lamella":0-100}`; motion: 0 stop, 1 opening, 2 closing, 3 calibrating | yes |
| `…/command/motor/<n>` | `{"position":50,"lamella":30}` or `{"motion":0\|1\|2\|3}` (stop/open/close/calibrate) | no |
| `…/power/motor/<n>`, `…/energy/motor/<n>` | number | yes |
| `…/state/led`, `…/command/led` | `{"on":0\|1,"r":0-255,"g":0-255,"b":0-255}` | yes / no |
| `…/event/button/<n>` (0–3 internal, 4 = external button on the input) | `p` press, `h` hold (every 1 s), `r` release after hold, `m<cnt>` multi-click (`m1`, `m2`, …) | no |
| `…/event/pir/<n>` (0 internal, 1 external) | `s` somebody, `ss` still somebody (every 3 s), `n` nobody | no |
| `…/state/input/0` | `0`/`1` (only if the input type is “state”) | yes |
| `…/sensor/temperature` | `27.21` (°C, on Δ 0.5) | yes |
| `…/sensor/light` | `97.00` (lux) | yes |
| `…/state/thermostat` | `{"status":"heating","mode":"heating"\|"cooling","target":22.0}` | yes |
| `…/command/function/…` | function control (undocumented) | no |
| `dingz/<id>/online` | `true`/`false`, last will = false | yes |
| `dingz/<id>/announce` | `{"model":"dz1f-pir","ip":"…","hw_version":"1.0","fw_version":"…"}` | yes |
| `dingz/<id>/last_alive` (docs) / `dingz/<id>/<model>/last_alive` (FW 2.4.3) | Unix timestamp | no |

**Verified (FW 2.4.3, fixture `tests/fixtures/mqtt/`)**:
- Light state without `fadetime`: `{"turn":"off","brightness":0,"exception":0}`. Non-dimmable outputs ignore `brightness`/`fadetime` and report `brightness: 100`. `toggle` works.
- Inactive outputs do not appear at all. Outputs of type `power_socket` etc. still appear as `state/light/<n>`.
- `state/led` is **not retained**; it only comes after a change or with the periodic status dump. Setting the colour from HA works.
- Periodic status dump every few minutes (observed: 5 min per device, not retained): all `state/*`, `sensor/*`, `power/*`, `energy/*`, `state/led`, `last_alive`.
- Buttons: HTTP `button/<N>` = MQTT `event/button/<N-1>`. Events `p`, `h` (every 1 s), `r`. `m<n>` not observed yet (cannot be simulated via HTTP).
- `sensor/light` is an integer, `sensor/temperature` e.g. `21.0`.
- `power/*` in W. `energy/*` is a counter in **Ws (joules)** (measured: ~50 W → +15,000 per 5 min); discovery converts to kWh via `value_template`. The counter is **not persistent**: after a reboot it restarts at 0 (verified: 4,481,994 Ws → 3,025 Ws). `state_class: total_increasing` makes HA treat the drop as a meter reset, so long-term statistics stay correct.
- MQTT client IDs must be unique; a second connection with the same ID kicks out the first.

Group commands: `dingz/command` (all), `dingz/groupe/<id>/command`. Not used by the bridge.

## dingz HTTP API (supplement)

Base `http://<ip>/api/v1/`. References:
- API/playground: https://api.dingz.ch/de/ (covers FW up to 1.3.x, FW 2.x only partly)
- Changelog 1.3.30 → 2.0.x: https://api.dingz.ch/de/cms/changelog-de/?_usehttp=true (endpoint signatures only, no fields)
- Configurator v2: https://api.dingz.ch/de/config/

Verify endpoints against real FW 2.x devices before using them.

Relevant FW 2.0 changes according to the changelog:
- **New**: `GET /outputs`, `GET|POST /output_config`, `GET /groups/status[/<a..z>]`, `GET|POST /lux_config`, `GET|POST /sta/fallback`, `GET|POST /protected` + `POST /reset_protection` (device lock), `POST /neighbors/clear`, `POST /restore_config`, `/scheduler`, PIR and thermostat actions.
- **Changed**: `action`, `button`, `dimmer`, `pir`, `thermostat`, `shade` (e.g. `shade/<n>/<action>` with optional `time` 200–10000, button actions `single`/`double`/`long`/`hold_up`/`hold_down`).
- **Not in the changelog**: MQTT, mDNS, `services_config`, `login`, motor payload (`motion` vs. `state`). There are no FW 2.x docs for these → determine on the device.

The bridge uses the API **read-only** for channel detection and device info. The only write is `services_config` during provisioning (see below). Never for controlling outputs – that is MQTT only:

| Path (GET) | Use |
|---|---|
| `/device` | model, HW/FW version, serial number, DIP switch, PIR present |
| `/info` | FW version, MAC, IP, SSID |
| `/output_config` | type per output (light, heater, pulse, fan, garage door, valve), FW 2.0+ |
| `/outputs` | output state, FW 2.0+ |
| `/dimmer_config` | name and light source type per dimmer channel |
| `/blind_config` | blind configuration, slat type (tilt yes/no) |
| `/input_config` | input mode/type |
| `/button_config` | button assignment |
| `/state` | combined state of all modules |
| `/scan` | WLAN scan: `[ssid, dBm, ssid, dBm, …]` (~2 s); the only source for signal strength |

With an active web interface password, `POST /login` is needed. MQTT settings on the device live in `/services_config` (`mqtt.uri`, `mqtt.enable`).

## Provisioning (device search, status, MQTT setup)

Purpose: find dingz devices that do not (yet) publish under `dingz/#`, show their status and set their MQTT broker. Without MQTT a device never shows up in discovery; provisioning closes that gap. The core principle stays: provisioning is setup/diagnostics, not a runtime path.

**Device search** (combine sources, deduplicate by MAC):
1. mDNS via `zeroconf` (async).
2. Retained `dingz/<id>/announce` from the broker (IP of already configured devices).
3. Subnet sweep as fallback (max /20): async port-80 check first, then `GET /api/v1/device` (`{"<MAC>": {"type": "dingz"}}`) as confirmation. `/info` alone is not enough, myStrom devices have it too.

**Status**: `GET /api/v1/info`, `/device`, `/system_config`, `/services_config`, `/protected`, `/outputs`; plus from MQTT whether the device is `online`, when its last message arrived and whether a discovery config exists.

**WLAN signal**: `GET /api/v1/scan`, strongest AP of the own SSID (`/info.ssid`) as an approximation of the current connection. Cached 5 min in the UI, measured sequentially.

**Set MQTT**: `POST /api/v1/services_config` with JSON `{"mqtt": {"uri": …, "enable": …}}`. Write format **confirmed** on FW 2.4.3: a JSON partial update (`POST /api/v1/system_config` with `{"origin": true}`) returned HTTP 200 and changed only that field — same shape `set_mqtt` uses. Read before writing, read again afterwards and only report success on a match. User/password in the URI are percent-encoded.

**Security**:
- The UI can reconfigure devices and handles broker credentials. Add-on: ingress only. Standalone: default bind `127.0.0.1`; other interfaces require `DINGZ_UI_PASSWORD` (HTTP basic), otherwise it refuses to start.
- State-changing UI requests need the header `X-Dingz-UI: 1` (CSRF protection). Device endpoints only accept hosts from the last scan (no requests to arbitrary hosts). CSP `default-src 'self'`, therefore no inline JS/CSS.
- Never log passwords (broker, web interface password per device) and never return them to the UI in clear text.
- Write actions only on explicit user action (CLI command or button with confirmation), never automatically for found devices.

**Verified on the device (FW 2.4.3, dz1f-4b; fixtures in `tests/fixtures/`)**:
- **mDNS**: service `_http._tcp`, instance `DINGZ <last 6 MAC digits>`, host `DINGZ-<model>-<MAC>.local`, port 80. TXT records: `mac`, `fw`, `id` (= MQTT `<id>`!), `name`, `room`, `home`, `pir`, `protected`, `colour`, `cp`, `identify_flag`. mDNS alone provides everything for the device list.
- `services_config` also contains `mdns`, `udp_search`, `broadcast_period` etc.; `mqtt.uri` has the form `mqtt://user:pass@host` (port optional).
- Broker URIs (`mqtt.uri`) can contain a password: never log them, mask them in UI/CLI (`mask_uri`), never put real values in fixtures.
- `output_config` returns per output `name`, `type` (`light`, …) and `light.dimmable` → entity names and relay vs. dimmer. `system_config` returns `dingz_name`, `room_name` and `id`.
- `/device` returns `front_hw_model` (= MQTT `<model>`) and `has_pir`.
- Device lock: `/protected`, `system_config.protected_status`; REST password flag: `system_config.rest_password`.
- **Confidential:** unpublished security findings about the dingz API are kept in `SECURITY-NOTES.local.md` (git-ignored, local only, under coordinated disclosure). Never copy their content into committed files, commit messages or PRs until the user explicitly allows it.

**Open points**:
- Motor payload (`motion` vs. `state`) and `input`: no devices with motor/input available.
- Observe multi-click events `m<n>` on real buttons.
- Special-character escaping in the `mqtt.uri` password, TLS (`mqtts://`, `mqtt.server.crt`).
- POST format of `/services_config`: **confirmed** as a JSON partial update (see Set MQTT above); whether a reboot is needed after an `mqtt.uri` change is still unverified.
- Behaviour of `/login` (session cookie?) with an active web interface password.
- Whether the device lock `/protected` (new in FW 2.0) blocks writes such as `services_config`. Show it in the status; never call `reset_protection` automatically.
- Temperature (verified, 4 devices, 1h45): the periodic status dump sends `sensor/temperature` **floored to whole degrees** (18.5 → 18.0, 22.5 → 22.0, 21.5 → 21.0), while change messages have 0.5 °C resolution and match HTTP `room_temperature`. In HA this produces a saw-tooth (x.5 ↔ x.0 every 5 min) and a ~0.25 °C low bias. A pure template filter cannot distinguish a dump from a real change to x.0; the bridge can: a dump is a burst of all topics of a device within ~40 ms that always ends with `<model>/last_alive`. **Handled** by the temperature filter (`filters.py`, window 1.5 s, start value from HTTP `room_temperature`, replay test on a real 21-min capture). Firmware bug, to be reported to iolo.
- One device (Flur OG) reported CPU temperatures of 85 °C median / 94 °C max (others 42–62 °C) and a stuck LED override (`led/get` → `override_level: 2`, LED ignores MQTT/HTTP colour changes although they are acknowledged). Cause unknown (not PIR auto mode, not output feedback, night light off).

## Mapping to HA components

- **Outputs** all appear as `…/light/<n>`. The real type comes from `output_config` (HTTP): `light` → `light` (brightness only with `light.dimmable`), all other types (`power_socket`, …) → `switch` on the same topics.
- **Light** → `light`; `schema: json` does not fit (dingz uses `turn` instead of `state`), hence `schema: template` with `command_on_template` / `command_off_template` / `state_template` / `brightness_template`. Convert brightness 0–100 ↔ HA 0–255.
- **Motor** → `cover` with `position_topic`/`set_position_topic` (0 = closed, 100 = open, matches HA) and `tilt_*` for slats. Stop/open/close via `{"motion":n}`.
- **Front LED** → `light` (RGB). Always created once the model is known (state is not retained).
- **Buttons** → `event` (`event_types: [p, h, r, m1 … m5]`), optionally also `device_automation` triggers.
- **PIR** → `binary_sensor` (`device_class: motion`). `s`/`ss` = on, `n` = off, plus `off_delay` (~10 s) as fallback if an `n` gets lost (`expire_after` would be wrong: it makes the entity *unavailable* instead of *off*). No runtime logic in the bridge needed.
- **Sensors** → `sensor` with matching `device_class`/`state_class` (temperature, illuminance, power W, energy kWh `total_increasing` converted from Ws).
- **Input** → `binary_sensor`.
- **Thermostat** → `climate` (later, low priority).
- **Availability** for all entities: `availability_topic: dingz/<id>/online`, `payload_available: "true"`.
- Device info (`model`, `sw_version`, `hw_version`, `configuration_url: http://<ip>`) from `announce`; device name from `system_config.dingz_name`, entity names from `output_config[n].name`. Origin name “dingz HA Bridge”.
- The first discovery of a device waits for the HTTP read (max ~15 s) so that entities do not change platform/name afterwards. Without HTTP (`--no-http` or errors) the generic defaults apply.

## Known pitfalls

- **Channel detection**: which outputs are lights, dimmers or motors only follows from the retained `state/*` topics. Publish discovery only after the retained messages have arrived after subscribing (short debounce per device). Optionally query the HTTP API (see above, especially `/device`, `/output_config`, `/dimmer_config`, `/blind_config`).
- **Inconsistent motor payload**: the doc examples partly use `"state":"stop"/"open"` instead of `"motion"`. Verify against real device messages and keep templates tolerant.
- **Buttons and PIR are not retained**: they are only discovered after the first event. Therefore create buttons up front based on the model (`dz1f-*` = 4 buttons).
- **Cleanup**: remove devices/channels with an empty retained payload on the discovery topic. Never touch foreign `homeassistant/…` topics.
- **Duplicate entities** with hass-dingz during the test phase.
- **mDNS in a container**: without host networking the scan finds nothing, silently. Log clearly when mDNS returns no answers and point to the other sources.
- **HTTP API tests**: test against recorded responses of real devices (fixtures in `tests/fixtures/`), not against doc examples alone. Anonymise MACs/IPs in fixtures.
- **HA “last changed”** only moves when the value changes; a stable temperature looks stale although messages arrive every 5 min.

## Commands

```bash
uv venv -p 3.12 .venv && source .venv/bin/activate     # or python3.12 -m venv .venv
uv pip install -e ".[dev,ui]"
pytest
ruff check . && ruff format .
python -m dingz_ha_bridge --host <broker> --username … --password …   # bridge (default: run)
python -m dingz_ha_bridge run --dry-run --id-prefix dingztest --name-prefix "TEST "
python -m dingz_ha_bridge run --ui                                   # bridge + web UI (127.0.0.1:8099)
python -m dingz_ha_bridge scan [--host <broker> …] [--subnet 192.168.1.0/24] [--json]
python -m dingz_ha_bridge status <ip> [--wifi]                       # device status (password masked)
python -m dingz_ha_bridge set-mqtt <ip> --broker <broker-ip> --broker-user dingz   # prompts for password + confirmation
python -m dingz_ha_bridge ui                                         # web UI only
cp .env.example .env && docker compose up -d                         # standalone, pulls the ghcr image
docker build -t dingz-ha-bridge:local .                              # local image build (development)
mosquitto_sub -h <broker> -u … -P … -v -t 'dingz/#'                  # capture real messages
python scripts/demo_ui.py 8095 en                                   # web UI with fake devices (screenshots in docs/images/)
dns-sd -B _services._dns-sd._udp                                     # list mDNS services on the network (macOS)
```

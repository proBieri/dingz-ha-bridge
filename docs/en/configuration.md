# Configuration

Settings come from **CLI arguments** or **environment variables** (`DINGZ_*`). CLI arguments take precedence. In the Home Assistant add-on they are set from the add-on options and the Supervisor instead.

## Overview

| Option (CLI) | Environment variable | Default | Commands | Meaning |
|---|---|---|---|---|
| `--host` | `DINGZ_MQTT_HOST` | – (required for `run`) | run, scan, ui | MQTT broker (host or IP) |
| `--port` | `DINGZ_MQTT_PORT` | `1883`, with TLS `8883` | run, scan, ui | Broker port |
| `--username` | `DINGZ_MQTT_USERNAME` | – | run, scan, ui | Broker user |
| `--password` | `DINGZ_MQTT_PASSWORD` | – | run, scan, ui | Broker password |
| `--client-id` | `DINGZ_MQTT_CLIENT_ID` | `dingz-ha-bridge-<random>` | run, scan, ui | MQTT client ID; must be unique per connection |
| `--tls` | `DINGZ_MQTT_TLS=1` | off | run, scan, ui | Connect to the broker with TLS (see [Security](security.md#tls-to-the-broker)) |
| `--ca-file` | `DINGZ_MQTT_CA_FILE` | system CAs | run, scan, ui | CA certificate (PEM) of the broker; implies `--tls` |
| `--client-cert`, `--client-key` | `DINGZ_MQTT_CLIENT_CERT`, `DINGZ_MQTT_CLIENT_KEY` | – | run, scan, ui | Client certificate and key (PEM) for certificate login |
| `--tls-insecure` | `DINGZ_MQTT_TLS_INSECURE=1` | off | run, scan, ui | Do not verify the broker certificate – **testing only** |
| `--id-prefix` | `DINGZ_ID_PREFIX` | `dingz` | run | Prefix of unique_ids, device IDs and discovery topics |
| `--name-prefix` | `DINGZ_NAME_PREFIX` | empty | run | Prepended to every device name in HA, e.g. `TEST ` |
| `--dry-run` | – | off | run | Only log discovery configs, publish nothing |
| `--no-http` | – | off | run | Do not read names/output types from the dingz HTTP API |
| `--no-temperature-filter` | `DINGZ_TEMPERATURE_FILTER=0` | filter on | run | Publish the raw temperature incl. the floored status-dump values (see [Features](features.md#temperature)) |
| `--ui` | `DINGZ_UI=1` | off | run | Also start the web UI |
| `--ui-bind` | `DINGZ_UI_BIND` | `127.0.0.1` | run, ui | Web UI listen address |
| `--ui-port` | `DINGZ_UI_PORT` | `8099` | run, ui | Web UI port |
| `--ui-password` | `DINGZ_UI_PASSWORD` | – | run, ui | Password (HTTP basic, any user name). **Required** unless `--ui-bind` is local |
| `--no-update-check` | `DINGZ_UPDATE_CHECK=0` | check on | run, ui | Do not ask GitHub for new versions |
| `--log-level` | `DINGZ_LOG_LEVEL` | `INFO` | all | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--broker-password` | `DINGZ_BROKER_PASSWORD` | prompt | set-mqtt | Password written to the dingz |

Options of single commands (`scan --subnet`, `status --wifi`, `set-mqtt --broker` …) are described under [Command line](cli.md).

## Environment variables

Template: [`.env.example`](../../.env.example). Save it as `.env` for Docker Compose.

```dotenv
# Broker the dingz publish to
DINGZ_MQTT_HOST=192.168.1.10
DINGZ_MQTT_PORT=1883
DINGZ_MQTT_USERNAME=dingz-ha-bridge
DINGZ_MQTT_PASSWORD=…

# TLS (port then defaults to 8883)
# DINGZ_MQTT_TLS=1
# DINGZ_MQTT_CA_FILE=/certs/mqtt-ca.pem

# Separate set of devices for testing next to an existing integration
# DINGZ_ID_PREFIX=dingztest
# DINGZ_NAME_PREFIX=TEST 

# Web UI
DINGZ_UI=1
DINGZ_UI_BIND=0.0.0.0
DINGZ_UI_PORT=8099
DINGZ_UI_PASSWORD=…

# Raw temperature instead of the filtered one
# DINGZ_TEMPERATURE_FILTER=0

# Disable the GitHub update check
# DINGZ_UPDATE_CHECK=0

# DINGZ_LOG_LEVEL=DEBUG
```

Boolean variables: `DINGZ_UI`, `DINGZ_MQTT_TLS` and `DINGZ_MQTT_TLS_INSECURE` are on for `1`, `true` or `yes`; `DINGZ_UPDATE_CHECK` and `DINGZ_TEMPERATURE_FILTER` are off for `0`, `false` or `no`.

## Add-on options

| Option | Default | Meaning |
|---|---|---|
| `id_prefix` | `dingz` | like `--id-prefix`. Letters, digits, `_`, `-` only |
| `name_prefix` | empty | like `--name-prefix` |
| `http_enrichment` | `true` | read names and output types via the HTTP API (`false` equals `--no-http`) |
| `log_level` | `info` | `debug`, `info`, `warning`, `error` |
| `update_check` | `true` | GitHub update check |
| `temperature_filter` | `true` | temperature filter (`false` equals `--no-temperature-filter`) |
| `mqtt_ca_file` | empty | CA file for TLS with an own CA, e.g. `/ssl/mqtt-ca.pem` (the add-on can read `/ssl`) |
| `mqtt_tls_insecure` | `false` | do not verify the broker certificate – testing only |

Fixed in the add-on:

- MQTT credentials from the Supervisor (MQTT integration / Mosquitto add-on), including whether TLS is used.
- Web UI always on, port 8099, reachable through ingress only.
- Host network for mDNS.

## ID and name prefix

The ID prefix determines every identifier the bridge creates in Home Assistant:

| What | Pattern (prefix `dingz`) | Example |
|---|---|---|
| Discovery topic | `homeassistant/device/<prefix>_<id>/config` | `homeassistant/device/dingz_kitchen/config` |
| Device identifier | `<prefix>_<id>` | `dingz_kitchen` |
| unique_id | `<prefix>_<id>_<channel>[_<n>]` | `dingz_kitchen_light_0`, `dingz_kitchen_led` |

`<id>` is the MQTT ID of the dingz (a device setting, e.g. `kitchen`; the MAC address by default). Characters other than letters, digits, `_` and `-` are replaced by `_`.

A different prefix creates a **completely separate set of devices**. The bridge only ever cleans up topics with its own prefix – foreign discovery configs are never touched.

The name prefix only changes the display (device name) and thereby the generated entity IDs of new entities (`light.test_dingz_kitchen_…`).

## Fixed values

These values are set in the code and cannot be configured:

| Value | | Where |
|---|---|---|
| Debounce before publishing | 2 s after the last structural change | `bridge.py` |
| Wait for the HTTP read before the first discovery | up to 15 s | `bridge.py` |
| Retry after an HTTP error | every 5 min | `bridge.py` |
| Wait before removing stale configs | 10 s after connecting | `bridge.py` |
| PIR “off” without new message | 10 s (`off_delay`) | `discovery.py` |
| Temperature filter window | 1.5 s | `filters.py` |
| WLAN measurement cache | 5 min | `web.py` |
| Update check cache | 6 h | `web.py` |

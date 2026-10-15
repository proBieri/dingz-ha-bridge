# Documentation – dingz HA Bridge

**English** · [Deutsch](../de/README.md)

The dingz HA Bridge exposes dingz switches (iolo AG) that publish via MQTT to Home Assistant through **MQTT discovery**. It does not translate messages: the entities in Home Assistant point directly at the original dingz topics. It also finds dingz devices on the network, shows their state and sets up their MQTT connection.

| Chapter | Contents |
|---|---|
| [Installation](installation.md) | Requirements, preparing dingz and broker, add-on, Docker, Python |
| [Configuration](configuration.md) | All options: CLI arguments, environment variables, add-on options |
| [Features](features.md) | What appears in Home Assistant and how discovery works |
| [Web UI](web-ui.md) | Device list, status, WLAN, MQTT activity, setting the broker, update check |
| [Command line](cli.md) | `run`, `scan`, `status`, `set-mqtt`, `ui` with examples |
| [Security](security.md) | Credentials, broker ACL, securing the web UI |
| [Troubleshooting](troubleshooting.md) | Common questions and known limitations |

## In 60 seconds

```text
dingz ──MQTT──▶ broker ◀──MQTT── Home Assistant
                  ▲
                  │ reads dingz/#, writes homeassistant/device/…/config (retained)
          dingz HA Bridge ──HTTP (read only)──▶ dingz (names, output types)
```

1. The dingz publish their state on `dingz/<id>/…`.
2. The bridge detects devices and channels and creates **one retained discovery config** per dingz.
3. Home Assistant reads that config and from then on talks **directly** to the dingz topics.
4. The bridge does not need to run for operating the devices – only to detect new devices or channels. The only exception is the filtered temperature (see [Features](features.md#temperature)).

## Highlights

- Discovery without a translation layer; works on while the bridge is stopped (except the filtered temperature).
- Names and output types (light, relay, socket → switch) from the dingz HTTP API.
- Temperature filter against the floored status-dump values; energy in kWh for the energy dashboard.
- Web UI (English/German): device list, live MQTT activity, WLAN signal, set the MQTT broker, update check.
- MQTT over TLS, broker ACL examples, hardened web UI.
- Home Assistant add-on, Docker image `ghcr.io/probieri/dingz-ha-bridge` (amd64/arm64), or Python.

## Tested with

- dingz firmware **2.4.3**, fronts `dz1f-4b` and `dz1f-pir`
- Home Assistant with the MQTT integration (device discovery, 2024.11 or later)
- Mosquitto as broker

What has not been verified on real devices yet is listed under [Known limitations](troubleshooting.md#known-limitations).

# dingz HA Bridge

Exposes dingz switches that publish via MQTT to Home Assistant through MQTT discovery. The entities point directly at the original dingz topics; the add-on does not need to run for operating the devices, only for detecting new devices and channels.

Full documentation: https://github.com/proBieri/dingz-ha-bridge/tree/main/docs/en (Deutsch: https://github.com/proBieri/dingz-ha-bridge/tree/main/docs/de)

## Requirements

- An MQTT broker: either the Mosquitto add-on (used automatically) or an external broker set with the `mqtt_*` options.
- The dingz publish to this broker. Set this up per device in the **dingz** panel (sidebar). Enter the broker's **LAN address** (not `core-mosquitto`), ideally with a dedicated broker user for the dingz.

## Options

| Option | Meaning |
|---|---|
| `id_prefix` | Prefix of unique_ids/discovery topics. For a test run next to an existing integration e.g. `dingztest`. |
| `name_prefix` | Prepended to device names, e.g. `TEST `. |
| `http_enrichment` | Read names and output types (light, relay, socket, …) via the dingz HTTP API. |
| `log_level` | `debug`, `info`, `warning`, `error`. |
| `update_check` | Show in the panel whether a newer version is available on GitHub (checked every 6 h). |
| `temperature_filter` | Drop the floored whole-degree temperatures of the dingz status dump (avoids a saw-tooth in the history). |
| `mqtt_host` | Only for an external broker: hostname or IP. Empty = broker of the Mosquitto add-on. |
| `mqtt_port` | Broker port, 1883 without TLS, usually 8883 with TLS. |
| `mqtt_username`, `mqtt_password` | Broker credentials. |
| `mqtt_tls` | Use TLS for the external broker. |
| `mqtt_ca_file` | Only for TLS with an own CA: path to the CA file (PEM) below `/ssl`, e.g. `/ssl/mqtt-ca.pem`. |
| `mqtt_tls_insecure` | Testing only: do not verify the broker certificate. |

## Notes

- With the Mosquitto add-on, TLS follows the Supervisor; with an external broker it follows `mqtt_tls`. With an own CA, copy it to `/ssl` and set `mqtt_ca_file`.
- The panel is available in English and German (browser language).

- The panel (ingress) lists the dingz on the network (mDNS, MQTT), shows their status, WLAN signal and MQTT activity, and sets their MQTT broker.
- Use a dedicated broker user for the dingz with permissions on `dingz/#` only.
- Removing: delete the device in HA or uninstall the add-on and clear the retained topics `homeassistant/device/<id_prefix>_*/config`.

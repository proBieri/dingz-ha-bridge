# Changelog

## 0.1.1

- External MQTT broker: new options `mqtt_host`, `mqtt_port`, `mqtt_username`, `mqtt_password`, `mqtt_tls`. The Mosquitto add-on is no longer required (`mqtt:want` instead of `mqtt:need`).
- Clear error message instead of a traceback when no broker is configured.

## 0.1.0

First release.

- MQTT device discovery for dingz (FW 2.x): lights (dimmable/relay), switches for other output types, blinds (untested), front LED (RGB), buttons as events, PIR, temperature, illuminance, power and energy (kWh).
- Names and output types from the dingz HTTP API.
- Temperature filter against the floored whole-degree values of the dingz status dump.
- Web UI (English/German): device search (mDNS, MQTT, subnet), status, WLAN signal, live MQTT activity, set the MQTT broker on a dingz, update check.
- MQTT over TLS (own CA, client certificates).
- ID and name prefix for a test run next to an existing integration.

## 0.1.1

- Support an external MQTT broker via the `mqtt_host` / `mqtt_username` / `mqtt_password` / `mqtt_tls` options; the add-on no longer requires the Mosquitto add-on.
- Start cleanly (`services: mqtt:want`) and show a clear message instead of a traceback when no broker is configured.

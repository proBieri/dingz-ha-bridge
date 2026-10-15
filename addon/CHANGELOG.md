# Changelog

## 0.1.0

First release.

- MQTT device discovery for dingz (FW 2.x): lights (dimmable/relay), switches for other output types, blinds (untested), front LED (RGB), buttons as events, PIR, temperature, illuminance, power and energy (kWh).
- Names and output types from the dingz HTTP API.
- Temperature filter against the floored whole-degree values of the dingz status dump.
- Web UI (English/German): device search (mDNS, MQTT, subnet), status, WLAN signal, live MQTT activity, set the MQTT broker on a dingz, update check.
- MQTT over TLS (own CA, client certificates).
- ID and name prefix for a test run next to an existing integration.

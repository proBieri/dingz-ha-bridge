# Changelog

## 0.1.4

- Web UI: show the logo in the header and as the browser tab icon (favicon).
- Add-on icon and logo (shown in the add-on store and the sidebar).
- Supersedes 0.1.3, whose images were never published (a CI formatting check failed on the tag).

## 0.1.3

- Buttons: added MQTT **device triggers** per action (short / double / triple / quadruple / quintuple press, long press, long release), so automations can react to a specific action without a template condition. The single `event` entity per button stays. Verified the dingz multi-click payloads on a real device (`m1`–`m6`; the counter is open-ended, triggers stop at quintuple because HA has no type beyond it).
- Web UI: responsive layout for phones. The device table now stacks into one card per device on narrow screens instead of scrolling sideways; the detail list and the broker form stack into a single column.
- Web UI: removed the "← Add-ons" link. Home Assistant runs ingress add-ons in a sandboxed iframe that may not navigate the surrounding frame, so the link 404'd on desktop and hung in the mobile app. Use the HA header and sidebar (enable **Show in sidebar** for the **Dingz** panel) instead.

## 0.1.2

- Web UI: a "← Add-ons" link back to the add-on dashboard when opened through Home Assistant ingress.

## 0.1.1

- Support an external MQTT broker via the `mqtt_host` / `mqtt_port` / `mqtt_username` / `mqtt_password` / `mqtt_tls` options; the add-on no longer requires the Mosquitto add-on (`mqtt:want` instead of `mqtt:need`).
- Start cleanly and show a clear message instead of a traceback when no broker is configured.

## 0.1.0

First release.

- MQTT device discovery for dingz (FW 2.x): lights (dimmable/relay), switches for other output types, blinds (untested), front LED (RGB), buttons as events, PIR, temperature, illuminance, power and energy (kWh).
- Names and output types from the dingz HTTP API.
- Temperature filter against the floored whole-degree values of the dingz status dump.
- Web UI (English/German): device search (mDNS, MQTT, subnet), status, WLAN signal, live MQTT activity, set the MQTT broker on a dingz, update check.
- MQTT over TLS (own CA, client certificates).
- ID and name prefix for a test run next to an existing integration.

# Troubleshooting

## Nothing appears in Home Assistant

1. **Do the dingz publish?** `mosquitto_sub -h <broker> -u … -P … -v -t 'dingz/#'` must show messages. Otherwise set up MQTT on the dingz ([Installation](installation.md#step-2-enable-mqtt-on-the-dingz)).
2. **Is the bridge running?** The log shows `new dingz …` and `publishing discovery for …`. With `--dry-run` nothing is published on purpose.
3. **Are the configs on the broker?** `mosquitto_sub … -v -t 'homeassistant/device/+/config'` shows `homeassistant/device/dingz_<id>/config`.
4. **Does Home Assistant use the same broker**, with MQTT discovery enabled (prefix `homeassistant`)? Rejected configs are logged by HA (*Settings → System → Logs*, filter “mqtt”).

## Entities are called “Light 1”, all outputs are dimmable lights

The HTTP read from the dingz failed (log: `HTTP read of … failed`) or is disabled (`--no-http`). Check that the bridge reaches the dingz via HTTP (`dingz-ha-bridge status <ip>`). The bridge retries every 5 minutes.

## Duplicate entities

A second integration (e.g. hass-dingz) creates the same devices. Use a test prefix while running both, then remove the old integration – see [Migrating](installation.md#migrating-from-hass-dingz-or-another-integration).

## Removing devices

Discovery configs are retained. A device disappears from Home Assistant when its config topic is cleared:

```bash
mosquitto_pub -h <broker> -u … -P … -r -n -t 'homeassistant/device/dingztest_kitchen/config'
```

Alternatively choose *Delete* on the MQTT device in Home Assistant. As long as the bridge runs and the dingz still sends data, the bridge recreates devices with the active prefix. Configs with a **different** prefix (e.g. old test devices) are not cleaned up by the bridge.

## Temperature is “unavailable”

With the temperature filter (default) the temperature entity reads the bridge's own topic and becomes unavailable while the bridge is not running. Start the bridge, or disable the filter (`--no-temperature-filter`) to read the dingz directly – then with the floored status-dump values.

## “Last changed 54 minutes ago” on the temperature

Home Assistant shows when the **value** last changed, not when the last message arrived. The dingz sends the temperature at least every 5 minutes and on changes in 0.5 °C steps. With a stable room temperature the timestamp therefore stays put for a long time. Whether messages arrive is shown by the activity dot in the [web UI](web-ui.md#mqtt-activity).

## Energy counter drops to zero

The dingz does not persist its energy counter; after a reboot or power loss it restarts at 0. Home Assistant treats this as a meter reset (`total_increasing`), so the energy dashboard stays correct. See [Features](features.md#energy).

## The device search finds nothing

- **mDNS** only works if multicast reaches the bridge – host network, same VLAN or an mDNS reflector. Never under Docker Desktop (macOS/Windows). The log then says `mDNS found no dingz`.
- Workaround: enter a subnet (web UI or `scan --subnet 192.168.1.0/24`) or pass broker settings (search via MQTT).

## WLAN shows “not found” or “Error”

The dingz does not see its own SSID in the WLAN scan (very weak signal) or was not reachable. Repeat with **measure again**.

## Update check says “repository not public or not found”

The bridge queries `api.github.com` without authentication. That only works for a public repository with at least one release or tag (`vX.Y.Z`). Disable with `--no-update-check`.

## “CERTIFICATE_VERIFY_FAILED” with TLS

The broker certificate is not trusted. With an own CA pass it with `--ca-file` (`DINGZ_MQTT_CA_FILE`). If the message mentions the host name, the address used by the bridge is not in the certificate's Subject Alternative Name – use the address from the certificate. `--tls-insecure` helps to narrow it down, but is not meant for production.

## The broker connection keeps dropping

Two connections with the same **client ID** keep kicking each other out. Only set `--client-id` if it is unique (default: random).

## Setting MQTT fails

- “device is protected”: the device lock is active on the dingz – disable it in the dingz web interface.
- “device did not take the new MQTT settings”: the API write format is not documented for firmware 2.x. Use the dingz web interface and feel free to report the result as an issue.

## More detail in the log

`--log-level DEBUG` or `DINGZ_LOG_LEVEL=DEBUG` (add-on: `log_level: debug`).

## Known limitations

| Topic | Status |
|---|---|
| Blinds/motors | discovery implemented but **untested** for lack of a device. The templates accept both documented formats (`motion` and `state`). |
| Input (`state/input/0`) | untested |
| Multi-click `m1`–`m5` | not observed on real buttons |
| *Set MQTT* | write format not officially documented; success is verified by reading back |
| Web interface password on the dingz | login (`/login`) not supported yet |
| Thermostat | no `climate` entity yet |
| WLAN signal | approximation via WLAN scan (strongest AP of the own SSID) |
| Group commands (`dingz/command`) | not used |

# Security

## Broker credentials of the dingz

Treat the broker credentials stored on the dingz like any credentials on an IoT device:

- Use a **dedicated broker user** for the dingz, never the Home Assistant user or an admin account.
- Restrict this user to `dingz/#` with an ACL (example below).
- If possible, run the dingz in a separate network/VLAN and allow HTTP (port 80) to them only from Home Assistant and the bridge.

The bridge never logs or displays broker passwords: logs, command line and web UI show them as `***`.

## Broker users and ACL

Example for Mosquitto (`acl_file`; with the Mosquitto add-on under `/share/mosquitto/` with `customize.active: true`):

```text
# dingz: only their own topics
user dingz
topic readwrite dingz/#

# bridge (Docker/Python): read dingz, write its own discovery configs
user dingz-ha-bridge
topic read dingz/#
topic readwrite homeassistant/device/#
topic readwrite dingz-ha-bridge/#

# Home Assistant: operate the dingz and read discovery
user homeassistant
topic readwrite dingz/#
topic readwrite homeassistant/#
topic read dingz-ha-bridge/#
```

As an add-on, the bridge uses the credentials provided by the Supervisor.

## TLS to the broker

The bridge can connect to the broker with TLS (`--tls`, port 8883 by default):

| Broker certificate | Setting |
|---|---|
| from a public CA (e.g. Let's Encrypt) | `--tls` |
| from an own CA | `--ca-file /path/ca.pem` (implies `--tls`) |
| login by client certificate | additionally `--client-cert` and `--client-key` |
| just testing | `--tls-insecure` (no verification – never in production) |

The host name check is active: the broker address used by the bridge (IP or name) must appear in the certificate's Subject Alternative Name. With Docker, mount the CA file read-only (see `docker-compose.yml`, `volumes`). In the add-on, TLS follows the MQTT integration; an own CA goes to `/ssl` and is selected with the option `mqtt_ca_file`.

The connection **dingz → broker** is separate: the dingz support `mqtts://` with their own server certificate (`mqtt.server.crt` in `services_config`). The bridge does not set this yet (*set MQTT broker* writes `mqtt://`); configure it in the dingz web interface if needed.

## Web UI

| Measure | Effect |
|---|---|
| Default address `127.0.0.1` | reachable from the same machine only |
| Password required outside localhost | without `DINGZ_UI_PASSWORD` it refuses to start on `0.0.0.0` (HTTP basic, constant-time comparison) |
| Add-on: ingress only | requests not coming from the HA ingress proxy get 403 – even in the host network |
| CSRF protection | state-changing requests need the header `X-Dingz-UI: 1`, which foreign web pages cannot set |
| Known devices only | status, WLAN and *set MQTT* only for devices from the last search – the UI never queries arbitrary hosts |
| No passwords in the browser | broker passwords are masked, entered passwords are not stored |
| Security headers | `Content-Security-Policy: default-src 'self'`, `nosniff`, `no-referrer`, `no-store` |

HTTP basic auth sends the password unencrypted. For access beyond the LAN, put a reverse proxy with TLS in front.

## What the bridge writes

- **MQTT**: `homeassistant/device/<prefix>_*/config` and, with the temperature filter, `dingz-ha-bridge/<prefix>/…` (status and filtered temperatures), all retained. It never sends commands to the dingz. A broker ACL for the bridge therefore needs `topic readwrite dingz-ha-bridge/#` as well.
- **HTTP to the dingz**: read only – with one exception: *set MQTT broker* (`POST /api/v1/services_config`), only after explicit confirmation.
- **Internet**: only the update check (`api.github.com`, at most every 6 h, can be disabled).

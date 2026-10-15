# Command line

```text
dingz-ha-bridge [--log-level LEVEL] [--version] [COMMAND] [OPTIONS]
```

Without a command, `run` is executed. In Docker: `docker run … dingz-ha-bridge <command> …` or `docker compose run --rm dingz-ha-bridge <command> …`. In the source tree also `python -m dingz_ha_bridge …`.

All options with environment variables and defaults: [Configuration](configuration.md).

## run

Starts the bridge (discovery), optionally with the web UI.

```bash
dingz-ha-bridge run --host 192.168.1.10 --username dingz-ha-bridge --password …
dingz-ha-bridge run --ui                                    # with web UI (127.0.0.1:8099)
dingz-ha-bridge run --ui --ui-bind 0.0.0.0 --ui-password …  # web UI on the LAN
dingz-ha-bridge run --dry-run                               # only show what would be published
dingz-ha-bridge run --id-prefix dingztest --name-prefix "TEST "   # test mode
dingz-ha-bridge run --host 192.168.1.10 --tls --ca-file ca.pem …    # MQTT over TLS (port 8883)
```

| Option | Meaning |
|---|---|
| `--host`, `--port`, `--username`, `--password`, `--client-id` | MQTT broker |
| `--tls`, `--ca-file`, `--client-cert`, `--client-key`, `--tls-insecure` | MQTT over TLS (see [Security](security.md#tls-to-the-broker)) |
| `--id-prefix`, `--name-prefix` | prefixes for IDs and device names |
| `--dry-run` | log configs instead of publishing |
| `--no-http` | no HTTP enrichment |
| `--no-temperature-filter` | raw temperature instead of the filtered one |
| `--ui`, `--ui-bind`, `--ui-port`, `--ui-password`, `--no-update-check` | web UI |

The bridge reconnects automatically after a connection loss (1 s to 60 s back-off) and exits cleanly on `SIGTERM`/`Ctrl+C`.

## scan

Searches the network for dingz devices.

```bash
dingz-ha-bridge scan                                   # mDNS
dingz-ha-bridge scan --host 192.168.1.10 …             # also via MQTT
dingz-ha-bridge scan --no-mdns --subnet 192.168.1.0/24 # subnet only
dingz-ha-bridge scan --json
```

| Option | Meaning |
|---|---|
| `--no-mdns` | skip mDNS |
| `--subnet CIDR` | additionally sweep a network via HTTP (max /20, ~5 s for a /24) |
| `--host` … | additionally read retained `announce`/`online` from the broker (TLS options apply) |
| `--timeout S` | wait time for mDNS/MQTT (default 3 s) |
| `--json` | JSON output |

Example output:

```text
NAME           IP            MAC           MODEL     FW     MQTT ID  MQTT    FOUND VIA
Dingz Kitchen  192.168.1.51  246F28000001  dz1f-pir  2.4.3  kitchen  online  mdns,mqtt
```

## status

Shows the state of one dingz. Passwords are masked.

```bash
dingz-ha-bridge status 192.168.1.51
dingz-ha-bridge status 192.168.1.51 --wifi    # incl. WLAN signal (~2 s)
dingz-ha-bridge status 192.168.1.51 --json
```

Output: IP, MAC, MQTT ID, name, room, model, firmware, hardware, PIR, device lock, MQTT enabled, broker URI (masked), outputs, optionally WLAN.

## set-mqtt

Writes the broker setting to a dingz and verifies it afterwards.

```bash
dingz-ha-bridge set-mqtt 192.168.1.51 --broker 192.168.1.10 --broker-user dingz
dingz-ha-bridge set-mqtt 192.168.1.51 --uri 'mqtt://dingz:secret@192.168.1.10'
dingz-ha-bridge set-mqtt 192.168.1.51 --broker 192.168.1.10 --disable
```

| Option | Meaning |
|---|---|
| `--broker HOST` | broker address as seen from the dingz (alternatively `--uri`) |
| `--broker-port` | default 1883 |
| `--broker-user` | user for the dingz |
| `--broker-password` | password; otherwise `DINGZ_BROKER_PASSWORD` or a prompt |
| `--uri URI` | full URI, e.g. `mqtt://user:pass@host:1883` |
| `--disable` | disable MQTT on the dingz |
| `--yes`, `-y` | no confirmation prompt |

Flow: show the current state → confirm → write → read back. User and password are URL-encoded.

Exit codes: `0` applied, `1` aborted, `2` the dingz did not take the setting.

## ui

Starts only the web UI (no discovery). With broker settings (incl. TLS options), the search also finds devices via MQTT; the MQTT activity column needs `run --ui`.

```bash
dingz-ha-bridge ui
dingz-ha-bridge ui --host 192.168.1.10 --username … --password …
```

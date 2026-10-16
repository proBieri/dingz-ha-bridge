# Installation

## Requirements

- **dingz** with firmware 2.x (tested: 2.4.3), reachable from the bridge via HTTP (port 80).
- **MQTT broker**, e.g. the Home Assistant Mosquitto add-on.
- **Home Assistant** with the **MQTT integration** set up and discovery enabled (default, prefix `homeassistant`). Device discovery is supported from HA 2024.11.
- For the bridge: Home Assistant add-on **or** Docker **or** Python ≥ 3.12.

There are three ways to run it. All use the same code and the same Docker image.

| Mode | Suited for | Web UI |
|---|---|---|
| [Home Assistant add-on](#home-assistant-add-on) | Home Assistant OS / Supervised | in the HA sidebar (ingress) |
| [Docker](#docker-standalone) | your own Linux server, HA Container/Core | `http://<server>:8099` (with password) |
| [Python](#python) | development, testing, one-off setup | `http://127.0.0.1:8099` |

## Step 1: Create broker users

Two dedicated broker users are recommended:

| User | Used by | Permissions |
|---|---|---|
| `dingz` | the dingz devices | read and write `dingz/#` |
| `dingz-ha-bridge` | the bridge (Docker/Python only; the add-on gets credentials automatically) | read `dingz/#`, read and write `homeassistant/device/#` and `dingz-ha-bridge/#` |

With the Mosquitto add-on: *Settings → Add-ons → Mosquitto broker → Configuration → Logins*. Why a separate user for the dingz matters and what an ACL looks like: [Security](security.md#broker-users-and-acl).

## Step 2: Enable MQTT on the dingz

Each dingz has to publish to the broker. Three ways:

1. **Bridge web UI** (recommended): click the device → *Set MQTT broker* → broker IP, port, user, password → *Apply*. See [Web UI](web-ui.md#setting-the-mqtt-broker).
2. **Command line**: `dingz-ha-bridge set-mqtt 192.168.1.50 --broker 192.168.1.10 --broker-user dingz`. See [Command line](cli.md#set-mqtt).
3. **dingz app or the dingz web interface** (`http://<dingz-ip>`), settings → MQTT.

The broker address must be reachable **from the dingz**, i.e. a LAN IP – not `core-mosquitto` or `localhost`. Format stored on the device: `mqtt://user:password@192.168.1.10` (port optional, default 1883).

Check: `mosquitto_sub -h <broker> -u … -P … -v -t 'dingz/#'` should show messages such as `dingz/<id>/online true`.

## Home Assistant add-on

1. *Settings → Add-ons → Add-on Store → ⋮ → Repositories*, add `https://github.com/proBieri/dingz-ha-bridge`.
2. Install **dingz HA Bridge**.
3. Review the options (see [Configuration](configuration.md#add-on-options)) and start the add-on.
4. A **dingz** entry appears in the sidebar – devices, their status and *Set MQTT broker* are available there.

Notes:

- With the **Mosquitto add-on** as broker, the add-on gets the credentials automatically (`services: mqtt:want`). With an **external broker** (anything else, incl. a broker only configured in the MQTT integration), set `mqtt_host`, `mqtt_username`, `mqtt_password` in the add-on options — the add-on cannot read the MQTT integration's settings.
- The add-on runs in the **host network** so that mDNS discovery works. The web UI still only answers requests coming through HA ingress.
- If the MQTT integration uses TLS, the add-on does too. For an own CA, copy it to `/ssl` and set the option `mqtt_ca_file`.
- The add-on pulls prebuilt images from `ghcr.io/probieri/dingz-ha-bridge-{arch}` (amd64, aarch64). Repository and images must be public.

## Docker (standalone)

No clone and no build needed – the prebuilt image `ghcr.io/probieri/dingz-ha-bridge` (amd64 and arm64) is pulled from GitHub:

```bash
mkdir dingz-ha-bridge && cd dingz-ha-bridge
curl -LO https://raw.githubusercontent.com/proBieri/dingz-ha-bridge/main/docker-compose.yml
curl -L -o .env https://raw.githubusercontent.com/proBieri/dingz-ha-bridge/main/.env.example
nano .env                 # fill in broker credentials and UI password
docker compose up -d
docker compose logs -f
```

`.env` needs at least:

```dotenv
DINGZ_MQTT_HOST=192.168.1.10
DINGZ_MQTT_USERNAME=dingz-ha-bridge
DINGZ_MQTT_PASSWORD=…
DINGZ_UI=1
DINGZ_UI_BIND=0.0.0.0
DINGZ_UI_PASSWORD=…
```

All variables: [Configuration](configuration.md#environment-variables).

Notes:

- `docker-compose.yml` uses `network_mode: host` (for mDNS). The image runs as the unprivileged user `app` (UID 1000); mounted certificates and keys must be readable by it (e.g. `chmod 644 ca.pem`, `chown 1000 client.key`).
- **Docker Desktop (macOS/Windows)** does not pass multicast through: mDNS discovery finds nothing there. Discovery, MQTT search and subnet search still work.
- Without Compose: `docker run -d --name dingz-ha-bridge --restart unless-stopped --network host --env-file .env ghcr.io/probieri/dingz-ha-bridge:latest`.
- A fixed version instead of `latest`: e.g. `ghcr.io/probieri/dingz-ha-bridge:0.1.0`.
- Building from source (development): in a clone of the repository, replace `image:` by `build: .` in `docker-compose.yml` and run `docker compose up -d --build`.
- With the temperature filter (default) the bridge should run permanently (`restart: unless-stopped`).
- **TLS to the broker:** set `DINGZ_MQTT_TLS=1`; with an own CA put it into `./certs/`, uncomment the `volumes` entry in `docker-compose.yml` and set `DINGZ_MQTT_CA_FILE=/certs/<ca>.pem`. See [Security](security.md#tls-to-the-broker).

## Python

```bash
git clone https://github.com/proBieri/dingz-ha-bridge.git
cd dingz-ha-bridge
python3.12 -m venv .venv && source .venv/bin/activate
pip install ".[ui]"          # without [ui]: bridge only, no web UI / mDNS
dingz-ha-bridge run --host 192.168.1.10 --username dingz-ha-bridge --password … --ui
```

The `ui` extra installs `aiohttp` (web UI) and `zeroconf` (mDNS). The bridge alone only needs `aiomqtt`.

## Step 3: Verify

- In Home Assistant under *Settings → Devices & services → MQTT* there is one device per dingz with lights/switches, LED, buttons and sensors.
- In the web UI, the *In HA* column shows “yes” for every device, and the MQTT activity dot flashes regularly.

## Migrating from hass-dingz (or another integration)

If another integration for the dingz is already running, entities appear twice. Recommended approach:

1. Run the bridge with a **test prefix** first: `--id-prefix dingztest --name-prefix "TEST "` (add-on: options `id_prefix`, `name_prefix`). The devices appear as “TEST …” and can be compared.
2. When everything works: remove the test devices (see [Troubleshooting](troubleshooting.md#removing-devices)), reset the prefix to the default `dingz`, restart the bridge.
3. Switch automations to the new entities, remove the old integration.

**What hass-dingz offers that the bridge does not** (by design — the bridge is a pure MQTT-discovery layer):

| hass-dingz | bridge |
|---|---|
| Reboot button, PIR timer reset | not exposed |
| Temperature offset as a setting | not exposed |
| CPU / FET temperature sensors | not exposed (only on the HTTP `/sensors` endpoint, not on MQTT) |
| MQTT settings as entities | not exposed; set the broker from the bridge's panel instead |

Check whether you rely on any of these regularly before removing hass-dingz. Several could be added later (e.g. CPU/FET temperature as diagnostic sensors via periodic HTTP polling, or a reboot button) — open an issue if you need one.

## Updating

- **Add-on**: updates appear in the add-on store.
- **Docker**: `docker compose pull && docker compose up -d`.
- **Python**: `git pull && pip install ".[ui]"`.

The web UI shows in its header whether a newer version is available on GitHub.

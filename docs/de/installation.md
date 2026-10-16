# Installation

## Voraussetzungen

- **dingz** mit Firmware 2.x (getestet: 2.4.3), von der Bridge per HTTP erreichbar (Port 80).
- **MQTT-Broker**, z. B. das Mosquitto-Add-on von Home Assistant.
- **Home Assistant** mit eingerichteter **MQTT-Integration** und aktivierter Discovery (Standard, Präfix `homeassistant`). Device-Discovery wird ab HA 2024.11 unterstützt.
- Für die Bridge: Home-Assistant-Add-on **oder** Docker **oder** Python ≥ 3.12.

Es gibt drei Betriebsarten. Alle nutzen denselben Code und dasselbe Docker-Image.

| Betriebsart | Geeignet für | Weboberfläche |
|---|---|---|
| [Home-Assistant-Add-on](#home-assistant-add-on) | Home Assistant OS / Supervised | in der HA-Seitenleiste (Ingress) |
| [Docker](#docker-standalone) | eigener Linux-Server, HA Container/Core | `http://<server>:8099` (mit Passwort) |
| [Python](#python) | Entwicklung, Tests, einmalige Einrichtung | `http://127.0.0.1:8099` |

## Schritt 1: Broker-Benutzer anlegen

Empfohlen sind zwei eigene Broker-Benutzer:

| Benutzer | Wofür | Rechte |
|---|---|---|
| `dingz` | die dingz selbst | `dingz/#` lesen und schreiben |
| `dingz-ha-bridge` | die Bridge (nur Docker/Python; das Add-on erhält Zugangsdaten automatisch) | `dingz/#` lesen, `homeassistant/device/#` und `dingz-ha-bridge/#` lesen und schreiben |

Beim Mosquitto-Add-on: *Einstellungen → Add-ons → Mosquitto broker → Konfiguration → Logins*. Warum ein eigener Benutzer für die dingz wichtig ist und wie eine ACL aussieht: [Sicherheit](security.md#broker-benutzer-und-acl).

## Schritt 2: MQTT auf den dingz einschalten

Jeder dingz muss auf den Broker publizieren. Drei Wege:

1. **Weboberfläche der Bridge** (empfohlen): Gerät anklicken → *MQTT-Broker setzen* → Broker-IP, Port, Benutzer, Passwort → *Übernehmen*. Siehe [Weboberfläche](web-ui.md#mqtt-broker-setzen).
2. **Kommandozeile**: `dingz-ha-bridge set-mqtt 192.168.1.50 --broker 192.168.1.10 --broker-user dingz`. Siehe [Kommandozeile](cli.md#set-mqtt).
3. **dingz-App oder Webinterface des dingz** (`http://<ip-des-dingz>`), Einstellungen → MQTT.

Die Broker-Adresse muss **aus Sicht des dingz** erreichbar sein, also eine LAN-IP – nicht `core-mosquitto` oder `localhost`. Format auf dem Gerät: `mqtt://benutzer:passwort@192.168.1.10` (Port optional, Standard 1883).

Kontrolle: `mosquitto_sub -h <broker> -u … -P … -v -t 'dingz/#'` sollte Nachrichten wie `dingz/<id>/online true` zeigen.

## Home-Assistant-Add-on

1. *Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories* und `https://github.com/proBieri/dingz-ha-bridge` hinzufügen.
2. **dingz HA Bridge** installieren.
3. Optionen prüfen (siehe [Konfiguration](configuration.md#add-on-optionen)), Add-on starten.
4. In der Seitenleiste erscheint **dingz** – dort sind die Geräte, ihr Status und *MQTT-Broker setzen* verfügbar.

Hinweise:

- Mit dem **Mosquitto-Add-on** als Broker bekommt das Add-on die Zugangsdaten automatisch (`services: mqtt:want`). Bei einem **externen Broker** (alles andere, auch ein nur in der MQTT-Integration konfigurierter Broker) die Optionen `mqtt_host`, `mqtt_username`, `mqtt_password` setzen — das Add-on kann die Einstellungen der MQTT-Integration nicht auslesen.
- Das Add-on läuft im **Host-Netzwerk**, damit die Gerätesuche per mDNS funktioniert. Die Weboberfläche beantwortet trotzdem nur Anfragen, die über HA-Ingress kommen.
- Verwendet die MQTT-Integration TLS, tut es das Add-on auch. Eine eigene CA nach `/ssl` kopieren und die Option `mqtt_ca_file` setzen.
- Das Add-on lädt fertige Images von `ghcr.io/probieri/dingz-ha-bridge-{arch}` (amd64, aarch64). Repository und Images müssen dafür öffentlich sein.

## Docker (standalone)

Kein Klonen und kein Bauen nötig – das fertige Image `ghcr.io/probieri/dingz-ha-bridge` (amd64 und arm64) wird von GitHub bezogen:

```bash
mkdir dingz-ha-bridge && cd dingz-ha-bridge
curl -LO https://raw.githubusercontent.com/proBieri/dingz-ha-bridge/main/docker-compose.yml
curl -L -o .env https://raw.githubusercontent.com/proBieri/dingz-ha-bridge/main/.env.example
nano .env                 # Broker-Daten und UI-Passwort eintragen
docker compose up -d
docker compose logs -f
```

`.env` enthält mindestens:

```dotenv
DINGZ_MQTT_HOST=192.168.1.10
DINGZ_MQTT_USERNAME=dingz-ha-bridge
DINGZ_MQTT_PASSWORD=…
DINGZ_UI=1
DINGZ_UI_BIND=0.0.0.0
DINGZ_UI_PASSWORD=…
```

Alle Variablen: [Konfiguration](configuration.md#umgebungsvariablen).

Hinweise:

- `docker-compose.yml` nutzt `network_mode: host` (für mDNS). Das Image läuft als unprivilegierter Benutzer `app` (UID 1000); eingebundene Zertifikate und Schlüssel müssen für ihn lesbar sein (z. B. `chmod 644 ca.pem`, `chown 1000 client.key`).
- **Docker Desktop (macOS/Windows)** reicht Multicast nicht durch: Die mDNS-Suche findet dort nichts. Discovery, MQTT-Suche und Subnetz-Suche funktionieren trotzdem.
- Ohne Compose: `docker run -d --name dingz-ha-bridge --restart unless-stopped --network host --env-file .env ghcr.io/probieri/dingz-ha-bridge:latest`.
- Feste Version statt `latest`: z. B. `ghcr.io/probieri/dingz-ha-bridge:0.1.0`.
- Aus dem Quellcode bauen (Entwicklung): in einem Klon des Repositorys in `docker-compose.yml` `image:` durch `build: .` ersetzen und `docker compose up -d --build` ausführen.
- Mit aktivem Temperaturfilter (Standard) sollte die Bridge dauerhaft laufen (`restart: unless-stopped`).
- **TLS zum Broker:** `DINGZ_MQTT_TLS=1` setzen; bei eigener CA diese nach `./certs/` legen, den `volumes`-Eintrag in `docker-compose.yml` aktivieren und `DINGZ_MQTT_CA_FILE=/certs/<ca>.pem` setzen. Siehe [Sicherheit](security.md#tls-zum-broker).

## Python

```bash
git clone https://github.com/proBieri/dingz-ha-bridge.git
cd dingz-ha-bridge
python3.12 -m venv .venv && source .venv/bin/activate
pip install ".[ui]"          # ohne [ui]: nur Bridge, keine Weboberfläche/mDNS
dingz-ha-bridge run --host 192.168.1.10 --username dingz-ha-bridge --password … --ui
```

Das Extra `ui` installiert `aiohttp` (Weboberfläche) und `zeroconf` (mDNS). Die reine Bridge braucht nur `aiomqtt`.

## Schritt 3: Prüfen

- In Home Assistant unter *Einstellungen → Geräte & Dienste → MQTT* erscheint pro dingz ein Gerät mit Lichtern/Schaltern, LED, Tastern und Sensoren.
- In der Weboberfläche steht bei jedem Gerät in der Spalte *In HA* „ja“, und der MQTT-Aktivitätspunkt leuchtet regelmässig auf.

## Umstieg von hass-dingz (oder einer anderen Integration)

Läuft parallel bereits eine Integration für die dingz, entstehen doppelte Entities. Empfohlenes Vorgehen:

1. Bridge zuerst mit **Testpräfix** betreiben: `--id-prefix dingztest --name-prefix "TEST "` (Add-on: Optionen `id_prefix`, `name_prefix`). Die Geräte erscheinen als „TEST …“ und lassen sich vergleichen.
2. Wenn alles passt: Testgeräte entfernen (siehe [Fehlersuche](troubleshooting.md#geräte-wieder-entfernen)), Präfix auf den Standard `dingz` zurücksetzen, Bridge neu starten.
3. Automationen auf die neuen Entities umstellen, alte Integration entfernen.

**Was hass-dingz bietet und die Bridge nicht** (bewusst — die Bridge ist eine reine MQTT-Discovery-Schicht):

| hass-dingz | Bridge |
|---|---|
| Neustart-Button, PIR-Zeit zurücksetzen | nicht vorhanden |
| Temperatur-Offset als Einstellung | nicht vorhanden |
| CPU-/FET-Temperatur-Sensoren | nicht vorhanden (nur über HTTP `/sensors`, nicht über MQTT) |
| MQTT-Einstellungen als Entities | nicht vorhanden; Broker stattdessen im Bridge-Panel setzen |

Prüfe vor dem Entfernen von hass-dingz, ob du davon etwas regelmässig brauchst. Mehreres liesse sich später ergänzen (z. B. CPU-/FET-Temperatur als Diagnose-Sensoren per regelmässigem HTTP-Abruf oder ein Neustart-Button) — bei Bedarf ein Issue eröffnen.

## Aktualisieren

- **Add-on**: Updates erscheinen im Add-on Store.
- **Docker**: `docker compose pull && docker compose up -d`.
- **Python**: `git pull && pip install ".[ui]"`.

Die Weboberfläche zeigt in der Kopfzeile an, ob auf GitHub eine neuere Version verfügbar ist.

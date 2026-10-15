# Konfiguration

Einstellungen kommen aus **CLI-Argumenten** oder **Umgebungsvariablen** (`DINGZ_*`). CLI-Argumente haben Vorrang. Im Home-Assistant-Add-on werden sie stattdessen aus den Add-on-Optionen und vom Supervisor gesetzt.

## Übersicht

| Option (CLI) | Umgebungsvariable | Standard | Befehle | Bedeutung |
|---|---|---|---|---|
| `--host` | `DINGZ_MQTT_HOST` | – (Pflicht für `run`) | run, scan, ui | MQTT-Broker (Host oder IP) |
| `--port` | `DINGZ_MQTT_PORT` | `1883`, mit TLS `8883` | run, scan, ui | Broker-Port |
| `--username` | `DINGZ_MQTT_USERNAME` | – | run, scan, ui | Broker-Benutzer |
| `--password` | `DINGZ_MQTT_PASSWORD` | – | run, scan, ui | Broker-Passwort |
| `--client-id` | `DINGZ_MQTT_CLIENT_ID` | `dingz-ha-bridge-<zufall>` | run, scan, ui | MQTT-Client-ID; muss je Verbindung eindeutig sein |
| `--tls` | `DINGZ_MQTT_TLS=1` | aus | run, scan, ui | Verbindung zum Broker mit TLS (siehe [Sicherheit](security.md#tls-zum-broker)) |
| `--ca-file` | `DINGZ_MQTT_CA_FILE` | System-CAs | run, scan, ui | CA-Zertifikat (PEM) des Brokers; schaltet TLS ein |
| `--client-cert`, `--client-key` | `DINGZ_MQTT_CLIENT_CERT`, `DINGZ_MQTT_CLIENT_KEY` | – | run, scan, ui | Client-Zertifikat und Schlüssel (PEM) für die Anmeldung per Zertifikat |
| `--tls-insecure` | `DINGZ_MQTT_TLS_INSECURE=1` | aus | run, scan, ui | Zertifikat des Brokers nicht prüfen – **nur zum Testen** |
| `--id-prefix` | `DINGZ_ID_PREFIX` | `dingz` | run | Präfix für unique_ids, Geräte-IDs und Discovery-Topics |
| `--name-prefix` | `DINGZ_NAME_PREFIX` | leer | run | Wird jedem Gerätenamen in HA vorangestellt, z. B. `TEST ` |
| `--dry-run` | – | aus | run | Discovery-Configs nur loggen, nichts publizieren |
| `--no-http` | – | aus | run | Keine Namen/Ausgangstypen über die HTTP-API der dingz lesen |
| `--no-temperature-filter` | `DINGZ_TEMPERATURE_FILTER=0` | Filter an | run | Rohe Temperatur inkl. der abgerundeten Statusdump-Werte publizieren (siehe [Funktionen](features.md#temperatur)) |
| `--ui` | `DINGZ_UI=1` | aus | run | Zusätzlich die Weboberfläche starten |
| `--ui-bind` | `DINGZ_UI_BIND` | `127.0.0.1` | run, ui | Adresse der Weboberfläche |
| `--ui-port` | `DINGZ_UI_PORT` | `8099` | run, ui | Port der Weboberfläche |
| `--ui-password` | `DINGZ_UI_PASSWORD` | – | run, ui | Passwort (HTTP Basic, beliebiger Benutzername). **Pflicht**, wenn `--ui-bind` nicht lokal ist |
| `--no-update-check` | `DINGZ_UPDATE_CHECK=0` | Check an | run, ui | Nicht bei GitHub nach neuen Versionen fragen |
| `--log-level` | `DINGZ_LOG_LEVEL` | `INFO` | alle | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--broker-password` | `DINGZ_BROKER_PASSWORD` | Abfrage | set-mqtt | Passwort, das auf den dingz geschrieben wird |

Optionen einzelner Befehle (`scan --subnet`, `status --wifi`, `set-mqtt --broker` …) stehen unter [Kommandozeile](cli.md).

## Umgebungsvariablen

Vorlage: [`.env.example`](../../.env.example). Für Docker Compose als `.env` ablegen.

```dotenv
# Broker, auf den die dingz publizieren
DINGZ_MQTT_HOST=192.168.1.10
DINGZ_MQTT_PORT=1883
DINGZ_MQTT_USERNAME=dingz-ha-bridge
DINGZ_MQTT_PASSWORD=…

# TLS (Port dann standardmässig 8883)
# DINGZ_MQTT_TLS=1
# DINGZ_MQTT_CA_FILE=/certs/mqtt-ca.pem

# Separater Gerätesatz zum Testen neben einer bestehenden Integration
# DINGZ_ID_PREFIX=dingztest
# DINGZ_NAME_PREFIX=TEST 

# Weboberfläche
DINGZ_UI=1
DINGZ_UI_BIND=0.0.0.0
DINGZ_UI_PORT=8099
DINGZ_UI_PASSWORD=…

# Rohe statt gefilterte Temperatur
# DINGZ_TEMPERATURE_FILTER=0

# Update-Check bei GitHub abschalten
# DINGZ_UPDATE_CHECK=0

# DINGZ_LOG_LEVEL=DEBUG
```

Boolesche Variablen: `DINGZ_UI`, `DINGZ_MQTT_TLS` und `DINGZ_MQTT_TLS_INSECURE` gelten bei `1`, `true` oder `yes` als an; `DINGZ_UPDATE_CHECK` und `DINGZ_TEMPERATURE_FILTER` sind bei `0`, `false` oder `no` aus.

## Add-on-Optionen

| Option | Standard | Bedeutung |
|---|---|---|
| `id_prefix` | `dingz` | wie `--id-prefix`. Nur Buchstaben, Ziffern, `_`, `-` |
| `name_prefix` | leer | wie `--name-prefix` |
| `http_enrichment` | `true` | Namen und Ausgangstypen über die HTTP-API lesen (`false` entspricht `--no-http`) |
| `log_level` | `info` | `debug`, `info`, `warning`, `error` |
| `update_check` | `true` | Update-Check bei GitHub |
| `temperature_filter` | `true` | Temperaturfilter (`false` entspricht `--no-temperature-filter`) |
| `mqtt_ca_file` | leer | CA-Datei bei TLS mit eigener CA, z. B. `/ssl/mqtt-ca.pem` (das Add-on kann `/ssl` lesen) |
| `mqtt_tls_insecure` | `false` | Zertifikat des Brokers nicht prüfen – nur zum Testen |

Fest eingestellt im Add-on:

- MQTT-Zugangsdaten vom Supervisor (MQTT-Integration / Mosquitto-Add-on), inklusive der Angabe, ob TLS verwendet wird.
- Weboberfläche immer an, Port 8099, nur über Ingress erreichbar.
- Host-Netzwerk für mDNS.

## ID- und Namenspräfix

Das ID-Präfix bestimmt alle Kennungen, die die Bridge in Home Assistant anlegt:

| Was | Muster (Präfix `dingz`) | Beispiel |
|---|---|---|
| Discovery-Topic | `homeassistant/device/<präfix>_<id>/config` | `homeassistant/device/dingz_kueche/config` |
| Geräte-Identifier | `<präfix>_<id>` | `dingz_kueche` |
| unique_id | `<präfix>_<id>_<kanal>[_<n>]` | `dingz_kueche_light_0`, `dingz_kueche_led` |

`<id>` ist die MQTT-ID des dingz (Einstellung auf dem Gerät, z. B. `kueche`; ab Werk die MAC). Zeichen ausser Buchstaben, Ziffern, `_` und `-` werden durch `_` ersetzt.

Ein anderes Präfix ergibt einen **komplett getrennten Satz Geräte**. Die Bridge räumt immer nur Topics mit dem eigenen Präfix auf – fremde Discovery-Configs werden nie angefasst.

Das Namenspräfix ändert nur die Anzeige (Gerätename) und damit die automatisch erzeugten Entity-IDs neuer Entities (`light.test_dingz_kueche_…`).

## Feste Werte

Diese Werte sind im Code festgelegt und nicht konfigurierbar:

| Wert | | Wo |
|---|---|---|
| Debounce vor dem Publizieren | 2 s nach der letzten strukturellen Änderung | `bridge.py` |
| Wartezeit auf die HTTP-Abfrage vor der ersten Discovery | max. 15 s | `bridge.py` |
| Neuer Versuch nach HTTP-Fehler | alle 5 min | `bridge.py` |
| Wartezeit vor dem Aufräumen veralteter Configs | 10 s nach Verbindungsaufbau | `bridge.py` |
| PIR „aus“ ohne neue Meldung | 10 s (`off_delay`) | `discovery.py` |
| Zeitfenster des Temperaturfilters | 1.5 s | `filters.py` |
| Cache WLAN-Messung | 5 min | `web.py` |
| Cache Update-Check | 6 h | `web.py` |

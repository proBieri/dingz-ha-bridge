# Kommandozeile

```text
dingz-ha-bridge [--log-level LEVEL] [--version] [BEFEHL] [OPTIONEN]
```

Ohne Befehl wird `run` ausgeführt. In Docker: `docker run … dingz-ha-bridge <befehl> …` bzw. `docker compose run --rm dingz-ha-bridge <befehl> …`. Im Quellverzeichnis auch `python -m dingz_ha_bridge …`.

Alle Optionen mit Umgebungsvariablen und Standardwerten: [Konfiguration](configuration.md).

## run

Startet die Bridge (Discovery), optional mit Weboberfläche.

```bash
dingz-ha-bridge run --host 192.168.1.10 --username dingz-ha-bridge --password …
dingz-ha-bridge run --ui                                    # mit Weboberfläche (127.0.0.1:8099)
dingz-ha-bridge run --ui --ui-bind 0.0.0.0 --ui-password …  # Oberfläche im LAN
dingz-ha-bridge run --dry-run                               # nur anzeigen, was publiziert würde
dingz-ha-bridge run --id-prefix dingztest --name-prefix "TEST "   # Testbetrieb
dingz-ha-bridge run --host 192.168.1.10 --tls --ca-file ca.pem …    # MQTT über TLS (Port 8883)
```

| Option | Bedeutung |
|---|---|
| `--host`, `--port`, `--username`, `--password`, `--client-id` | MQTT-Broker |
| `--tls`, `--ca-file`, `--client-cert`, `--client-key`, `--tls-insecure` | MQTT über TLS (siehe [Sicherheit](security.md#tls-zum-broker)) |
| `--id-prefix`, `--name-prefix` | Präfixe für IDs und Gerätenamen |
| `--dry-run` | Configs loggen statt publizieren |
| `--no-http` | keine HTTP-Anreicherung |
| `--no-temperature-filter` | rohe Temperatur statt gefilterter |
| `--ui`, `--ui-bind`, `--ui-port`, `--ui-password`, `--no-update-check` | Weboberfläche |

Die Bridge verbindet sich bei Verbindungsabbruch automatisch neu (1 s bis 60 s Wartezeit) und beendet sich sauber bei `SIGTERM`/`Ctrl+C`.

## scan

Sucht dingz im Netz.

```bash
dingz-ha-bridge scan                                   # mDNS
dingz-ha-bridge scan --host 192.168.1.10 …             # zusätzlich über MQTT
dingz-ha-bridge scan --no-mdns --subnet 192.168.1.0/24 # nur Subnetz
dingz-ha-bridge scan --json
```

| Option | Bedeutung |
|---|---|
| `--no-mdns` | keine mDNS-Suche |
| `--subnet CIDR` | zusätzlich ein Netz per HTTP absuchen (max. /20, ~5 s für /24) |
| `--host` … | zusätzlich retained `announce`/`online` vom Broker lesen (TLS-Optionen gelten) |
| `--timeout S` | Wartezeit für mDNS/MQTT (Standard 3 s) |
| `--json` | Ausgabe als JSON |

Beispielausgabe:

```text
NAME          IP            MAC           MODEL     FW     MQTT ID  MQTT    FOUND VIA
Dingz Küche   192.168.1.51  246F28000001  dz1f-pir  2.4.3  kueche   online  mdns,mqtt
```

## status

Zeigt den Zustand eines dingz. Passwörter werden maskiert.

```bash
dingz-ha-bridge status 192.168.1.51
dingz-ha-bridge status 192.168.1.51 --wifi    # inkl. WLAN-Signal (~2 s)
dingz-ha-bridge status 192.168.1.51 --json
```

Ausgabe: IP, MAC, MQTT-ID, Name, Raum, Modell, Firmware, Hardware, PIR, Gerätesperre, MQTT aktiv, Broker-URI (maskiert), Ausgänge, optional WLAN.

## set-mqtt

Schreibt die Broker-Einstellung auf einen dingz und prüft sie anschliessend.

```bash
dingz-ha-bridge set-mqtt 192.168.1.51 --broker 192.168.1.10 --broker-user dingz
dingz-ha-bridge set-mqtt 192.168.1.51 --uri 'mqtt://dingz:geheim@192.168.1.10'
dingz-ha-bridge set-mqtt 192.168.1.51 --broker 192.168.1.10 --disable
```

| Option | Bedeutung |
|---|---|
| `--broker HOST` | Broker-Adresse aus Sicht des dingz (alternativ `--uri`) |
| `--broker-port` | Standard 1883 |
| `--broker-user` | Benutzer für die dingz |
| `--broker-password` | Passwort; sonst `DINGZ_BROKER_PASSWORD` oder Abfrage |
| `--uri URI` | komplette URI, z. B. `mqtt://user:pass@host:1883` |
| `--disable` | MQTT auf dem dingz ausschalten |
| `--yes`, `-y` | ohne Rückfrage |

Ablauf: aktuellen Zustand anzeigen → Bestätigung → schreiben → zurücklesen. Benutzer und Passwort werden URL-kodiert.

Exit-Codes: `0` übernommen, `1` abgebrochen, `2` der dingz hat die Einstellung nicht übernommen.

## ui

Startet nur die Weboberfläche (ohne Discovery). Mit Broker-Angaben (inkl. TLS-Optionen) findet die Suche zusätzlich Geräte über MQTT; die MQTT-Aktivität braucht `run --ui`.

```bash
dingz-ha-bridge ui
dingz-ha-bridge ui --host 192.168.1.10 --username … --password …
```

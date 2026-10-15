# Sicherheit

## Broker-Zugangsdaten der dingz

Die auf den dingz gespeicherten Broker-Zugangsdaten wie alle Zugangsdaten auf IoT-Geräten behandeln:

- Für die dingz einen **eigenen Broker-Benutzer** verwenden, nie den von Home Assistant oder einen Admin-Zugang.
- Diesem Benutzer per ACL nur `dingz/#` erlauben (Beispiel unten).
- Wenn möglich, die dingz in einem eigenen Netz/VLAN betreiben und HTTP (Port 80) zu ihnen nur von Home Assistant und der Bridge zulassen.

Die Bridge loggt und zeigt Broker-Passwörter nie an: In Logs, Kommandozeile und Weboberfläche erscheinen sie als `***`.

## Broker-Benutzer und ACL

Beispiel für Mosquitto (`acl_file`; beim Mosquitto-Add-on unter `/share/mosquitto/` mit `customize.active: true`):

```text
# dingz: nur ihre eigenen Topics
user dingz
topic readwrite dingz/#

# Bridge (Docker/Python): dingz lesen, eigene Discovery-Configs und Werte schreiben
user dingz-ha-bridge
topic read dingz/#
topic readwrite homeassistant/device/#
topic readwrite dingz-ha-bridge/#

# Home Assistant: dingz bedienen und Discovery lesen
user homeassistant
topic readwrite dingz/#
topic readwrite homeassistant/#
topic read dingz-ha-bridge/#
```

Im Add-on-Betrieb nutzt die Bridge den Zugang, den der Supervisor bereitstellt.

## TLS zum Broker

Die Bridge kann sich per TLS mit dem Broker verbinden (`--tls`, standardmässig Port 8883):

| Zertifikat des Brokers | Einstellung |
|---|---|
| von einer öffentlichen CA (z. B. Let's Encrypt) | `--tls` |
| von einer eigenen CA | `--ca-file /pfad/ca.pem` (schaltet TLS ein) |
| Anmeldung per Client-Zertifikat | zusätzlich `--client-cert` und `--client-key` |
| nur zum Testen | `--tls-insecure` (keine Prüfung – nie im Produktivbetrieb) |

Die Prüfung des Hostnamens ist aktiv: Die Broker-Adresse, die die Bridge verwendet (IP oder Name), muss im Subject Alternative Name des Zertifikats stehen. Bei Docker die CA-Datei schreibgeschützt einbinden (siehe `docker-compose.yml`, `volumes`). Im Add-on richtet sich TLS nach der MQTT-Integration; eine eigene CA gehört nach `/ssl` und wird mit der Option `mqtt_ca_file` ausgewählt.

Die Verbindung **dingz → Broker** ist davon getrennt: Die dingz unterstützen `mqtts://` mit eigenem Server-Zertifikat (`mqtt.server.crt` in `services_config`). Die Bridge setzt das noch nicht (*MQTT-Broker setzen* schreibt `mqtt://`); bei Bedarf im Webinterface des dingz einrichten.

## Weboberfläche

| Massnahme | Wirkung |
|---|---|
| Standard-Adresse `127.0.0.1` | nur vom selben Rechner erreichbar |
| Passwortpflicht ausserhalb von localhost | ohne `DINGZ_UI_PASSWORD` startet sie auf `0.0.0.0` nicht (HTTP Basic, Vergleich in konstanter Zeit) |
| Add-on: nur Ingress | Anfragen, die nicht vom HA-Ingress-Proxy kommen, werden mit 403 abgelehnt – auch im Host-Netzwerk |
| CSRF-Schutz | ändernde Anfragen brauchen den Header `X-Dingz-UI: 1`, den fremde Webseiten nicht setzen können |
| Nur bekannte Geräte | Status, WLAN und *MQTT setzen* nur für Geräte aus der letzten Suche – die Oberfläche fragt keine beliebigen Hosts ab |
| Keine Passwörter im Browser | Broker-Passwörter werden maskiert, eingegebene Passwörter nicht gespeichert |
| Security-Header | `Content-Security-Policy: default-src 'self'`, `nosniff`, `no-referrer`, `no-store` |

HTTP Basic überträgt das Passwort unverschlüsselt. Für den Zugriff über das LAN hinaus einen Reverse-Proxy mit TLS davorschalten.

## Was die Bridge schreibt

- **MQTT**: `homeassistant/device/<präfix>_*/config` und, mit Temperaturfilter, `dingz-ha-bridge/<präfix>/…` (Status und gefilterte Temperaturen), alles retained. Sie sendet keine Befehle an die dingz. Eine Broker-ACL für die Bridge braucht deshalb auch `topic readwrite dingz-ha-bridge/#`.
- **HTTP an die dingz**: nur lesend – mit einer Ausnahme: *MQTT-Broker setzen* (`POST /api/v1/services_config`), ausschliesslich nach ausdrücklicher Bestätigung.
- **Internet**: nur der Update-Check (`api.github.com`, höchstens alle 6 h, abschaltbar).

# Funktionen

## Was in Home Assistant erscheint

Pro dingz entsteht **ein Gerät** (Hersteller „iolo AG“, Modell = Front, z. B. `dz1f-pir`, mit Firmware-/Hardware-Version und Link auf das Webinterface des dingz). Darin:

| dingz | HA-Entity | Details |
|---|---|---|
| Ausgang, Typ `light`, dimmbar | `light` mit Helligkeit | Helligkeit 0–100 % ↔ HA 0–255, Übergangszeit → `fadetime` |
| Ausgang, Typ `light`, nicht dimmbar | `light` ein/aus | |
| Ausgang, anderer Typ (`power_socket`, Heizung, Lüfter, …) | `switch` | |
| Storen-Motor | `cover` mit Position; Lamellen als Tilt | 0 = zu, 100 = offen; *ungetestet* |
| Front-LED | `light` mit RGB-Farbe | wird immer angelegt |
| Taster 1–4 | `event` | Ereignisse `p`, `h`, `r`, `m1` … `m5` |
| externer Taster am Input | `event` „External button“ | erscheint nach dem ersten Ereignis |
| PIR (Bewegungsmelder) | `binary_sensor` motion | |
| externer PIR | `binary_sensor` motion | erscheint nach dem ersten Ereignis |
| Temperatur | `sensor` °C | von der Bridge gefiltert (siehe unten); Rohwert als ausgeblendetes Diagnose-Entity |
| Helligkeit | `sensor` lx | |
| Leistung je Ausgang | `sensor` W | |
| Energie je Ausgang | `sensor` kWh (`total_increasing`) | für das Energie-Dashboard geeignet |
| Input (Typ „state“) | `binary_sensor` | |

Namen: Gerätename aus dem dingz (`dingz_name`), Entity-Namen aus den Ausgangsnamen des dingz. Ohne HTTP-Anreicherung: „dingz <id>“, „Light 1“ …

Alle Entities sind **nicht verfügbar**, wenn der dingz offline ist (`dingz/<id>/online` = `false`, Last Will).

### Taster-Ereignisse

| Ereignis | Bedeutung |
|---|---|
| `p` | gedrückt (press) |
| `h` | gehalten (hold), wiederholt sich jede Sekunde |
| `r` | losgelassen nach Halten (release) |
| `m1` … `m5` | Mehrfachklick (`m2` = Doppelklick) |

In Automationen: Auslöser *Entität → Zustand* des Event-Entitys, Bedingung auf das Attribut `event_type`.

### Bewegungsmelder

Der dingz meldet `s` (jemand da), `ss` (immer noch jemand da, alle 3 s) und `n` (niemand). Kommt 10 s lang keine Meldung, geht der Sensor auf „aus“ – auch wenn ein `n` verloren geht.

### Temperatur

Der dingz sendet seine Raumtemperatur doppelt: bei jeder Änderung mit 0.5 °C Auflösung und alle 5 Minuten in einem Statusdump, der den Wert **auf ganze Grad abrundet** (21.5 → 21.0). Ungefiltert zeigt Home Assistant ein Sägezahnmuster (21.5 → 21.0 → 21.5 …) und eine um rund 0.25 °C zu tiefe Statistik.

Der **Temperaturfilter** (standardmässig an) behebt das:

- Ein Statusdump ist ein Burst aller Topics eines Geräts, der immer mit `…/last_alive` endet. Die Bridge hält jede Temperatur 1.5 s zurück; folgt ein `last_alive`, stammt der Wert aus dem Dump und wird verworfen, wenn er nur der abgerundete letzte gute Wert ist (eine grössere Abweichung wird als Notlösung übernommen).
- Beim Start liest die Bridge den exakten Wert per HTTP (`room_temperature`), weil der retained MQTT-Wert selbst ein abgerundeter Dump-Wert sein kann.
- Der gefilterte Wert wird retained auf `dingz-ha-bridge/<präfix>/<id>/temperature` publiziert; das Temperatur-Entity liest von dort.
- Dies ist das einzige Entity, das die laufende Bridge braucht. Stoppt die Bridge, setzt ihr Last Will `dingz-ha-bridge/<präfix>/status` auf `offline` und die Temperatur wird **nicht verfügbar**, statt falsche Werte zu zeigen.
- Der ungefilterte Wert bleibt als ausgeblendetes Diagnose-Entity „Temperature (raw)“ erhalten.

Abschalten mit `--no-temperature-filter`, `DINGZ_TEMPERATURE_FILTER=0` oder der Add-on-Option `temperature_filter: false`.

### Energie

Der dingz zählt Energie in Wattsekunden (Joule). Die Bridge lässt Home Assistant auf kWh umrechnen; die Sensoren eignen sich für das Energie-Dashboard.

Der Zähler auf dem dingz ist **nicht dauerhaft gespeichert**: Nach einem Neustart oder Stromunterbruch beginnt er wieder bei 0. Die Zustandsgrafik fällt dann auf fast null, weil die Sensoren aber `state_class: total_increasing` verwenden, wertet Home Assistant den Abfall als Zählerreset – Energie-Dashboard und Langzeitstatistik laufen korrekt weiter. Es fehlt nur der Verbrauch zwischen der letzten Meldung vor dem Neustart und dem Neustart selbst (höchstens einige Minuten).

## Wie die Discovery arbeitet

1. Die Bridge abonniert `dingz/#` und die eigenen Discovery-Topics `homeassistant/device/<präfix>_*/config`.
2. Aus den **retained** Nachrichten erkennt sie Geräte und Kanäle (`state/light/<n>`, `power/…`, `sensor/…`, `announce` …). Taster und PIR sind nicht retained und werden anhand des Modells vorab angelegt (`dz1f-*`: 4 Taster; Modelle mit `pir`: interner PIR).
3. Mit der IP aus `announce` liest sie per HTTP **einmal pro Gerät** Gerätename, Ausgangsnamen, Ausgangstypen und Dimmbarkeit (`system_config`, `output_config`).
4. 2 s nach der letzten Änderung publiziert sie pro Gerät **eine** Device-Discovery-Config – retained, QoS 1. Die erste Config wartet bis zu 15 s auf die HTTP-Abfrage, damit Entities nicht nachträglich Name oder Typ wechseln.
5. Ist die Config unverändert, wird nichts publiziert. Ein Neustart der Bridge erzeugt also keine unnötigen Updates.

Die State- und Command-Topics in der Config zeigen auf die **originalen** dingz-Topics. Die Umrechnung (z. B. `{"turn":"on"}` ↔ an/aus, Helligkeit, Energie) erledigt Home Assistant über Templates. Darum funktioniert die Bedienung auch, wenn die Bridge gestoppt ist.

### Änderungen und Aufräumen

| Situation | Verhalten |
|---|---|
| Neuer Kanal (z. B. Ausgang aktiviert) | Config wird ergänzt |
| Kanal verschwindet (retained Topic geleert) | Entity wird in HA entfernt |
| dingz offline | Entities „nicht verfügbar“; das Gerät bleibt |
| Discovery-Config mit eigenem Präfix, zu der kein dingz mehr Daten sendet | wird 10 s nach dem Start gelöscht |
| Fremde Discovery-Configs | werden nie angefasst |

### Ohne HTTP

Mit `--no-http` (Add-on: `http_enrichment: false`) oder wenn ein dingz per HTTP nicht erreichbar ist, gelten Standardwerte: alle Ausgänge als dimmbare Lichter mit generischen Namen. Nach einem HTTP-Fehler versucht die Bridge es alle 5 Minuten erneut und aktualisiert die Config danach.

## Gerätesuche

Die Gerätesuche (Weboberfläche, `scan`) kombiniert drei Quellen und führt Treffer über MAC, IP und MQTT-ID zusammen:

| Quelle | Findet | Voraussetzung |
|---|---|---|
| **mDNS** (`_http._tcp`, „DINGZ …“) | alle dingz im Netz, auch ohne MQTT | Multicast erreicht die Bridge (Host-Netzwerk, gleiches VLAN oder mDNS-Reflector) |
| **MQTT** (`dingz/+/announce`, `online`) | dingz, die bereits auf den Broker publizieren | Broker-Zugang |
| **Subnetz** (`--subnet`, Feld in der Weboberfläche) | alle dingz in einem Netz bis /20 | HTTP-Zugriff; Bestätigung über `GET /api/v1/device` |

## Weiteres

- **Weboberfläche** mit Geräteliste, Status, WLAN-Signal, MQTT-Aktivität, Broker-Einrichtung und Update-Check – siehe [Weboberfläche](web-ui.md).
- **Kommandozeile** für Suche, Status und Broker-Einrichtung – siehe [Kommandozeile](cli.md).
- **Testbetrieb** neben einer bestehenden Integration mit `--id-prefix` / `--name-prefix`, **Probelauf** mit `--dry-run`.
- **MQTT über TLS** mit eigener CA und Client-Zertifikaten – siehe [Sicherheit](security.md#tls-zum-broker).
- **Update-Check** gegen die GitHub-Releases, angezeigt in der Weboberfläche.

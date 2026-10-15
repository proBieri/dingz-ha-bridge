# Fehlersuche

## In Home Assistant erscheint nichts

1. **Publizieren die dingz?** `mosquitto_sub -h <broker> -u … -P … -v -t 'dingz/#'` muss Nachrichten zeigen. Sonst MQTT auf den dingz einrichten ([Installation](installation.md#schritt-2-mqtt-auf-den-dingz-einschalten)).
2. **Läuft die Bridge?** Im Log stehen `new dingz …` und `publishing discovery for …`. Mit `--dry-run` wird bewusst nichts publiziert.
3. **Liegen die Configs auf dem Broker?** `mosquitto_sub … -v -t 'homeassistant/device/+/config'` zeigt `homeassistant/device/dingz_<id>/config`.
4. **Nutzt Home Assistant denselben Broker** und ist die MQTT-Discovery aktiv (Präfix `homeassistant`)? Abgelehnte Configs stehen im HA-Log (*Einstellungen → System → Protokolle*, Filter „mqtt“).

## Entities heissen „Light 1“, alle Ausgänge sind dimmbare Lichter

Die HTTP-Abfrage an den dingz hat nicht geklappt (Log: `HTTP read of … failed`) oder ist abgeschaltet (`--no-http`). Prüfen, ob die Bridge den dingz per HTTP erreicht (`dingz-ha-bridge status <ip>`). Die Bridge versucht es alle 5 Minuten erneut.

## Doppelte Entities

Eine zweite Integration (z. B. hass-dingz) legt dieselben Geräte an. Für den Parallelbetrieb ein Testpräfix verwenden, danach die alte Integration entfernen – siehe [Umstieg](installation.md#umstieg-von-hass-dingz-oder-einer-anderen-integration).

## Geräte wieder entfernen

Discovery-Configs sind retained. Ein Gerät verschwindet aus Home Assistant, wenn sein Config-Topic geleert wird:

```bash
mosquitto_pub -h <broker> -u … -P … -r -n -t 'homeassistant/device/dingztest_kueche/config'
```

Alternativ in Home Assistant beim MQTT-Gerät *Löschen* wählen. Solange die Bridge läuft und der dingz noch Daten sendet, legt sie Geräte mit dem aktiven Präfix wieder an. Configs mit einem **anderen** Präfix (z. B. alte Testgeräte) räumt sie nicht selbst auf.

## Temperatur ist „nicht verfügbar“

Mit Temperaturfilter (Standard) liest das Temperatur-Entity das eigene Topic der Bridge und ist nicht verfügbar, solange die Bridge nicht läuft. Bridge starten oder den Filter abschalten (`--no-temperature-filter`), um den dingz direkt zu lesen – dann mit den abgerundeten Statusdump-Werten.

## „Zuletzt geändert vor 54 Minuten“ bei der Temperatur

Home Assistant zeigt, wann sich der **Wert** zuletzt geändert hat, nicht wann zuletzt eine Nachricht kam. Der dingz sendet die Temperatur mindestens alle 5 Minuten und bei Änderungen in 0.5-°C-Schritten. Bei stabiler Raumtemperatur bleibt der Zeitstempel daher lange stehen. Ob Nachrichten ankommen, zeigt der Aktivitätspunkt in der [Weboberfläche](web-ui.md#mqtt-aktivität).

## Energiezähler fällt auf null

Der dingz speichert seinen Energiezähler nicht dauerhaft; nach einem Neustart oder Stromunterbruch beginnt er wieder bei 0. Home Assistant wertet das als Zählerreset (`total_increasing`), das Energie-Dashboard bleibt korrekt. Siehe [Funktionen](features.md#energie).

## Gerätesuche findet nichts

- **mDNS** funktioniert nur, wenn Multicast die Bridge erreicht – Host-Netzwerk, gleiches VLAN oder ein mDNS-Reflector. Unter Docker Desktop (macOS/Windows) nie. Das Log meldet dann `mDNS found no dingz`.
- Ausweg: Subnetz angeben (Weboberfläche oder `scan --subnet 192.168.1.0/24`) oder Broker-Daten mitgeben (Suche über MQTT).

## WLAN zeigt „nicht gefunden“ oder „Fehler“

Der dingz sieht im WLAN-Scan seine eigene SSID nicht (sehr schwaches Signal) oder war nicht erreichbar. Mit **neu messen** wiederholen.

## Update-Check meldet „Repository nicht öffentlich oder nicht gefunden“

Die Bridge fragt `api.github.com` ohne Anmeldung. Das klappt nur bei einem öffentlichen Repository mit mindestens einem Release oder Tag (`vX.Y.Z`). Abschalten: `--no-update-check`.

## „CERTIFICATE_VERIFY_FAILED“ bei TLS

Das Zertifikat des Brokers ist nicht vertrauenswürdig. Bei einer eigenen CA diese mit `--ca-file` (`DINGZ_MQTT_CA_FILE`) angeben. Nennt die Meldung den Hostnamen, steht die Adresse, die die Bridge verwendet, nicht im Subject Alternative Name des Zertifikats – dann die Adresse aus dem Zertifikat verwenden. `--tls-insecure` hilft beim Eingrenzen, ist aber nicht für den Dauerbetrieb gedacht.

## Verbindung zum Broker bricht ständig ab

Zwei Verbindungen mit derselben **Client-ID** werfen sich gegenseitig hinaus. `--client-id` nur setzen, wenn sie eindeutig ist (Standard: zufällig).

## MQTT setzen schlägt fehl

- „device is protected“: Auf dem dingz ist die Gerätesperre aktiv – im Webinterface des dingz aufheben.
- „Der dingz hat die neuen MQTT-Einstellungen nicht übernommen“: Das Schreibformat der API ist für Firmware 2.x nicht dokumentiert. Einstellung im Webinterface des dingz vornehmen und das Ergebnis gern als Issue melden.

## Mehr Details im Log

`--log-level DEBUG` bzw. `DINGZ_LOG_LEVEL=DEBUG` (Add-on: `log_level: debug`).

## Bekannte Einschränkungen

| Thema | Stand |
|---|---|
| Storen/Motoren | Discovery vorhanden, mangels Gerät **nicht getestet**. Die Templates akzeptieren beide dokumentierten Formate (`motion` und `state`). |
| Input (`state/input/0`) | nicht getestet |
| Mehrfachklick `m1`–`m5` | nicht an echten Tastern beobachtet |
| *MQTT setzen* | Schreibformat nicht offiziell dokumentiert, Erfolg wird zurückgelesen |
| Webinterface-Passwort auf dem dingz | Anmeldung (`/login`) noch nicht unterstützt |
| Thermostat | noch keine `climate`-Entity |
| WLAN-Signal | Näherung über WLAN-Scan (stärkster AP der eigenen SSID) |
| Gruppenbefehle (`dingz/command`) | nicht genutzt |

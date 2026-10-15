# Dokumentation – dingz HA Bridge

[English](../en/README.md) · **Deutsch**

Die dingz HA Bridge macht dingz-Schalter (iolo AG), die per MQTT publizieren, über **MQTT Discovery** in Home Assistant bekannt. Sie übersetzt keine Nachrichten: Die Entities in Home Assistant zeigen direkt auf die originalen dingz-Topics. Zusätzlich findet sie dingz im Netz, zeigt ihren Zustand an und richtet ihre MQTT-Verbindung ein.

| Kapitel | Inhalt |
|---|---|
| [Installation](installation.md) | Voraussetzungen, dingz und Broker vorbereiten, Add-on, Docker, Python |
| [Konfiguration](configuration.md) | Alle Optionen: CLI-Argumente, Umgebungsvariablen, Add-on-Optionen |
| [Funktionen](features.md) | Was in Home Assistant erscheint und wie die Discovery arbeitet |
| [Weboberfläche](web-ui.md) | Geräteliste, Status, WLAN, MQTT-Aktivität, Broker setzen, Update-Check |
| [Kommandozeile](cli.md) | `run`, `scan`, `status`, `set-mqtt`, `ui` mit Beispielen |
| [Sicherheit](security.md) | Zugangsdaten, Broker-ACL, Absicherung der Weboberfläche |
| [Fehlersuche](troubleshooting.md) | Häufige Fragen und bekannte Einschränkungen |

## In 60 Sekunden

```text
dingz ──MQTT──▶ Broker ◀──MQTT── Home Assistant
                  ▲
                  │ liest dingz/#, schreibt homeassistant/device/…/config (retained)
          dingz HA Bridge ──HTTP (nur lesend)──▶ dingz (Namen, Ausgangstypen)
```

1. Die dingz publizieren ihren Zustand auf `dingz/<id>/…`.
2. Die Bridge erkennt Geräte und Kanäle und legt pro dingz **eine retained Discovery-Config** an.
3. Home Assistant liest diese Config und spricht danach **direkt** mit den dingz-Topics.
4. Die Bridge muss für die Bedienung nicht laufen – nur, um neue Geräte oder Kanäle zu erkennen. Einzige Ausnahme ist die gefilterte Temperatur (siehe [Funktionen](features.md#temperatur)).

## Das Wichtigste

- Discovery ohne Übersetzungsschicht; funktioniert auch bei gestoppter Bridge weiter (ausser der gefilterten Temperatur).
- Namen und Ausgangstypen (Licht, Relais, Steckdose → Schalter) aus der HTTP-API der dingz.
- Temperaturfilter gegen die abgerundeten Statusdump-Werte; Energie in kWh für das Energie-Dashboard.
- Weboberfläche (Deutsch/Englisch): Geräteliste, Live-MQTT-Aktivität, WLAN-Signal, MQTT-Broker setzen, Update-Check.
- MQTT über TLS, Beispiele für Broker-ACLs, abgesicherte Weboberfläche.
- Home-Assistant-Add-on, Docker-Image `ghcr.io/probieri/dingz-ha-bridge` (amd64/arm64) oder Python.

## Getestet mit

- dingz Firmware **2.4.3**, Fronten `dz1f-4b` und `dz1f-pir`
- Home Assistant mit MQTT-Integration (Device-Discovery, ab 2024.11)
- Mosquitto als Broker

Was noch nicht an echten Geräten geprüft ist, steht unter [Bekannte Einschränkungen](troubleshooting.md#bekannte-einschränkungen).

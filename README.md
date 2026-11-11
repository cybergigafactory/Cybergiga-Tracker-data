# Cybergiga Tracker Data

Öffentliche Zählung der in Texas zugelassenen Tesla Cybercabs, gelesen aus der öffentlichen Liste automatisierter Fahrzeuge des Texas Department of Motor Vehicles (TxMCCS TruckStop).

Die Datei `tracker.json` ist zum Einlesen durch das Widget auf cybergigafactory.grok.me gedacht. `data/vins.json` enthält die aktuelle VIN-Liste mit dem Zeitpunkt, zu dem dieses Archiv die VIN zum ersten Mal gesehen hat. Es werden keine Personendaten, keine Adressen und keine Kennzeichen gespeichert. Die amtliche Liste enthält davon auch keine.

## Was die Zahlen bedeuten

`registered_total` ist die Zahl der VINs mit Präfix `5YJAJEEU` (Cybercab). Das ist eine Zulassungszahl für Texas, keine Zahl der Autos auf der Straße und keine Aufteilung nach Stadt.

`delta_1d` und `delta_1w` sind die Änderung gegenüber dem Tageswert von vor einem Tag bzw. vor sieben Tagen (UTC). Solange das Archiv noch nicht so alt ist, stehen dort `null`.

`last_updated` ist der Zeitpunkt des letzten geschriebenen Stands in UTC.

## Aktualisierung

Ein GitHub-Actions-Workflow liest die API stündlich. In `tracker.json` und `data/vins.json` wird nur geschrieben und committed, wenn sich die Zahlen oder die VIN-Liste geändert haben, oder wenn `last_updated` älter als 12 Stunden ist. Bei einem API-Fehler bleibt der letzte gute Stand stehen, der Lauf wird als fehlgeschlagen markiert und setzt die Werte nicht auf 0.

Lokal:

```
python3 scripts/update_tracker.py
```

## Quelle

- Oberfläche: https://txmccs.txdmv.gov/truckstop
- API der Firma Tesla Robotaxi, LLC, öffentlich ohne Konto

Dieses Projekt ist nicht von Tesla und nicht vom TxDMV herausgegeben.

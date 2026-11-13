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


## Staaten-Datei für die Seite /tracker

`states.json` fasst die Zeitreihe je Bundesstaat zusammen. Texas wird stündlich aus der TxDMV-Liste fortgeschrieben. Historische Texas-Punkte bis 10.11.2026 liegen fest in `data/tx-history-bootstrap.json` (robotaxistats, CC BY 4.0, plus ein Wayback-API-Snapshot) und werden nicht überschrieben.

Andere Staaten stehen in `data/states-manuell.json` und werden nur von Hand geändert. Ohne belegte Fahrzeugzahl bleibt `current` leer und es gibt keine Linie im Chart. Bitte keine Schätzungen ohne Quelle eintragen.

Die Seite darf `states.json` und `tracker.json` per raw.githubusercontent.com (Ausweichadresse jsDelivr) lesen. Bei Nutzung der historischen Texas-Werte muss robotaxistats mit Link und der Lizenz CC BY 4.0 genannt werden.

## TAD/FSD-Datei für die Seite /tad

`tad-fsd.json` beschreibt den belegten Stand von TAD/FSD Supervised je Land. Statuswerte sind `approved`, `announced` oder `none`. Es stehen nur Tesla-Primärquellen und amtliche Stellen darin. X, Blogs und Tracker-Seiten sind keine Belege. Ein fehlendes oder leeres File darf auf der Seite nicht als Freigabe gelesen werden.

Ausnahme seit 13.11.2026: Startdaten für USA, Kanada, Mexiko, Puerto Rico, China, Australien, Neuseeland und Südkorea sowie der Status von China stammen von Rappy (selbst geprüft, Feld `date_source`: "Rappy, geprüft 13.11.2026"), nicht aus einer Tesla- oder Behördenseite. Felder: `date` (YYYY-MM-DD oder YYYY-MM), `date_precision` (`day` oder `month`), optional `note_de`/`note_en` (kurzer Zusatz wie "eingeschränkt").

Die Datei wird von Hand gepflegt, nicht vom stündlichen Texas-Workflow. Die Seite darf sie per raw.githubusercontent.com lesen, Ausweichadresse jsDelivr, analog zu `tracker.json` und `states.json`.

## Tagesänderungen (+1D, +1W), Stand 13.11.2026

- Stichtag ist der UTC-Kalendertag. Verglichen wird mit dem Stand am Ende des Vortags bzw. vor sieben Tagen, und zwar mit dem letzten bekannten Wert an oder vor diesem Tag (Bestandszahl, fehlende Tage gelten als unverändert). Ohne Wert vor dem Stichtag bleibt das Feld `null`.
- `delta_1d` / `delta_1w`: Cybercabs (VIN-Präfix `5YJAJEEU`), nur aus dem eigenen Archiv ab 11.11.2026. `delta_1w` ist deshalb erst ab 18.11.2026 belegt.
- `delta_total_1d` / `delta_total_1w`: alle Tesla-Robotaxis (Model Y und Cybercab). Gerechnet aus derselben Texas-Reihe wie die Linie in `states.json` (Bootstrap plus eigene Tageswerte). Diese Werte passen zum Chart.
- `delta_model_y_1d` / `delta_model_y_1w`: Model Y (Präfix `7SAYGDEE`), eigenes Archiv ab 11.11.2026.
- `history` enthält je Tag `registered_total` (Cybercab), `tesla_total` und `model_y`. Die Tage 11.11. und 12.11.2026 wurden aus den eigenen Commits fdcf1fa und 25e1958 nachgetragen.
- Bis 13.11.2026 hing `states.json` nur den heutigen Live-Punkt an, eigene Vortage fielen wieder aus der Linie. Jetzt bleiben alle eigenen Tageswerte stehen.

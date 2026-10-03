# Backend (Python / FastAPI)

```bash
cp .env.example .env   # einmalig, dann DATABASE_URL eintragen
uv run uvicorn app.main:app --reload
```

- http://localhost:8000/health – App läuft
- http://localhost:8000/health/db – Datenbankverbindung funktioniert
- http://localhost:8000/docs – automatische API-Doku (zum Ausprobieren der Endpunkte)

## Beispieldaten zum Ausprobieren

```bash
uv run python -m app.demo_daten anlegen     # Stammdaten, Demo-Kunden, Instrumente, offene Aufträge, Historie
uv run python -m app.demo_daten anzeigen    # IDs und fertige Beispiel-Anfragen erneut anzeigen
uv run python -m app.demo_daten entfernen   # Demo-Kunden samt Instrumenten und Aufträgen entfernen
```

Demo-Daten erkennt man an Kundennummern und Auftragsnummern mit `DEMO-`. Beim Entfernen
bleiben die Stammdaten (Instrumentenklassen, Reparaturarten, Vorgabewerte) erhalten.
Mit ihnen kann man auch echt arbeiten.

## Termine nachrechnen

```bash
uv run python -m app.termine_nachrechnen --probelauf   # nur anzeigen
uv run python -m app.termine_nachrechnen               # offene Aufträge ohne Termin
uv run python -m app.termine_nachrechnen --alle        # alle offenen Aufträge neu (z. B. nach neuen Abwesenheiten)
```

Aufträge ohne geschätzte Arbeitsstunden werden übersprungen (ohne Stunden kein Termin).

## Tests

```bash
uv run pytest
```

Die Tests laufen gegen die Datenbank aus der `.env`, aber jeder Test in einer
Transaktion, die danach zurückgerollt wird. Es bleiben keine Testdaten zurück.

## Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/auth/login` | Anmelden (E-Mail als `username` + Passwort) → Token |
| GET | `/auth/ich` | Wer bin ich? (prüft die Anmeldung) |
| GET | `/admin/vorgabewerte` | Vorgabewerte-Liste nach 9.11 (`suche`, Filter `reparaturart_id`, `instrumentenklasse_id`, `status`; `sortierung`, `seite`) |
| GET | `/admin/vorgabewerte/{id}` | Einen Vorgabewert abrufen |
| POST | `/admin/vorgabewerte` | Vorgabewert anlegen (409, falls Kombination schon existiert) |
| PATCH | `/admin/vorgabewerte/{id}` | Vorgabewert ändern (nur mitgeschickte Felder) |
| POST | `/admin/vorgabewerte/{id}/archivieren`, `/…/reaktivieren` | Vorgabewert zurücknehmen/zurückholen (Schätzung ignoriert archivierte) |
| GET | `/kunden?suche=…&status=…&sortierung=…&seite=…`, `/kunden/{id}` | Kundenliste nach 9.11 (Suche auch nach externer Kundennummer; `status` archiviert/alle nur Leitung), Kunde mit Instrumenten |
| POST, PATCH | `/kunden`, `/kunden/{id}` | Kunde anlegen/bearbeiten (alle Angemeldeten; Kundennummer wird vergeben; `externe_kundennummer` optional, eindeutig falls gesetzt) |
| POST | `/kunden/{id}/archivieren`, `/…/reaktivieren` | Archivieren/Zurückholen (Werkstattleitung/Admin; nicht bei offenen Aufträgen) |
| GET | `/instrumente?kunde_id=…&archivierte=…`, `/instrumente/{id}` | Instrumente auflisten/abrufen |
| POST, PATCH | `/instrumente`, `/instrumente/{id}` | Instrument anlegen/bearbeiten (alle Angemeldeten) |
| POST | `/instrumente/{id}/archivieren`, `/…/reaktivieren` | Archivieren/Zurückholen (Werkstattleitung/Admin) |
| GET | `/instrumentenklassen`, `/reparaturarten`, `/auftragsstatus`, `/mitarbeiter` | Auswahllisten (nur lesen, nur aktive, für alle Angemeldeten) |
| GET, POST, PATCH | `/admin/instrumentenklassen`, `/admin/reparaturarten` (+ `/{id}`) | Stammdaten pflegen (nur Admin); Listen nach 9.11 mit `suche`, `status` (aktiv/archiviert/alle), `sortierung`, `seite` |
| POST | `/admin/…/{id}/archivieren`, `/admin/…/{id}/reaktivieren` | Stammdaten archivieren/zurückholen (nur Admin) |
| GET | `/admin/mitarbeiter`, `/admin/mitarbeiter/{id}` | Mitarbeiter mit Rolle, Status, aktuellen Wochenstunden, offenen Aufträgen (nur Admin) |
| POST | `/admin/mitarbeiter/{id}/deaktivieren`, `/…/aktivieren` | Deaktivieren/Reaktivieren (nicht sich selbst, nicht den letzten Admin, nicht bei offenen Aufträgen) |
| PATCH | `/admin/mitarbeiter/{id}/systemrolle` | Systemrolle ändern (sich selbst nicht herabstufen, letzter Admin bleibt) |
| GET, POST | `/admin/mitarbeiter/{id}/wochenstunden` | Verlauf ansehen / neuen Wert ab Datum festlegen (schließt den bisherigen ab) |
| GET | `/dashboard` | Werkstattleiter-Startseite (9.5, nur Werkstattleitung/Admin): Kennzahlen offen, überfällig, hohe Priorität, pausiert – jeweils passend zum Filter der Auftragsliste; die 5 nächsten fälligen Aufträge; Auslastung je aktivem Mitarbeiter in der laufenden Woche (Formel 8.2); heute geltende Abwesenheiten |
| GET | `/auswertungen?jahr=…` | Jahresstatistik (9.14, nur Werkstattleitung/Admin) über die im Jahr abgeschlossenen Aufträge; bisher Menge (Anzahl, pro Monat, Verteilung nach Reparaturart und Instrumentenklasse, Top 5 + Sonstige) und Zeit (Ø Bearbeitungsdauer in Kalendertagen gesamt und pro Monat, Ø reine Arbeitszeit, Pünktlichkeitsquote gegenüber der ersten automatischen Terminschätzung) |
| GET | `/auftraege` | Auftragsliste nach 9.11 (Standard: offene, Priorität hoch zuerst, dann älteste; `suche`; Filter `status` = offen/abgeschlossen/alle/Status-Schlüssel, `mitarbeiter` = ID/keiner, `instrumentenklasse_id`, `prioritaet`, `termin=ueberfaellig`, `pausiert=true`, `kunde_id`) |
| GET | `/auftraege/{id}` | Auftrag mit Statusverlauf und allen Schätzungen |
| POST | `/auftraege` | Auftrag anlegen – schätzt Stunden, Kosten und Fertigstellungstermin automatisch und protokolliert die Schätzung |
| PATCH | `/auftraege/{id}` | Zuweisung/Priorität ändern (Werkstattleitung/Admin) – berechnet den Termin neu |
| POST | `/auftraege/{id}/status` | Statuswechsel (neuer Eintrag im Statusverlauf; bei „Fertig“ Pflicht: `arbeitszeit_minuten`) |
| POST | `/auftraege/{id}/schaetzung-korrektur` | Geschätzte Stunden/Kosten manuell korrigieren (Pflicht: `grund`) |
| POST | `/auftraege/{id}/termin-korrektur` | Fertigstellungstermin manuell festlegen (nur Werkstattleitung/Admin, Begründung Pflicht; eigener Eintrag im Schätzprotokoll; die nächste automatische Neuberechnung überschreibt ihn wieder) |
| GET | `/abwesenheiten?suche=…&mitarbeiter=…&typ=…&zeitraum=…&status=…` | Abwesenheiten-Liste nach 9.11 (nur Werkstattleitung/Admin; Standard: laufende und künftige, nicht stornierte; `mitarbeiter` = ID oder `werkstatt`) |
| POST, PATCH | `/abwesenheiten`, `/abwesenheiten/{id}` | Abwesenheit eintragen/bearbeiten (Urlaub, Krankheit, Schulung, reduzierte Stunden je Mitarbeiter; Feiertag, Betriebsschließung für die ganze Werkstatt; optionale Notiz; kein Doppeleintrag gleichen Typs im selben Zeitraum) |
| POST | `/abwesenheiten/{id}/stornieren`, `/…/wiederherstellen` | Stornieren statt Löschen (zählt dann nicht mehr für die Terminschätzung) und Zurückholen |
| GET | `/abwesenheiten/raster?von=…&tage=7&stornierte=…` | Daten für das Abwesenheits-Raster (9.13): aktive Mitarbeiter mit normalen Tagesstunden und alle Abwesenheiten im Ausschnitt |
| GET, PUT | `/admin/einstellungen`, `/admin/einstellungen/{schluessel}` | Werkstatt-Einstellungen lesen/setzen (nur Admin; bisher `bundesland`, Auswahl aus den 16 Bundesländern) |
| GET, POST | `/admin/feiertage` | Stand der erzeugten Jahre / „Feiertage für Jahr X erzeugen“ (nur Admin; Bundesland aus den Einstellungen; legt nur Fehlendes an, überschreibt nichts). Laufendes und kommendes Jahr entstehen automatisch beim Festlegen des Bundeslands und beim Öffnen des Rasters |

Alle Endpunkte außer `/health` und `/auth/login` erfordern Anmeldung.

## Erster Admin und Anmeldung

```bash
# Ersten Admin anlegen (Passwort wird verdeckt abgefragt, mind. 12 Zeichen):
uv run python -m app.konto_anlegen --email chefin@werkstatt.de --name "Anna Beispiel"

# Weitere Konten, z. B. zum Testen der Rollen:
uv run python -m app.konto_anlegen --email max@werkstatt.de --name "Max" --rolle mitarbeiter
```

Anmelden in http://localhost:8000/docs: oben rechts **Authorize**, bei `username` die
E-Mail und bei `password` das Passwort eintragen. Danach schickt /docs das Token automatisch mit.
Das Token gilt 8 Stunden.

## Datenbank-Schema (Alembic)

Tabellen sind in `app/models.py` definiert. Änderungen am Schema immer so:

```bash
# 1. app/models.py anpassen, dann Migration erzeugen und prüfen:
uv run alembic revision --autogenerate -m "Kurze Beschreibung"
# 2. Auf die Datenbank anwenden:
uv run alembic upgrade head
```

Nie Tabellen direkt im Supabase-Dashboard ändern, sonst passen Code und Datenbank nicht mehr zusammen.
Neue Tabellen brauchen in ihrer Migration `ENABLE ROW LEVEL SECURITY` (siehe erste Migration).

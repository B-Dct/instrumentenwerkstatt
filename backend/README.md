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
uv run python -m app.demo_daten anlegen     # Stammdaten, Demo-Kunden, Instrumente, Historie
uv run python -m app.demo_daten anzeigen    # IDs und fertige Beispiel-Anfragen erneut anzeigen
uv run python -m app.demo_daten entfernen   # Demo-Kunden samt Instrumenten und Aufträgen entfernen
```

Demo-Daten erkennt man an Kundennummern und Auftragsnummern mit `DEMO-`. Beim Entfernen
bleiben die Stammdaten (Instrumentenklassen, Reparaturarten, Vorgabewerte) erhalten.
Mit ihnen kann man auch echt arbeiten.

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
| GET | `/admin/vorgabewerte` | Vorgabewerte auflisten (Filter: `reparaturart_id`, `instrumentenklasse_id`) |
| GET | `/admin/vorgabewerte/{id}` | Einen Vorgabewert abrufen |
| POST | `/admin/vorgabewerte` | Vorgabewert anlegen (409, falls Kombination schon existiert) |
| PATCH | `/admin/vorgabewerte/{id}` | Vorgabewert ändern (nur mitgeschickte Felder) |
| GET | `/auftraege` | Aufträge auflisten (Priorität hoch zuerst, dann älteste; Filter: `status_id`, `nur_offene`, `zugewiesener_mitarbeiter_id`, `kunde_id`, `prioritaet`) |
| GET | `/auftraege/{id}` | Auftrag mit Statusverlauf und allen Schätzungen |
| POST | `/auftraege` | Auftrag anlegen – schätzt Stunden/Kosten automatisch und protokolliert die Schätzung |
| POST | `/auftraege/{id}/status` | Statuswechsel (neuer Eintrag im Statusverlauf; bei „Fertig“ Pflicht: `arbeitszeit_minuten`) |
| POST | `/auftraege/{id}/schaetzung-korrektur` | Geschätzte Stunden/Kosten manuell korrigieren (Pflicht: `grund`) |

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

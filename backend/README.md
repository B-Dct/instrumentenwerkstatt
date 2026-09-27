# Backend (Python / FastAPI)

```bash
cp .env.example .env   # einmalig, dann DATABASE_URL eintragen
uv run uvicorn app.main:app --reload
```

- http://localhost:8000/health – App läuft
- http://localhost:8000/health/db – Datenbankverbindung funktioniert
- http://localhost:8000/docs – automatische API-Doku

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

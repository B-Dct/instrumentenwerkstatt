# Backend (Python / FastAPI)

```bash
cp .env.example .env   # einmalig, dann DATABASE_URL eintragen
uv run uvicorn app.main:app --reload
```

- http://localhost:8000/health – App läuft
- http://localhost:8000/health/db – Datenbankverbindung funktioniert
- http://localhost:8000/docs – automatische API-Doku

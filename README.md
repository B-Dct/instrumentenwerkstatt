# Auftragsmanagement Reparaturwerkstatt für Musikinstrumente

Software zur Verwaltung von Reparaturaufträgen einer Musikinstrumenten-Werkstatt: Zuordnung von Aufträgen zu Mitarbeitern, Status- und Kapazitätsübersicht für die Werkstatt, sowie ein öffentliches Kunden-Dashboard zur Statusabfrage.

> **Status:** In Entwicklung / Konzeptphase. Das vollständige Datenmodell und die Architekturentscheidungen sind in [`ARCHITECTURE.md`](./ARCHITECTURE.md) sowie in [`docs/datenmodell.md`](./docs/datenmodell.md) beschrieben.

## Was die Software kann (Zielbild)

- Aufträge anlegen, Mitarbeitern zuweisen, Status verfolgen (mit vollständiger Statushistorie)
- Automatische Schätzung des voraussichtlichen Fertigstellungstermins (zunächst regelbasiert, später datengetrieben)
- Internes Dashboard für Mitarbeiter (eigene Aufträge, sortiert nach Priorität/Eingang)
- Werkstattleiter-Dashboard (Gesamtübersicht, Kapazitätsplanung, Auslastung pro Mitarbeiter)
- Administrationsbereich (Mitarbeiterverwaltung, Stammdaten, Systemrollen)
- Öffentliches Kunden-Dashboard: Statusabfrage per Auftragsnummer + Zugriffstoken, ohne Login

## Tech-Stack

| Schicht | Technologie |
|---|---|
| Datenbank | PostgreSQL (gehostet bei Supabase) |
| Backend | Python 3.12 / FastAPI, SQLAlchemy 2, psycopg 3 (Paketverwaltung mit `uv`) |
| Frontend | React (mit Vite) |

Details und Begründung der Wahl siehe [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Projektstruktur

```
/backend      Backend-Anwendung (API, Geschäftslogik, Datenbankzugriff)
/frontend     Frontend-Anwendung (Mitarbeiter-, Admin- und Kunden-Oberfläche)
/docs         Datenmodell, Architekturentscheidungen, weitere Dokumentation
```

## Lokale Entwicklung

Voraussetzungen: [uv](https://docs.astral.sh/uv/) und Node.js.

```bash
# Backend (läuft auf http://localhost:8000, API-Doku unter /docs)
cd backend
cp .env.example .env        # einmalig, dann DATABASE_URL und JWT_SECRET eintragen
uv run uvicorn app.main:app --reload

# Frontend (läuft auf http://localhost:5173) – in einem zweiten Terminal
cd frontend
npm install                 # einmalig
npm run dev
```

Erstes Konto und Beispieldaten: siehe `backend/README.md` (`app.konto_anlegen`, `app.demo_daten`).

Verbindung prüfen: http://localhost:8000/health/db sollte `"datenbank": "verbunden"` zurückgeben.

**Hinweis Supabase:** Die direkte Datenbankadresse (`db.<projekt>.supabase.co`) ist nur per IPv6 erreichbar. In der `.env` wird deshalb die Adresse des **Session Poolers** (IPv4) verwendet. Man findet sie im Supabase-Dashboard unter „Connect“.

## Entwicklungsprinzipien

- Jede Änderung wird committet, mit aussagekräftiger Commit-Nachricht
- Neue Funktionen werden mit Tests abgesichert
- Größere Architekturentscheidungen werden in `ARCHITECTURE.md` nachgetragen
- Kein hartes Löschen von Datensätzen (Aufträge, Mitarbeiter) — nur Archivieren/Deaktivieren

## Weiterführende Dokumentation

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — Architekturentscheidungen im Überblick
- [`docs/datenmodell.md`](./docs/datenmodell.md) — Datenmodell (Tabellen, Sicherheitskonzept, UI-Richtlinien, Kapazitätsplanung)


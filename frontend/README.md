# Frontend (React / Vite) – Klick-Prototyp

> **Nur funktional, ohne Design-Anspruch.** Wird komplett neu gestaltet, sobald das
> Design-System (Datenmodell 9.6) feststeht. UI-Richtlinien aus Abschnitt 9 sind hier
> bewusst noch nicht umgesetzt.

## Starten

Voraussetzung: Das Backend läuft auf http://localhost:8000 (siehe `backend/README.md`).

```bash
npm install     # einmalig bzw. nach Änderungen an package.json
npm run dev     # startet auf http://localhost:5173
```

Anmelden mit einem Konto, das per `uv run python -m app.konto_anlegen` im Backend angelegt wurde.
Eine andere Backend-Adresse lässt sich über `VITE_API_URL` setzen (siehe `.env.example`).

## Seiten

| Adresse | Inhalt |
|---|---|
| `/login` | Anmeldung (Token wird im `localStorage` des Browsers gespeichert) |
| `/` | Auftragsliste (Sortierung vom Backend: Priorität hoch zuerst, dann älteste) |
| `/neu` | Auftrag anlegen (Kunde → Instrument → Reparaturart; Schätzung erfolgt automatisch) |
| `/auftrag/:id` | Details, Statuswechsel (bei „Fertig“ mit Pflicht-Arbeitszeit), Schätzungs-Korrektur, Statusverlauf, Schätzungsprotokoll |

## Aufbau

- `src/api.js`: alle Backend-Aufrufe, Token-Verwaltung und Anzeige-Helfer (Datum, Euro)
- `src/seiten/`: eine Datei pro Seite
- Bei abgelaufener Anmeldung (401) geht es automatisch zurück zur Login-Seite

# Frontend (React / Vite)

Interne Oberfläche für Mitarbeiter, Werkstattleitung und Admin. Gestaltet nach dem
Design-System in `docs/datenmodell.md`, Abschnitt 9.6.

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

## Design-System

- **Alle Farben, Schriftgrößen, Abstände und Radien** stehen als CSS-Variablen in
  `src/styles/tokens.css`. In Komponenten und `src/styles/basis.css` werden nur diese
  Variablen verwendet, keine festen Werte.
- **Statusfarben und -symbole** kommen aus der Datenbank (`auftragsstatus.farbe`/`.symbol`),
  weil die Status pflegbar sind. Die Komponente `komponenten/Status.jsx` zeigt immer
  Farbe, Symbol und Text zusammen (9.3).
- **Schriften** Inter und Fraunces sind lokal eingebunden (`@fontsource-variable/…`).
  Es gibt keine Anfrage an Google-Server (Datenschutz).
- Layout: feste linke Seitenleiste; der Werkstattname oben links führt zur Startseite (9.2).

## Aufbau

- `src/api.js`: alle Backend-Aufrufe, Token-Verwaltung und Anzeige-Helfer (Datum, Euro)
- `src/seiten/`: eine Datei pro Seite
- `src/komponenten/`: wiederverwendbare Bausteine (Statusanzeige, Markierungen)
- `src/styles/`: `tokens.css` (Design-Tokens) und `basis.css` (Grundstile, Bausteine)
- Bei abgelaufener Anmeldung (401) geht es automatisch zurück zur Login-Seite

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
| `/kunden` | Kundenliste mit Suche; „Neuer Kunde“ öffnet das Formular eingebettet |
| `/kunden/:id` | Kundenseite: Eckdaten, Aktionen (bearbeiten, Instrument hinzufügen, archivieren), Instrumente |
| `/verwaltung/instrumentenklassen`, `/verwaltung/reparaturarten` | Stammdaten pflegen und archivieren (nur Admin) |
| `/verwaltung/vorgabewerte` | Vorgabewerte für Dauer/Kosten je Reparaturart (nur Admin) |
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

## Fokussierte Oberflächen (Datenmodell 9.10)

Neue Seiten verwenden die Bausteine aus `src/komponenten/`:

- `useFokusFormular()` (`fokusFormular.js`): höchstens ein Formular offen, eingebettete Rückfrage
  „Änderungen verwerfen?“ bei Wechsel, Abbrechen, Escape und Wegnavigieren (Router-Blocker),
  Browser-Rückfrage beim Schließen des Tabs
- `AktionsButton`, `FormularBereich`, `FokusFormular`, `Feld` (`FokusFormular.jsx`): Aktionsleiste
  mit `aria-expanded`, Fokus ins erste Feld, Fehler direkt am Feld (9.1)
- `useRueckmeldung()` (`rueckmeldung.js`): Erfolgsbestätigung am Bildschirmrand (9.1)
- `useHervorhebung()` (`hervorhebung.js`): geänderten Eintrag kurz hervorheben
- `useSpeichern()` (`speichern.js`): Senden, Fehler je Feld; „gibt es bereits“ (409) am passenden Feld
- `NurRolle` (`NurRolle.jsx`): Seite nur ab einer Mindestrolle
- `seiten/verwaltung/StammdatenListe.jsx`: gemeinsame Listenseite für einfache Stammdaten

Aktionen werden nur angezeigt, wenn die Rolle sie erlaubt (`hatRolle(...)` in `api.js`);
das Backend prüft unabhängig davon.

## Aufbau

- `src/api.js`: alle Backend-Aufrufe, Token-Verwaltung und Anzeige-Helfer (Datum, Euro)
- `src/router.jsx`: Seitenadressen; `src/Layout.jsx`: Seitenleiste und Rahmen für angemeldete Nutzer
- `src/seiten/`: eine Datei pro Seite
- `src/komponenten/`: wiederverwendbare Bausteine (Statusanzeige, Markierungen)
- `src/styles/`: `tokens.css` (Design-Tokens) und `basis.css` (Grundstile, Bausteine)
- Bei abgelaufener Anmeldung (401) geht es automatisch zurück zur Login-Seite

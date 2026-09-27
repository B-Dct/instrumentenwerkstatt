# Auftragsmanagement Reparaturwerkstatt für Musikinstrumente

Software zur Verwaltung von Reparaturaufträgen einer Musikinstrumenten-Werkstatt: Zuordnung von Aufträgen zu Mitarbeitern, Status- und Kapazitätsübersicht für die Werkstatt, sowie ein öffentliches Kunden-Dashboard zur Statusabfrage.

> **Status:** In Entwicklung / Konzeptphase. Das vollständige Datenmodell und die Architekturentscheidungen sind in [`ARCHITECTURE.md`](./ARCHITECTURE.md) sowie im begleitenden Datenmodell-Dokument beschrieben.

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
| Datenbank | PostgreSQL |
| Backend | *(hier eintragen, z. B. Python/FastAPI oder Node.js/Express)* |
| Frontend | *(hier eintragen, z. B. React)* |

Details und Begründung der Wahl siehe [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Projektstruktur

```
/backend      Backend-Anwendung (API, Geschäftslogik, Datenbankzugriff)
/frontend     Frontend-Anwendung (Mitarbeiter-, Admin- und Kunden-Oberfläche)
/docs         Datenmodell, Architekturentscheidungen, weitere Dokumentation
```

*(Struktur bei Bedarf anpassen, sobald der konkrete Stack feststeht.)*

## Lokale Entwicklung

> Wird ergänzt, sobald das Grundgerüst steht (Schritt 3 im Umsetzungsplan).

```bash
# Backend
cd backend
# Setup-Befehle hier ergänzen

# Frontend
cd frontend
# Setup-Befehle hier ergänzen
```

## Entwicklungsprinzipien

- Jede Änderung wird committet, mit aussagekräftiger Commit-Nachricht
- Neue Funktionen werden mit Tests abgesichert
- Größere Architekturentscheidungen werden in `ARCHITECTURE.md` nachgetragen
- Kein hartes Löschen von Datensätzen (Aufträge, Mitarbeiter) — nur Archivieren/Deaktivieren

## Weiterführende Dokumentation

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — Architekturentscheidungen im Überblick
- Datenmodell-Dokument (Tabellen, Sicherheitskonzept, UI-Richtlinien, Kapazitätsplanung) — Link/Ablageort hier ergänzen

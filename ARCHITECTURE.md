# Architektur-Übersicht

Dieses Dokument hält die zentralen Architekturentscheidungen fest — als Gedächtnis für dich selbst und für jede neue KI-Session, die ohne Gesprächsverlauf startet. Bei jeder größeren Entscheidung während der Entwicklung: hier ergänzen, nicht nur im Chat besprechen.

## 1. Tech-Stack

| Schicht | Wahl | Begründung |
|---|---|---|
| Datenbank | PostgreSQL (gehostet bei Supabase) | Relationale Struktur passt zu Kunden/Aufträgen/Mitarbeitern; weit verbreitet, gut dokumentiert |
| Backend | Python 3.12 / FastAPI, SQLAlchemy 2, psycopg 3 | Breite Trainingsbasis für KI-Tools, große Community, stabile Konventionen |
| Frontend | React (mit Vite) | Ebenso weit verbreitet, gute Unterstützung durch KI-Coding-Tools |

**Prinzip:** Bewusst "langweiliger", breit verbreiteter Stack statt exotischer Frameworks — wichtig, damit KI-Tools auch in ein paar Jahren noch zuverlässig helfen können.

## 2. Datenmodell

Das vollständige Datenmodell (alle Tabellen, Felder, Beziehungen) ist im separaten Datenmodell-Dokument festgehalten: [`docs/datenmodell.md`](./docs/datenmodell.md).

Kernprinzipien:
- **Statushistorie statt Statusfeld:** Jeder Statuswechsel eines Auftrags wird als eigener Datensatz mit Zeitstempel gespeichert
- **Kein hartes Löschen:** Mitarbeiter und Aufträge werden archiviert/deaktiviert, nie gelöscht — erhält die Historie
- **Strukturierte Kategorien statt Freitext:** Instrumentenklassen und Reparaturarten sind eigene Tabellen, nicht Freitextfelder — Voraussetzung für spätere Auswertbarkeit

## 3. Terminschätzung (Stufenmodell)

- **Stufe 1 (Start):** Regelbasierte Schätzung aus historischem Durchschnitt, Auftragsvolumen, Abwesenheiten und Komplexitätsfaktor
- **Stufe 2 (später, nach ausreichend Datenbasis):** Datengetriebenes Modell (z. B. Gradient Boosting) auf Basis abgeschlossener Aufträge, inkl. Vorhersageintervall statt Einzelwert

Details und Berechnungsformeln: siehe Datenmodell-Dokument, Abschnitte 4–5.

## 4. Berechtigungskonzept

Drei Systemrollen, kumulativ (Admin ⊇ Werkstattleiter ⊇ Mitarbeiter):

- **Mitarbeiter:** eigene zugewiesene Aufträge
- **Werkstattleiter:** operativer Betrieb (Zuweisung, Abwesenheiten, Werkstattübersicht, Kapazitätsplanung)
- **Admin:** technische/strukturelle Verwaltung (Accounts, Stammdaten, Systemrollen)

Details: siehe Datenmodell-Dokument, Abschnitt 7.

## 5. Kundenauthentifizierung

Kein Login für Kunden. Zugriff auf das Status-Dashboard über **Auftragsnummer + zufälliges Zugriffstoken** (auf dem Abgabebeleg/als QR-Code ausgegeben). Details und Begründung (u. a. warum keine Postleitzahl): siehe Datenmodell-Dokument, Abschnitt 6.

## 6. Kapazitätsplanung

Wochenbasiertes Kapazitätsmodell (angelehnt an Ressourcenplanungs-Tools wie Float/Resource Guru): Wochenstunden je Mitarbeiter minus Abwesenheiten minus gebundene Stunden aus offenen Aufträgen ergibt die freie Kapazität. Bewusst keine Tages-/Uhrzeitplanung. Details: siehe Datenmodell-Dokument, Abschnitt 8.

## 7. UI/UX-Grundregeln

- Keine Popups bei Eingabemasken, Inline-Validierung
- Warnung bei ungespeicherten Änderungen beim Verlassen einer Seite
- Nicht-blockierende Erfolgsbestätigung nach dem Speichern
- Fester Startseiten-Link oben links auf jeder Seite
- Responsives Design statt aktiver Geräteerkennung
- Design-System (Farben, Typografie, Statusfarben) vor dem ersten UI-Baustein festlegen

Vollständige Liste: siehe Datenmodell-Dokument, Abschnitt 9.

## 8. Änderungsprotokoll dieses Dokuments

| Datum | Änderung |
|---|---|
| *(Datum ergänzen)* | Ersterstellung |
| 27.09.2026 | Tech-Stack festgelegt (FastAPI, React/Vite, PostgreSQL bei Supabase); Datenbankzugriff über Supabase Session Pooler (IPv4) |


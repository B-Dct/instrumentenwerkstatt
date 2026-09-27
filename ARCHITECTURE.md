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

Umsetzung in der Datenbank (Stand 27.09.2026):
- **Tabellen-Definitionen** in `backend/app/models.py` (SQLAlchemy), Änderungen am Schema ausschließlich über **Alembic-Migrationen** (`backend/migrations/`), nie direkt in Supabase
- **Primärschlüssel sind UUIDs** (von PostgreSQL per `gen_random_uuid()` erzeugt) — nicht erratbar, einheitlich in allen Tabellen
- **Keine Umlaute in Tabellen-/Spaltennamen:** Umschreibung (z. B. `prioritaet`, `schaetzungs_log`, `geschaetztes_fertigstellungsdatum`)
- **Auftragsstatus als eigene, pflegbare Tabelle** `auftragsstatus` (statt fester Liste): mit stabilem `schluessel` für den Code, Anzeigename, Reihenfolge, Farbe sowie den Schaltern `erfordert_zeiterfassung` (z. B. „Fertig“) und `ist_abgeschlossen`. `auftrag.status_aktuell_id` und `auftrag_statusverlauf.status_id` verweisen darauf. Die UI darf Status/Farben daher nicht hart kodieren
- **Feste Auswahllisten** (PostgreSQL-Enums) nur für `systemrolle`, `prioritaet` und Abwesenheits-`typ`, weil daran Programmlogik hängt
- **Plausibilitätsregeln in der Datenbank** (z. B. Komplexität 1–5, Enddatum ≥ Startdatum, Gleitzeit-Woche beginnt montags)
- **Row Level Security auf allen Tabellen aktiv, ohne Freigabe-Regeln:** sperrt die automatische öffentliche REST-API von Supabase. Zugriff auf Daten nur über unser Backend
- **Zeitstempel = echte Uhrzeit des Eintrags** (`clock_timestamp()`), nicht Transaktionsbeginn (`now()`) — sonst hätten mehrere Einträge einer Transaktion denselben Zeitstempel und die Reihenfolge von Verläufen/Logs wäre zufällig

## 3. Terminschätzung (Stufenmodell)

- **Stufe 1 (Start):** Regelbasierte Schätzung aus historischem Durchschnitt, Auftragsvolumen, Abwesenheiten und Komplexitätsfaktor
- **Stufe 2 (später, nach ausreichend Datenbasis):** Datengetriebenes Modell (z. B. Gradient Boosting) auf Basis abgeschlossener Aufträge, inkl. Vorhersageintervall statt Einzelwert

Details und Berechnungsformeln: siehe Datenmodell-Dokument, Abschnitte 4–5.

**Umsetzung Stufe 1, Teil Arbeitsstunden/Kosten (Stand 27.09.2026):** `backend/app/schaetzung.py`, Funktionen `schaetze_arbeitsstunden` und `schaetze_kosten`
- Vergleichsfälle = Aufträge mit gleicher Instrumentenklasse (über `instrument`) + Reparaturart, deren aktueller Status `ist_abgeschlossen` ist (derzeit „Fertig“ und „Abgeholt“) **und** die einen Ist-Wert haben (mind. ein `arbeitszeiterfassung`-Eintrag bzw. `tatsaechliche_kosten` gesetzt)
- Arbeitszeit: erst je Auftrag alle Zeiteinträge summieren, dann über die Aufträge mitteln
- Ab `MINDESTANZAHL_VERGLEICHSFAELLE = 5` Vergleichsfällen → historischer Durchschnitt; sonst Vorgabewert (spezifisch vor allgemein); sonst keine Schätzung
- Ergebnis enthält neben dem Wert auch die Quelle und die Anzahl Vergleichsfälle (für das spätere `schaetzungs_log`)
- Anbindung: Beim Anlegen eines Auftrags werden Stunden und Kosten geschätzt, im Auftrag gespeichert und als ein Eintrag im `schaetzungs_log` (`methode = "regelbasiert"`, Eingabefaktoren inkl. Quelle und Anzahl Vergleichsfälle) protokolliert
- Manuelle Korrektur (Datenmodell 4.2): neuer Log-Eintrag `methode = "manuelle_korrektur"` mit Mitarbeiter, Pflicht-Begründung und vorherigen Werten; bisherige Log-Einträge bleiben unverändert. Die Datenbank erzwingt Mitarbeiter + Grund bei Korrektur-Einträgen
- Noch **nicht** umgesetzt: Komplexitätsfaktor, Terminschätzung (Fertigstellungsdatum), Neuberechnung bei späteren Änderungen am Auftrag

## 4. Berechtigungskonzept

Drei Systemrollen, kumulativ (Admin ⊇ Werkstattleiter ⊇ Mitarbeiter):

- **Mitarbeiter:** eigene zugewiesene Aufträge
- **Werkstattleiter:** operativer Betrieb (Zuweisung, Abwesenheiten, Werkstattübersicht, Kapazitätsplanung)
- **Admin:** technische/strukturelle Verwaltung (Accounts, Stammdaten, Systemrollen)

Details: siehe Datenmodell-Dokument, Abschnitt 7.

**Technische Umsetzung (Stand 27.09.2026):** alles in `backend/app/auth.py`
- **Login:** `POST /auth/login` mit E-Mail + Passwort (OAuth2-Formular, Feld `username` = E-Mail) → signiertes Token (JWT, HS256) mit `mitarbeiter_id` (`sub`) und `systemrolle`, gültig 8 Stunden. Schlüssel `JWT_SECRET` in der `.env`
- **Passwörter:** Argon2 (`pwdlib`), nie im Klartext. Fehlermeldung beim Login unterscheidet bewusst nicht zwischen „E-Mail unbekannt“ und „Passwort falsch“
- **Jede Anfrage:** Dependency `aktueller_mitarbeiter` prüft das Token und lädt den Mitarbeiter. **Rolle und Aktiv-Status kommen aus der Datenbank**, nicht aus dem Token — Deaktivierung/Rollenänderung wirkt sofort
- **Rollenprüfung:** `rolle_mindestens(Systemrolle.X)` (Rollen kumulativ); `require_admin` am gesamten `/admin`-Router; `darf_auftrag_bearbeiten` für Statuswechsel/Korrektur (zugewiesener Mitarbeiter oder Werkstattleiter/Admin)
- **Erster Admin:** Kommandozeilen-Skript `uv run python -m app.konto_anlegen` (siehe `backend/README.md`)
- Offen: Auftragsliste/-details für Rolle `mitarbeiter` ggf. auf eigene Aufträge einschränken; Passwort ändern/zurücksetzen; Begrenzung von Login-Fehlversuchen

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
| 27.09.2026 | Login (JWT, Argon2) und Rollenprüfung; Header `X-Mitarbeiter-Id` entfernt; Skript für den ersten Admin |
| 27.09.2026 | Auftrags-Endpunkte (Anlegen mit Schätzung, Liste, Detail, Statuswechsel, manuelle Korrektur); vorläufige Identifikation per `X-Mitarbeiter-Id`; alle Zeitstempel auf `clock_timestamp()` |
| 27.09.2026 | Stufe-1-Schätzung für Arbeitsstunden und Kosten (isoliert, noch nicht angebunden) |
| 27.09.2026 | Tabelle `reparatur_vorgabewert` + Kostenfelder in `auftrag`; Admin-Endpunkte für Vorgabewerte (noch ohne Berechtigungsprüfung, siehe Abschnitt 4) |
| 27.09.2026 | Grundschema angelegt (Alembic-Migration), Datenbank-Konventionen festgelegt (siehe Abschnitt 2) |
| 27.09.2026 | Tech-Stack festgelegt (FastAPI, React/Vite, PostgreSQL bei Supabase); Datenbankzugriff über Supabase Session Pooler (IPv4) |


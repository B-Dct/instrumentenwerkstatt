# Architektur-Übersicht

Dieses Dokument hält die zentralen Architekturentscheidungen fest — als Gedächtnis für dich selbst und für jede neue KI-Session, die ohne Gesprächsverlauf startet. Bei jeder größeren Entscheidung während der Entwicklung: hier ergänzen, nicht nur im Chat besprechen.

## 1. Tech-Stack

| Schicht | Wahl | Begründung |
|---|---|---|
| Datenbank | PostgreSQL (gehostet bei Supabase) | Relationale Struktur passt zu Kunden/Aufträgen/Mitarbeitern; weit verbreitet, gut dokumentiert |
| Backend | Python 3.12 / FastAPI, SQLAlchemy 2, psycopg 3 | Breite Trainingsbasis für KI-Tools, große Community, stabile Konventionen |
| Frontend | React (mit Vite), `react-router`, CSS-Variablen als Design-Tokens | Ebenso weit verbreitet, gute Unterstützung durch KI-Coding-Tools |

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
- **Unterbrechungen automatisch aus dem Status:** Status mit gesetztem `auftragsstatus.unterbrechungsgrund` (derzeit „Wartet auf Ersatzteil“) öffnen beim Wechsel hinein einen `unterbrechung`-Eintrag und schließen ihn beim Wechsel heraus. Höchstens eine offene Unterbrechung je Auftrag (Datenbank-Index). Grundlage, um Wartezeiten später aus der Bearbeitungsdauer herauszurechnen
- **Archivieren statt Löschen:** Stammdaten bekommen `archiviert_am` (NULL = aktiv); archivierte Einträge fehlen in Standardlisten und sind für neue Aufträge gesperrt, bleiben aber erhalten und lassen sich reaktivieren. Kunden/Instrumente mit offenen Aufträgen können nicht archiviert werden
- **Listen (9.11) zentral:** Suche, Filter, Sortierung und Seiten übernimmt das Backend über `app/listen.py` (`listen_parameter`, `seite_abfragen`, Antwort `Seite[...]` mit `treffer`/`gesamt`); das Frontend nutzt `komponenten/liste.js` + `Liste.jsx` (Zustand in der Adresse, Suche mit Eingabepause, Filter-Chips, Trefferzahl, sortierbare Spaltenköpfe, Seitenwahl). Alle Listen umgestellt (Mitarbeiter, Kunden, Instrumentenklassen, Reparaturarten, Vorgabewerte, Aufträge). Ein Sortierschlüssel kann Nachrang-Spalten haben (z. B. Oberkategorie, darin Bezeichnung)
- **Änderungsprotokoll:** Anlegen, Ändern, Archivieren und Reaktivieren von Stammdaten wird im `system_ereignis_log` festgehalten (Helfer `app/ereignisse.py`)
- **Speichern mit Datenbankregeln (zentral):** Änderungen, die eine Eindeutigkeitsregel verletzen könnten, laufen immer über `app/speichern.py` (`with sicher_speichern(db): …`). Der Baustein setzt die Änderungen in einem Speicherpunkt, nimmt bei Verletzung genau diese zurück und liefert 409 mit deutscher Meldung aus `KONFLIKT_MELDUNGEN`. Ein Sicherheitsnetz in `main.py` macht aus übersehenen Fällen ebenfalls 409 statt 500. Tests erzwingen: jede Eindeutigkeitsregel hat eine Meldung, niemand fängt `IntegrityError` selbst ab, nach einem Konflikt bleibt nichts in der Sitzung hängen
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
- Noch **nicht** umgesetzt: Komplexitätsfaktor

**Umsetzung Terminschätzung (Stand 27.09.2026):** `backend/app/terminschaetzung.py`, Funktion `schaetze_fertigstellung`
- Baut auf `auftrag.geschaetzte_arbeitsstunden` auf (keine separate historische Dauer)
- Vorlauf = Stunden der offenen Aufträge desselben Mitarbeiters, die vor diesem an der Reihe sind (Priorität hoch zuerst, dann ältester Eingang, wie 9.4). Pausierte Aufträge zählen mit, bereits geleistete Teil-Arbeitszeit wird nicht abgezogen (bewusste Vereinfachung)
- Abgearbeitet ab dem nächsten Tag mit Wochenstunden / 5 pro Tag (`mitarbeiter_arbeitszeit`, sonst Standard 40 Std.); Wochenenden, betriebsweite Abwesenheiten und ganztägige Abwesenheiten des Mitarbeiters werden übersprungen. `abwesenheit.reduzierte_stunden` wird als **verfügbare Wochenstunden im Zeitraum** gelesen (z. B. 20 → 4 Std./Tag)
- Bandbreite ± 20 % der Arbeitstage, mindestens ± 1 Arbeitstag, nicht vor Arbeitsbeginn
- Ohne Zuweisung: durchschnittliche offene Stunden je aktivem Mitarbeiter als Vorlauf
- Neuberechnung beim Anlegen und bei Änderung von Zuweisung/Priorität (`PATCH /auftraege/{id}`, Werkstattleitung/Admin), jeweils mit Eintrag im `schaetzungs_log` (Anlass + Eingabefaktoren)
- Bewusst **nicht**: Neuberechnung der *anderen* Aufträge, wenn sich die Warteschlange ändert; Neuberechnung nach manueller Korrektur der Stunden
- Befehl `uv run python -m app.termine_nachrechnen` berechnet Termine offener Aufträge (nach), z. B. nach neuen Abwesenheiten (`--alle`). Protokoll-Anlass „nachberechnet“
- „Überfällig“ berechnet das Backend (`ist_ueberfaellig`: Termin vor heute und Status nicht abgeschlossen)

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
- **Mitarbeiter-Verwaltung** (`/admin/mitarbeiter`): Schutz gegen Aussperren – kein Selbst-Deaktivieren/-Herabstufen, der letzte aktive Admin bleibt (mit Zeilensperre gegen gleichzeitige Änderungen), Deaktivieren erst ohne offene zugewiesene Aufträge
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

**Umsetzung Design-System (Stand 27.09.2026):**
- Design-Tokens als CSS-Variablen in `frontend/src/styles/tokens.css` (einzige Quelle für Farben, Typskala, 4-px-Raster, Radius)
- Statusfarben/-symbole liegen in der Datenbank (`auftragsstatus.farbe`, `.symbol`), passend zur pflegbaren Status-Tabelle. Werte entsprechen der Tabelle in 9.6. „Abgeholt“ ist dort nicht festgelegt und vorläufig `#5E554C` / ●
- Schriften Inter/Fraunces lokal eingebunden (`@fontsource-variable`) statt über Google Fonts, damit keine IP-Adressen an Google übertragen werden (DSGVO)
- „Überfällig“ wird im Frontend aus `geschaetztes_fertigstellungsdatum` berechnet. Wirkt erst, sobald die Terminschätzung umgesetzt ist (bisher nur in Demo-Daten gesetzt)

## 8. Änderungsprotokoll dieses Dokuments

| Datum | Änderung |
|---|---|
| *(Datum ergänzen)* | Ersterstellung |
| 02.10.2026 | Manuelle Terminkorrektur (4.2): Endpunkt `termin-korrektur` nur für Werkstattleitung/Admin mit Pflichtbegründung und Protokolleintrag; Aktion „Termin korrigieren“ auf der Auftragsdetailseite |
| 29.09.2026 | Auftragsdetailseite nach 9.10: Eckdaten im Lesezustand, Aktionsleiste (Status ändern, Schätzung korrigieren, Zuweisung & Priorität) mit eingebetteten Formularen, Verläufe zugeklappt; Namen der Handelnden liefert das Backend direkt in Statusverlauf, Schätzprotokoll und Wochenstunden-Verlauf (auch für deaktivierte Mitarbeiter) |
| 29.09.2026 | Auftragsliste auf Listen-Baustein umgestellt (Standard offene Aufträge nach Priorität, dann Eingang; Filter Status, Mitarbeiter, Instrument, Priorität, überfällig) – Umstellung aller Listen abgeschlossen |
| 29.09.2026 | Vorgabewerte auf Listen-Baustein umgestellt (Suche, Filter Reparaturart/Instrumentenklasse/Status, sortierbar) |
| 29.09.2026 | Instrumentenklassen und Reparaturarten auf Listen-Baustein umgestellt (Status-Filter statt „archivierte anzeigen“) |
| 29.09.2026 | Kundenliste auf Listen-Baustein umgestellt (Status-Filter statt „archivierte anzeigen“, Rechte im Backend geprüft) |
| 29.09.2026 | Wochenstunden ändern und Verlauf auf der Mitarbeiterseite (Verwaltung Schritt 4c-2); Aufklappbereich-Baustein; Trefferzahl zeigt „x von y“ auch bei Standardfiltern |
| 29.09.2026 | Listen-Baustein (9.11) im Backend und Frontend; Mitarbeiterliste und Mitarbeiterseite (Verwaltung Schritt 4c-1) |
| 28.09.2026 | Externe Kundennummer eindeutig ohne Beachtung der Groß-/Kleinschreibung (Index auf lower(...); Migration bricht bei Altkonflikten ab) |
| 28.09.2026 | Externe Kundennummer am Kunden (optional, eindeutig falls gesetzt, in Suche); Konfliktmeldungen können den betroffenen Datensatz nennen |
| 28.09.2026 | Zentraler Speicher-Baustein `app/speichern.py` für Datenbankkonflikte + Sicherheitsnetz + Mustertests |
| 28.09.2026 | Vorgabewerte archivierbar (Eindeutigkeit nur unter aktiven, Schätzung ignoriert archivierte) |
| 28.09.2026 | Frontend: Verwaltung Instrumentenklassen, Reparaturarten, Vorgabewerte (Schritt 4b, nur Admin) |
| 28.09.2026 | Frontend: Kunden und Instrumente nach 9.10 (Verwaltung Schritt 4a); Bausteine für fokussierte Formulare; Daten-Router |
| 28.09.2026 | Mitarbeiter-Verwaltung und Wochenstunden mit Verlauf (Verwaltung Schritt 3, nur Admin) |
| 28.09.2026 | Instrumentenklassen/Reparaturarten pflegen und archivieren (Verwaltung Schritt 2, nur Admin); `aktiv` → `archiviert_am` |
| 27.09.2026 | Kunden/Instrumente anlegen, bearbeiten, archivieren (Verwaltung Schritt 1); Kundennummern `K-00001` |
| 27.09.2026 | Befehl `app.termine_nachrechnen`; einmalig für offene Aufträge ohne Termin angewendet |
| 27.09.2026 | Terminschätzung (Fertigstellungsdatum + Bandbreite) mit Neuberechnung bei Anlegen, Umzuweisung, Prioritätsänderung; `PATCH /auftraege/{id}`; „überfällig“ im Backend |
| 27.09.2026 | Unterbrechungen automatisch bei pausierenden Status (z. B. „Wartet auf Ersatzteil“); Datenmodell-Doku an Tabelle `auftragsstatus` angeglichen |
| 27.09.2026 | Design-System umgesetzt (Tokens, Seitenleiste, Statusfarben/-symbole aus der DB, lokale Schriften) |
| 27.09.2026 | React-Klick-Prototyp (nur funktional, wird mit dem Design-System ersetzt); Lese-Endpunkte für Auswahllisten |
| 27.09.2026 | Beispieldaten-Skript `app/demo_daten.py` (anlegen/anzeigen/entfernen) |
| 27.09.2026 | Login (JWT, Argon2) und Rollenprüfung; Header `X-Mitarbeiter-Id` entfernt; Skript für den ersten Admin |
| 27.09.2026 | Auftrags-Endpunkte (Anlegen mit Schätzung, Liste, Detail, Statuswechsel, manuelle Korrektur); vorläufige Identifikation per `X-Mitarbeiter-Id`; alle Zeitstempel auf `clock_timestamp()` |
| 27.09.2026 | Stufe-1-Schätzung für Arbeitsstunden und Kosten (isoliert, noch nicht angebunden) |
| 27.09.2026 | Tabelle `reparatur_vorgabewert` + Kostenfelder in `auftrag`; Admin-Endpunkte für Vorgabewerte (noch ohne Berechtigungsprüfung, siehe Abschnitt 4) |
| 27.09.2026 | Grundschema angelegt (Alembic-Migration), Datenbank-Konventionen festgelegt (siehe Abschnitt 2) |
| 27.09.2026 | Tech-Stack festgelegt (FastAPI, React/Vite, PostgreSQL bei Supabase); Datenbankzugriff über Supabase Session Pooler (IPv4) |


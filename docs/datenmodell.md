# Datenmodell: Auftragsmanagement Reparaturwerkstatt für Musikinstrumente

Dieses Dokument beschreibt das Datenmodell für Version 1 (regelbasierte Terminschätzung) und legt gleichzeitig die Grundlage für Version 2 (datengetriebene Schätzung mittels ML), ohne dass später ein Umbau nötig wird.

---

## 1. Grundprinzip

Jeder Statuswechsel eines Auftrags wird als eigener Datensatz mit Zeitstempel gespeichert (nicht nur als aktuelles Statusfeld). Nur so lassen sich später echte Bearbeitungszeiten pro Instrumentenklasse und Reparaturart auswerten.

---

## 2. Tabellen

### 2.1 `kunde`

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| kundennummer | VARCHAR, UNIQUE | Für das Kunden-Dashboard sichtbar (siehe Hinweis zu Sicherheit unten) |
| name | VARCHAR | |
| email | VARCHAR | Optional, für Statusbenachrichtigungen |
| telefon | VARCHAR | Optional |
| erstellt_am | TIMESTAMP | |

**Sicherheitshinweis:** Zum sicheren Dashboard-Zugriff wird zusätzlich zur Auftragsnummer ein Zugriffstoken benötigt — Details siehe Abschnitt 6 "Kundenauthentifizierung".

---

### 2.2 `mitarbeiter`

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| name | VARCHAR | |
| rolle | VARCHAR | Fachliche Rolle, z. B. Geigenbauer, Blechblas-Techniker |
| systemrolle | ENUM | `mitarbeiter` / `werkstattleiter` / `admin` — steuert die Berechtigungen in der Software (siehe Abschnitt 7) |
| email | VARCHAR | Für Login |
| passwort_hash | VARCHAR | Niemals Klartext speichern |
| aktiv | BOOLEAN | Für ausgeschiedene Mitarbeiter — Datensatz wird deaktiviert, nicht gelöscht, damit die Auftragshistorie erhalten bleibt |
| erstellt_am | TIMESTAMP | |
| deaktiviert_am | TIMESTAMP | NULL solange aktiv |

---

### 2.3 `abwesenheit`

Für Urlaub, Krankheit, Feiertage — wichtig sowohl für die interne Kapazitätsplanung als auch später als Modell-Feature ("Saisonalität").

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| mitarbeiter_id | FK → mitarbeiter | NULL = betrifft ganze Werkstatt (z. B. Betriebsurlaub) |
| von_datum | DATE | |
| bis_datum | DATE | |
| typ | VARCHAR | Urlaub / Krankheit / Feiertag / Betriebsschließung / Schulung / Reduzierte Stunden |
| reduzierte_stunden | DECIMAL | NULL = ganztägig abwesend im angegebenen Zeitraum. Ansonsten: die in diesem Zeitraum tatsächlich **verfügbare** Wochenstundenzahl (absoluter Wert, kein Abzugsbetrag) — z. B. "diese Woche nur 20 Std. verfügbar" wegen Arztterminen o. Ä., statt der vollen `mitarbeiter_arbeitszeit.wochenstunden` |

---

### 2.4 `instrumentenklasse`

Strukturierte Kategorie statt Freitext — Pflicht für spätere Auswertbarkeit.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| bezeichnung | VARCHAR | z. B. "Violine", "Trompete", "Klarinette", "Klavier" |
| oberkategorie | VARCHAR | z. B. "Streichinstrument", "Blechblas", "Holzblas", "Tasteninstrument" |

---

### 2.5 `instrument`

Erfasst das konkrete Instrument eines Kunden — getrennt von der Klasse (2.4), damit Hersteller, Typenbezeichnung und Baujahr gespeichert werden können. Ein Kunde kann mehrere Instrumente haben, ein Instrument kann über die Zeit mehrere Aufträge durchlaufen.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| kunde_id | FK → kunde | Eigentümer des Instruments |
| instrumentenklasse_id | FK → instrumentenklasse | z. B. "Violine" |
| hersteller | VARCHAR | z. B. "Yamaha", "Stainer", Werkstattname bei Manufakturinstrumenten |
| typenbezeichnung | VARCHAR | Modell-/Typbezeichnung, z. B. "YFL-222" |
| baujahr | INT | Optional, falls bekannt/schätzbar |
| seriennummer | VARCHAR | Optional, hilfreich zur eindeutigen Identifikation bei Folgeaufträgen |
| notizen | TEXT | z. B. Besonderheiten, bekannte Vorschäden |

**Nutzen fürs spätere Modell (Stufe 2):** Hersteller/Baujahr können als zusätzliche Merkmale einfließen — ältere oder bestimmte Hersteller-Instrumente benötigen bei manchen Reparaturarten erfahrungsgemäß mehr Zeit (z. B. Ersatzteilbeschaffung bei alten oder seltenen Modellen).

---

### 2.6 `reparaturart`

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| bezeichnung | VARCHAR | z. B. "Saitenwechsel", "Ventil-Überholung", "Rissreparatur Decke" |
| standard_komplexität | INT (1–5) | Vorbelegung, kann pro Auftrag überschrieben werden |

---

### 2.6a `reparatur_vorgabewert`

Vorgabedaten je Reparaturart (optional zusätzlich verfeinert je Instrumentenklasse), damit ein Mitarbeiter schon bei Auftragsannahme eine ungefähre Orientierung zu Dauer und Kosten hat — auch bevor genug reale historische Daten vorliegen. Dient außerdem als Ausgangswert ("Prior"), der mit zunehmender Anzahl abgeschlossener Aufträge zunehmend durch echte historische Durchschnittswerte ergänzt bzw. abgelöst wird (siehe Abschnitt 4).

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| reparaturart_id | FK → reparaturart | |
| instrumentenklasse_id | FK → instrumentenklasse | Optional (NULL = gilt allgemein für die Reparaturart, unabhängig von der Instrumentenklasse). Ein Eintrag mit gesetzter Instrumentenklasse überschreibt für diese Kombination den allgemeinen Wert (z. B. "Saitenwechsel" allgemein 0,5 Std., aber für "Kontrabass" spezifisch 1,5 Std.) |
| vorgabe_stunden | DECIMAL | Erwarteter Arbeitsaufwand in Stunden |
| vorgabe_kosten | DECIMAL | Erwarteter Preis für den Kunden (Arbeits- + ggf. übliche Materialkosten als Pauschale) |
| notiz | TEXT | Optional, z. B. "inkl. neuer Saiten, exkl. Spezialsaiten" |
| geändert_von_mitarbeiter_id | FK → mitarbeiter | |
| geändert_am | TIMESTAMP | |

**Pflege:** Über den Administrationsbereich, Systemrolle `admin` (siehe Berechtigungsmatrix, Abschnitt 7.2) — passt zur bestehenden Stammdatenpflege von Instrumentenklassen und Reparaturarten.

---

### 2.7 `auftrag`

Die zentrale Tabelle.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| auftragsnummer | VARCHAR, UNIQUE | Für Kunden sichtbar, dient als Referenz — allein nicht ausreichend für den Dashboard-Zugriff (siehe Abschnitt 6) |
| zugriffstoken | VARCHAR, UNIQUE | Zufällig generierter Code (z. B. 10–12 alphanumerische Zeichen), zusammen mit der Auftragsnummer der einzige Schlüssel zum Kunden-Dashboard. Wird bei Auftragsannahme erzeugt und auf dem Abgabebeleg/als QR-Code ausgegeben. Muss kryptografisch zufällig sein, nicht aus anderen Feldern ableitbar |
| kunde_id | FK → kunde | |
| instrument_id | FK → instrument | Ersetzt die direkte Referenz auf `instrumentenklasse` — die Klasse ergibt sich über den Join `instrument.instrumentenklasse_id` |
| reparaturart_id | FK → reparaturart | Bei mehreren Arbeiten am selben Instrument: separate Aufträge oder Teilaufgaben-Tabelle |
| zugewiesener_mitarbeiter_id | FK → mitarbeiter | Kann initial NULL sein (noch nicht zugewiesen) |
| priorität | ENUM (`normal` / `hoch`) | Manuell durch Werkstattleiter/Admin setzbar, z. B. bei Eilaufträgen oder Kulanzfällen. Fließt in die Sortierung der Mitarbeiter- und Werkstattleiter-Dashboards ein (siehe Abschnitt 9) |
| komplexität | INT (1–5) | Vom Mitarbeiter bei Anlage geschätzt |
| status_aktuell_id | FK → status | Redundant zu Performance-Zwecken — Quelle der Wahrheit ist `auftrag_statusverlauf` |
| erstellt_am | TIMESTAMP | |
| geschätztes_fertigstellungsdatum | DATE | Ergebnis der Berechnung (Stufe 1 oder 2) |
| geschätzte_bandbreite_von | DATE | z. B. für Anzeige "zwischen dem 12. und 16.10." |
| geschätzte_bandbreite_bis | DATE | |
| geschätzte_arbeitsstunden | DECIMAL | Geschätzter reiner Arbeitsaufwand in Stunden (nicht Kalenderdauer) — Grundlage für die Kapazitätsplanung (Abschnitt 9.9). Wird wie die Terminschätzung selbst aus historischen `arbeitszeiterfassung`-Werten vergleichbarer Kombinationen aus Instrumentenklasse/Reparaturart berechnet, mit Fallback auf `reparatur_vorgabewert` (2.6a), solange zu wenig historische Daten vorliegen |
| geschätzte_kosten | DECIMAL | Voraussichtlicher Preis für den Kunden — analog zu `geschätzte_arbeitsstunden` berechnet (historischer Durchschnitt tatsächlicher Kosten vergleichbarer Aufträge, Fallback auf `reparatur_vorgabewert.vorgabe_kosten`) |
| tatsächliche_kosten | DECIMAL | Tatsächlich abgerechneter Preis — NULL bis Abschluss. Wie `tatsächliches_fertigstellungsdatum` ein Trainingswert für Stufe 2, hier für die Kostenschätzung statt der Terminschätzung |
| tatsächliches_fertigstellungsdatum | DATE | NULL bis abgeschlossen — **das ist dein Trainingslabel für Stufe 2** |
| notizen | TEXT | Freitext für interne Zwecke |

---

### 2.7a `status`

Nachschlagetabelle für Auftragsstatus — eingeführt bei der UI-Umsetzung, damit Farbe und Symbol (Abschnitt 9.3/9.6) direkt aus der Datenbank kommen, statt im Frontend-Code hinterlegt zu sein. Neue Status lassen sich damit ohne Code-Änderung ergänzen.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| bezeichnung | VARCHAR | z. B. "Angenommen", "In Bearbeitung", "Wartet auf Ersatzteil", "Qualitätsprüfung", "Fertig", "Abgeholt" |
| farbe | VARCHAR | Hex-Wert, siehe Statusfarben-Tabelle in Abschnitt 9.6 |
| symbol | VARCHAR | z. B. "○", "◐", "⏸", "◑", "✓", "●" |
| reihenfolge | INT | Für konsistente Sortierung/Anzeige (z. B. in Auswahllisten) |

**Aktuelle Werte** (siehe Abschnitt 9.6 für die vollständige Farbtabelle): Angenommen (○, Grau), In Bearbeitung (◐, Blau), Wartet auf Ersatzteil (⏸, Orange), Qualitätsprüfung (◑, Violett), Fertig (✓, Grün), Abgeholt (●, dunkles Neutral `#5E554C`).

---

### 2.8 `auftrag_statusverlauf`

Kernstück für spätere Auswertung — jeder Wechsel wird protokolliert, nichts wird überschrieben.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| auftrag_id | FK → auftrag | |
| status_id | FK → status | |
| geändert_am | TIMESTAMP | |
| geändert_von_mitarbeiter_id | FK → mitarbeiter | |
| kommentar | TEXT | Optional |

---

### 2.9 `unterbrechung`

Erfasst Gründe für Verzögerungen — wichtig, damit das spätere Modell "hausgemachte" Verzögerungen (Ersatzteillieferzeit) von echter Bearbeitungsdauer unterscheiden kann.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| auftrag_id | FK → auftrag | |
| grund | VARCHAR | z. B. "Ersatzteil bestellt", "Rückfrage beim Kunden", "Zusatzschaden entdeckt" |
| von_datum | TIMESTAMP | |
| bis_datum | TIMESTAMP | NULL solange ungelöst |

---

### 2.10 `schätzungs_log` (für Stufe 2 vorbereitet)

Protokolliert jede automatische Schätzung **und** jede manuelle Korrektur durch einen Mitarbeiter oder Werkstattleiter — damit du später prüfen kannst, wie gut das Modell tatsächlich war (Ist- vs. Prognosewert), und nachvollziehbar bleibt, wer wann aus welchem Grund manuell eingegriffen hat.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| auftrag_id | FK → auftrag | |
| berechnet_am | TIMESTAMP | |
| methode | VARCHAR | "regelbasiert" / "ml_modell_v1" / "manuelle_korrektur" |
| geschätztes_datum | DATE | Optional, je nachdem was bei diesem Log-Eintrag geschätzt/korrigiert wurde |
| geschätzte_stunden | DECIMAL | Optional, siehe oben |
| geschätzte_kosten | DECIMAL | Optional, siehe oben |
| eingabefaktoren | JSONB | Snapshot der Faktoren zum Berechnungszeitpunkt (Auftragsvolumen, verfügbare Mitarbeiter, Saison etc.) — wichtig für Nachvollziehbarkeit und späteres Modell-Debugging |
| korrigiert_von_mitarbeiter_id | FK → mitarbeiter | NULL bei automatischer Berechnung, gesetzt bei `methode = "manuelle_korrektur"` |
| grund | TEXT | Nur bei manueller Korrektur relevant, z. B. "Instrument in sehr schlechtem Zustand, deutlich mehr Aufwand als Standardfall" |

**Ablauf bei manueller Korrektur:** Ein neuer Eintrag mit `methode = "manuelle_korrektur"` wird angelegt (der automatisch berechnete Wert bleibt als vorheriger Log-Eintrag erhalten, wird nicht überschrieben), und `auftrag.geschätzte_arbeitsstunden`/`geschätzte_kosten` werden auf den korrigierten Wert aktualisiert — das ist dann der für Dashboards und Kunden-Anzeige maßgebliche, aktuelle Wert.

**Wichtig für Stufe 2:** Eine manuelle Korrektur der *Schätzung* verändert nicht die späteren *Ist-Werte* (`arbeitszeiterfassung`, `auftrag.tatsächliche_kosten`) — diese werden weiterhin unabhängig aus der echten Bearbeitung erfasst. Die Trainingsdaten für das spätere ML-Modell bleiben dadurch unverfälscht.

---

### 2.11 `arbeitszeiterfassung`

Erfasst die tatsächlich aufgewendete Arbeitszeit je Auftrag — Grundlage für die Abrechnung und, unabhängig davon, ein präziseres Merkmal für die Terminschätzung als die reine Kalenderdauer: Ein Auftrag kann kalendarisch zwei Wochen dauern, aber nur drei Stunden reine Werkstattzeit umfassen (Rest ist Warten auf Ersatzteile, siehe `unterbrechung`). Für Stufe 2 ist die reine Arbeitszeit daher oft das aussagekräftigere Trainingsmerkmal als das Enddatum allein.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| auftrag_id | FK → auftrag | |
| mitarbeiter_id | FK → mitarbeiter | Falls mehrere Mitarbeiter am selben Auftrag gearbeitet haben, entsteht je Mitarbeiter ein eigener Eintrag |
| dauer_minuten | INT | Vom Mitarbeiter beim Abschluss eingegeben |
| erfasst_am | TIMESTAMP | Zeitpunkt der Eingabe (i. d. R. beim Setzen des Status "Fertig") |
| kommentar | TEXT | Optional, z. B. "davon 20 Min. Wartezeit auf Kleber-Trocknung" |

**Auslösender Workflow:** Setzt ein Mitarbeiter den Auftragsstatus auf "Fertig", fordert die Oberfläche verpflichtend die Eingabe der aufgewendeten Arbeitszeit an, bevor der Statuswechsel abgeschlossen wird (siehe Abschnitt 9.8). Bei mehreren Bearbeitungssitzungen (z. B. Unterbrechung durch Ersatzteilbestellung, danach Weiterarbeit) können auch mehrere Einträge über die Laufzeit des Auftrags entstehen — die Summe aller `dauer_minuten` je Auftrag ergibt die gesamte Bearbeitungszeit.

---

### 2.12 `mitarbeiter_arbeitszeit`

Vertraglich vereinbarte Wochenarbeitsstunden je Mitarbeiter — Grundlage der Kapazitätsplanung (Abschnitt 9.9). Als eigene Tabelle mit Gültigkeitszeitraum angelegt statt als einfaches Feld in `mitarbeiter`, damit Änderungen (z. B. Aufstockung von Teilzeit) nachvollziehbar bleiben und rückwirkende Auswertungen weiterhin den zum jeweiligen Zeitpunkt gültigen Wert verwenden.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| mitarbeiter_id | FK → mitarbeiter | |
| wochenstunden | DECIMAL | z. B. 35,0 |
| gültig_ab | DATE | |
| gültig_bis | DATE | NULL = aktuell gültig |
| geändert_von_mitarbeiter_id | FK → mitarbeiter | Wer die Änderung vorgenommen hat (Admin) |
| geändert_am | TIMESTAMP | |

**Pflege:** Ausschließlich über den Administrationsbereich durch die Systemrolle `admin` (siehe Berechtigungsmatrix, Abschnitt 7.2) — ein neuer Eintrag mit neuem `gültig_ab`-Datum schließt automatisch den vorherigen Eintrag ab (`gültig_bis` = Tag davor), statt den alten Wert zu überschreiben.

---

### 2.13 `mitarbeiter_qualifikation`

Hält fest, wofür ein Mitarbeiter durch Ausbildung oder Schulung qualifiziert ist. Wird anfangs von der Berechnungslogik noch nicht ausgewertet, ist aber ohne Mehraufwand mitgepflegt und später direkt nutzbar — z. B. um bei der Auftragszuweisung nur qualifizierte Mitarbeiter vorzuschlagen oder als zusätzliches Merkmal für die Stufe-2-Schätzung (erfahrene vs. neu qualifizierte Mitarbeiter brauchen bei derselben Reparaturart oft unterschiedlich lang).

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| mitarbeiter_id | FK → mitarbeiter | |
| reparaturart_id | FK → reparaturart | Optional — wofür die Qualifikation gilt |
| instrumentenklasse_id | FK → instrumentenklasse | Optional — alternativ oder zusätzlich auf Instrumentenklasse bezogen |
| bezeichnung | VARCHAR | z. B. "Zertifikat E-Gitarren-Elektronik", "Meisterkurs Blechblasinstrumente" |
| erworben_am | DATE | |
| gültig_bis | DATE | Optional, für Zertifikate mit Ablaufdatum — NULL = unbefristet |

**Zusammenhang mit Abwesenheit:** Die Schulung selbst (der Zeitraum, in dem der Mitarbeiter nicht für Reparaturen verfügbar ist) wird über `abwesenheit` mit `typ = "Schulung"` erfasst (siehe 2.3) — diese Tabelle hält nur das *Ergebnis* der Schulung fest, nicht den Abwesenheitszeitraum selbst.

---

### 2.14 `arbeitszeit_anpassung`

Bildet Gleitzeit-Ausgleich ab, ohne ein vollständiges Zeiterfassungssystem (Kommen/Gehen-Stempeluhr) bauen zu müssen — das wäre ein eigenes Thema jenseits des Auftragsmanagements. Stattdessen werden nur die Wochen-Abweichungen von der Regelarbeitszeit erfasst.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| mitarbeiter_id | FK → mitarbeiter | |
| woche_start_datum | DATE | Montag der betroffenen Woche |
| anpassung_stunden | DECIMAL | Positiv = mehr Kapazität diese Woche (z. B. `+5`), negativ = Ausgleichstag/-stunden (z. B. `-8`) |
| grund | VARCHAR | z. B. "Gleitzeitausgleich", "Vorarbeit vor Betriebsurlaub" |
| erfasst_von_mitarbeiter_id | FK → mitarbeiter | |
| erfasst_am | TIMESTAMP | |

**Aktueller Gleitzeitsaldo** eines Mitarbeiters ergibt sich bei Bedarf durch Summierung aller bisherigen Einträge — muss nicht separat als eigener Wert gepflegt werden. Wird anfangs von der Kapazitätsberechnung (Abschnitt 8) noch nicht zwingend einbezogen, lässt sich aber später als zusätzlicher Term in die Formel aufnehmen, ohne die Struktur zu ändern.

---

## 3. Beziehungsdiagramm (vereinfacht)

```mermaid
erDiagram
    KUNDE ||--o{ AUFTRAG : hat
    KUNDE ||--o{ INSTRUMENT : besitzt
    MITARBEITER ||--o{ AUFTRAG : bearbeitet
    MITARBEITER ||--o{ ABWESENHEIT : hat
    INSTRUMENTENKLASSE ||--o{ INSTRUMENT : klassifiziert
    INSTRUMENT ||--o{ AUFTRAG : betrifft
    REPARATURART ||--o{ AUFTRAG : ist
    REPARATURART ||--o{ REPARATUR_VORGABEWERT : hat
    INSTRUMENTENKLASSE ||--o{ REPARATUR_VORGABEWERT : verfeinert
    AUFTRAG ||--o{ AUFTRAG_STATUSVERLAUF : durchläuft
    STATUS ||--o{ AUFTRAG_STATUSVERLAUF : ist
    STATUS ||--o{ AUFTRAG : aktueller_status
    AUFTRAG ||--o{ UNTERBRECHUNG : hat
    AUFTRAG ||--o{ SCHÄTZUNGS_LOG : erhält
    AUFTRAG ||--o{ ARBEITSZEITERFASSUNG : hat
    MITARBEITER ||--o{ ARBEITSZEITERFASSUNG : erfasst
    MITARBEITER ||--o{ MITARBEITER_ARBEITSZEIT : hat
    MITARBEITER ||--o{ MITARBEITER_QUALIFIKATION : besitzt
    MITARBEITER ||--o{ ARBEITSZEIT_ANPASSUNG : hat
```

---

## 4. Stufe 1: Regelbasierte Berechnungslogik

**Umgesetzte Logik (Warteschlangen-Prinzip):**

```
vorlauf_stunden =
    Summe(geschätzte_arbeitsstunden aller offenen Aufträge desselben Mitarbeiters,
          die nach Priorität + Eingang vor diesem Auftrag stehen, siehe 9.4)
    (bei nicht zugewiesenem Auftrag: durchschnittliche offene Arbeit pro Mitarbeiter als Fallback)

benötigte_stunden = vorlauf_stunden + auftrag.geschätzte_arbeitsstunden (siehe 4.1)

verfügbare_stunden_pro_tag = mitarbeiter_arbeitszeit.wochenstunden / 5
    (Wochenenden, Betriebsschließungen, Feiertage und alle ganztägigen Abwesenheiten des
     Mitarbeiters – Urlaub, Krankheit, Schulung usw. – übersprungen;
     an Tagen mit abwesenheit.reduzierte_stunden gilt reduzierte_stunden / 5 statt der vollen
     Wochenstunden, höchstens jedoch die regulären Wochenstunden / 5)

geschätztes_fertigstellungsdatum = der Arbeitstag, an dem benötigte_stunden 
    durch tägliches Abarbeiten ab morgen aufgebraucht sind

geschätzte_bandbreite = ± 20 % der benötigten Arbeitstage, mindestens ± 1 Tag
```

`auftrag.geschätzte_arbeitsstunden` (die Grundlage für `benötigte_stunden`) wird wie in Abschnitt 4.1 beschrieben ermittelt: historischer Durchschnitt vergleichbarer abgeschlossener Aufträge, mit Fallback auf `reparatur_vorgabewert` (2.6a), solange zu wenig historische Daten vorliegen (Schwellenwert: 5 Vergleichsfälle).

**Neuberechnung ausgelöst bei:** Auftragserstellung, Änderung von Zuweisung oder Priorität (über `PATCH /auftraege/{id}`, nur Werkstattleiter/Admin). Jede Berechnung wird in `schätzungs_log` protokolliert, inkl. Anlass und allen verwendeten Zahlen (z. B. "13,50 Std. Vorlauf (4 Aufträge davor) + 0,50 Std., 8,00 Std./Tag, 2 Arbeitstage").

### 4.0a Bekannte vereinfachte Annahmen (Version 1)

Bewusste Vereinfachungen für den Start, festgehalten für spätere Überarbeitung:

- Pausierte Aufträge (siehe `unterbrechung`, 2.9) zählen voll zum Vorlauf mit; bereits geleistete Teilarbeit wird nicht vom Vorlauf abgezogen
- Ändert sich die Warteschlange eines Mitarbeiters (z. B. neuer Eilauftrag mit hoher Priorität schiebt sich davor), werden die Termine der anderen, bereits laufenden Aufträge desselben Mitarbeiters nicht automatisch neu berechnet
- Nach einer manuellen Korrektur der Stunden (4.2) wird der Termin nicht automatisch neu berechnet — die Werkstattleitung müsste das bei Bedarf manuell anstoßen (z. B. durch kurzes Ändern der Priorität)
- Ohne hinterlegte `mitarbeiter_arbeitszeit` gilt ein Standard-Fallback von 40 Wochenstunden



### 4.1 Kostenschätzung (analoges Vorgehen)

Dieselbe Fallback-Logik wird für die Kostenschätzung verwendet — Grundlage für `auftrag.geschätzte_kosten`:

```
geschätzte_kosten =
    durchschnitt(bisherige_ist_kosten WHERE instrumentenklasse = X AND reparaturart = Y)
    (falls ausreichend historische Fälle vorhanden)
  ODER
    reparatur_vorgabewert.vorgabe_kosten (instrumentenklassen-spezifisch, sonst allgemein)
    (als Fallback, solange zu wenig historische Daten vorliegen)
```

`bisherige_ist_kosten` bezieht sich auf `auftrag.tatsächliche_kosten` vergleichbarer, bereits abgerechneter Aufträge.

### 4.2 Manuelle Korrektur der Schätzung

Sowohl die automatisch berechneten Stunden als auch Kosten lassen sich manuell überschreiben — z. B. wenn ein Mitarbeiter beim Öffnen des Instruments feststellt, dass der Zustand deutlich schlechter ist als der Standardfall und mehr Aufwand nötig sein wird. Details zur technischen Umsetzung (Protokollierung, wer korrigieren darf) siehe `schätzungs_log` (2.10) und Berechtigungsmatrix (7.2). Wirkt sich eine Korrektur voraussichtlich auch auf den Fertigstellungstermin aus, sollte das dem Werkstattleiter auffallen (z. B. durch eine Markierung im Dashboard) — eine automatische Neuberechnung des Termins aus korrigierten Stunden ist möglich, aber kein Muss für den Start.

---

## 5. Übergang zu Stufe 2 (ML-Modell)

Sobald ausreichend abgeschlossene Aufträge vorliegen (Richtwert: mind. 200–300, besser mehr, pro relevanter Kombination aus Instrumentenklasse/Reparaturart mindestens ~20–30):

- **Zielgröße (Label):** wahlweise `tatsächliches_fertigstellungsdatum − erstellt_am` (Kalenderdauer, ggf. abzüglich `unterbrechung`-Zeiten) oder die Summe der `arbeitszeiterfassung.dauer_minuten` je Auftrag (reine Bearbeitungszeit) — Letztere ist präziser, da sie Wartezeiten auf Ersatzteile o. ä. automatisch ausklammert
- **Merkmale (Features):** Instrumentenklasse, Hersteller, Baujahr, Reparaturart, Komplexität, Mitarbeiter, aktuelles Auftragsvolumen zum Erstellzeitpunkt, Monat/Saison, Anzahl gleichzeitig abwesender Mitarbeiter, historische durchschnittliche Arbeitszeit für vergleichbare Kombinationen aus Instrumentenklasse/Reparaturart
- **Zweites Modell für Kostenschätzung:** Analog zur Terminschätzung lässt sich ein zweites, gleich aufgebautes Modell für `tatsächliche_kosten` trainieren (dieselben Merkmale, eigenes Label). Beide Modelle teilen sich Trainingsdaten und Infrastruktur, sind aber unabhängig — Genauigkeit bei der Terminschätzung sagt nichts über die Genauigkeit der Kostenschätzung aus
- **Modelltyp:** Gradient Boosting (z. B. XGBoost/LightGBM) oder einfache multiple Regression — beides deutlich transparenter als neuronale Netze und für diese Datenmenge völlig ausreichend
- **Ausgabe:** idealerweise ein Vorhersageintervall statt eines Einzelwerts (z. B. 10./90. Perzentil), damit das Kunden-Dashboard eine Bandbreite statt eines Fixdatums anzeigen kann
- **Re-Training:** periodisch (z. B. monatlich) auf Basis aller neu abgeschlossenen Aufträge

Weil `schätzungs_log` von Anfang an mitläuft, kannst du beim Wechsel zu Stufe 2 direkt vergleichen: "Wie gut hätte das Modell in der Vergangenheit vorhergesagt?" (Backtesting), bevor es live geschaltet wird.

---

## 6. Kundenauthentifizierung (Dashboard-Zugriff ohne Login)

Ziel: Kunden sollen ihren Auftragsstatus abrufen können, ohne ein Benutzerkonto anzulegen oder sich mit Passwort anzumelden — die Hürde muss aber trotzdem hoch genug sein, dass niemand fremde Auftragsdaten einsehen kann.

### 6.1 Warum Postleitzahl als zweiter Faktor ungeeignet ist

- **Zu kleiner Wertebereich:** In Deutschland gibt es nur ca. 8.200 Postleitzahlen — automatisiertes Durchprobieren (Brute-Force) ist ohne große Hürden möglich
- **Kein echtes Geheimnis:** Nachbarn, Kollegen oder Familienmitglieder kennen häufig dieselbe PLZ
- **Nicht änderbar:** Einmal in Verbindung mit einem Namen bekannt (z. B. aus einer anderen Datenpanne), bleibt sie dauerhaft schwach

Die Postleitzahl erhöht die Sicherheit gegenüber einer alleinigen Auftragsnummer zwar etwas, ersetzt aber kein echtes Geheimnis.

### 6.2 Gewählter Ansatz: Zugriffstoken

Auftragsnummer + `zugriffstoken` (siehe 2.7) bilden gemeinsam den Schlüssel zum Dashboard:

- Der Token wird bei Auftragsannahme **kryptografisch zufällig** erzeugt (nicht aus Datum, Auftragsnummer o. ä. ableitbar)
- Er wird auf dem Abgabebeleg gedruckt oder als QR-Code mitgegeben — ähnlich der Sendungsverfolgung bei Paketdiensten, ein Muster, das Kunden bereits kennen
- Die Kundennummer wird für den Dashboard-Zugriff nicht mehr benötigt, da Auftragsnummer + Token bereits ausreichend eindeutig und sicher sind

### 6.3 Alternative/Ergänzung: Magic Link per E-Mail

Falls ohnehin E-Mail-Adressen erfasst werden (z. B. für Fertigstellungsbenachrichtigungen), ist das die sicherste Variante:

- Kunde gibt nur die Auftragsnummer ein
- System sendet einen zeitlich begrenzten Link an die hinterlegte E-Mail-Adresse
- Kein Code zum Abtippen nötig, dafür Abhängigkeit vom Mailversand (SMTP) und vom Zugriff auf die Mails im jeweiligen Moment

Für die erste Version empfiehlt sich der Zugriffstoken (Abschnitt 6.2) als einfachere, sofort umsetzbare Lösung; der Magic-Link-Ansatz lässt sich später ergänzen, ohne das Datenmodell zu ändern.

### 6.4 Zusätzliche Schutzmaßnahmen (unabhängig vom gewählten Verfahren)

- **Rate Limiting:** z. B. nach 5 Fehlversuchen pro IP-Adresse kurzzeitig sperren, um automatisiertes Durchprobieren zu verhindern
- **Keine differenzierte Fehlermeldung:** "Auftragsnummer oder Code ungültig" statt anzuzeigen, welcher Teil falsch war — sonst lässt sich die Kombination stückweise erraten
- **HTTPS zwingend**, damit Auftragsnummer und Token nicht im Klartext übertragen werden
- **Datenminimierung im Dashboard:** nur Status und voraussichtlicher Fertigstellungstermin anzeigen, keine sensiblen Zusatzdaten wie vollständige Adresse oder Telefonnummer

---

## 7. Administrationsbereich

Der Administrationsbereich ist kein separates System, sondern ein zusätzlicher Bereich der internen Oberfläche, der nur für die Systemrollen `werkstattleiter` und `admin` sichtbar ist (siehe `mitarbeiter.systemrolle`, Abschnitt 2.2). Normale Mitarbeiter sehen ihn nicht.

### 7.1 Warum zwei unterschiedliche Rollen statt nur "Admin"?

In der Praxis sind das zwei unterschiedliche Verantwortungsbereiche, die nicht zwingend dieselbe Person betreffen müssen (z. B. wenn ein externer Dienstleister die Software technisch betreut, aber der Werkstattleiter den Tagesbetrieb steuert):

- **Werkstattleiter:** verantwortet den **operativen Betrieb** — wer arbeitet woran, wer ist wann abwesend, wie ist die Auslastung
- **Admin:** verantwortet die **technische/strukturelle Verwaltung** des Systems — welche Mitarbeiter-Accounts es gibt, welche Kategorien/Stammdaten zur Verfügung stehen

Ein Admin hat automatisch auch alle Rechte eines Werkstattleiters (Rollen sind kumulativ), aber nicht umgekehrt.

### 7.2 Berechtigungsmatrix

| Funktion | Mitarbeiter | Werkstattleiter | Admin |
|---|---|---|---|
| Eigene zugewiesene Aufträge einsehen/bearbeiten | ✅ | ✅ | ✅ |
| Alle Aufträge werkstattweit einsehen | ❌ | ✅ | ✅ |
| Aufträge einem Mitarbeiter zuweisen/umverteilen | ❌ | ✅ | ✅ |
| Geschätztes Fertigstellungsdatum manuell korrigieren | ❌ | ✅ | ✅ |
| Geschätzte Arbeitsstunden/Kosten für eigene zugewiesene Aufträge manuell korrigieren (mit Begründung) | ✅ | ✅ | ✅ |
| Abwesenheiten (Urlaub/Krankheit) für Mitarbeiter eintragen | ❌ | ✅ | ✅ |
| Betriebsweite Abwesenheit eintragen (z. B. Betriebsurlaub) | ❌ | ✅ | ✅ |
| Gleitzeit-Anpassung erfassen | ❌ | ✅ | ✅ |
| Mitarbeiter-Qualifikationen pflegen | ❌ | ❌ | ✅ |
| Wochenarbeitsstunden je Mitarbeiter festlegen | ❌ | ❌ | ✅ |
| Instrumentenklassen pflegen | ❌ | ❌ | ✅ |
| Reparaturarten + Standard-Komplexität pflegen | ❌ | ❌ | ✅ |
| Vorgabewerte (Dauer/Kosten) je Reparaturart pflegen | ❌ | ❌ | ✅ |
| Neue Mitarbeiter-Accounts anlegen | ❌ | ❌ | ✅ |
| Mitarbeiter deaktivieren | ❌ | ❌ | ✅ |
| Systemrollen vergeben (wer ist Werkstattleiter/Admin) | ❌ | ❌ | ✅ |
| Parameter der Stufe-1-Berechnungslogik anpassen (z. B. Komplexitätsfaktoren) | ❌ | ❌ | ✅ |
| Abfrage-Assistent für historische Erfahrungswerte nutzen (Abschnitt 8a) | ❌ | ✅ | ✅ |

In einer kleinen Werkstatt ist es üblich, dass der Werkstattleiter zusätzlich als Admin eingerichtet wird — die Trennung kostet dich beim Bauen kaum Mehraufwand (es ist im Kern eine zusätzliche Prüfung "ist systemrolle = admin?"), gibt dir aber die Flexibilität, es später sauber zu trennen, falls z. B. ein externer IT-Dienstleister die technische Pflege übernimmt.

### 7.3 Neue Tabelle: `system_ereignis_log`

Empfehlenswert, sobald mehrere Personen administrative Rechte haben — protokolliert sicherheitsrelevante Änderungen nachvollziehbar.

| Feld | Typ | Beschreibung |
|---|---|---|
| id | UUID / SERIAL | Primärschlüssel |
| ausgeführt_von_mitarbeiter_id | FK → mitarbeiter | |
| aktion | VARCHAR | z. B. "mitarbeiter_angelegt", "mitarbeiter_deaktiviert", "reparaturart_geändert", "rolle_geändert" |
| betroffene_entität | VARCHAR | z. B. "mitarbeiter", "reparaturart" |
| betroffene_id | UUID | ID des betroffenen Datensatzes |
| details | JSONB | Was genau geändert wurde (alter/neuer Wert) |
| zeitpunkt | TIMESTAMP | |

### 7.4 Funktionsübersicht des Administrationsbereichs

- **Mitarbeiterverwaltung** (nur Admin): Accounts anlegen, Systemrolle zuweisen, deaktivieren (nie hart löschen — sonst verwaisen vergangene Aufträge), Wochenarbeitsstunden festlegen (2.12), Qualifikationen pflegen (2.13)
- **Abwesenheitskalender** (Werkstattleiter + Admin): idealerweise als Kalenderansicht pro Mitarbeiter und für die gesamte Werkstatt, direkt verknüpft mit der `abwesenheit`-Tabelle (2.3, inkl. Typ "Schulung" und reduzierter Stunden) und damit unmittelbar wirksam für die Terminschätzung (Stufe 1) sowie die Kapazitätsplanung (Abschnitt 8)
- **Gleitzeit-Anpassungen** (Werkstattleiter + Admin): einzelne Wochen-Abweichungen erfassen (2.14), operativ genutzt, ohne vollständige Zeiterfassung
- **Stammdatenpflege** (nur Admin): Instrumentenklassen (2.4), Reparaturarten (2.6) inkl. Standardkomplexität, sowie Vorgabewerte für Dauer und Kosten je Reparaturart/Instrumentenklasse (2.6a)
- **Werkstattübersicht** (Werkstattleiter + Admin): alle laufenden Aufträge, Auslastung pro Mitarbeiter, überfällige/kritische Aufträge hervorgehoben
- **Änderungsprotokoll** (nur Admin einsehbar): Anzeige des `system_ereignis_log`

---

## 8. Kapazitätsplanung der Mitarbeiter

### 8.1 Grundprinzip

Statt einer detaillierten Tages-/Stundenplanung (wie sie klassische Schichtplanungs-Software macht) reicht für eine kleine Werkstatt ein einfacheres, wochenbasiertes Kapazitätsmodell, wie es Ressourcenplanungs-Tools wie Float, Resource Guru oder die "Workload"-Ansichten in Asana/monday.com verwenden: Jeder Mitarbeiter hat eine wöchentliche Kapazität in Stunden, davon wird abgezogen, was bereits durch Abwesenheiten und zugewiesene offene Aufträge gebunden ist. Das Ergebnis ist die freie Kapazität für neue Aufträge — ganz ohne Tages- oder Uhrzeit-genaue Planung.

### 8.2 Berechnungsformel

```
verfügbare_stunden(mitarbeiter, woche) =
    wochenstunden                                    (aus mitarbeiter_arbeitszeit, 2.12)
    − abwesenheitsstunden in dieser Woche             (aus abwesenheit, 2.3 — bei ganztägiger Abwesenheit
                                                       die Tagesstunden; bei reduzierter Verfügbarkeit die
                                                       Differenz wochenstunden − reduzierte_stunden, da
                                                       reduzierte_stunden die verfügbare Zahl ist)
    − Summe(geschätzte_arbeitsstunden aller zugewiesenen, noch offenen Aufträge)   (aus auftrag, 2.7)

auslastung_prozent = gebundene_stunden / wochenstunden * 100
```

Diese Berechnung läuft automatisch im Hintergrund und muss von niemandem manuell gepflegt werden — gepflegt werden nur die Grunddaten (Wochenstunden im Adminbereich, Abwesenheiten durch den Werkstattleiter, Aufträge durch Zuweisung).

**Spätere Erweiterung:** Sobald gewünscht, lässt sich die Formel um `± Summe(arbeitszeit_anpassung.anpassung_stunden)` für Gleitzeitausgleich (siehe 2.14) ergänzen, ohne die Grundstruktur zu ändern. Ebenso lässt sich `mitarbeiter_qualifikation` (2.13) später nutzen, um bei der Auftragszuweisung nur passend qualifizierte Mitarbeiter vorzuschlagen. Beide Tabellen sind bereits jetzt mitgepflegt, auch wenn die Berechnungslogik sie anfangs noch nicht auswertet — so entsteht kein Nachpflegeaufwand, wenn du sie später brauchst.

### 8.3 Warum keine feinere Tagesplanung nötig ist

Eine Reparaturwerkstatt hat in der Regel keine exakt terminierten Slots wie ein Frisör oder eine Arztpraxis — die Reihenfolge der Bearbeitung ergibt sich ohnehin aus Priorität und Auftragseingang (siehe Mitarbeiter-Dashboard, Abschnitt 9.4). Eine wochenweise Kapazitätsübersicht reicht daher aus, um zu erkennen: "Mitarbeiter X ist diese und nächste Woche schon voll ausgelastet, neue Aufträge besser an Mitarbeiter Y vergeben." Sollte sich später herausstellen, dass doch eine feinere Terminplanung nötig ist (z. B. bei Zusagen fester Abholtermine), lässt sich das Modell erweitern, ohne die Grundstruktur zu ändern.

---

## 8a. Abfrage-Assistent für historische Erfahrungswerte (spätere Erweiterung)

**Status:** Noch nicht umzusetzen — Voraussetzung ist die Berechnungslogik aus Abschnitt 4/4.1 sowie Login/Rollen (Abschnitt 7), da dies ein Werkstattleiter-Feature ist. Hier dokumentiert, damit die Kernberechnung von Anfang an so gebaut wird, dass sie sich später ohne Umbau wiederverwenden lässt.

### 8a.1 Zielbild

Der Werkstattleiter kann eine Frage in normaler Sprache stellen, z. B. *"Ich habe einen Saitenwechsel an einer Gibson vorzunehmen, gibt es hierzu Erfahrungswerte aus der Vergangenheit, wie hoch die Aufwände waren?"*, und erhält eine Antwort auf Basis echter historischer Daten aus der eigenen Werkstatt-Datenbank.

### 8a.2 Funktionsweise (kein "Erfinden" von Werten)

Der Ablauf hat drei getrennte Schritte, damit die Antwort immer auf echten Daten beruht und nicht auf plausibel klingenden, aber erfundenen Zahlen:

1. **Frage verstehen:** Ein Sprachmodell (Claude API) übersetzt die freie Texteingabe in strukturierte Suchkriterien (`reparaturart`, `instrumentenklasse`, ggf. `hersteller` — z. B. wird "Gibson" als Gitarrenhersteller erkannt und auf `instrumentenklasse = Gitarre` abgebildet)
2. **Echte Datenbankabfrage:** Mit diesen Kriterien wird dieselbe historische Durchschnittsberechnung ausgeführt, die auch für die automatische Kosten-/Terminschätzung genutzt wird (Abschnitt 4/4.1) — inklusive Fallzahl und ggf. Fallback auf `reparatur_vorgabewert`, falls zu wenig historische Daten vorliegen
3. **Antwort formulieren:** Erst mit dem echten Ergebnis aus Schritt 2 im Kontext formuliert das Sprachmodell eine natürlichsprachliche Antwort. Technisch über "Tool Use" der Anthropic-API umgesetzt — das Modell antwortet ausschließlich auf Basis des zurückgegebenen Datenbankergebnisses, nie aus eigenem, antrainiertem "Wissen"

### 8a.3 Wiederverwendbarkeit als Bauprinzip

Damit diese Erweiterung später ohne Umbau der Kernlogik möglich ist: Die Berechnungsfunktionen aus Abschnitt 4/4.1 (historischer Durchschnitt inkl. Fallback-Logik) sollten von Anfang an als eigenständige, aufrufbare Funktionen gebaut werden (nicht fest in einen einzelnen API-Endpunkt verwoben) — genau das ist bereits so beauftragt.

### 8a.4 Zugriff

Nur für die Systemrolle `werkstattleiter` und `admin` (siehe Berechtigungsmatrix, Abschnitt 7.2) — ergänzt dort als neue Zeile, sobald umgesetzt.

---

## 9. UI/UX-Richtlinien

Diese Regeln gelten seitenübergreifend für die gesamte Software (internes Dashboard, Administrationsbereich, Kunden-Dashboard), damit ein konsistentes und vorhersehbares Verhalten entsteht — unabhängig davon, wer welchen Teil später baut oder erweitert.

### 9.1 Formulare & Eingabemasken

- **Keine Popups/modale Dialoge** für Dateneingabe — Formulare sind eigene Seiten oder fest eingebettete Bereiche, keine Overlays
- **Inline-Validierung:** Fehler (Pflichtfeld leer, falsches Format) werden direkt am betroffenen Feld angezeigt, nicht als Dialog oder Sammel-Fehlermeldung am Seitenende
- **Speichern-Bestätigung:** Nach erfolgreichem Speichern erhält der Nutzer eine sichtbare, aber nicht blockierende Bestätigung (z. B. eine kurze Erfolgsmeldung/Toast am Bildschirmrand), kein Popup, das weggeklickt werden muss
- **Warnung bei ungespeicherten Änderungen:** Verlässt der Nutzer eine Seite mit ungespeicherten Änderungen (Navigation, Schließen), erscheint eine Rückfrage, ob er wirklich verlassen möchte

### 9.2 Navigation

- **Startseiten-Link oben links:** Auf jeder Seite führt ein fest positioniertes Element oben links zurück zur jeweiligen Startseite (Mitarbeiter zur Mitarbeiter-Übersicht, Werkstattleiter/Admin zu deren Dashboard, Kunde zur Statusabfrage)
- **Breadcrumbs** auf tieferliegenden Seiten (z. B. Auftrag-Detail), damit klar ist, wo man sich befindet
- **Kein hartes Löschen:** Aufträge, Mitarbeiter und Stammdaten werden nie endgültig gelöscht, sondern archiviert/deaktiviert — ein versehentlicher Klick soll nichts unwiederbringlich zerstören

### 9.3 Statusdarstellung

- **Farbe + Symbol/Label kombiniert**, nie Farbe allein — wichtig für Lesbarkeit und Barrierefreiheit (z. B. Farbfehlsichtigkeit)
- **Feste, durchgängige Farbzuordnung** pro Status (z. B. Grau = Angenommen, Blau = In Bearbeitung, Orange = Wartet auf Ersatzteil, Grün = Fertig)
- **Überfällige Aufträge** (geschätztes Fertigstellungsdatum überschritten, noch nicht fertig) werden sofort optisch hervorgehoben, ohne dass man den Auftrag öffnen muss
- **Priorisierte Aufträge** (`priorität = hoch`, siehe 2.7) werden zusätzlich visuell markiert (z. B. Kennzeichnung/Icon in der Liste)

### 9.4 Mitarbeiter-Dashboard

- Übersicht der dem Mitarbeiter zugewiesenen aktuellen Aufträge
- Standard-Sortierung: zuerst nach `priorität` (hoch vor normal), innerhalb gleicher Priorität nach Auftragseingang (`erstellt_am`, älteste zuerst)
- Nutzer kann die Sortierung umschalten (z. B. zusätzlich nach geschätztem Fertigstellungsdatum)
- Ein Klick führt direkt zur Auftragsdetailseite (Statuswechsel, Notizen)

### 9.5 Werkstattleiter-Dashboard

- **Gesamtübersicht** aller Aufträge werkstattweit, nicht nur eigene
- Kennzahlen auf einen Blick: Anzahl offener, abgeschlossener und pausierter Aufträge (pausiert = Aufträge mit aktiver `unterbrechung`, siehe 2.9)
- Auslastung pro Mitarbeiter (Anzahl zugewiesener offener Aufträge)
- Überfällige und priorisierte Aufträge separat hervorgehoben/filterbar
- Von hier aus direkter Zugriff auf Umverteilung von Aufträgen und den Administrationsbereich (sofern Rolle `admin`)

### 9.6 Design-System (Farbgebung & Anmutung)

Festgelegt, bevor die UI überarbeitet wird — danach konsequent einzuhalten, damit keine Seite optisch aus der Reihe fällt. Bewusst am Thema Musikinstrumenten-Werkstatt orientiert statt an einer generischen Software-Optik.

**Prinzip:** Werkstatt-Logbuch, keine Software-Demo. Ruhig, materialbezogen, funktional — die interne Oberfläche ist ein Arbeitswerkzeug (datendicht, klar), das Kunden-Dashboard bewusst ruhiger und einfacher.

**Farbpalette:**

| Rolle | Wert | Verwendung |
|---|---|---|
| Hintergrund | `#FAF8F4` | Seitenhintergrund |
| Text/Grundfarbe | `#2B2420` | Fließtext, Standard-UI-Text |
| Primärakzent | `#8A6D3B` (gedecktes Messing) | Primäre Buttons, Links, aktive Navigation |
| Sekundärakzent / Erfolg | `#4B6B4F` (gedämpftes Fichtengrün) | Status "Fertig", Erfolgsmeldungen |
| Warnung/Überfällig | `#B23A34` (gedecktes Rot) | Überfällige Aufträge, Gefahren-Aktionen (z. B. Archivieren) |
| Neutral/Rand | `#D9D2C7` | Trennlinien, Tabellenränder |

**Statusfarben (Auftragsstatus, Abschnitt 9.3):**

| Status | Farbe | Symbol |
|---|---|---|
| Angenommen | Grau `#8A8378` | ○ |
| In Bearbeitung | Blau `#4A6FA5` | ◐ |
| Wartet auf Ersatzteil | Orange `#C97F2E` | ⏸ |
| Qualitätsprüfung | Violett `#6B5B8A` | ◑ |
| Fertig | Grün `#4B6B4F` | ✓ |
| Abgeholt | Dunkles Neutral `#5E554C` | ● |
| Überfällig (zusätzliche Markierung, kein eigener Status) | Rot `#B23A34` | ⚠ |

**Typografie:**
- UI-Schrift (Tabellen, Formulare, Fließtext): *Inter* — funktional, sehr gut lesbar bei kleinen Größen
- Auszeichnungsschrift (Seitentitel, Werkstattname im Header): *Fraunces* — wärmer, mit handwerklichem Charakter, ausschließlich für Titel, nicht für datendichte Bereiche
- Typskala: 12 / 14 / 16 / 20 / 28 / 36 px, Zeilenhöhe 1,5 für Fließtext

**Layout:**
- Interne Oberfläche (Mitarbeiter/Werkstattleiter/Admin): feste linke Seitenleiste mit Navigation (erfüllt zugleich die Regel "Startseite oben links erreichbar", Abschnitt 9.2), Inhalt datendicht und linksbündig, Tabellenzeilen mit klaren Trennlinien statt einheitlicher Card-Kacheln mit Schlagschatten
- Kunden-Dashboard: einspaltig, zentriert, großzügiger Weißraum, ruhiger — andere Zielgruppe (kein Fachpersonal), anderer Zweck (kurzer Statuscheck statt Arbeiten)

**Bewusst vermieden** (typische generische/KI-Standardoptik): warmes Creme mit Terracotta-Akzent, identische abgerundete Karten mit gleichem grauem Schlagschatten überall, ALL-CAPS-Eyebrow-Labels über Überschriften, Pfeile (→) an Buttons/Links.

**Weitere feste Regeln:**
- Abstands-/Rastersystem: 4-px-Basis (4, 8, 12, 16, 24, 32, 48 px) statt beliebiger Pixelwerte
- Einheitliches Datumsformat: `TT.MM.JJJJ`
- Button-Stile: Primär (Messing, gefüllt) für Hauptaktion pro Seite, Sekundär (Umriss) für Nebenaktionen, Gefahren-Aktion (Rot, z. B. "Archivieren") optisch klar abgesetzt
- Eckenradius durchgängig 4 px (klein, nicht das stark abgerundete "SaaS-Card"-Aussehen)

### 9.7 Weitere Empfehlungen

- **Responsives Design statt Geräteerkennung:** Die Oberfläche passt sich automatisch an die verfügbare Bildschirmgröße an (responsives Layout auf Basis von CSS-Regeln für Breakpoints), statt aktiv zu erkennen, ob ein Tablet oder PC zugreift. Das ist der technisch robustere und heute übliche Standardansatz — eine echte Geräteerkennung ist unzuverlässig (z. B. bei Tablets mit angeschlossener Tastatur oder Convertible-Laptops) und pflegeintensiver. Ergebnis für den Nutzer ist dasselbe: großzügigere Klickflächen und angepasstes Layout auf kleineren/Touch-Bildschirmen, kompaktere, dichtere Darstellung auf großen PC-Bildschirmen — ohne dass man dafür getrennte Versionen der Seite bauen oder pflegen muss
- **Touch-Freundlichkeit als Teil davon:** ausreichend große Klickflächen, keine winzigen Icons, größere Abstände zwischen klickbaren Elementen auf schmaleren/Touch-Bildschirmen
- **Druckansicht für den Abgabebeleg:** eigene, aufs Drucken optimierte Seite mit Auftragsnummer, Zugriffstoken/QR-Code (siehe Abschnitt 6) und den wichtigsten Auftragsdaten
- **Leere Zustände klar kommunizieren:** z. B. "Keine offenen Aufträge" statt einer leeren, irritierenden Liste
- **Ladezustände sichtbar machen:** kurze Ladeanzeige statt eingefroren wirkender Seite bei längeren Abfragen
- **Suchen/Filtern** in allen Listenansichten, insbesondere der Auftragsliste, sobald diese im echten Betrieb wächst: Filter nach Status, Mitarbeiter, Instrumentenklasse, Priorität, plus eine Freitext-Suche über Kundenname und Auftragsnummer (siehe auch Abschnitt 10, Punkt 6a)
- **Barrierefreiheit (Kontrast, Tastaturbedienbarkeit):** insbesondere für den internen Bereich sinnvoll, falls künftig auch weniger technikaffine oder ältere Mitarbeiter damit arbeiten

### 9.8 Auftragsabschluss (Pflicht-Zeiterfassung)

- Setzt ein Mitarbeiter den Status eines Auftrags auf "Fertig", öffnet sich kein Popup, sondern ein fest eingebettetes Eingabefeld im selben Ablauf, das die aufgewendete Arbeitszeit (`arbeitszeiterfassung.dauer_minuten`, siehe 2.11) abfragt
- Der Abschluss lässt sich erst bestätigen, wenn die Arbeitszeit eingetragen ist — passend zur allgemeinen Regel "Seite nicht verlassen ohne vollständige/gespeicherte Daten" (9.1)
- Eingabe möglichst einfach halten (z. B. Stunden **und/oder** Minuten, keine Pflicht zu sekundengenauer Erfassung)
- Nach dem Speichern erscheint dieselbe nicht-blockierende Erfolgsbestätigung wie bei anderen Speichervorgängen (9.1), z. B. "Auftrag abgeschlossen, Arbeitszeit erfasst"

### 9.9 Kapazitäts-Dashboard (Werkstattleiter/Admin)

Umsetzung der Kapazitätsplanung aus Abschnitt 8 als einfache, wöchentliche Balkenansicht — dem Muster gängiger Ressourcenplanungs-Tools (Float, Resource Guru) folgend:

- Eine Zeile pro Mitarbeiter, eine Spalte pro Woche (aktuelle Woche + einige Wochen im Voraus)
- Je Zeile/Woche ein horizontaler Balken, der sich proportional zur Auslastung füllt, farblich abgestuft (z. B. grün < 80 %, gelb 80–100 %, rot > 100 % = überbucht)
- Klick auf eine Zelle zeigt Details: welche Aufträge sind zugewiesen, welche Abwesenheit liegt vor
- Von hier aus direkter Sprung zur Auftragsumverteilung (bei Überbuchung) oder zur Abwesenheitspflege
- Bewusst **keine** Tages- oder Uhrzeit-genaue Planung (siehe Begründung in Abschnitt 8.3) — das hält die Ansicht einfach und für den Werkstattleiter auf einen Blick erfassbar

---

## 10. Nächste Schritte

1. Tabellen als PostgreSQL-Schema anlegen (kann ich dir als SQL-DDL ausformulieren)
2. Design-System festlegen (Farben, Typografie, Statusfarben — Abschnitt 9.6), bevor die erste UI-Seite gebaut wird
3. Backend-Endpunkte für Auftragserstellung, Statuswechsel, Mitarbeiterzuordnung
4. Login/Authentifizierung + Berechtigungsprüfung nach `systemrolle` implementieren
5. Stufe-1-Berechnungslogik implementieren
6. Internes Dashboard (Mitarbeitersicht) gemäß Abschnitt 9.4
6a. Filter (Status, Mitarbeiter, Instrumentenklasse, Priorität) und Freitext-Suche (Kundenname, Auftragsnummer) für die Auftragsliste — noch nicht dringend bei wenigen Test-Aufträgen, aber sobald der echte Auftragsbestand wächst, wird die Liste sonst unübersichtlich (siehe Abschnitt 9.7)
7. Administrationsbereich (Werkstattleiter- und Admin-Ansicht gemäß Berechtigungsmatrix in Abschnitt 7, Werkstattleiter-Dashboard gemäß 9.5, Kapazitäts-Dashboard gemäß 8 und 9.9)
8. Kunden-Dashboard (Auftragsnummer + Zugriffstoken gemäß Abschnitt 6)
9. Abfrage-Assistent für historische Erfahrungswerte (Abschnitt 8a) — nach Login/Rollen
10. Erst nach einigen Monaten Echtbetrieb: Stufe 2 evaluieren

"""Vorgabewerte für Blechblasinstrumente (Stand der Erfassung: Oktober 2026).

Quelle: Preisliste Reisser Musik, Meisterwerkstatt für Blasinstrumente. Die Stunden sind aus
den Preisen abgeleitet (Preis ÷ 45 €, gerundet auf 0,25 Std.). Der Stundensatz von 45 €/Std.
stammt aus dem "ab 45 €"-Richtwert der Quelle und wurde gegen branchenübliche Gehaltsdaten
plausibilisiert. Das ist keine verbindliche Kalkulation, nur eine erste Orientierung für die
Werkstatt – sobald genug eigene abgeschlossene Aufträge vorliegen, rechnet die Schätzung
ohnehin mit dem eigenen historischen Durchschnitt (Datenmodell Abschnitt 4).

Abgrenzung (Datenmodell 2.6a): Ein echtes anderes Instrument (andere Bauform/Tonlage) ist eine
eigene Instrumentenklasse. Eine reine Ausführungsvariante desselben Instruments (Oberfläche,
Ventilmechanik) ist KEINE eigene Klasse, sondern eine `ausfuehrung` am Vorgabewert – deshalb
gibt es eine Klasse "Trompete" mit vier Ausführungen und eine Klasse "Flügelhorn/Kornett" mit zwei.
Die Standardausführung (ausfuehrung = NULL) ist jeweils "Perinet, lackiert".

"Generalüberholung" bekommt bewusst keinen Vorgabewert (nur individuelles Angebot).

Die Funktion `anlegen` ist beliebig oft aufrufbar: Sie legt nur an, was fehlt, und überschreibt
nichts, was es schon gibt (auch nichts, was inzwischen von Hand geändert oder archiviert wurde).
Aufgerufen wird sie von der Migration `blechblas_vorgabewerte`.
"""

from sqlalchemy import Connection, text

OBERKATEGORIE = "Blechblasinstrument"  # Schreibweise wie bei den vorhandenen Klassen (Einzahl)
STUNDENSATZ = "45"  # €/Std., als Werkstatt-Einstellung "stundensatz" (7.5)
QUELLE = "Quelle: Preisliste Reisser Musik (Stand 10/2026), Stunden = Preis ÷ 45 €"
AB_PREIS = "„ab“-Preis, tatsächlicher Aufwand variiert. " + QUELLE
STANDARD = None  # Standardausführung

# Bezeichnung → Standard-Komplexität
REPARATURARTEN = {"Reinigung": 2, "Überholung": 3}

# Instrumentenklasse → Ausführung → ((Stunden, Euro) für Reinigung, (Stunden, Euro) für Überholung)
VORGABEWERTE: dict[str, dict[str | None, tuple[tuple[str, str], tuple[str, str]]]] = {
    "Trompete": {
        STANDARD: (("1.75", "80"), ("2.25", "105")),  # Perinet, lackiert
        "Perinet, versilbert": (("3.50", "155"), ("4.75", "219")),
        "Drehventile, lackiert": (("3.00", "130"), ("4.00", "185")),
        "Drehventile, versilbert": (("3.75", "165"), ("5.50", "250")),
    },
    "Flügelhorn/Kornett": {
        STANDARD: (("1.75", "80"), ("2.25", "105")),  # Perinet, lackiert
        "Drehventile, lackiert": (("3.00", "130"), ("4.00", "185")),
    },
    "Waldhorn": {STANDARD: (("3.00", "130"), ("4.00", "185"))},
    "Doppelhorn": {STANDARD: (("3.75", "169"), ("5.25", "235"))},
    "Tenorhorn/Bariton (3 Ventile)": {STANDARD: (("3.25", "145"), ("4.75", "210"))},
    "Tenorhorn/Bariton (4 Ventile)": {STANDARD: (("3.75", "169"), ("5.25", "235"))},
    "Euphonium (ohne Kompensation)": {STANDARD: (("2.50", "115"), ("3.50", "159"))},
    "Euphonium (mit Kompensation)": {STANDARD: (("3.50", "159"), ("4.75", "209"))},
    "Tenorposaune": {STANDARD: (("1.75", "80"), ("1.00", "45"))},
    "Tenorposaune mit Quartventil": {STANDARD: (("2.50", "109"), ("1.00", "45"))},
    "Bassposaune (2 Ventile)": {STANDARD: (("2.75", "125"), ("1.00", "45"))},
    "F-Tuba (5/6 Ventile)": {STANDARD: (("5.50", "245"), ("8.25", "369"))},
    "Es-Tuba (4 Ventile)": {STANDARD: (("5.00", "225"), ("7.25", "329"))},
    "B-Tuba (3 Ventile)": {STANDARD: (("4.75", "209"), ("6.75", "300"))},
    "B-Tuba (4 Ventile)": {STANDARD: (("5.00", "225"), ("7.25", "329"))},
}
# Bei den Posaunen nennt die Quelle für die Überholung nur einen "ab"-Preis
UEBERHOLUNG_AB_PREIS = {"Tenorposaune", "Tenorposaune mit Quartventil", "Bassposaune (2 Ventile)"}
STANDARD_IST = "Standardausführung: Perinet, lackiert. "  # Notiz bei Klassen mit mehreren Ausführungen


def anlegen(verbindung: Connection) -> dict[str, int]:
    """Legt Fehlendes an und gibt zurück, wie viel neu entstanden ist."""
    neu = {"reparaturarten": 0, "instrumentenklassen": 0, "vorgabewerte": 0, "einstellungen": 0}

    for bezeichnung, komplexitaet in REPARATURARTEN.items():
        neu["reparaturarten"] += verbindung.execute(text(
            "INSERT INTO reparaturart (bezeichnung, standard_komplexitaet) SELECT CAST(:b AS varchar), CAST(:k AS smallint) "
            "WHERE NOT EXISTS (SELECT 1 FROM reparaturart WHERE bezeichnung = CAST(:b AS varchar))"
        ), {"b": bezeichnung, "k": komplexitaet}).rowcount

    for bezeichnung in VORGABEWERTE:  # "Trompete" gibt es in der Regel schon – dann bleibt sie, wie sie ist
        neu["instrumentenklassen"] += verbindung.execute(text(
            "INSERT INTO instrumentenklasse (bezeichnung, oberkategorie) SELECT CAST(:b AS varchar), CAST(:o AS varchar) "
            "WHERE NOT EXISTS (SELECT 1 FROM instrumentenklasse WHERE bezeichnung = CAST(:b AS varchar))"
        ), {"b": bezeichnung, "o": OBERKATEGORIE}).rowcount

    # Vorgabewert nur, wenn es für Reparaturart + Klasse + Ausführung noch gar keinen gibt (auch keinen archivierten)
    for klasse, je_ausfuehrung in VORGABEWERTE.items():
        for ausfuehrung, werte in je_ausfuehrung.items():
            for reparaturart, (stunden, kosten) in zip(REPARATURARTEN, werte):
                notiz = AB_PREIS if reparaturart == "Überholung" and klasse in UEBERHOLUNG_AB_PREIS else QUELLE
                if ausfuehrung is STANDARD and len(je_ausfuehrung) > 1:
                    notiz = STANDARD_IST + notiz
                neu["vorgabewerte"] += verbindung.execute(text(
                    "INSERT INTO reparatur_vorgabewert "
                    "  (reparaturart_id, instrumentenklasse_id, ausfuehrung, vorgabe_stunden, vorgabe_kosten, notiz) "
                    "SELECT r.id, k.id, CAST(:a AS varchar), CAST(:stunden AS numeric), CAST(:kosten AS numeric), CAST(:notiz AS text) "
                    "FROM reparaturart r, instrumentenklasse k "
                    "WHERE r.bezeichnung = :r AND k.bezeichnung = :k AND NOT EXISTS ("
                    "  SELECT 1 FROM reparatur_vorgabewert v WHERE v.reparaturart_id = r.id AND v.instrumentenklasse_id = k.id"
                    "  AND v.ausfuehrung IS NOT DISTINCT FROM CAST(:a AS varchar))"
                ), {"r": reparaturart, "k": klasse, "a": ausfuehrung, "stunden": stunden, "kosten": kosten, "notiz": notiz}).rowcount

    neu["einstellungen"] += verbindung.execute(text(
        "INSERT INTO einstellung (schluessel, wert) SELECT 'stundensatz', CAST(:w AS varchar) "
        "WHERE NOT EXISTS (SELECT 1 FROM einstellung WHERE schluessel = 'stundensatz')"
    ), {"w": STUNDENSATZ}).rowcount
    return neu

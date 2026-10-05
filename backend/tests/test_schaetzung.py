"""Tests der Stufe-1-Schätzung (Datenmodell 4 / 4.1) mit Beispieldaten.

Beispiel-Werkstatt: Reparaturart "Saitenwechsel", Instrumentenklassen
"Kontrabass" (um die es geht) und "Violine" (darf nie mitgezählt werden).
Vorgabewerte: allgemein 0,5 Std. / 20 €, speziell Kontrabass 1,5 Std. / 60 €.
"""

from decimal import Decimal

import pytest

from app.schaetzung import MINDESTANZAHL_VERGLEICHSFAELLE, Quelle, schaetze_arbeitsstunden
from tests.beispieldaten import Werkstatt


@pytest.fixture
def w(db):
    werkstatt = Werkstatt(db)
    werkstatt.vorgabe(stunden="0.50", kosten="20.00")                       # allgemein
    werkstatt.vorgabe(werkstatt.kontrabass, stunden="1.50", kosten="60.00")  # Kontrabass
    return werkstatt


def test_schwelle_ist_fuenf():
    assert MINDESTANZAHL_VERGLEICHSFAELLE == 5


# --- Arbeitsstunden ---------------------------------------------------------

def test_stunden_genug_historische_daten(w):
    # 5 abgeschlossene Kontrabass-Aufträge: 60, 90, 120, 60+60 (zwei Sitzungen), 150 Min.
    for minuten in [(60,), (90,), (120,), (60, 60), (150,)]:
        w.auftrag(minuten=minuten, status=w.abgeholt if minuten == (150,) else w.fertig)

    s = w.stunden()
    assert s.quelle == Quelle.historisch
    assert s.anzahl_vergleichsfaelle == 5
    assert s.wert == Decimal("1.80")  # (60+90+120+120+150)/5 = 108 Min. = 1,8 Std.


def test_stunden_zu_wenig_daten_fallback_instrumentenklasse(w):
    for minuten in [(600,), (600,), (600,), (600,)]:  # nur 4 abgeschlossene
        w.auftrag(minuten=minuten)

    s = w.stunden()
    assert s.quelle == Quelle.vorgabe_instrumentenklasse
    assert s.anzahl_vergleichsfaelle == 4
    assert s.wert == Decimal("1.50")


def test_stunden_zaehlt_nur_passende_abgeschlossene_auftraege_mit_zeiterfassung(w):
    for _ in range(4):
        w.auftrag(minuten=(60,))                           # zählt
    w.auftrag(minuten=(60,), status=w.in_bearbeitung)       # nicht abgeschlossen
    w.auftrag(minuten=())                                   # keine Zeiterfassung
    w.auftrag(minuten=(60,), klasse=w.violine)              # andere Instrumentenklasse

    s = w.stunden()
    assert s.anzahl_vergleichsfaelle == 4
    assert s.quelle == Quelle.vorgabe_instrumentenklasse


def test_stunden_fallback_allgemein_ohne_spezifischen_wert(db):
    w = Werkstatt(db)
    w.vorgabe(stunden="0.50")  # nur allgemeiner Wert

    s = w.stunden()
    assert (s.quelle, s.wert, s.anzahl_vergleichsfaelle) == (Quelle.vorgabe_allgemein, Decimal("0.50"), 0)


def test_stunden_keine_daten_keine_vorgabe(db):
    s = Werkstatt(db).stunden()
    assert (s.quelle, s.wert) == (Quelle.keine, None)


# --- Kosten -----------------------------------------------------------------

def test_kosten_genug_historische_daten(w):
    for kosten in ["50.00", "55.00", "60.00", "65.00", "70.50"]:
        w.auftrag(kosten=kosten)

    s = w.kosten()
    assert s.quelle == Quelle.historisch
    assert s.anzahl_vergleichsfaelle == 5
    assert s.wert == Decimal("60.10")  # 300,50 / 5


def test_kosten_zu_wenig_daten_fallback_instrumentenklasse(w):
    for kosten in ["999.00"] * 4:  # nur 4 abgerechnete
        w.auftrag(kosten=kosten)
    w.auftrag(kosten=None)                              # abgeschlossen, aber nicht abgerechnet
    w.auftrag(kosten="999.00", status=w.in_bearbeitung)  # nicht abgeschlossen
    w.auftrag(kosten="999.00", klasse=w.violine)         # andere Instrumentenklasse

    s = w.kosten()
    assert s.quelle == Quelle.vorgabe_instrumentenklasse
    assert s.anzahl_vergleichsfaelle == 4
    assert s.wert == Decimal("60.00")


def test_kosten_fallback_allgemein_ohne_spezifischen_wert(db):
    w = Werkstatt(db)
    w.vorgabe(kosten="20.00")

    s = w.kosten()
    assert (s.quelle, s.wert) == (Quelle.vorgabe_allgemein, Decimal("20.00"))


def test_kosten_keine_daten_keine_vorgabe(db):
    s = Werkstatt(db).kosten()
    assert (s.quelle, s.wert) == (Quelle.keine, None)


# --- Ausführung des Instruments (Abschnitt 4, zwei Reihenfolgen; Ausführungen je Klasse 2.4b) ---

@pytest.fixture
def a(w, db):
    """Der Kontrabass bekommt Ausführungen: Der bisher einzige Wert (1,5 Std. / 60 €) gehört zum Standard "natur",
    dazu "versilbert" (3 Std. / 120 €) und "lackiert" (2 Std. / 80 €)."""
    from sqlalchemy import select
    from app.models import ReparaturVorgabewert
    natur = w.ausfuehrung("natur", standard=True)
    db.scalar(select(ReparaturVorgabewert).where(ReparaturVorgabewert.instrumentenklasse_id == w.kontrabass.id)).ausfuehrung_id = natur.id
    versilbert, lackiert = w.ausfuehrung("versilbert"), w.ausfuehrung("lackiert")
    w.vorgabe(w.kontrabass, stunden="3.00", kosten="120.00", ausfuehrung=versilbert)
    w.vorgabe(w.kontrabass, stunden="2.00", kosten="80.00", ausfuehrung=lackiert)
    return {"natur": natur, "versilbert": versilbert, "lackiert": lackiert}


def test_durchschnitt_bleibt_je_ausfuehrung_getrennt(w, a):
    for _ in range(5):
        w.auftrag(minuten=(240,), kosten="200.00", ausfuehrung=a["versilbert"])
    for _ in range(4):
        w.auftrag(minuten=(60,), kosten="40.00", ausfuehrung=a["lackiert"])

    # versilbert: 5 eigene Fälle → eigener Durchschnitt, die lackierten zählen nicht mit
    s, k = w.stunden(a["versilbert"]), w.kosten(a["versilbert"])
    assert (s.quelle, s.wert, k.quelle, k.wert) == (Quelle.historisch, Decimal("4.00"), Quelle.historisch, Decimal("200.00"))
    # lackiert: nur 4 eigene Fälle → Richtpreis dieser Ausführung, obwohl es in der Klasse 9 Fälle gibt
    s, k = w.stunden(a["lackiert"]), w.kosten(a["lackiert"])
    assert (s.quelle, s.wert, s.anzahl_vergleichsfaelle) == (Quelle.vorgabe_instrumentenklasse, Decimal("2.00"), 4)
    assert (k.quelle, k.wert) == (Quelle.vorgabe_instrumentenklasse, Decimal("80.00"))
    # Unbekannte Ausführung: alle 9 Fälle der Klasse
    assert (w.stunden().quelle, w.stunden().anzahl_vergleichsfaelle) == (Quelle.historisch, 9)
    # Bewusst eingetragener Standard ist etwas anderes als unbekannt: keine eigene Historie → sein Richtpreis
    assert (w.stunden(a["natur"]).quelle, w.stunden(a["natur"]).wert) == (Quelle.vorgabe_instrumentenklasse, Decimal("1.50"))


def test_reihenfolge_der_vorgabewerte(w, a, db):
    vergoldet = w.ausfuehrung("vergoldet")                                  # Ausführung ohne eigenen Richtpreis
    assert w.stunden(vergoldet).wert == Decimal("1.50")                     # → Richtpreis des Standards
    assert w.stunden().wert == Decimal("1.50") and w.kosten().wert == Decimal("60.00")   # unbekannt → Standard
    assert w.stunden(a["versilbert"]).wert == Decimal("3.00") and w.kosten(a["versilbert"]).wert == Decimal("120.00")
    # Klasse ohne Ausführungen: ihr einziger Wert bzw. der allgemeine
    assert schaetze_arbeitsstunden(db, w.violine.id, w.saitenwechsel.id).quelle == Quelle.vorgabe_allgemein
    w.vorgabe(w.violine, stunden="0.75", kosten="30.00")
    assert schaetze_arbeitsstunden(db, w.violine.id, w.saitenwechsel.id).wert == Decimal("0.75")
    # Die Ausführung einer anderen Klasse spielt für die Violine keine Rolle
    assert schaetze_arbeitsstunden(db, w.violine.id, w.saitenwechsel.id, a["versilbert"].id).wert == Decimal("0.75")


def test_archivierte_ausfuehrung_wird_ignoriert_und_gilt_als_unbekannt(w, a, db):
    """2.4b: Ihre Richtpreise zählen nicht mehr; ein Instrument mit dieser Ausführung wird wie "unbekannt" geschätzt."""
    from sqlalchemy import func
    for _ in range(5):
        w.auftrag(minuten=(240,), kosten="200.00", ausfuehrung=a["versilbert"])
    assert w.stunden(a["versilbert"]).quelle == Quelle.historisch
    a["versilbert"].archiviert_am = func.clock_timestamp()
    db.flush()
    db.expire_all()
    # wie unbekannt: Historie der ganzen Klasse (dieselben 5 Aufträge), nicht mehr "nur versilbert"
    assert (w.stunden(a["versilbert"]).quelle, w.stunden(a["versilbert"]).anzahl_vergleichsfaelle) == (Quelle.historisch, 5)
    assert w.stunden(a["lackiert"]).wert == Decimal("2.00")
    # Wird der Standard selbst archiviert, bleibt für Unbekannte nur der allgemeine Wert
    a["natur"].archiviert_am = func.clock_timestamp()
    db.flush()
    db.expire_all()
    assert w.stunden(a["lackiert"]).wert == Decimal("2.00")
    assert w.kosten(a["natur"]).quelle == w.kosten().quelle == Quelle.historisch       # beide wie unbekannt

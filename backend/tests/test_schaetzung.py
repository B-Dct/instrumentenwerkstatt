"""Tests der Stufe-1-Schätzung (Datenmodell 4 / 4.1) mit Beispieldaten.

Beispiel-Werkstatt: Reparaturart "Saitenwechsel", Instrumentenklassen
"Kontrabass" (um die es geht) und "Violine" (darf nie mitgezählt werden).
Vorgabewerte: allgemein 0,5 Std. / 20 €, speziell Kontrabass 1,5 Std. / 60 €.
"""

from decimal import Decimal

import pytest

from app.schaetzung import MINDESTANZAHL_VERGLEICHSFAELLE, Quelle
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

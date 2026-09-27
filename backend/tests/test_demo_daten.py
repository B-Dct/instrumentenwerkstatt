"""Tests für das Beispieldaten-Skript.

Die Tests dürfen nicht davon abhängen, ob die Demo-Daten in der echten Datenbank schon
angelegt sind: Jeder Test startet deshalb mit "entfernen" (wird wie alles andere am
Testende zurückgerollt – die echten Daten bleiben unberührt).
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app import demo_daten
from app.models import Auftrag, Instrument, Instrumentenklasse, Kunde, Mitarbeiter, Reparaturart, ReparaturVorgabewert
from app.schaetzung import Quelle, schaetze_arbeitsstunden, schaetze_kosten
from tests.beispieldaten import Werkstatt


@pytest.fixture(autouse=True)
def ohne_demo_daten(db):
    demo_daten.entfernen(db)


def _anzahl(db, modell, *bedingung):
    return db.scalar(select(func.count()).select_from(modell).where(*bedingung))


def _id(db, modell, bezeichnung):
    return db.scalar(select(modell.id).where(modell.bezeichnung == bezeichnung))


def test_anlegen_ist_wiederholbar(db):
    demo_daten.anlegen(db)
    vorher = [_anzahl(db, m) for m in (Instrumentenklasse, Reparaturart, ReparaturVorgabewert, Kunde, Instrument, Auftrag)]
    demo_daten.anlegen(db)
    nachher = [_anzahl(db, m) for m in (Instrumentenklasse, Reparaturart, ReparaturVorgabewert, Kunde, Instrument, Auftrag)]
    assert vorher == nachher
    assert _anzahl(db, Kunde, Kunde.kundennummer.startswith("DEMO-")) == 3
    assert _anzahl(db, Auftrag, Auftrag.auftragsnummer.startswith("DEMO-01")) == 4


def test_schaetzungen_wie_im_spickzettel_angekuendigt(db):
    demo_daten.anlegen(db)
    violine, cello, trompete, klarinette = (_id(db, Instrumentenklasse, b)
                                            for b in ("Violine", "Violoncello", "Trompete", "Klarinette"))
    saiten, ventil, general = (_id(db, Reparaturart, b)
                               for b in ("Saitenwechsel", "Ventil-Überholung", "Generalüberholung"))

    s = schaetze_arbeitsstunden(db, violine, saiten)
    k = schaetze_kosten(db, violine, saiten)
    assert (s.quelle, k.quelle) == (Quelle.historisch, Quelle.historisch)
    # Exakte Werte nur, wenn keine echten Violine/Saitenwechsel-Aufträge dazukommen
    if s.anzahl_vergleichsfaelle == k.anzahl_vergleichsfaelle == 5:
        assert (s.wert, k.wert) == (Decimal("0.70"), Decimal("30.60"))

    assert schaetze_arbeitsstunden(db, cello, saiten).quelle == Quelle.vorgabe_instrumentenklasse
    assert schaetze_kosten(db, trompete, ventil).quelle == Quelle.vorgabe_allgemein
    assert schaetze_arbeitsstunden(db, klarinette, general).quelle == Quelle.keine


def test_entfernen_loescht_nur_demo_daten(db, client):
    demo_daten.anlegen(db)
    # Ein echter (Nicht-Demo-)Auftrag mit denselben Stammdaten muss erhalten bleiben
    w = Werkstatt(db)
    w.auftrag(minuten=(30,))
    echte_auftraege = _anzahl(db, Auftrag, Auftrag.kunde_id == w.kunde.id)

    demo_daten.entfernen(db)

    assert _anzahl(db, Kunde, Kunde.kundennummer.startswith("DEMO-")) == 0
    assert _anzahl(db, Auftrag, Auftrag.auftragsnummer.startswith("DEMO-")) == 0
    assert _anzahl(db, Mitarbeiter, Mitarbeiter.email == demo_daten.DEMO_MITARBEITER_EMAIL) == 0
    assert _anzahl(db, Auftrag, Auftrag.kunde_id == w.kunde.id) == echte_auftraege == 1
    # Stammdaten bleiben
    assert _id(db, Reparaturart, "Saitenwechsel") is not None
    assert _anzahl(db, ReparaturVorgabewert) >= len(demo_daten.VORGABEWERTE)


def test_anzeigen_gibt_ids_und_beispiele_aus(db, capsys):
    demo_daten.anzeigen(db)
    assert "Keine Demo-Daten" in capsys.readouterr().out
    demo_daten.anlegen(db)
    demo_daten.anzeigen(db)
    ausgabe = capsys.readouterr().out
    assert "Marie Schneider" in ausgabe and "kunde_id" in ausgabe
    assert ausgabe.count('"reparaturart_id"') == 4

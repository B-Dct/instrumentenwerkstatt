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
    assert _anzahl(db, Kunde, Kunde.kundennummer.startswith("DEMO-")) == 4
    assert _anzahl(db, Auftrag, Auftrag.auftragsnummer.startswith("DEMO-01")) == 4


def test_blechblas_kunde_zum_durchklicken_der_ausfuehrung(db):
    """DEMO-004: Trompete ohne Ausführung, Flügelhorn mit Ausführung (falls die Preisliste sie kennt), Tuba."""
    demo_daten.anlegen(db)
    kunde = db.scalar(select(Kunde).where(Kunde.kundennummer == "DEMO-004"))
    instrumente = {klasse: ausfuehrung for klasse, ausfuehrung in db.execute(
        select(Instrumentenklasse.bezeichnung, Instrument.ausfuehrung)
        .join(Instrumentenklasse, Instrument.instrumentenklasse_id == Instrumentenklasse.id)
        .where(Instrument.kunde_id == kunde.id))}
    assert set(instrumente) == {"Trompete", "Flügelhorn/Kornett", "B-Tuba (4 Ventile)"}
    assert instrumente["Trompete"] is None and instrumente["B-Tuba (4 Ventile)"] is None
    # Die Ausführung steht nur am Instrument, wenn es sie in der Preisliste der Klasse gibt
    kornett = _id(db, Instrumentenklasse, "Flügelhorn/Kornett")
    bekannt = _anzahl(db, ReparaturVorgabewert, ReparaturVorgabewert.instrumentenklasse_id == kornett,
                      ReparaturVorgabewert.ausfuehrung == "Drehventile, lackiert", ReparaturVorgabewert.archiviert_am.is_(None))
    assert instrumente["Flügelhorn/Kornett"] == ("Drehventile, lackiert" if bekannt else None)

    assert demo_daten.entfernen(db)
    assert _anzahl(db, Kunde, Kunde.kundennummer == "DEMO-004") == 0


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



def test_entfernen_mit_wochenstunden_am_demo_mitarbeiter(db):
    """Fehlerfall aus dem Echtbetrieb: Wochenstunden am Demo-Mitarbeiter verhinderten das Entfernen."""
    from datetime import date
    from app.models import MitarbeiterArbeitszeit
    demo_daten.anlegen(db)
    demo = db.scalar(select(Mitarbeiter).where(Mitarbeiter.email == demo_daten.DEMO_MITARBEITER_EMAIL))
    db.add(MitarbeiterArbeitszeit(mitarbeiter_id=demo.id, wochenstunden=Decimal("40"), gueltig_ab=date(2026, 9, 29)))
    db.flush()
    assert demo_daten.entfernen(db) is True
    assert _anzahl(db, Mitarbeiter, Mitarbeiter.email == demo_daten.DEMO_MITARBEITER_EMAIL) == 0
    assert _anzahl(db, MitarbeiterArbeitszeit, MitarbeiterArbeitszeit.mitarbeiter_id == demo.id) == 0


def test_demo_mitarbeiter_bleibt_wenn_echt_verwendet(db, capsys):
    demo_daten.anlegen(db)
    demo = db.scalar(select(Mitarbeiter).where(Mitarbeiter.email == demo_daten.DEMO_MITARBEITER_EMAIL))
    w = Werkstatt(db)
    w.auftrag(status=w.in_bearbeitung, zugewiesen=demo)  # echter (Nicht-Demo-)Auftrag
    assert demo_daten.entfernen(db) is False
    assert db.get(Mitarbeiter, demo.id) is not None
    assert "auftrag.zugewiesener_mitarbeiter_id" in capsys.readouterr().out

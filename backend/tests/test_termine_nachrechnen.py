"""Tests für den Nachrechnen-Befehl."""

import secrets
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Auftrag, SchaetzungsLog
from app.termine_nachrechnen import nachrechnen
from tests.beispieldaten import Werkstatt


@pytest.fixture
def w(db):
    return Werkstatt(db)


def auftrag(w, stunden, status=None, mit_termin=False):
    a = Auftrag(
        auftragsnummer=f"T-{secrets.token_hex(5)}", zugriffstoken=secrets.token_hex(6),
        kunde_id=w.kunde.id, instrument_id=w.instrument().id, reparaturart_id=w.saitenwechsel.id,
        zugewiesener_mitarbeiter_id=w.mitarbeiter.id, komplexitaet=1,
        status_aktuell_id=status or w.in_bearbeitung,
        geschaetzte_arbeitsstunden=None if stunden is None else Decimal(stunden),
    )
    if mit_termin:
        from datetime import date
        a.geschaetztes_fertigstellungsdatum = date(2020, 1, 1)
    w.db.add(a)
    w.db.flush()
    return a


def logs(db, a):
    return db.scalars(select(SchaetzungsLog).where(SchaetzungsLog.auftrag_id == a.id)).all()


def _eigene(ergebnis, *auftraege):
    nummern = {a.auftragsnummer for a in auftraege}
    return {n: t for n, t in ergebnis if n in nummern}


def test_rechnet_offene_ohne_termin_nach(db, w):
    ohne = auftrag(w, "8")
    mit = auftrag(w, "8", mit_termin=True)
    fertig = auftrag(w, "8", status=w.fertig)
    ohne_stunden = auftrag(w, None)

    ergebnis = _eigene(nachrechnen(db), ohne, mit, fertig, ohne_stunden)

    assert set(ergebnis) == {ohne.auftragsnummer, ohne_stunden.auftragsnummer}
    assert "übersprungen" in ergebnis[ohne_stunden.auftragsnummer]
    db.refresh(ohne)
    assert ohne.geschaetztes_fertigstellungsdatum is not None
    [log] = logs(db, ohne)
    assert log.eingabefaktoren["anlass"] == "nachberechnet"
    assert log.geschaetztes_datum == ohne.geschaetztes_fertigstellungsdatum
    assert logs(db, ohne_stunden) == [] and logs(db, fertig) == []


def test_alle_rechnet_auch_vorhandene_termine_neu(db, w):
    mit = auftrag(w, "8", mit_termin=True)
    nachrechnen(db, alle=True)
    db.refresh(mit)
    assert mit.geschaetztes_fertigstellungsdatum.year > 2020


def test_probelauf_speichert_nichts(db, w):
    ohne = auftrag(w, "8")
    ergebnis = _eigene(nachrechnen(db, probelauf=True), ohne)
    assert ohne.auftragsnummer in ergebnis
    db.refresh(ohne)
    assert ohne.geschaetztes_fertigstellungsdatum is None and logs(db, ohne) == []


def test_zweiter_lauf_findet_nichts_mehr(db, w):
    ohne = auftrag(w, "8")
    nachrechnen(db)
    assert ohne.auftragsnummer not in dict(nachrechnen(db))

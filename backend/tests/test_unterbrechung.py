"""Unterbrechungen entstehen und enden automatisch mit dem Status (Datenmodell 2.9)."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Auftragsstatus, Unterbrechung
from tests.beispieldaten import Werkstatt
from tests.conftest import angemeldet_als

URL = "/auftraege"


@pytest.fixture
def w(db, client):
    werkstatt = Werkstatt(db)
    werkstatt.vorgabe()
    werkstatt.wartet = werkstatt.status["wartet_auf_ersatzteil"]
    client.headers.update(angemeldet_als(werkstatt.mitarbeiter))
    return werkstatt


def neuer_auftrag(client, w):
    antwort = client.post(URL, json={
        "kunde_id": str(w.kunde.id),
        "instrument_id": str(w.instrument().id),
        "reparaturart_id": str(w.saitenwechsel.id),
        "zugewiesener_mitarbeiter_id": str(w.mitarbeiter.id),
    })
    return antwort.json()["id"]


def wechseln(client, auftrag_id, status_id, **extra):
    antwort = client.post(f"{URL}/{auftrag_id}/status", json={"status_id": str(status_id), **extra})
    assert antwort.status_code == 200, antwort.json()
    return antwort.json()


def unterbrechungen(db, auftrag_id):
    return db.scalars(select(Unterbrechung).where(Unterbrechung.auftrag_id == uuid.UUID(auftrag_id))
                      .order_by(Unterbrechung.von_datum)).all()


def test_wartet_auf_ersatzteil_ist_pausierender_status(db, w):
    assert db.get(Auftragsstatus, w.wartet).unterbrechungsgrund == "Ersatzteil bestellt"


def test_wechsel_zu_wartet_auf_ersatzteil_erzeugt_offene_unterbrechung(client, db, w):
    auftrag_id = neuer_auftrag(client, w)
    wechseln(client, auftrag_id, w.in_bearbeitung)
    a = wechseln(client, auftrag_id, w.wartet)

    [u] = unterbrechungen(db, auftrag_id)
    assert u.grund == "Ersatzteil bestellt"
    assert isinstance(u.von_datum, datetime) and u.bis_datum is None
    # Auch in der Detailansicht sichtbar
    assert a["unterbrechungen"][0]["grund"] == "Ersatzteil bestellt"
    assert a["unterbrechungen"][0]["bis_datum"] is None


def test_eigener_grund(client, db, w):
    auftrag_id = neuer_auftrag(client, w)
    wechseln(client, auftrag_id, w.wartet, unterbrechungsgrund="  Mundstück beim Hersteller bestellt ")
    assert unterbrechungen(db, auftrag_id)[0].grund == "Mundstück beim Hersteller bestellt"


def test_wechsel_weg_schliesst_unterbrechung(client, db, w):
    auftrag_id = neuer_auftrag(client, w)
    wechseln(client, auftrag_id, w.wartet)
    a = wechseln(client, auftrag_id, w.in_bearbeitung)

    [u] = unterbrechungen(db, auftrag_id)
    db.refresh(u)
    assert u.bis_datum is not None and u.bis_datum >= u.von_datum
    assert a["unterbrechungen"][0]["bis_datum"] is not None


def test_mehrere_unterbrechungen_nacheinander(client, db, w):
    auftrag_id = neuer_auftrag(client, w)
    wechseln(client, auftrag_id, w.wartet)
    wechseln(client, auftrag_id, w.in_bearbeitung)
    wechseln(client, auftrag_id, w.wartet, unterbrechungsgrund="Zweites Teil fehlt")
    wechseln(client, auftrag_id, w.fertig, arbeitszeit_minuten=45, abgerechneter_betrag=30)  # Abschluss schließt ebenfalls

    liste = unterbrechungen(db, auftrag_id)
    for u in liste:
        db.refresh(u)
    assert [u.grund for u in liste] == ["Ersatzteil bestellt", "Zweites Teil fehlt"]
    assert all(u.bis_datum is not None for u in liste)
    assert liste[0].bis_datum <= liste[1].von_datum


def test_wechsel_zwischen_zwei_pausierenden_status(client, db, w):
    rueckfrage = Auftragsstatus(schluessel="test_rueckfrage", bezeichnung="TEST Rückfrage", reihenfolge=35,
                                farbe="#000000", unterbrechungsgrund="Rückfrage beim Kunden")
    db.add(rueckfrage)
    db.flush()
    auftrag_id = neuer_auftrag(client, w)
    wechseln(client, auftrag_id, w.wartet)
    wechseln(client, auftrag_id, rueckfrage.id)

    liste = unterbrechungen(db, auftrag_id)
    for u in liste:
        db.refresh(u)
    assert [(u.grund, u.bis_datum is None) for u in liste] == [
        ("Ersatzteil bestellt", False), ("Rückfrage beim Kunden", True)
    ]


def test_normaler_statuswechsel_ohne_unterbrechung(client, db, w):
    auftrag_id = neuer_auftrag(client, w)
    wechseln(client, auftrag_id, w.in_bearbeitung)
    assert unterbrechungen(db, auftrag_id) == []


def test_grund_bei_nicht_pausierendem_status_abgelehnt(client, w):
    auftrag_id = neuer_auftrag(client, w)
    antwort = client.post(f"{URL}/{auftrag_id}/status",
                          json={"status_id": str(w.in_bearbeitung), "unterbrechungsgrund": "x"})
    assert antwort.status_code == 422


def test_datenbank_erlaubt_nur_eine_offene_unterbrechung(client, db, w):
    auftrag_id = uuid.UUID(neuer_auftrag(client, w))
    db.add(Unterbrechung(auftrag_id=auftrag_id, grund="a", von_datum=datetime.now()))
    db.flush()
    db.add(Unterbrechung(auftrag_id=auftrag_id, grund="b", von_datum=datetime.now()))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

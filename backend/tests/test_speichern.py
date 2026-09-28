"""Sichert das Muster "speichern, bei Verletzung einer Datenbankregel sauber zurücknehmen und
verständlich melden" allgemein ab (app/speichern.py), damit neue Endpunkte es nicht vergessen.
"""

import re
import uuid
from pathlib import Path

import pytest
from fastapi import Depends
from sqlalchemy import UniqueConstraint, select
from sqlalchemy.orm import Session

from app.db import Base, get_db
from app.main import app
from app.models import Reparaturart, Systemrolle
from app.speichern import ALLGEMEINE_MELDUNG, KONFLIKT_MELDUNGEN
from tests.beispieldaten import Werkstatt
from tests.conftest import angemeldet_als, konto_anlegen

APP_ORDNER = Path(__file__).resolve().parent.parent / "app"


# --- 1. Jede Eindeutigkeitsregel hat eine verständliche Meldung -----------------------

def _eindeutigkeitsregeln() -> set[str]:
    namen = set()
    for tabelle in Base.metadata.sorted_tables:
        namen |= {str(c.name) for c in tabelle.constraints if isinstance(c, UniqueConstraint)}
        namen |= {str(i.name) for i in tabelle.indexes if i.unique}
    return namen


def test_jede_eindeutigkeitsregel_hat_eine_meldung():
    fehlend = _eindeutigkeitsregeln() - KONFLIKT_MELDUNGEN.keys()
    assert not fehlend, f"Meldung in app/speichern.py KONFLIKT_MELDUNGEN ergänzen für: {sorted(fehlend)}"


def test_keine_veralteten_meldungen():
    veraltet = KONFLIKT_MELDUNGEN.keys() - _eindeutigkeitsregeln()
    assert not veraltet, f"Regel existiert nicht mehr, Meldung entfernen: {sorted(veraltet)}"


# --- 2. Niemand baut das Muster selbst nach ------------------------------------------

@pytest.mark.parametrize("muster", [r"except\s+.*IntegrityError", r"begin_nested\("])
def test_muster_nur_im_zentralen_baustein(muster):
    erlaubt = {APP_ORDNER / "speichern.py"}
    treffer = [
        f"{datei.relative_to(APP_ORDNER.parent)}:{nr}"
        for datei in APP_ORDNER.rglob("*.py") if datei not in erlaubt
        for nr, zeile in enumerate(datei.read_text().splitlines(), 1) if re.search(muster, zeile)
    ]
    assert not treffer, f"Statt eigenem Abfangen app.speichern.sicher_speichern verwenden: {treffer}"


# --- 3. Nach einem Konflikt ist nichts hängen geblieben ----------------------------------

@pytest.fixture
def admin(db, client):
    client.headers.update(angemeldet_als(konto_anlegen(db, Systemrolle.admin)))


@pytest.fixture
def w(db, admin):
    werkstatt = Werkstatt(db)
    werkstatt.vorgabe()                          # allgemein
    werkstatt.vorgabe(werkstatt.kontrabass)      # speziell Kontrabass
    return werkstatt


def _vorgabe_ids(client, w):
    werte = client.get("/admin/vorgabewerte", params={"reparaturart_id": str(w.saitenwechsel.id)}).json()
    return {v["instrumentenklasse_id"]: v["id"] for v in werte}


def _konflikt_neue_reparaturart(client, w):
    return client.post("/admin/reparaturarten", json={"bezeichnung": "TEST Saitenwechsel", "standard_komplexitaet": 1})


def _konflikt_klasse_umbenennen(client, w):
    return client.patch(f"/admin/instrumentenklassen/{w.violine.id}", json={"bezeichnung": "TEST Kontrabass"})


def _konflikt_neuer_vorgabewert(client, w):
    return client.post("/admin/vorgabewerte", json={
        "reparaturart_id": str(w.saitenwechsel.id), "vorgabe_stunden": 1, "vorgabe_kosten": 1})


def _konflikt_vorgabewert_kombination_aendern(client, w):
    spezifisch = _vorgabe_ids(client, w)[str(w.kontrabass.id)]
    return client.patch(f"/admin/vorgabewerte/{spezifisch}", json={"instrumentenklasse_id": None})


def _konflikt_vorgabewert_reaktivieren(client, w):
    allgemein = _vorgabe_ids(client, w)[None]
    client.post(f"/admin/vorgabewerte/{allgemein}/archivieren")
    client.post("/admin/vorgabewerte", json={
        "reparaturart_id": str(w.saitenwechsel.id), "vorgabe_stunden": 2, "vorgabe_kosten": 2})
    return client.post(f"/admin/vorgabewerte/{allgemein}/reaktivieren")


@pytest.mark.parametrize("konflikt", [
    _konflikt_neue_reparaturart,
    _konflikt_klasse_umbenennen,
    _konflikt_neuer_vorgabewert,
    _konflikt_vorgabewert_kombination_aendern,
    _konflikt_vorgabewert_reaktivieren,
])
def test_nach_konflikt_bleibt_nichts_haengen(client, db, w, konflikt):
    klassen_vorher = {k["id"]: k["bezeichnung"] for k in client.get("/admin/instrumentenklassen").json()}
    vorgaben_vorher = _vorgabe_ids(client, w)

    antwort = konflikt(client, w)
    assert antwort.status_code == 409
    assert antwort.json()["detail"] != ALLGEMEINE_MELDUNG  # konkrete, verständliche Meldung

    # Die Sitzung ist sauber: ein weiterer, gültiger Schreibvorgang gelingt …
    folge = client.post("/admin/reparaturarten", json={"bezeichnung": f"TEST neu {uuid.uuid4()}", "standard_komplexitaet": 2})
    assert folge.status_code == 201
    # … und der abgelehnte Wert wurde nirgends übernommen
    assert {k["id"]: k["bezeichnung"] for k in client.get("/admin/instrumentenklassen").json()} == klassen_vorher
    nachher = _vorgabe_ids(client, w)
    if konflikt is _konflikt_vorgabewert_reaktivieren:
        # Der archivierte Wert ist archiviert geblieben, der neue allgemeine Wert ist aktiv
        assert vorgaben_vorher[None] not in nachher.values() and None in nachher
    else:
        assert nachher == vorgaben_vorher
    assert len(db.scalars(select(Reparaturart).where(Reparaturart.bezeichnung == "TEST Saitenwechsel")).all()) == 1


# --- 4. Sicherheitsnetz für Endpunkte ohne sicher_speichern ---------------------------

def test_sicherheitsnetz_liefert_409_statt_500(client, w, admin):
    def ohne_baustein(db: Session = Depends(get_db)):
        db.add(Reparaturart(bezeichnung="TEST Saitenwechsel", standard_komplexitaet=1))
        db.flush()  # verletzt uq_reparaturart_bezeichnung – absichtlich ohne sicher_speichern

    app.add_api_route("/_test_ohne_baustein", ohne_baustein, methods=["POST"])
    try:
        antwort = client.post("/_test_ohne_baustein")
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/_test_ohne_baustein"]
    assert antwort.status_code == 409
    assert antwort.json()["detail"] == KONFLIKT_MELDUNGEN["uq_reparaturart_bezeichnung"]

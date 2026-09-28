"""Stammdaten: Instrumentenklassen, Reparaturarten, Vorgabewerte – nur Admin (2.4, 2.6, 2.6a, 7.2)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Reparaturart, Systemrolle, SystemEreignisLog
from tests.beispieldaten import Werkstatt
from tests.conftest import angemeldet_als, konto_anlegen


@pytest.fixture
def admin(db):
    return angemeldet_als(konto_anlegen(db, Systemrolle.admin, name="Admin"))


@pytest.fixture
def w(db):
    return Werkstatt(db)


# --- Berechtigungen -------------------------------------------------------------

@pytest.mark.parametrize("rolle", [Systemrolle.mitarbeiter, Systemrolle.werkstattleiter])
@pytest.mark.parametrize("methode, pfad, daten", [
    ("post", "/admin/reparaturarten", {"bezeichnung": "X", "standard_komplexitaet": 1}),
    ("post", "/admin/instrumentenklassen", {"bezeichnung": "X", "oberkategorie": "Y"}),
    ("get", "/admin/reparaturarten", None),
    ("post", "/admin/vorgabewerte", {"reparaturart_id": str(uuid.uuid4()), "vorgabe_stunden": 1, "vorgabe_kosten": 1}),
    ("patch", f"/admin/vorgabewerte/{uuid.uuid4()}", {"notiz": "x"}),
])
def test_nur_admin(client, db, rolle, methode, pfad, daten):
    header = angemeldet_als(konto_anlegen(db, rolle))
    antwort = getattr(client, methode)(pfad, headers=header, **({"json": daten} if daten else {}))
    assert antwort.status_code == 403


def test_mitarbeiter_kann_kunde_anlegen_aber_keine_reparaturart(client, db):
    header = angemeldet_als(konto_anlegen(db, Systemrolle.mitarbeiter))
    assert client.post("/kunden", headers=header, json={"name": "Neukunde"}).status_code == 201
    assert client.post("/admin/reparaturarten", headers=header,
                       json={"bezeichnung": "Neu", "standard_komplexitaet": 2}).status_code == 403


# --- Reparaturarten ---------------------------------------------------------------

def test_reparaturart_anlegen_bearbeiten_archivieren(client, db, admin):
    r = client.post("/admin/reparaturarten", headers=admin,
                    json={"bezeichnung": " TEST Bogen behaaren ", "standard_komplexitaet": 2})
    assert r.status_code == 201
    r = r.json()
    assert r["bezeichnung"] == "TEST Bogen behaaren"

    r = client.patch(f"/admin/reparaturarten/{r['id']}", headers=admin, json={"standard_komplexitaet": 3}).json()
    assert r["standard_komplexitaet"] == 3

    r = client.post(f"/admin/reparaturarten/{r['id']}/archivieren", headers=admin).json()
    assert r["archiviert_am"] is not None
    # Nicht gelöscht, nur ausgeblendet
    assert db.get(Reparaturart, uuid.UUID(r["id"])) is not None
    assert r["id"] not in [x["id"] for x in client.get("/admin/reparaturarten", headers=admin).json()]
    assert r["id"] in [x["id"] for x in client.get("/admin/reparaturarten", headers=admin,
                                                   params={"archivierte": True}).json()]
    assert r["id"] not in [x["id"] for x in client.get("/reparaturarten", headers=admin).json()]

    r = client.post(f"/admin/reparaturarten/{r['id']}/reaktivieren", headers=admin).json()
    assert r["archiviert_am"] is None

    aktionen = db.scalars(select(SystemEreignisLog.aktion).where(SystemEreignisLog.betroffene_id == uuid.UUID(r["id"]))
                          .order_by(SystemEreignisLog.zeitpunkt)).all()
    assert aktionen == ["reparaturart_angelegt", "reparaturart_geaendert", "reparaturart_archiviert", "reparaturart_reaktiviert"]


@pytest.mark.parametrize("daten", [
    {"bezeichnung": "", "standard_komplexitaet": 2},
    {"bezeichnung": "X", "standard_komplexitaet": 0},
    {"bezeichnung": "X", "standard_komplexitaet": 6},
])
def test_reparaturart_ungueltig(client, admin, daten):
    assert client.post("/admin/reparaturarten", headers=admin, json=daten).status_code == 422


def test_doppelte_bezeichnung(client, admin, w):
    antwort = client.post("/admin/reparaturarten", headers=admin,
                          json={"bezeichnung": "TEST Saitenwechsel", "standard_komplexitaet": 1})
    assert antwort.status_code == 409
    antwort = client.patch(f"/admin/instrumentenklassen/{w.violine.id}", headers=admin,
                           json={"bezeichnung": "TEST Kontrabass"})
    assert antwort.status_code == 409
    # Folgeanfrage funktioniert, die abgelehnte Bezeichnung wurde nicht übernommen
    klassen = client.get("/admin/instrumentenklassen", headers=admin).json()
    assert next(k for k in klassen if k["id"] == str(w.violine.id))["bezeichnung"] == "TEST Violine"


def test_archivierte_reparaturart_nicht_fuer_neue_auftraege(client, admin, w):
    client.post(f"/admin/reparaturarten/{w.saitenwechsel.id}/archivieren", headers=admin)
    antwort = client.post("/auftraege", headers=admin, json={
        "kunde_id": str(w.kunde.id), "instrument_id": str(w.instrument().id),
        "reparaturart_id": str(w.saitenwechsel.id),
    })
    assert antwort.status_code == 422


# --- Instrumentenklassen ----------------------------------------------------------

def test_instrumentenklasse_anlegen_und_archivieren(client, admin, w):
    k = client.post("/admin/instrumentenklassen", headers=admin,
                    json={"bezeichnung": "TEST Harfe", "oberkategorie": "Zupfinstrument"}).json()
    assert k["id"] in [x["id"] for x in client.get("/instrumentenklassen", headers=admin).json()]
    client.post(f"/admin/instrumentenklassen/{k['id']}/archivieren", headers=admin)
    assert k["id"] not in [x["id"] for x in client.get("/instrumentenklassen", headers=admin).json()]
    # Kein neues Instrument mit archivierter Klasse
    antwort = client.post("/instrumente", headers=admin,
                          json={"kunde_id": str(w.kunde.id), "instrumentenklasse_id": k["id"]})
    assert antwort.status_code == 422


def test_instrumentenklassen_leseliste_fuer_alle(client, w):
    header = angemeldet_als(w.mitarbeiter)
    namen = [k["bezeichnung"] for k in client.get("/instrumentenklassen", headers=header).json()]
    assert "TEST Violine" in namen


# --- Vorgabewerte und Archiv ------------------------------------------------------

def test_vorgabewert_bleibt_bearbeitbar_nach_archivierung_der_reparaturart(client, admin, w):
    v = client.post("/admin/vorgabewerte", headers=admin, json={
        "reparaturart_id": str(w.saitenwechsel.id), "vorgabe_stunden": 1, "vorgabe_kosten": 30,
    }).json()
    client.post(f"/admin/reparaturarten/{w.saitenwechsel.id}/archivieren", headers=admin)

    # Bestehenden Wert anpassen: erlaubt
    assert client.patch(f"/admin/vorgabewerte/{v['id']}", headers=admin, json={"vorgabe_kosten": 35}).status_code == 200
    # Neuen Wert für die archivierte Reparaturart: nicht erlaubt
    antwort = client.post("/admin/vorgabewerte", headers=admin, json={
        "reparaturart_id": str(w.saitenwechsel.id), "instrumentenklasse_id": str(w.violine.id),
        "vorgabe_stunden": 1, "vorgabe_kosten": 30,
    })
    assert antwort.status_code == 422

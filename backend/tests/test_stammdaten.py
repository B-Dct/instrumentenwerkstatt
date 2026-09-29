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


def _ids(antwort):
    return [x["id"] for x in antwort.json()["eintraege"]]


def _bezeichnungen(antwort, kennung):
    return [x["bezeichnung"].removeprefix(f"{kennung} ") for x in antwort.json()["eintraege"]]


# --- Berechtigungen -------------------------------------------------------------

@pytest.mark.parametrize("rolle", [Systemrolle.mitarbeiter, Systemrolle.werkstattleiter])
@pytest.mark.parametrize("methode, pfad, daten", [
    ("post", "/admin/reparaturarten", {"bezeichnung": "X", "standard_komplexitaet": 1}),
    ("post", "/admin/instrumentenklassen", {"bezeichnung": "X", "oberkategorie": "Y"}),
    ("get", "/admin/reparaturarten", None),
    ("get", "/admin/instrumentenklassen", None),
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
    suche = {"suche": "TEST Bogen"}
    assert _ids(client.get("/admin/reparaturarten", headers=admin, params=suche)) == []
    assert _ids(client.get("/admin/reparaturarten", headers=admin, params={**suche, "status": "archiviert"})) == [r["id"]]
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
    klassen = client.get("/admin/instrumentenklassen", headers=admin, params={"suche": "TEST Violine"}).json()
    assert [k["bezeichnung"] for k in klassen["eintraege"]] == ["TEST Violine"]


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


# --- Listen nach 9.11 -------------------------------------------------------------

@pytest.fixture
def klassenkreis(client, admin):
    """Eigene Test-Klassen mit eindeutiger Kennung, damit echte Daten nicht stören."""
    kennung = f"KK{uuid.uuid4().hex[:6]}"
    for bezeichnung, oberkategorie in [("Viola", "Streich"), ("Harfe", "Zupf"), ("Cello", "Streich"), ("Laute", "Zupf")]:
        client.post("/admin/instrumentenklassen", headers=admin,
                    json={"bezeichnung": f"{kennung} {bezeichnung}", "oberkategorie": f"{kennung} {oberkategorie}"})
    laute = client.get("/admin/instrumentenklassen", headers=admin, params={"suche": f"{kennung} Laute"}).json()
    client.post(f"/admin/instrumentenklassen/{laute['eintraege'][0]['id']}/archivieren", headers=admin)
    return kennung


def test_klassenliste_standard_nach_oberkategorie_dann_bezeichnung(client, admin, klassenkreis):
    antwort = client.get("/admin/instrumentenklassen", headers=admin, params={"suche": klassenkreis})
    assert _bezeichnungen(antwort, klassenkreis) == ["Cello", "Viola", "Harfe"]  # Streich vor Zupf; Laute archiviert
    daten = antwort.json()
    assert daten["treffer"] == 3 and daten["gesamt"] > daten["treffer"]


def test_klassenliste_absteigend_bezeichnung_bleibt_aufsteigend(client, admin, klassenkreis):
    antwort = client.get("/admin/instrumentenklassen", headers=admin,
                         params={"suche": klassenkreis, "richtung": "ab", "status": "alle"})
    assert _bezeichnungen(antwort, klassenkreis) == ["Harfe", "Laute", "Cello", "Viola"]  # Zupf vor Streich


def test_klassenliste_suche_auch_in_oberkategorie_und_status_filter(client, admin, klassenkreis):
    assert _bezeichnungen(client.get("/admin/instrumentenklassen", headers=admin,
                                     params={"suche": f"{klassenkreis} Zupf", "status": "alle"}), klassenkreis) == ["Harfe", "Laute"]
    assert _bezeichnungen(client.get("/admin/instrumentenklassen", headers=admin,
                                     params={"suche": klassenkreis, "status": "archiviert"}), klassenkreis) == ["Laute"]


def test_reparaturartenliste_sortierung_seiten_und_platzhalter(client, admin):
    kennung = f"RA{uuid.uuid4().hex[:6]}"
    for bezeichnung, komplexitaet in [("Bogen", 3), ("Anstrich 100%_neu", 3), ("Steg", 1)]:
        client.post("/admin/reparaturarten", headers=admin,
                    json={"bezeichnung": f"{kennung} {bezeichnung}", "standard_komplexitaet": komplexitaet})
    params = {"suche": kennung}
    assert _bezeichnungen(client.get("/admin/reparaturarten", headers=admin, params=params), kennung) == \
        ["Anstrich 100%_neu", "Bogen", "Steg"]
    params |= {"sortierung": "standard_komplexitaet", "richtung": "ab", "seitengroesse": 2}
    seite1, seite2 = (client.get("/admin/reparaturarten", headers=admin, params={**params, "seite": n}) for n in (1, 2))
    assert _bezeichnungen(seite1, kennung) + _bezeichnungen(seite2, kennung) == ["Anstrich 100%_neu", "Bogen", "Steg"]
    assert seite1.json()["treffer"] == 3
    assert _bezeichnungen(client.get("/admin/reparaturarten", headers=admin, params={"suche": "100%_neu"}), kennung) == \
        ["Anstrich 100%_neu"]
    assert _ids(client.get("/admin/reparaturarten", headers=admin, params={"suche": f"{kennung} %"})) == []


@pytest.mark.parametrize("pfad", ["/admin/instrumentenklassen", "/admin/reparaturarten"])
def test_stammdatenliste_ungueltige_parameter(client, admin, pfad):
    assert client.get(pfad, headers=admin, params={"sortierung": "archiviert_am"}).status_code == 422
    assert client.get(pfad, headers=admin, params={"status": "geloescht"}).status_code == 422

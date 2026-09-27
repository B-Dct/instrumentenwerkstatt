import uuid

import pytest
from sqlalchemy import select

from app.models import Instrumentenklasse, Reparaturart, SystemEreignisLog

URL = "/admin/vorgabewerte"


@pytest.fixture
def stammdaten(db):
    saitenwechsel = Reparaturart(bezeichnung="TEST Saitenwechsel", standard_komplexitaet=1)
    kontrabass = Instrumentenklasse(bezeichnung="TEST Kontrabass", oberkategorie="Streichinstrument")
    db.add_all([saitenwechsel, kontrabass])
    db.flush()
    return {"reparaturart": saitenwechsel.id, "klasse": kontrabass.id}


def neu(stammdaten, **extra):
    return {
        "reparaturart_id": str(stammdaten["reparaturart"]),
        "vorgabe_stunden": 0.5,
        "vorgabe_kosten": 25,
        **extra,
    }


def test_anlegen_und_abrufen(client, stammdaten):
    antwort = client.post(URL, json=neu(stammdaten, notiz="inkl. Saiten"))
    assert antwort.status_code == 201
    daten = antwort.json()
    assert daten["reparaturart_bezeichnung"] == "TEST Saitenwechsel"
    assert daten["instrumentenklasse_id"] is None
    assert daten["vorgabe_stunden"] == 0.5
    assert daten["vorgabe_kosten"] == 25.0

    assert client.get(f"{URL}/{daten['id']}").json() == daten


def test_allgemein_und_spezifisch_nebeneinander(client, stammdaten):
    assert client.post(URL, json=neu(stammdaten)).status_code == 201
    spezifisch = neu(stammdaten, instrumentenklasse_id=str(stammdaten["klasse"]), vorgabe_stunden=1.5)
    assert client.post(URL, json=spezifisch).status_code == 201

    liste = client.get(URL, params={"reparaturart_id": str(stammdaten["reparaturart"])}).json()
    assert [e["instrumentenklasse_bezeichnung"] for e in liste] == [None, "TEST Kontrabass"]

    nur_klasse = client.get(URL, params={"instrumentenklasse_id": str(stammdaten["klasse"])}).json()
    assert [e["vorgabe_stunden"] for e in nur_klasse] == [1.5]


@pytest.mark.parametrize("mit_klasse", [False, True])
def test_doppelte_kombination_wird_abgelehnt(client, stammdaten, mit_klasse):
    extra = {"instrumentenklasse_id": str(stammdaten["klasse"])} if mit_klasse else {}
    assert client.post(URL, json=neu(stammdaten, **extra)).status_code == 201
    antwort = client.post(URL, json=neu(stammdaten, **extra))
    assert antwort.status_code == 409


@pytest.mark.parametrize("feld, wert", [
    ("vorgabe_stunden", -1),
    ("vorgabe_kosten", -0.01),
    ("vorgabe_kosten", 12.345),  # mehr als 2 Nachkommastellen
])
def test_ungueltige_werte(client, stammdaten, feld, wert):
    assert client.post(URL, json=neu(stammdaten, **{feld: wert})).status_code == 422


def test_unbekannte_reparaturart_oder_klasse(client, stammdaten):
    unbekannt = str(uuid.uuid4())
    assert client.post(URL, json=neu(stammdaten, reparaturart_id=unbekannt)).status_code == 422
    assert client.post(URL, json=neu(stammdaten, instrumentenklasse_id=unbekannt)).status_code == 422


def test_bearbeiten_aendert_nur_mitgeschickte_felder(client, stammdaten, db):
    vorher = client.post(URL, json=neu(stammdaten, notiz="alt")).json()

    antwort = client.patch(f"{URL}/{vorher['id']}", json={"vorgabe_kosten": 30})
    assert antwort.status_code == 200
    nachher = antwort.json()
    assert nachher["vorgabe_kosten"] == 30.0
    assert nachher["vorgabe_stunden"] == 0.5
    assert nachher["notiz"] == "alt"

    log = db.scalars(select(SystemEreignisLog).where(
        SystemEreignisLog.betroffene_id == uuid.UUID(vorher["id"])
    ).order_by(SystemEreignisLog.zeitpunkt)).all()
    assert [e.aktion for e in log] == ["vorgabewert_angelegt", "vorgabewert_geaendert"]
    assert log[1].details["alt"]["vorgabe_kosten"] == "25.00"
    assert log[1].details["neu"]["vorgabe_kosten"] == "30.00"


def test_bearbeiten_klasse_auf_allgemein_zuruecksetzen(client, stammdaten):
    eintrag = client.post(URL, json=neu(stammdaten, instrumentenklasse_id=str(stammdaten["klasse"]))).json()
    antwort = client.patch(f"{URL}/{eintrag['id']}", json={"instrumentenklasse_id": None})
    assert antwort.status_code == 200
    assert antwort.json()["instrumentenklasse_id"] is None


def test_bearbeiten_pflichtfeld_nicht_leeren(client, stammdaten):
    eintrag = client.post(URL, json=neu(stammdaten)).json()
    antwort = client.patch(f"{URL}/{eintrag['id']}", json={"vorgabe_kosten": None})
    assert antwort.status_code == 422


def test_bearbeiten_in_bestehende_kombination_abgelehnt(client, stammdaten):
    client.post(URL, json=neu(stammdaten))
    spezifisch = client.post(URL, json=neu(stammdaten, instrumentenklasse_id=str(stammdaten["klasse"]))).json()
    antwort = client.patch(f"{URL}/{spezifisch['id']}", json={"instrumentenklasse_id": None})
    assert antwort.status_code == 409


def test_nicht_gefunden(client):
    assert client.get(f"{URL}/{uuid.uuid4()}").status_code == 404
    assert client.patch(f"{URL}/{uuid.uuid4()}", json={"notiz": "x"}).status_code == 404

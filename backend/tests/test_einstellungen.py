"""Werkstatt-Einstellungen (Datenmodell 7.5): nur Admin, Auswahl statt Freitext, mit Protokoll."""

import pytest
from sqlalchemy import select

from app.einstellungen import BUNDESLAENDER, wert
from app.models import Einstellung, Systemrolle, SystemEreignisLog
from tests.conftest import OHNE_ANMELDUNG, angemeldet_als, konto_anlegen

URL = "/admin/einstellungen"


@pytest.fixture
def admin(db, client):
    person = konto_anlegen(db, Systemrolle.admin, name="Admin")
    client.headers.update(angemeldet_als(person))
    return person


@pytest.fixture
def ohne_bundesland(db):
    """Ausgangslage unabhängig von echten Daten (wird wie alles im Test zurückgerollt)."""
    for e in db.scalars(select(Einstellung).where(Einstellung.schluessel == "bundesland")):
        db.delete(e)
    db.flush()


def _bundesland(client):
    return next(e for e in client.get(URL).json() if e["schluessel"] == "bundesland")


@pytest.mark.parametrize("rolle", [Systemrolle.mitarbeiter, Systemrolle.werkstattleiter])
def test_nur_admin(client, db, rolle):
    header = angemeldet_als(konto_anlegen(db, rolle))
    assert client.get(URL, headers=header).status_code == 403
    assert client.put(f"{URL}/bundesland", headers=header, json={"wert": "Bayern"}).status_code == 403
    assert client.get(URL, headers=OHNE_ANMELDUNG).status_code == 401


def test_sechzehn_bundeslaender_zur_auswahl(client, admin, ohne_bundesland):
    e = _bundesland(client)
    assert len(e["optionen"]) == 16 and e["optionen"] == list(BUNDESLAENDER)
    assert (e["wert"], e["geaendert_von_name"], e["geaendert_am"]) == (None, None, None)


def test_setzen_aendern_und_protokoll(client, db, admin, ohne_bundesland):
    antwort = client.put(f"{URL}/bundesland", json={"wert": "Baden-Württemberg"})
    assert antwort.status_code == 200
    assert (antwort.json()["wert"], antwort.json()["geaendert_von_name"]) == ("Baden-Württemberg", "Admin")
    assert wert(db, "bundesland") == "Baden-Württemberg"

    assert client.put(f"{URL}/bundesland", json={"wert": "Bayern"}).json()["wert"] == "Bayern"
    client.put(f"{URL}/bundesland", json={"wert": "Bayern"})  # ohne Änderung: kein weiterer Protokolleintrag
    assert _bundesland(client)["wert"] == "Bayern"
    assert len(db.scalars(select(Einstellung).where(Einstellung.schluessel == "bundesland")).all()) == 1

    eintrag_id = db.scalar(select(Einstellung.id).where(Einstellung.schluessel == "bundesland"))
    details = [log.details for log in db.scalars(
        select(SystemEreignisLog).where(SystemEreignisLog.betroffene_id == eintrag_id).order_by(SystemEreignisLog.zeitpunkt))]
    assert details == [
        {"schluessel": "bundesland", "alt": None, "neu": "Baden-Württemberg"},
        {"schluessel": "bundesland", "alt": "Baden-Württemberg", "neu": "Bayern"},
    ]


@pytest.mark.parametrize("daten", [{"wert": "Atlantis"}, {"wert": "BY"}, {"wert": ""}, {}])
def test_kein_freitext(client, db, admin, ohne_bundesland, daten):
    antwort = client.put(f"{URL}/bundesland", json=daten)
    assert antwort.status_code == 422
    assert antwort.json()["detail"][0]["loc"][-1] == "wert"
    assert wert(db, "bundesland") is None


def test_unbekannte_einstellung(client, admin):
    assert client.put(f"{URL}/waehrung", json={"wert": "Euro"}).status_code == 404


# --- Zahl-Einstellung: Stundensatz ---------------------------------------------------

def _stundensatz(client):
    return next(e for e in client.get(URL).json() if e["schluessel"] == "stundensatz")


def test_stundensatz_ist_eine_zahl_mit_einheit(client, admin):
    e = _stundensatz(client)
    assert (e["art"], e["einheit"], e["optionen"]) == ("zahl", "€/Std.", [])
    assert _bundesland(client)["art"] == "auswahl"


@pytest.mark.parametrize("eingabe, gespeichert", [("52", "52"), ("47,50", "47.5"), (" 60.00 ", "60")])
def test_stundensatz_setzen(client, db, admin, eingabe, gespeichert):
    antwort = client.put(f"{URL}/stundensatz", json={"wert": eingabe})
    assert antwort.status_code == 200 and antwort.json()["wert"] == gespeichert
    assert wert(db, "stundensatz") == gespeichert


@pytest.mark.parametrize("eingabe", ["0", "-5", "viel", "1001", "45,123", "", "NaN"])
def test_stundensatz_ungueltig(client, db, admin, eingabe):
    vorher = wert(db, "stundensatz")
    antwort = client.put(f"{URL}/stundensatz", json={"wert": eingabe})
    assert antwort.status_code == 422 and antwort.json()["detail"][0]["loc"][-1] == "wert"
    assert wert(db, "stundensatz") == vorher

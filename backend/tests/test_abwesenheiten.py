"""Abwesenheiten pflegen (Datenmodell 2.3, 7.2): nur Werkstattleitung/Admin, stornieren statt löschen."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Abwesenheit, Systemrolle, SystemEreignisLog
from app.terminschaetzung import schaetze_fertigstellung
from tests.beispieldaten import Werkstatt
from tests.conftest import OHNE_ANMELDUNG, angemeldet_als, konto_anlegen

URL = "/abwesenheiten"
HEUTE = date.today()


def tag(n: int) -> str:
    return (HEUTE + timedelta(days=n)).isoformat()


@pytest.fixture
def leitung(db, client):
    person = konto_anlegen(db, Systemrolle.werkstattleiter, name="Leitung")
    client.headers.update(angemeldet_als(person))
    return person


@pytest.fixture
def m(db):
    """Ein Mitarbeiter mit eindeutigem Namen (für die Suche)."""
    return konto_anlegen(db, name=f"AB{uuid.uuid4().hex[:6]} Geigenbauer")


def urlaub(m, von=10, bis=14, **extra):
    return {"mitarbeiter_id": str(m.id), "typ": "urlaub", "von_datum": tag(von), "bis_datum": tag(bis), **extra}


def _felder(antwort):
    assert antwort.status_code == 422, antwort.text
    return {f["loc"][-1]: f["msg"] for f in antwort.json()["detail"]}


# --- Berechtigungen ----------------------------------------------------------------

@pytest.mark.parametrize("methode, pfad", [
    ("get", URL), ("post", URL), ("patch", f"{URL}/{uuid.uuid4()}"),
    ("post", f"{URL}/{uuid.uuid4()}/stornieren"), ("post", f"{URL}/{uuid.uuid4()}/wiederherstellen"),
])
def test_nur_leitung_und_admin(client, db, m, methode, pfad):
    daten = {} if methode == "get" else {"json": urlaub(m)}
    mitarbeiter = angemeldet_als(konto_anlegen(db, Systemrolle.mitarbeiter))
    assert getattr(client, methode)(pfad, headers=mitarbeiter, **daten).status_code == 403
    assert getattr(client, methode)(pfad, headers=OHNE_ANMELDUNG, **daten).status_code == 401


def test_admin_darf_auch(client, db, m):
    admin = angemeldet_als(konto_anlegen(db, Systemrolle.admin))
    assert client.post(URL, headers=admin, json=urlaub(m)).status_code == 201


# --- Anlegen und Regeln ------------------------------------------------------------

def test_anlegen_mit_protokoll(client, db, leitung, m):
    antwort = client.post(URL, json=urlaub(m))
    assert antwort.status_code == 201
    a = antwort.json()
    assert (a["mitarbeiter_name"], a["typ"], a["von_datum"], a["bis_datum"]) == (m.name, "urlaub", tag(10), tag(14))
    assert a["reduzierte_stunden"] is None and a["storniert_am"] is None

    [log] = db.scalars(select(SystemEreignisLog).where(SystemEreignisLog.betroffene_id == uuid.UUID(a["id"]))).all()
    assert (log.aktion, log.ausgefuehrt_von_mitarbeiter_id) == ("abwesenheit_angelegt", leitung.id)
    assert log.details["neu"]["von_datum"] == tag(10)


def test_betriebsweit_ohne_mitarbeiter(client, leitung, m):
    a = client.post(URL, json={"typ": "betriebsschliessung", "von_datum": tag(100), "bis_datum": tag(104)})
    assert a.status_code == 201 and a.json()["mitarbeiter_name"] is None
    assert "ganze Werkstatt" in _felder(client.post(URL, json=urlaub(m, typ="feiertag")))["mitarbeiter_id"]


def test_reduzierte_stunden(client, leitung, m):
    a = client.post(URL, json=urlaub(m, typ="reduzierte_stunden", reduzierte_stunden=20))
    assert a.status_code == 201 and a.json()["reduzierte_stunden"] == 20.0
    assert "reduzierte_stunden" in _felder(client.post(URL, json=urlaub(m, 30, 31, typ="reduzierte_stunden")))
    assert "reduzierte_stunden" in _felder(client.post(URL, json=urlaub(m, 30, 31, reduzierte_stunden=20)))


@pytest.mark.parametrize("aenderung, feld", [
    ({"bis_datum": tag(5)}, "bis_datum"),                    # Ende vor Beginn
    ({"mitarbeiter_id": None}, "mitarbeiter_id"),            # Urlaub braucht einen Mitarbeiter
    ({"mitarbeiter_id": str(uuid.uuid4())}, "mitarbeiter_id"),
    ({"typ": "ferien"}, "typ"),
    ({"von_datum": "kein Datum"}, "von_datum"),
    ({"typ": "reduzierte_stunden", "reduzierte_stunden": 0}, "reduzierte_stunden"),
    ({"typ": "reduzierte_stunden", "reduzierte_stunden": 81}, "reduzierte_stunden"),
])
def test_ungueltige_eingaben_melden_das_feld(client, leitung, m, aenderung, feld):
    assert feld in _felder(client.post(URL, json={**urlaub(m), **aenderung}))


def test_deaktivierter_mitarbeiter_abgelehnt(client, db, leitung, m):
    m.aktiv, m.deaktiviert_am = False, datetime.now(timezone.utc)
    db.flush()
    assert "deaktiviert" in _felder(client.post(URL, json=urlaub(m)))["mitarbeiter_id"]


def test_doppeleintrag_gleicher_typ_abgelehnt(client, leitung, m, db):
    assert client.post(URL, json=urlaub(m, 10, 14)).status_code == 201
    antwort = client.post(URL, json=urlaub(m, 14, 20))
    assert antwort.status_code == 409 and "Überschneidet" in antwort.json()["detail"]
    # Anderer Typ im selben Zeitraum (krank im Urlaub) und anderer Mitarbeiter sind erlaubt
    assert client.post(URL, json=urlaub(m, 12, 13, typ="krankheit")).status_code == 201
    assert client.post(URL, json=urlaub(konto_anlegen(db, name="Kollegin"), 10, 14)).status_code == 201
    # Die Sitzung ist sauber: ein gültiger Eintrag danach gelingt
    assert client.post(URL, json=urlaub(m, 15, 20)).status_code == 201


def test_notiz_optional_und_leer_ist_keine(client, db, leitung, m):
    a = client.post(URL, json=urlaub(m, notiz="  Familienfeier  ")).json()
    assert a["notiz"] == "Familienfeier"
    assert client.patch(f"{URL}/{a['id']}", json={"notiz": "   "}).json()["notiz"] is None
    assert client.post(URL, json=urlaub(m, 40, 41)).json()["notiz"] is None
    assert "notiz" in _felder(client.post(URL, json=urlaub(m, 60, 61, notiz="x" * 501)))
    log = db.scalars(select(SystemEreignisLog).where(SystemEreignisLog.betroffene_id == uuid.UUID(a["id"]))
                     .order_by(SystemEreignisLog.zeitpunkt)).all()
    assert (log[0].details["neu"]["notiz"], log[1].details["neu"]["notiz"]) == ("Familienfeier", None)


# --- Bearbeiten, Stornieren, Wiederherstellen --------------------------------------

def test_bearbeiten_mit_protokoll_und_ablehnung_ohne_reste(client, db, leitung, m):
    a = client.post(URL, json=urlaub(m)).json()
    neu = client.patch(f"{URL}/{a['id']}", json={"bis_datum": tag(16)})
    assert neu.status_code == 200 and neu.json()["bis_datum"] == tag(16)

    # Abgelehnte Änderung: nichts davon bleibt hängen
    assert "bis_datum" in _felder(client.patch(f"{URL}/{a['id']}", json={"bis_datum": tag(1)}))
    assert "mitarbeiter_id" in _felder(client.patch(f"{URL}/{a['id']}", json={"typ": "feiertag"}))
    db.expire_all()
    gespeichert = db.get(Abwesenheit, uuid.UUID(a["id"]))
    assert (gespeichert.bis_datum.isoformat(), gespeichert.typ.value) == (tag(16), "urlaub")

    aktionen = db.scalars(select(SystemEreignisLog.aktion).where(SystemEreignisLog.betroffene_id == uuid.UUID(a["id"]))
                          .order_by(SystemEreignisLog.zeitpunkt)).all()
    assert aktionen == ["abwesenheit_angelegt", "abwesenheit_geaendert"]
    # Ohne tatsächliche Änderung kein weiterer Protokolleintrag
    client.patch(f"{URL}/{a['id']}", json={"bis_datum": tag(16)})
    assert db.scalar(select(SystemEreignisLog).where(SystemEreignisLog.betroffene_id == uuid.UUID(a["id"]))
                     .order_by(SystemEreignisLog.zeitpunkt.desc()).limit(1)).aktion == "abwesenheit_geaendert"
    assert client.patch(f"{URL}/{uuid.uuid4()}", json={"bis_datum": tag(16)}).status_code == 404


def test_typwechsel_auf_betriebsweit(client, leitung, m):
    a = client.post(URL, json=urlaub(m)).json()
    neu = client.patch(f"{URL}/{a['id']}", json={"typ": "betriebsschliessung", "mitarbeiter_id": None})
    assert neu.status_code == 200 and neu.json()["mitarbeiter_name"] is None


def test_stornieren_loescht_nicht_und_ist_umkehrbar(client, db, leitung, m):
    a = client.post(URL, json=urlaub(m)).json()
    storniert = client.post(f"{URL}/{a['id']}/stornieren")
    assert storniert.status_code == 200 and storniert.json()["storniert_am"] is not None
    assert db.get(Abwesenheit, uuid.UUID(a["id"])) is not None
    assert client.post(f"{URL}/{a['id']}/stornieren").status_code == 409
    assert client.patch(f"{URL}/{a['id']}", json={"bis_datum": tag(16)}).status_code == 409  # erst wiederherstellen

    # Storniert blockiert keinen neuen Eintrag – der neue blockiert dann aber das Wiederherstellen
    ersatz = client.post(URL, json=urlaub(m)).json()
    assert client.post(f"{URL}/{a['id']}/wiederherstellen").status_code == 409
    client.post(f"{URL}/{ersatz['id']}/stornieren")
    wieder = client.post(f"{URL}/{a['id']}/wiederherstellen")
    assert wieder.status_code == 200 and wieder.json()["storniert_am"] is None
    assert client.post(f"{URL}/{a['id']}/wiederherstellen").status_code == 409

    aktionen = db.scalars(select(SystemEreignisLog.aktion).where(SystemEreignisLog.betroffene_id == uuid.UUID(a["id"]))
                          .order_by(SystemEreignisLog.zeitpunkt)).all()
    assert aktionen == ["abwesenheit_angelegt", "abwesenheit_storniert", "abwesenheit_wiederhergestellt"]


def test_stornierte_abwesenheit_zaehlt_nicht_fuer_den_termin(client, db, leitung):
    w = Werkstatt(db)
    auftrag = w.auftrag(status=w.in_bearbeitung, zugewiesen=w.mitarbeiter, stunden="8.00")
    ohne = schaetze_fertigstellung(db, auftrag).datum

    a = client.post(URL, json=urlaub(w.mitarbeiter, 0, 20)).json()
    assert schaetze_fertigstellung(db, auftrag).datum > ohne
    client.post(f"{URL}/{a['id']}/stornieren")
    assert schaetze_fertigstellung(db, auftrag).datum == ohne


# --- Liste nach 9.11 ---------------------------------------------------------------

@pytest.fixture
def eintraege(client, leitung, m):
    suche = m.name.split()[0]
    client.post(URL, json=urlaub(m, 30, 35))
    client.post(URL, json=urlaub(m, 10, 12, typ="krankheit"))
    client.post(URL, json=urlaub(m, -20, -15, typ="schulung"))                      # vergangen
    storniert = client.post(URL, json=urlaub(m, 50, 55)).json()
    client.post(f"{URL}/{storniert['id']}/stornieren")
    return suche


def _typen(antwort):
    assert antwort.status_code == 200, antwort.text
    return [a["typ"] for a in antwort.json()["eintraege"]]


def test_liste_standard_ab_heute_naechste_zuerst(client, eintraege):
    antwort = client.get(URL, params={"suche": eintraege})
    assert _typen(antwort) == ["krankheit", "urlaub"]  # ohne vergangene und stornierte
    daten = antwort.json()
    assert daten["treffer"] == 2 and daten["gesamt"] > daten["treffer"]


def test_liste_filter_und_sortierung(client, eintraege, m):
    assert _typen(client.get(URL, params={"suche": eintraege, "zeitraum": "vergangen"})) == ["schulung"]
    assert _typen(client.get(URL, params={"suche": eintraege, "zeitraum": "alle", "status": "alle"})) == \
        ["schulung", "krankheit", "urlaub", "urlaub"]
    assert _typen(client.get(URL, params={"suche": eintraege, "status": "storniert"})) == ["urlaub"]
    assert _typen(client.get(URL, params={"mitarbeiter": str(m.id), "typ": "urlaub"})) == ["urlaub"]
    assert _typen(client.get(URL, params={"mitarbeiter": str(m.id), "richtung": "ab", "seitengroesse": 1})) == ["urlaub"]
    assert client.get(URL, params={"sortierung": "storniert_am"}).status_code == 422
    assert client.get(URL, params={"mitarbeiter": "jemand"}).status_code == 422


def test_liste_filter_werkstatt(client, leitung, m):
    client.post(URL, json=urlaub(m, 400, 401))
    b = client.post(URL, json={"typ": "feiertag", "von_datum": tag(400), "bis_datum": tag(400)}).json()
    ids = [a["id"] for a in client.get(URL, params={"mitarbeiter": "werkstatt", "seitengroesse": 100}).json()["eintraege"]]
    assert b["id"] in ids
    assert all(a["mitarbeiter_id"] is None
               for a in client.get(URL, params={"mitarbeiter": "werkstatt"}).json()["eintraege"])

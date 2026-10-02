"""Feiertags-Automatik (Datenmodell 9.13.1): erzeugen, nichts doppelt, nichts überschreiben."""

from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select

from app.feiertage import AKTION, automatik_zuruecksetzen, feiertage_sicherstellen, gesetzliche_feiertage
from app.models import Abwesenheit, Abwesenheitstyp, Einstellung, Systemrolle, SystemEreignisLog
from tests.conftest import angemeldet_als, konto_anlegen

URL = "/admin/feiertage"
JAHR = date.today().year + 3  # liegt im erlaubten Bereich, wird von der Automatik aber nicht angefasst
FRONLEICHNAM = next(tag for tag, name in gesetzliche_feiertage("Baden-Württemberg", JAHR).items() if name == "Fronleichnam")


@pytest.fixture
def admin(db, client):
    person = konto_anlegen(db, Systemrolle.admin, name="Admin")
    client.headers.update(angemeldet_als(person))
    return person


@pytest.fixture(autouse=True)
def leere_ausgangslage(db):
    """Unabhängig von echten Daten: keine Feiertage, keine Läufe, kein Bundesland (wird zurückgerollt)."""
    db.execute(delete(Abwesenheit).where(Abwesenheit.typ == Abwesenheitstyp.feiertag))
    db.execute(delete(SystemEreignisLog).where(SystemEreignisLog.aktion == AKTION))
    db.execute(delete(Einstellung).where(Einstellung.schluessel == "bundesland"))
    db.flush()
    automatik_zuruecksetzen()
    yield
    automatik_zuruecksetzen()


def bundesland(db, name="Baden-Württemberg"):
    eintrag = db.scalar(select(Einstellung).where(Einstellung.schluessel == "bundesland"))
    if eintrag is None:
        db.add(Einstellung(schluessel="bundesland", wert=name))
    else:
        eintrag.wert = name
    db.flush()


def feiertage(db, jahr=JAHR, nur_aktive=False):
    abfrage = select(Abwesenheit).where(
        Abwesenheit.typ == Abwesenheitstyp.feiertag,
        Abwesenheit.von_datum >= date(jahr, 1, 1), Abwesenheit.von_datum <= date(jahr, 12, 31),
    ).order_by(Abwesenheit.von_datum)
    if nur_aktive:
        abfrage = abfrage.where(Abwesenheit.storniert_am.is_(None))
    return db.scalars(abfrage).all()


def erzeugen(client, jahr=JAHR):
    antwort = client.post(URL, json={"jahr": jahr})
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


# --- Erzeugen ----------------------------------------------------------------------

def test_erzeugt_feiertage_des_bundeslands_fuer_ein_jahr(client, db, admin):
    bundesland(db)
    ergebnis = erzeugen(client)
    assert (ergebnis["jahr"], ergebnis["bundesland"], len(ergebnis["angelegt"]), ergebnis["uebersprungen"]) == \
        (JAHR, "Baden-Württemberg", 12, [])

    eintraege = feiertage(db)
    assert len(eintraege) == 12
    namen = {e.notiz for e in eintraege}
    assert {"Neujahr", "Heilige Drei Könige", "Fronleichnam", "Allerheiligen", "Erster Weihnachtstag"} <= namen
    for e in eintraege:  # werkstattweit, ganztägig, eintägig
        assert (e.mitarbeiter_id, e.reduzierte_stunden, e.storniert_am) == (None, None, None) and e.von_datum == e.bis_datum
    # Jeder Feiertag steht im Änderungsprotokoll, ausgelöst vom Admin
    logs = db.scalars(select(SystemEreignisLog).where(SystemEreignisLog.betroffene_id.in_([e.id for e in eintraege]))).all()
    assert len(logs) == 12 and all(log.ausgefuehrt_von_mitarbeiter_id == admin.id for log in logs)
    assert logs[0].details["quelle"] == "feiertags_automatik"


def test_bundeslandspezifisch(client, db, admin):
    bundesland(db, "Berlin")
    namen = {t["name"] for t in erzeugen(client)["angelegt"]}
    assert "Fronleichnam" not in namen and "Allerheiligen" not in namen and "Frauentag" in namen


def test_erneuter_aufruf_legt_nichts_doppelt_an(client, db, admin):
    bundesland(db)
    erzeugen(client)
    zweiter = erzeugen(client)
    assert (zweiter["angelegt"], len(zweiter["uebersprungen"])) == ([], 12)
    assert len(feiertage(db)) == 12


def test_feiertage_erscheinen_im_raster(client, db, admin):
    bundesland(db)
    erzeugen(client)
    raster = client.get("/abwesenheiten/raster", params={"von": FRONLEICHNAM.isoformat(), "tage": 1}).json()
    [eintrag] = [a for a in raster["abwesenheiten"] if a["typ"] == "feiertag"]
    assert (eintrag["mitarbeiter_id"], eintrag["notiz"]) == (None, "Fronleichnam")


# --- Nichts überschreiben ----------------------------------------------------------

def test_manuell_geaenderter_feiertag_wird_nicht_ueberschrieben(client, db, admin):
    bundesland(db)
    erzeugen(client)
    fronleichnam = next(e for e in feiertage(db) if e.notiz == "Fronleichnam")
    # Von Hand angepasst: Brückentag dazu und eigene Notiz
    geaendert = client.patch(f"/abwesenheiten/{fronleichnam.id}", json={
        "bis_datum": (FRONLEICHNAM + timedelta(days=1)).isoformat(), "notiz": "Fronleichnam + Brückentag"})
    assert geaendert.status_code == 200

    assert erzeugen(client)["angelegt"] == []
    db.expire_all()
    eintrag = db.get(Abwesenheit, fronleichnam.id)
    assert (eintrag.notiz, (eintrag.bis_datum - eintrag.von_datum).days) == ("Fronleichnam + Brückentag", 1)
    assert len(feiertage(db)) == 12


def test_stornierter_und_verschobener_feiertag_kommt_nicht_wieder(client, db, admin):
    bundesland(db)
    erzeugen(client)
    eintraege = {e.notiz: e for e in feiertage(db)}
    client.post(f"/abwesenheiten/{eintraege['Allerheiligen'].id}/stornieren")
    # Verschoben: am ursprünglichen Tag liegt danach kein Eintrag mehr
    verschoben = (FRONLEICHNAM + timedelta(days=1)).isoformat()
    assert client.patch(f"/abwesenheiten/{eintraege['Fronleichnam'].id}",
                        json={"von_datum": verschoben, "bis_datum": verschoben}).status_code == 200

    assert erzeugen(client)["angelegt"] == []
    assert len(feiertage(db)) == 12 and len(feiertage(db, nur_aktive=True)) == 11


def test_von_hand_eingetragener_feiertag_bleibt(client, db, admin):
    bundesland(db)
    neujahr = date(JAHR, 1, 1).isoformat()
    client.post("/abwesenheiten", json={"typ": "feiertag", "von_datum": neujahr, "bis_datum": neujahr, "notiz": "selbst eingetragen"})
    ergebnis = erzeugen(client)
    assert len(ergebnis["angelegt"]) == 11 and [t["name"] for t in ergebnis["uebersprungen"]] == ["Neujahr"]
    assert feiertage(db)[0].notiz == "selbst eingetragen"


# --- Bundesland aus den Einstellungen ----------------------------------------------

def test_ohne_bundesland_kein_erzeugen(client, db, admin):
    antwort = client.post(URL, json={"jahr": JAHR})
    assert antwort.status_code == 409 and "Bundesland" in antwort.json()["detail"]
    assert feiertage_sicherstellen(db) == [] and feiertage(db) == []


def test_bundesland_festlegen_erzeugt_laufendes_und_kommendes_jahr(client, db, admin):
    heute = date.today().year
    assert client.put("/admin/einstellungen/bundesland", json={"wert": "Baden-Württemberg"}).status_code == 200
    assert (len(feiertage(db, heute)), len(feiertage(db, heute + 1)), len(feiertage(db, heute + 2))) == (12, 12, 0)
    # Automatisch erzeugt: ohne auslösenden Mitarbeiter im Protokoll
    lauf = db.scalar(select(SystemEreignisLog).where(SystemEreignisLog.aktion == AKTION).limit(1))
    assert lauf.ausgefuehrt_von_mitarbeiter_id is None and lauf.details["bundesland"] == "Baden-Württemberg"

    stand = client.get(URL).json()
    assert stand["bundesland"] == "Baden-Württemberg"
    assert [(j["jahr"], j["anzahl"], j["bundesland"]) for j in stand["jahre"]] == \
        [(heute, 12, "Baden-Württemberg"), (heute + 1, 12, "Baden-Württemberg")]


def test_bundeslandwechsel_wirkt_nur_auf_neu_erzeugte_jahre(client, db, admin):
    heute = date.today().year
    client.put("/admin/einstellungen/bundesland", json={"wert": "Baden-Württemberg"})
    client.put("/admin/einstellungen/bundesland", json={"wert": "Berlin"})
    # Bereits erzeugte Jahre bleiben, wie sie sind (weiterhin mit Fronleichnam, ohne Frauentag)
    for jahr in (heute, heute + 1):
        namen = {e.notiz for e in feiertage(db, jahr)}
        assert len(namen) == 12 and "Fronleichnam" in namen and "Frauentag" not in namen
    # Ein neu erzeugtes Jahr nutzt das neue Bundesland
    namen = {t["name"] for t in erzeugen(client, heute + 2)["angelegt"]}
    assert "Frauentag" in namen and "Fronleichnam" not in namen


def test_raster_stoesst_die_automatik_an(client, db, admin):
    """Z. B. nach dem Jahreswechsel: Öffnen des Rasters legt das fehlende Jahr nach."""
    bundesland(db)
    heute = date.today().year
    assert feiertage(db, heute + 1) == []
    client.get("/abwesenheiten/raster", params={"von": date.today().isoformat()})
    assert (len(feiertage(db, heute)), len(feiertage(db, heute + 1))) == (12, 12)
    client.get("/abwesenheiten/raster", params={"von": date.today().isoformat()})
    assert len(feiertage(db, heute)) == 12


# --- Berechtigung und Eingaben -----------------------------------------------------

@pytest.mark.parametrize("rolle", [Systemrolle.mitarbeiter, Systemrolle.werkstattleiter])
def test_nur_admin(client, db, rolle):
    header = angemeldet_als(konto_anlegen(db, rolle))
    assert client.get(URL, headers=header).status_code == 403
    assert client.post(URL, headers=header, json={"jahr": JAHR}).status_code == 403


@pytest.mark.parametrize("jahr", [date.today().year - 2, date.today().year + 6, "bald", None])
def test_jahr_ausserhalb_des_bereichs(client, db, admin, jahr):
    bundesland(db)
    antwort = client.post(URL, json={"jahr": jahr})
    assert antwort.status_code == 422 and antwort.json()["detail"][0]["loc"][-1] == "jahr"

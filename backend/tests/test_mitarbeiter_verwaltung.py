"""Mitarbeiter-Verwaltung und Wochenstunden – nur Admin (2.2, 2.12, 7.2)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from app.models import Mitarbeiter, MitarbeiterArbeitszeit, Systemrolle, SystemEreignisLog
from app.routers.admin.mitarbeiter import letzter_aktiver_admin_pruefen
from app.terminschaetzung import schaetze_fertigstellung
from tests.beispieldaten import Werkstatt
from tests.conftest import TEST_PASSWORT, angemeldet_als, konto_anlegen

URL = "/admin/mitarbeiter"


@pytest.fixture
def admin(db, client):
    person = konto_anlegen(db, Systemrolle.admin, name="Admin A")
    client.headers.update(angemeldet_als(person))
    return person


def log(db, betroffen, aktion):
    return db.scalars(select(SystemEreignisLog).where(
        SystemEreignisLog.betroffene_id == betroffen, SystemEreignisLog.aktion == aktion)).all()


# --- Berechtigungen -------------------------------------------------------------

@pytest.mark.parametrize("rolle", [Systemrolle.mitarbeiter, Systemrolle.werkstattleiter])
@pytest.mark.parametrize("methode, pfad, daten", [
    ("get", "", None),
    ("post", "/{id}/deaktivieren", None),
    ("patch", "/{id}/systemrolle", {"systemrolle": "admin"}),
    ("post", "/{id}/wochenstunden", {"wochenstunden": 30, "gueltig_ab": "2030-01-01"}),
    ("get", "/{id}/wochenstunden", None),
])
def test_nicht_admin_abgelehnt(client, db, rolle, methode, pfad, daten):
    person = konto_anlegen(db, rolle)
    antwort = getattr(client, methode)(URL + pfad.format(id=person.id), headers=angemeldet_als(person),
                                       **({"json": daten} if daten else {}))
    assert antwort.status_code == 403


# --- Liste ----------------------------------------------------------------------

def test_liste_mit_rolle_status_und_wochenstunden(client, db, admin):
    m = konto_anlegen(db, name="Liste Testperson")
    eintrag = next(x for x in client.get(URL, params={"suche": "Liste Testperson"}).json()["eintraege"]
                   if x["id"] == str(m.id))
    assert eintrag["systemrolle"] == "mitarbeiter" and eintrag["aktiv"] is True
    assert eintrag["wochenstunden"] == {"wochenstunden": 40.0, "quelle": "standard", "gueltig_ab": None}
    assert eintrag["offene_auftraege"] == 0


# --- Deaktivieren / Aktivieren ------------------------------------------------------

def test_deaktivieren_sperrt_anmeldung_sofort_und_loescht_nicht(client, db, admin):
    m = konto_anlegen(db, name="Geht bald")
    token = angemeldet_als(m)
    assert client.get("/auth/ich", headers=token).status_code == 200

    antwort = client.post(f"{URL}/{m.id}/deaktivieren")
    assert antwort.status_code == 200
    assert antwort.json()["aktiv"] is False and antwort.json()["deaktiviert_am"] is not None

    assert client.get("/auth/ich", headers=token).status_code == 401  # bestehendes Token wertlos
    assert client.post("/auth/login", data={"username": m.email, "password": TEST_PASSWORT}).status_code == 401
    assert db.get(Mitarbeiter, m.id) is not None  # nicht gelöscht
    [eintrag] = log(db, m.id, "mitarbeiter_deaktiviert")
    assert eintrag.ausgefuehrt_von_mitarbeiter_id == admin.id
    assert eintrag.details == {"alt": {"aktiv": True}, "neu": {"aktiv": False}}

    antwort = client.post(f"{URL}/{m.id}/aktivieren").json()
    assert antwort["aktiv"] is True and antwort["deaktiviert_am"] is None
    assert client.post("/auth/login", data={"username": m.email, "password": TEST_PASSWORT}).status_code == 200


def test_selbst_deaktivieren_abgelehnt(client, admin):
    antwort = client.post(f"{URL}/{admin.id}/deaktivieren")
    assert antwort.status_code == 409
    assert "selbst" in antwort.json()["detail"]


def test_deaktivieren_mit_offenen_auftraegen_abgelehnt(client, db, admin):
    w = Werkstatt(db)
    w.auftrag(status=w.in_bearbeitung, zugewiesen=w.mitarbeiter)
    antwort = client.post(f"{URL}/{w.mitarbeiter.id}/deaktivieren")
    assert antwort.status_code == 409
    assert "neu zuweisen" in antwort.json()["detail"]
    assert db.get(Mitarbeiter, w.mitarbeiter.id).aktiv is True
    # Abgeschlossene Aufträge stehen dem Deaktivieren nicht im Weg
    andere = konto_anlegen(db, name="Nur Erledigtes")
    w.auftrag(status=w.fertig, zugewiesen=andere)
    assert client.post(f"{URL}/{andere.id}/deaktivieren").status_code == 200


def test_doppelt_deaktivieren_oder_aktivieren(client, db, admin):
    m = konto_anlegen(db)
    assert client.post(f"{URL}/{m.id}/aktivieren").status_code == 409
    client.post(f"{URL}/{m.id}/deaktivieren")
    assert client.post(f"{URL}/{m.id}/deaktivieren").status_code == 409


# --- Systemrolle ----------------------------------------------------------------------

def test_systemrolle_aendern_wirkt_sofort(client, db, admin):
    m = konto_anlegen(db)
    header = angemeldet_als(m)
    assert client.get("/admin/reparaturarten", headers=header).status_code == 403

    antwort = client.patch(f"{URL}/{m.id}/systemrolle", json={"systemrolle": "admin"})
    assert antwort.json()["systemrolle"] == "admin"
    assert client.get("/admin/reparaturarten", headers=header).status_code == 200  # gleiches Token
    [eintrag] = log(db, m.id, "rolle_geaendert")
    assert eintrag.details == {"alt": {"systemrolle": "mitarbeiter"}, "neu": {"systemrolle": "admin"}}


def test_selbst_herabstufen_abgelehnt(client, admin):
    antwort = client.patch(f"{URL}/{admin.id}/systemrolle", json={"systemrolle": "werkstattleiter"})
    assert antwort.status_code == 409


def test_anderen_admin_herabstufen_erlaubt(client, db, admin):
    zweiter = konto_anlegen(db, Systemrolle.admin, name="Admin B")
    assert client.patch(f"{URL}/{zweiter.id}/systemrolle", json={"systemrolle": "werkstattleiter"}).status_code == 200


def test_letzter_aktiver_admin_geschuetzt(db):
    # Über die API nur bei gleichzeitigen Änderungen erreichbar (Selbstschutz greift vorher),
    # deshalb direkt geprüft: Es gibt genau einen aktiven Admin.
    db.execute(update(Mitarbeiter).where(Mitarbeiter.systemrolle == Systemrolle.admin)
               .values(systemrolle=Systemrolle.werkstattleiter))
    einziger = konto_anlegen(db, Systemrolle.admin, name="Einziger Admin")
    with pytest.raises(HTTPException) as fehler:
        letzter_aktiver_admin_pruefen(db, einziger)
    assert fehler.value.status_code == 409
    # Mit einem zweiten aktiven Admin ist es erlaubt
    konto_anlegen(db, Systemrolle.admin, name="Zweiter Admin")
    letzter_aktiver_admin_pruefen(db, einziger)


# --- Wochenstunden --------------------------------------------------------------------

def test_wochenstunden_verlauf_schliesst_alten_eintrag_ab(client, db, admin):
    m = konto_anlegen(db, name="Teilzeit")
    v = client.get(f"{URL}/{m.id}/wochenstunden").json()
    assert v["aktuell"]["quelle"] == "standard" and v["eintraege"] == []

    v = client.post(f"{URL}/{m.id}/wochenstunden", json={"wochenstunden": 20, "gueltig_ab": "2025-01-01"}).json()
    assert v["aktuell"] == {"wochenstunden": 20.0, "quelle": "hinterlegt", "gueltig_ab": "2025-01-01"}

    antwort = client.post(f"{URL}/{m.id}/wochenstunden", json={"wochenstunden": 30, "gueltig_ab": "2026-03-01"})
    assert antwort.status_code == 201
    v = antwort.json()
    neu, alt = v["eintraege"]  # neueste zuerst
    assert (neu["wochenstunden"], neu["gueltig_ab"], neu["gueltig_bis"]) == (30.0, "2026-03-01", None)
    assert (alt["wochenstunden"], alt["gueltig_ab"], alt["gueltig_bis"]) == (20.0, "2025-01-01", "2026-02-28")
    assert neu["geaendert_von_mitarbeiter_id"] == str(admin.id)
    assert v["aktuell"]["wochenstunden"] == 30.0

    # Alter Wert wurde nicht überschrieben, sondern steht weiterhin in der Datenbank
    werte = db.scalars(select(MitarbeiterArbeitszeit.wochenstunden).where(
        MitarbeiterArbeitszeit.mitarbeiter_id == m.id).order_by(MitarbeiterArbeitszeit.gueltig_ab)).all()
    assert werte == [Decimal("20.00"), Decimal("30.00")]

    [eintrag] = log(db, m.id, "wochenstunden_festgelegt")[1:]
    assert eintrag.details["alt"] == {"wochenstunden": "20.00", "gueltig_ab": "2025-01-01", "gueltig_bis": "2026-02-28"}
    assert eintrag.details["neu"] == {"wochenstunden": "30.00", "gueltig_ab": "2026-03-01"}


def test_wochenstunden_in_der_zukunft_gelten_noch_nicht(client, db, admin):
    m = konto_anlegen(db)
    client.post(f"{URL}/{m.id}/wochenstunden", json={"wochenstunden": 25, "gueltig_ab": "2099-01-01"})
    assert client.get(f"{URL}/{m.id}/wochenstunden").json()["aktuell"]["quelle"] == "standard"


def test_wochenstunden_nicht_rueckdatiert_vor_bisherigen(client, db, admin):
    m = konto_anlegen(db)
    client.post(f"{URL}/{m.id}/wochenstunden", json={"wochenstunden": 30, "gueltig_ab": "2026-01-01"})
    for datum in ["2026-01-01", "2025-06-01"]:
        antwort = client.post(f"{URL}/{m.id}/wochenstunden", json={"wochenstunden": 35, "gueltig_ab": datum})
        assert antwort.status_code == 409


@pytest.mark.parametrize("stunden", [0, -5, 81, 12.345])
def test_wochenstunden_ungueltig(client, db, admin, stunden):
    m = konto_anlegen(db)
    antwort = client.post(f"{URL}/{m.id}/wochenstunden", json={"wochenstunden": stunden, "gueltig_ab": "2026-01-01"})
    assert antwort.status_code == 422


def test_wochenstunden_wirken_auf_terminschaetzung(client, db, admin):
    w = Werkstatt(db)
    a = w.auftrag(status=w.in_bearbeitung, zugewiesen=w.mitarbeiter, stunden="8")
    client.post(f"{URL}/{w.mitarbeiter.id}/wochenstunden", json={"wochenstunden": 20, "gueltig_ab": "2020-01-01"})
    t = schaetze_fertigstellung(db, a, heute=date(2030, 3, 4))
    assert t.eingabefaktoren["stunden_pro_tag"] == "4.00"
    assert t.eingabefaktoren["wochenstunden_quelle"] == "mitarbeiter_arbeitszeit"


def test_nicht_gefunden(client, admin):
    assert client.get(f"{URL}/{uuid.uuid4()}").status_code == 404
    assert client.post(f"{URL}/{uuid.uuid4()}/deaktivieren").status_code == 404



# --- Liste nach 9.11: Suche, Filter, Sortierung, Seiten --------------------------

@pytest.fixture
def personal(db):
    """Eigene Test-Mitarbeiter mit eindeutigem Namensteil, damit echte Daten nicht stören."""
    kennung = f"LT{uuid.uuid4().hex[:6]}"
    leute = {
        "anna": konto_anlegen(db, name=f"{kennung} Anna"),
        "bert": konto_anlegen(db, Systemrolle.werkstattleiter, name=f"{kennung} Bert"),
        "cleo": konto_anlegen(db, name=f"{kennung} Cleo 100%_sicher"),
        "dora": konto_anlegen(db, name=f"{kennung} Dora"),
    }
    leute["anna"].rolle = "Geigenbauerin"  # fachliche Rolle
    leute["bert"].rolle = "Blechblas-Techniker"
    leute["dora"].aktiv = False
    from datetime import UTC, datetime
    leute["dora"].deaktiviert_am = datetime.now(UTC)
    db.flush()
    return kennung, leute


def namen(antwort):
    return [e["name"].split(" ", 1)[1] for e in antwort.json()["eintraege"]]


def test_liste_standard_nur_aktive_nach_name(client, admin, personal):
    kennung, _ = personal
    antwort = client.get(URL, params={"suche": kennung})
    daten = antwort.json()
    assert namen(antwort) == ["Anna", "Bert", "Cleo 100%_sicher"]
    assert (daten["treffer"], daten["seite"], daten["sortierung"], daten["richtung"]) == (3, 1, "name", "auf")
    assert daten["gesamt"] >= 5  # alle Mitarbeiter ohne Suche/Filter (inkl. Admin, Deaktivierte)


def test_liste_filter_status_und_rolle(client, admin, personal):
    kennung, _ = personal
    assert namen(client.get(URL, params={"suche": kennung, "status": "deaktiviert"})) == ["Dora"]
    assert len(namen(client.get(URL, params={"suche": kennung, "status": "alle"}))) == 4
    assert namen(client.get(URL, params={"suche": kennung, "systemrolle": "werkstattleiter"})) == ["Bert"]


def test_liste_suche_in_fachrolle_und_email(client, admin, personal):
    kennung, leute = personal
    assert namen(client.get(URL, params={"suche": "blechblas", "status": "alle"}))[-1:] == ["Bert"]
    antwort = client.get(URL, params={"suche": leute["anna"].email.upper()})
    assert namen(antwort) == ["Anna"]


def test_liste_suche_platzhalter_werden_woertlich_genommen(client, admin, personal):
    kennung, _ = personal
    assert namen(client.get(URL, params={"suche": f"{kennung} Cleo 100%_"})) == ["Cleo 100%_sicher"]
    assert namen(client.get(URL, params={"suche": f"{kennung}%"})) == []  # "%" ist kein Platzhalter


def test_liste_sortierung_und_seiten(client, admin, personal):
    kennung, _ = personal
    params = {"suche": kennung, "status": "alle", "sortierung": "name", "richtung": "ab", "seitengroesse": 3}
    seite1 = client.get(URL, params=params).json()
    seite2 = client.get(URL, params={**params, "seite": 2}).json()
    alle = [e["name"].split(" ", 1)[1] for e in seite1["eintraege"] + seite2["eintraege"]]
    assert alle == ["Dora", "Cleo 100%_sicher", "Bert", "Anna"]
    assert (seite1["treffer"], len(seite1["eintraege"]), len(seite2["eintraege"])) == (4, 3, 1)
    assert namen(client.get(URL, params={"suche": kennung, "sortierung": "systemrolle", "richtung": "ab"}))[0] == "Bert"


@pytest.mark.parametrize("params", [{"sortierung": "passwort_hash"}, {"seite": 0}, {"seitengroesse": 101}, {"status": "weg"}])
def test_liste_ungueltige_parameter(client, admin, params):
    assert client.get(URL, params=params).status_code == 422

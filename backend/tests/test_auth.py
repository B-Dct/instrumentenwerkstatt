"""Tests für Login und Berechtigungen (Datenmodell 2.2, 7.2)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app import konto_anlegen as skript
from app.auth import passwort_pruefen
from app.config import settings
from app.models import Mitarbeiter, SchaetzungsLog, Systemrolle
from tests.beispieldaten import Werkstatt
from tests.conftest import OHNE_ANMELDUNG, TEST_PASSWORT, angemeldet_als, konto_anlegen


def einloggen(client, email, passwort):
    return client.post("/auth/login", data={"username": email, "password": passwort})


# --- Login ------------------------------------------------------------------

def test_login_erfolgreich(client, db):
    admin = konto_anlegen(db, Systemrolle.admin, name="Chefin")
    antwort = einloggen(client, admin.email, TEST_PASSWORT)
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["token_type"] == "bearer"
    assert daten["mitarbeiter"]["systemrolle"] == "admin"

    inhalt = jwt.decode(daten["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert inhalt["sub"] == str(admin.id)
    assert inhalt["systemrolle"] == "admin"

    # Mit dem Token funktioniert eine geschützte Anfrage
    ich = client.get("/auth/ich", headers={"Authorization": f"Bearer {daten['access_token']}"})
    assert ich.json()["id"] == str(admin.id)


def test_login_email_ohne_gross_klein_und_leerzeichen(client, db):
    m = konto_anlegen(db)
    assert einloggen(client, f"  {m.email.upper()} ", TEST_PASSWORT).status_code == 200


@pytest.mark.parametrize("fall", ["falsches_passwort", "unbekannte_email", "deaktiviert"])
def test_login_abgelehnt(client, db, fall):
    m = konto_anlegen(db)
    email, passwort = m.email, TEST_PASSWORT
    if fall == "falsches_passwort":
        passwort = "falsch"
    elif fall == "unbekannte_email":
        email = "niemand@test.invalid"
    else:
        m.aktiv, m.deaktiviert_am = False, datetime.now(UTC)
        db.flush()

    antwort = einloggen(client, email, passwort)
    assert antwort.status_code == 401
    # Immer dieselbe Meldung – verrät nicht, ob die E-Mail existiert
    assert antwort.json()["detail"] == "E-Mail oder Passwort ungültig"


# --- Token-Prüfung ----------------------------------------------------------

def test_ohne_token_abgelehnt(client):
    assert client.get("/auftraege").status_code == 401
    assert client.post("/auftraege", json={}).status_code == 401
    assert client.get("/admin/vorgabewerte").status_code == 401


def _token(sub, **aenderungen):
    jetzt = datetime.now(UTC)
    inhalt = {"sub": str(sub), "systemrolle": "admin", "iat": jetzt, "exp": jetzt + timedelta(hours=1)}
    inhalt.update(aenderungen)
    return {"Authorization": f"Bearer {jwt.encode(inhalt, settings.jwt_secret, 'HS256')}"}


def test_ungueltige_tokens_abgelehnt(client, db):
    m = konto_anlegen(db)
    gefaelscht = jwt.encode({"sub": str(m.id), "exp": datetime.now(UTC) + timedelta(hours=1)}, "falscher-schluessel", "HS256")
    for header in [
        _token(m.id, exp=datetime.now(UTC) - timedelta(minutes=1)),  # abgelaufen
        {"Authorization": f"Bearer {gefaelscht}"},                   # falsch signiert
        _token(uuid.uuid4()),                                        # unbekannter Mitarbeiter
        _token("keine-uuid"),                                        # kaputter Inhalt
        {"Authorization": "Bearer quatsch"},
    ]:
        assert client.get("/auth/ich", headers=header).status_code == 401


def test_deaktivierter_mitarbeiter_verliert_zugriff_sofort(client, db):
    m = konto_anlegen(db)
    header = angemeldet_als(m)
    assert client.get("/auth/ich", headers=header).status_code == 200
    m.aktiv, m.deaktiviert_am = False, datetime.now(UTC)
    db.flush()
    assert client.get("/auth/ich", headers=header).status_code == 401


def test_rolle_kommt_aus_datenbank_nicht_aus_token(client, db):
    m = konto_anlegen(db, Systemrolle.mitarbeiter)
    # Token behauptet "admin" – zählt aber nicht
    assert client.get("/admin/vorgabewerte", headers=_token(m.id, systemrolle="admin")).status_code == 403


# --- Rollen -----------------------------------------------------------------

@pytest.mark.parametrize("rolle, erwartet", [
    (Systemrolle.mitarbeiter, 403),
    (Systemrolle.werkstattleiter, 403),
    (Systemrolle.admin, 200),
])
def test_adminbereich_nur_fuer_admin(client, db, rolle, erwartet):
    antwort = client.get("/admin/vorgabewerte", headers=angemeldet_als(konto_anlegen(db, rolle)))
    assert antwort.status_code == erwartet


@pytest.fixture
def w(db):
    werkstatt = Werkstatt(db)
    werkstatt.vorgabe()
    return werkstatt


def _auftrag_fuer(client, w, zugewiesen=None):
    antwort = client.post("/auftraege", headers=angemeldet_als(w.mitarbeiter), json={
        "kunde_id": str(w.kunde.id),
        "instrument_id": str(w.instrument().id),
        "reparaturart_id": str(w.saitenwechsel.id),
        "zugewiesener_mitarbeiter_id": str(zugewiesen.id) if zugewiesen else None,
    })
    assert antwort.status_code == 201
    return antwort.json()["id"]


@pytest.mark.parametrize("wer, erwartet", [
    ("zugewiesen", 200),
    ("anderer_mitarbeiter", 403),
    ("werkstattleiter", 200),
    ("admin", 200),
])
@pytest.mark.parametrize("aktion", ["status", "schaetzung-korrektur"])
def test_auftrag_bearbeiten_nach_rolle(client, db, w, wer, erwartet, aktion):
    auftrag_id = _auftrag_fuer(client, w, zugewiesen=w.mitarbeiter)
    person = {
        "zugewiesen": w.mitarbeiter,
        "anderer_mitarbeiter": konto_anlegen(db, Systemrolle.mitarbeiter),
        "werkstattleiter": konto_anlegen(db, Systemrolle.werkstattleiter),
        "admin": konto_anlegen(db, Systemrolle.admin),
    }[wer]
    daten = ({"status_id": str(w.in_bearbeitung)} if aktion == "status"
             else {"geschaetzte_kosten": 99, "grund": "Test"})
    antwort = client.post(f"/auftraege/{auftrag_id}/{aktion}", headers=angemeldet_als(person), json=daten)
    assert antwort.status_code == erwartet


def test_nicht_zugewiesenen_auftrag_darf_nur_leitung_bearbeiten(client, db, w):
    auftrag_id = _auftrag_fuer(client, w, zugewiesen=None)
    daten = {"status_id": str(w.in_bearbeitung)}
    assert client.post(f"/auftraege/{auftrag_id}/status", headers=angemeldet_als(w.mitarbeiter), json=daten).status_code == 403
    leitung = konto_anlegen(db, Systemrolle.werkstattleiter)
    assert client.post(f"/auftraege/{auftrag_id}/status", headers=angemeldet_als(leitung), json=daten).status_code == 200


def test_alle_angemeldeten_duerfen_anlegen_und_lesen(client, db, w):
    auftrag_id = _auftrag_fuer(client, w)  # angelegt von Rolle "mitarbeiter"
    fremder = angemeldet_als(konto_anlegen(db, Systemrolle.mitarbeiter))
    assert client.get("/auftraege", headers=fremder).status_code == 200
    assert client.get(f"/auftraege/{auftrag_id}", headers=fremder).status_code == 200


def test_korrektur_uebernimmt_mitarbeiter_aus_token(client, db, w):
    auftrag_id = _auftrag_fuer(client, w, zugewiesen=w.mitarbeiter)
    leitung = konto_anlegen(db, Systemrolle.werkstattleiter, name="Leitung")

    antwort = client.post(f"/auftraege/{auftrag_id}/schaetzung-korrektur", headers=angemeldet_als(leitung),
                          json={"geschaetzte_arbeitsstunden": 3, "grund": "Mehraufwand"})
    assert antwort.status_code == 200
    assert antwort.json()["schaetzungen"][-1]["korrigiert_von_mitarbeiter_id"] == str(leitung.id)

    log = db.scalars(select(SchaetzungsLog).where(
        SchaetzungsLog.auftrag_id == uuid.UUID(auftrag_id), SchaetzungsLog.methode == "manuelle_korrektur"
    )).one()
    assert log.korrigiert_von_mitarbeiter_id == leitung.id


def test_statuswechsel_protokolliert_angemeldeten_mitarbeiter(client, w):
    auftrag_id = _auftrag_fuer(client, w, zugewiesen=w.mitarbeiter)
    a = client.post(f"/auftraege/{auftrag_id}/status", headers=angemeldet_als(w.mitarbeiter),
                    json={"status_id": str(w.in_bearbeitung)}).json()
    assert [v["geaendert_von_mitarbeiter_id"] for v in a["statusverlauf"]] == [str(w.mitarbeiter.id)] * 2


# --- Skript für den ersten Admin --------------------------------------------

def test_skript_legt_admin_an(db, monkeypatch, capsys):
    eingaben = iter(["zu-kurz", "ein-sicheres-passwort", "ein-sicheres-passwort"])
    monkeypatch.setattr(skript.getpass, "getpass", lambda _: next(eingaben))
    monkeypatch.setattr(skript, "SessionLocal", lambda: db)
    monkeypatch.setattr("sys.argv", ["konto_anlegen", "--email", " Chefin@Test.Invalid ", "--name", "Chefin"])

    assert skript.main() == 0
    admin = db.scalars(select(Mitarbeiter).where(Mitarbeiter.email == "chefin@test.invalid")).one()
    assert admin.systemrolle == Systemrolle.admin
    assert admin.passwort_hash != "ein-sicheres-passwort"
    assert passwort_pruefen("ein-sicheres-passwort", admin.passwort_hash)
    assert "Zu kurz" in capsys.readouterr().out

    # Zweiter Aufruf mit derselben E-Mail wird abgelehnt
    assert skript.main() == 1

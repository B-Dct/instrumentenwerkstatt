"""Ausführungen je Instrumentenklasse (Datenmodell 2.4b): anlegen, umbenennen, Standard, archivieren."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Instrument, Instrumentenklasse, Kunde, Reparaturart, ReparaturVorgabewert, Systemrolle, SystemEreignisLog
from app.schaetzung import schaetze_kosten
from tests.conftest import OHNE_ANMELDUNG, angemeldet_als, konto_anlegen

URL = "/admin/ausfuehrungen"


@pytest.fixture
def s(db, client):
    """Eine Klasse mit je einem Richtpreis für zwei Reparaturarten, noch ohne Ausführungen."""
    admin = konto_anlegen(db, Systemrolle.admin, name="Test Admin")
    client.headers.update(angemeldet_als(admin))
    klasse = Instrumentenklasse(bezeichnung="TEST Trompete", oberkategorie="Test")
    andere = Instrumentenklasse(bezeichnung="TEST Posaune", oberkategorie="Test")
    reinigung = Reparaturart(bezeichnung="TEST Reinigung", standard_komplexitaet=2)
    ueberholung = Reparaturart(bezeichnung="TEST Überholung", standard_komplexitaet=3)
    kunde = Kunde(kundennummer=f"TEST-{uuid.uuid4().hex[:8]}", name="Test Kunde")
    db.add_all([klasse, andere, reinigung, ueberholung, kunde])
    db.flush()
    werte = {}
    for art, kosten in ((reinigung, "80.00"), (ueberholung, "105.00")):
        werte[art.bezeichnung] = ReparaturVorgabewert(reparaturart_id=art.id, instrumentenklasse_id=klasse.id,
                                                      vorgabe_stunden=Decimal("2.00"), vorgabe_kosten=Decimal(kosten))
    db.add_all(werte.values())
    db.flush()
    return {"admin": admin, "klasse": klasse, "andere": andere, "reinigung": reinigung, "ueberholung": ueberholung,
            "kunde": kunde, "werte": werte}


def anlegen(client, s, bezeichnung, klasse="klasse", **extra):
    antwort = client.post(URL, json={"instrumentenklasse_id": str(s[klasse].id), "bezeichnung": bezeichnung, **extra})
    assert antwort.status_code == 201, antwort.json()
    return antwort.json()


def liste(client, s, **parameter):
    antwort = client.get(URL, params={"instrumentenklasse_id": str(s["klasse"].id), **parameter})
    return [(e["bezeichnung"], e["ist_standard"]) for e in antwort.json()]


def test_erste_ausfuehrung_wird_standard_und_uebernimmt_die_richtpreise(client, s, db):
    """Hat die Klasse schon Richtpreise, wird zuerst die Standardausführung benannt – ihr gehören sie dann."""
    erste = anlegen(client, s, "  Perinet,   lackiert ")
    assert (erste["bezeichnung"], erste["ist_standard"], erste["richtpreise"], erste["instrumente"]) == ("Perinet, lackiert", True, 2, 0)
    for wert in s["werte"].values():
        db.refresh(wert)
        assert str(wert.ausfuehrung_id) == erste["id"]
    zweite = anlegen(client, s, "Perinet, versilbert")
    assert (zweite["ist_standard"], zweite["richtpreise"]) == (False, 0)
    assert liste(client, s) == [("Perinet, lackiert", True), ("Perinet, versilbert", False)]
    # Die andere Klasse ist unberührt
    assert client.get(URL, params={"instrumentenklasse_id": str(s["andere"].id)}).json() == []
    log = db.scalars(select(SystemEreignisLog).where(SystemEreignisLog.betroffene_id == uuid.UUID(erste["id"]))).one()
    assert (log.aktion, log.details["zugeordnete_richtpreise"]) == ("ausfuehrung_angelegt", 2)


def test_bezeichnung_je_klasse_eindeutig_ohne_gross_klein_und_leerzeichen(client, s):
    anlegen(client, s, "Perinet, lackiert")
    for doppelt in ("perinet, LACKIERT", "  Perinet,  lackiert  "):
        antwort = client.post(URL, json={"instrumentenklasse_id": str(s["klasse"].id), "bezeichnung": doppelt})
        assert antwort.status_code == 409 and "gibt es" in antwort.json()["detail"]
    anlegen(client, s, "Perinet, lackiert", klasse="andere")                # in einer anderen Klasse erlaubt
    leer = client.post(URL, json={"instrumentenklasse_id": str(s["klasse"].id), "bezeichnung": "   "})
    assert leer.status_code == 422 and leer.json()["detail"][0]["loc"][-1] == "bezeichnung"


def test_standard_nur_weitergeben_nicht_entfernen(client, s, db):
    lackiert, versilbert = anlegen(client, s, "lackiert"), anlegen(client, s, "versilbert")
    weg = client.patch(f"{URL}/{lackiert['id']}", json={"ist_standard": False})
    assert weg.status_code == 422 and weg.json()["detail"][0]["loc"][-1] == "ist_standard"
    assert client.patch(f"{URL}/{versilbert['id']}", json={"ist_standard": True}).json()["ist_standard"] is True
    assert liste(client, s) == [("versilbert", True), ("lackiert", False)]
    # Gleich als Standard anlegen übernimmt das Kennzeichen
    anlegen(client, s, "vergoldet", ist_standard=True)
    assert liste(client, s) == [("vergoldet", True), ("lackiert", False), ("versilbert", False)]


def test_datenbank_erlaubt_nur_einen_aktiven_standard_je_klasse(db, s):
    from sqlalchemy.exc import IntegrityError
    from app.models import Ausfuehrung
    db.add_all([Ausfuehrung(instrumentenklasse_id=s["klasse"].id, bezeichnung=n, ist_standard=True) for n in ("a", "b")])
    with pytest.raises(IntegrityError, match="uq_ausfuehrung_standard"):
        db.flush()
    db.rollback()


def test_umbenennen_wirkt_an_allen_reparaturarten_und_instrumenten_ohne_mitumbenennen(client, s, db):
    """Richtpreise und Instrumente verweisen auf die Ausführung: Geändert wird genau eine Zeile."""
    anlegen(client, s, "lackiert")
    versilbert = anlegen(client, s, "versilbert")
    for art in ("reinigung", "ueberholung"):
        db.add(ReparaturVorgabewert(reparaturart_id=s[art].id, instrumentenklasse_id=s["klasse"].id,
                                    ausfuehrung_id=uuid.UUID(versilbert["id"]), vorgabe_stunden=3, vorgabe_kosten=150))
    instrument = Instrument(kunde_id=s["kunde"].id, instrumentenklasse_id=s["klasse"].id, ausfuehrung_id=uuid.UUID(versilbert["id"]))
    db.add(instrument)
    db.flush()
    logs_vorher = db.scalars(select(SystemEreignisLog.id)).all()

    umbenannt = client.patch(f"{URL}/{versilbert['id']}", json={"bezeichnung": " Silber  matt "}).json()
    assert (umbenannt["bezeichnung"], umbenannt["richtpreise"], umbenannt["instrumente"]) == ("Silber matt", 2, 1)
    preise = client.get("/admin/vorgabewerte", params={"instrumentenklasse_id": str(s["klasse"].id), "suche": "Silber"}).json()["eintraege"]
    assert sorted(e["reparaturart_bezeichnung"] for e in preise) == ["TEST Reinigung", "TEST Überholung"]
    assert client.get(f"/instrumente/{instrument.id}").json()["ausfuehrung"] == "Silber matt"
    # Genau ein Protokolleintrag (die Ausführung) – kein Instrument, kein Richtpreis wurde angefasst
    neue = db.scalars(select(SystemEreignisLog).where(SystemEreignisLog.id.not_in(logs_vorher))).all()
    assert [(l.aktion, l.betroffene_entitaet, l.details["alt"]["bezeichnung"], l.details["neu"]["bezeichnung"]) for l in neue] == [
        ("ausfuehrung_geaendert", "ausfuehrung", "versilbert", "Silber matt")]
    # Unveränderte Angaben erzeugen keinen Eintrag
    client.patch(f"{URL}/{versilbert['id']}", json={"bezeichnung": "Silber matt"})
    assert len(db.scalars(select(SystemEreignisLog.id).where(SystemEreignisLog.id.not_in(logs_vorher))).all()) == 1


def test_archivieren_zaehlt_vorab_und_standard_nur_als_letzter(client, s, db):
    lackiert, versilbert = anlegen(client, s, "lackiert"), anlegen(client, s, "versilbert")
    db.add(ReparaturVorgabewert(reparaturart_id=s["reinigung"].id, instrumentenklasse_id=s["klasse"].id,
                                ausfuehrung_id=uuid.UUID(versilbert["id"]), vorgabe_stunden=3, vorgabe_kosten=150))
    db.add_all([Instrument(kunde_id=s["kunde"].id, instrumentenklasse_id=s["klasse"].id, ausfuehrung_id=uuid.UUID(versilbert["id"]))
                for _ in range(2)])
    db.flush()
    # Die Zahlen stehen schon in der Liste – die Oberfläche zeigt sie vor dem Archivieren
    zahlen = {e["bezeichnung"]: (e["instrumente"], e["richtpreise"]) for e in client.get(URL, params={"instrumentenklasse_id": str(s["klasse"].id)}).json()}
    assert zahlen == {"lackiert": (0, 2), "versilbert": (2, 1)}

    gesperrt = client.post(f"{URL}/{lackiert['id']}/archivieren")
    assert gesperrt.status_code == 409 and "Standard" in gesperrt.json()["detail"]
    assert client.post(f"{URL}/{versilbert['id']}/archivieren").status_code == 200
    assert liste(client, s) == [("lackiert", True)] and liste(client, s, status="archiviert") == [("versilbert", False)]
    # Ihr Richtpreis wird ignoriert: Für ein Instrument dieser Ausführung gilt jetzt der Standard (80 €)
    assert schaetze_kosten(db, s["klasse"].id, s["reinigung"].id, uuid.UUID(versilbert["id"])).wert == Decimal("80.00")
    # Die Instrumente behalten den Verweis
    assert db.scalar(select(Instrument.ausfuehrung_id).where(Instrument.kunde_id == s["kunde"].id).limit(1)) == uuid.UUID(versilbert["id"])
    assert client.patch(f"{URL}/{versilbert['id']}", json={"bezeichnung": "x"}).status_code == 409   # erst reaktivieren

    # Der Standard als letzte aktive Ausführung lässt sich archivieren; reaktiviert wird er wieder Standard
    assert client.post(f"{URL}/{lackiert['id']}/archivieren").status_code == 200
    assert liste(client, s) == []
    assert client.post(f"{URL}/{versilbert['id']}/reaktivieren").json()["ist_standard"] is True
    assert client.post(f"{URL}/{lackiert['id']}/reaktivieren").json()["ist_standard"] is False
    assert liste(client, s) == [("versilbert", True), ("lackiert", False)]
    assert client.post(f"{URL}/{lackiert['id']}/reaktivieren").status_code == 409


def test_reaktivieren_mit_gleichnamiger_aktiver_ausfuehrung(client, s):
    alt = anlegen(client, s, "lackiert")
    client.post(f"{URL}/{alt['id']}/archivieren")
    anlegen(client, s, "Lackiert")
    antwort = client.post(f"{URL}/{alt['id']}/reaktivieren")
    assert antwort.status_code == 409 and "gibt es" in antwort.json()["detail"]


def test_nur_admin_und_nicht_gefunden(client, s, db):
    assert client.post(f"{URL}/{uuid.uuid4()}/archivieren").status_code == 404
    assert client.patch(f"{URL}/{uuid.uuid4()}", json={"bezeichnung": "x"}).status_code == 404
    assert client.post(URL, json={"instrumentenklasse_id": str(uuid.uuid4()), "bezeichnung": "x"}).status_code == 422
    assert client.get(URL, headers=OHNE_ANMELDUNG).status_code == 401
    leitung = konto_anlegen(db, Systemrolle.werkstattleiter, name="Test Leitung")
    assert client.get(URL, headers=angemeldet_als(leitung)).status_code == 403

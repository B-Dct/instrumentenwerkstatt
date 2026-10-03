"""Tests der Terminschätzung (Datenmodell 4).

Feste Rechenbasis: "heute" = Montag, 04.03.2030 → Arbeit beginnt Dienstag, 05.03.2030.
Ohne hinterlegte Wochenarbeitszeit gelten 40 Std./Woche = 8 Std./Tag.
"""

import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    Abwesenheit,
    Abwesenheitstyp,
    Auftrag,
    MitarbeiterArbeitszeit,
    Prioritaet,
    SchaetzungsLog,
    Systemrolle,
)
from app.terminschaetzung import schaetze_fertigstellung
from tests.beispieldaten import Werkstatt
from tests.conftest import OHNE_ANMELDUNG, angemeldet_als, konto_anlegen

HEUTE = date(2030, 3, 4)  # Montag
DI, MI, DO, FR = date(2030, 3, 5), date(2030, 3, 6), date(2030, 3, 7), date(2030, 3, 8)
MO2 = date(2030, 3, 11)


@pytest.fixture
def w(db):
    return Werkstatt(db)


_zeit = iter(range(1, 10_000))


def offener_auftrag(w, stunden, mitarbeiter=None, prioritaet=Prioritaet.normal, status=None, reihenfolge=None):
    """Offener Auftrag (Eingang 2020, also vor allen heute angelegten); `reihenfolge`: kleiner = früher."""
    instrument = w.instrument()
    auftrag = Auftrag(
        auftragsnummer=f"T-{secrets.token_hex(5)}",
        zugriffstoken=secrets.token_hex(6),
        kunde_id=w.kunde.id,
        instrument_id=instrument.id,
        reparaturart_id=w.saitenwechsel.id,
        zugewiesener_mitarbeiter_id=(mitarbeiter or w.mitarbeiter).id if mitarbeiter is not False else None,
        prioritaet=prioritaet,
        komplexitaet=1,
        status_aktuell_id=status or w.in_bearbeitung,
        geschaetzte_arbeitsstunden=Decimal(stunden),
        erstellt_am=datetime(2020, 1, 1, tzinfo=UTC) + timedelta(minutes=reihenfolge or next(_zeit)),
    )
    w.db.add(auftrag)
    w.db.flush()
    return auftrag


def schaetzen(w, auftrag):
    return schaetze_fertigstellung(w.db, auftrag, heute=HEUTE)


# --- Ohne Warteschlange -------------------------------------------------------

def test_mitarbeiter_frei_ein_tag(w):
    t = schaetzen(w, offener_auftrag(w, "8"))
    assert t.datum == DI
    assert (t.bandbreite_von, t.bandbreite_bis) == (DI, MI)  # nicht vor Arbeitsbeginn
    assert t.eingabefaktoren["auftraege_davor"] == 0
    assert t.eingabefaktoren["wochenstunden_quelle"] == "Standard 40"


def test_mitarbeiter_frei_mehrere_tage(w):
    t = schaetzen(w, offener_auftrag(w, "20"))  # Di 8 + Mi 8 + Do 4
    assert t.datum == DO
    assert t.eingabefaktoren["arbeitstage"] == 3


def test_wochenende_wird_uebersprungen(w):
    t = schaetzen(w, offener_auftrag(w, "40"))  # Di–Fr = 32 Std., Rest am Montag
    assert t.datum == MO2
    assert t.eingabefaktoren["uebersprungene_tage"]["wochenende"] == 2


def test_hinterlegte_wochenstunden(w, db):
    db.add(MitarbeiterArbeitszeit(mitarbeiter_id=w.mitarbeiter.id, wochenstunden=Decimal("20"),
                                  gueltig_ab=date(2030, 1, 1)))
    t = schaetzen(w, offener_auftrag(w, "8"))  # 4 Std./Tag → Di + Mi
    assert t.datum == MI
    assert t.eingabefaktoren["wochenstunden_quelle"] == "mitarbeiter_arbeitszeit"


def test_ohne_stunden_keine_schaetzung(w):
    auftrag = offener_auftrag(w, "1")
    auftrag.geschaetzte_arbeitsstunden = None
    assert schaetzen(w, auftrag).datum is None


# --- Mit Warteschlange --------------------------------------------------------

def test_warteschlange_vor_dem_auftrag(w):
    anderer = konto_anlegen(w.db, name="Anderer")
    offener_auftrag(w, "8", reihenfolge=1)                          # älter → davor
    offener_auftrag(w, "8", reihenfolge=2)                          # älter → davor
    offener_auftrag(w, "40", reihenfolge=3, status=w.fertig)        # abgeschlossen → zählt nicht
    offener_auftrag(w, "40", reihenfolge=4, mitarbeiter=anderer)    # anderer Mitarbeiter → zählt nicht
    eigener = offener_auftrag(w, "8", reihenfolge=5)
    offener_auftrag(w, "8", reihenfolge=6, prioritaet=Prioritaet.hoch)  # neuer, aber hohe Priorität → davor
    offener_auftrag(w, "40", reihenfolge=7)                         # neuer, normal → danach

    t = schaetzen(w, eigener)
    assert t.eingabefaktoren["auftraege_davor"] == 3
    assert Decimal(t.eingabefaktoren["warteschlange_stunden"]) == 24
    assert t.datum == FR  # 24 + 8 = 32 Std. = Di bis Fr


def test_hohe_prioritaet_ueberholt_normale(w):
    offener_auftrag(w, "32", reihenfolge=1)
    eilig = offener_auftrag(w, "8", reihenfolge=2, prioritaet=Prioritaet.hoch)
    assert schaetzen(w, eilig).datum == DI


# --- Abwesenheiten --------------------------------------------------------------

def test_urlaub_des_mitarbeiters_verschiebt_termin(w, db):
    db.add(Abwesenheit(mitarbeiter_id=w.mitarbeiter.id, von_datum=MI, bis_datum=DO, typ=Abwesenheitstyp.urlaub))
    t = schaetzen(w, offener_auftrag(w, "20"))  # Di 8, Mi+Do Urlaub, Fr 8, Mo 4
    assert t.datum == MO2
    assert t.eingabefaktoren["uebersprungene_tage"] == {"wochenende": 2, "betrieb": 0, "persoenlich": 2}


def test_betriebsschliessung_gilt_fuer_alle(w, db):
    db.add(Abwesenheit(mitarbeiter_id=None, von_datum=DI, bis_datum=DI, typ=Abwesenheitstyp.feiertag))
    t = schaetzen(w, offener_auftrag(w, "8"))
    assert t.datum == MI
    assert t.eingabefaktoren["uebersprungene_tage"]["betrieb"] == 1


def test_abwesenheit_anderer_mitarbeiter_zaehlt_nicht(w, db):
    anderer = konto_anlegen(db, name="Anderer")
    db.add(Abwesenheit(mitarbeiter_id=anderer.id, von_datum=DI, bis_datum=FR, typ=Abwesenheitstyp.krankheit))
    assert schaetzen(w, offener_auftrag(w, "8")).datum == DI


def test_reduzierte_stunden(w, db):
    db.add(Abwesenheit(mitarbeiter_id=w.mitarbeiter.id, von_datum=DI, bis_datum=FR,
                       typ=Abwesenheitstyp.reduzierte_stunden, reduzierte_stunden=Decimal("20")))
    assert schaetzen(w, offener_auftrag(w, "8")).datum == MI  # nur 4 Std./Tag


# --- Ohne Zuweisung --------------------------------------------------------------

def test_ohne_zuweisung_fallback(w):
    t = schaetzen(w, offener_auftrag(w, "8", mitarbeiter=False))
    assert t.datum is not None and t.datum >= DI
    assert t.eingabefaktoren["ohne_zuweisung"]["verfahren"] == "durchschnittliche Warteschlange"


# --- Über die API: Anlegen, Umzuweisen, Priorität --------------------------------

@pytest.fixture
def leitung(db, client):
    person = konto_anlegen(db, Systemrolle.werkstattleiter, name="Leitung")
    client.headers.update(angemeldet_als(person))
    return person


def api_auftrag(client, w, **extra):
    w.vorgabe(stunden="8.00")  # 8 Std. geschätzt
    antwort = client.post("/auftraege", json={
        "kunde_id": str(w.kunde.id), "instrument_id": str(w.instrument().id),
        "reparaturart_id": str(w.saitenwechsel.id), **extra,
    })
    assert antwort.status_code == 201
    return antwort.json()


def test_anlegen_berechnet_und_protokolliert_termin(client, w, leitung):
    a = api_auftrag(client, w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id))
    assert a["geschaetztes_fertigstellungsdatum"] > date.today().isoformat()
    assert a["geschaetzte_bandbreite_von"] <= a["geschaetztes_fertigstellungsdatum"] <= a["geschaetzte_bandbreite_bis"]
    [log] = a["schaetzungen"]
    assert log["geschaetztes_datum"] == a["geschaetztes_fertigstellungsdatum"]
    assert log["eingabefaktoren"]["anlass"] == "auftrag_angelegt"
    assert log["eingabefaktoren"]["termin"]["eigene_stunden"] == "8.00"


def test_umzuweisung_berechnet_neu(client, w, leitung, db):
    beschaeftigt = konto_anlegen(db, name="Beschäftigt")
    offener_auftrag(w, "80", mitarbeiter=beschaeftigt, reihenfolge=1)  # 10 Arbeitstage Vorlauf
    a = api_auftrag(client, w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id))
    vorher = a["geschaetztes_fertigstellungsdatum"]

    antwort = client.patch(f"/auftraege/{a['id']}", json={"zugewiesener_mitarbeiter_id": str(beschaeftigt.id)})
    assert antwort.status_code == 200
    a = antwort.json()
    assert a["zugewiesener_mitarbeiter_name"] == "Beschäftigt"
    assert a["geschaetztes_fertigstellungsdatum"] > vorher
    neu = a["schaetzungen"][-1]
    assert neu["eingabefaktoren"]["anlass"] == "zuweisung_geaendert"
    assert neu["geschaetztes_datum"] == a["geschaetztes_fertigstellungsdatum"]
    assert neu["eingabefaktoren"]["termin"]["auftraege_davor"] == 1
    assert len(a["schaetzungen"]) == 2  # ursprüngliche Schätzung bleibt erhalten


def test_prioritaet_hoch_zieht_termin_vor(client, w, leitung):
    offener_auftrag(w, "80", reihenfolge=1)
    a = api_auftrag(client, w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id))
    a2 = client.patch(f"/auftraege/{a['id']}", json={"prioritaet": "hoch"}).json()
    assert a2["geschaetztes_fertigstellungsdatum"] < a["geschaetztes_fertigstellungsdatum"]
    assert a2["schaetzungen"][-1]["eingabefaktoren"]["anlass"] == "prioritaet_geaendert"


def test_zuweisung_aufheben_nutzt_fallback(client, w, leitung):
    a = api_auftrag(client, w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id))
    a = client.patch(f"/auftraege/{a['id']}", json={"zugewiesener_mitarbeiter_id": None}).json()
    assert a["zugewiesener_mitarbeiter_id"] is None
    assert "ohne_zuweisung" in a["schaetzungen"][-1]["eingabefaktoren"]["termin"]


def test_ohne_aenderung_keine_neuberechnung(client, w, leitung):
    a = api_auftrag(client, w, prioritaet="normal")
    a = client.patch(f"/auftraege/{a['id']}", json={"prioritaet": "normal"}).json()
    assert len(a["schaetzungen"]) == 1


def test_aendern_nur_fuer_leitung(client, w, db):
    client.headers.update(angemeldet_als(w.mitarbeiter))
    a = api_auftrag(client, w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id))
    assert client.patch(f"/auftraege/{a['id']}", json={"prioritaet": "hoch"}).status_code == 403


# --- Überfällig ------------------------------------------------------------------

def test_ueberfaellig_nur_offen_und_termin_vorbei(client, w, leitung, db):
    a = api_auftrag(client, w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id))
    assert a["ist_ueberfaellig"] is False

    auftrag = db.get(Auftrag, uuid.UUID(a["id"]))
    auftrag.geschaetztes_fertigstellungsdatum = date.today() - timedelta(days=1)
    db.flush()
    liste = client.get("/auftraege", params={"kunde_id": str(w.kunde.id)}).json()["eintraege"]
    assert [x["ist_ueberfaellig"] for x in liste] == [True]

    client.post(f"/auftraege/{a['id']}/status", json={"status_id": str(w.fertig), "arbeitszeit_minuten": 60, "abgerechneter_betrag": 50})
    assert client.get(f"/auftraege/{a['id']}").json()["ist_ueberfaellig"] is False


def test_log_hat_termin(db, client, w, leitung):
    a = api_auftrag(client, w)
    log = db.scalars(select(SchaetzungsLog).where(SchaetzungsLog.auftrag_id == uuid.UUID(a["id"]))).one()
    assert log.geschaetztes_datum is not None


# --- Manuelle Terminkorrektur (4.2) ------------------------------------------------

def _termin_korrigieren(client, auftrag_id, datum, grund="Ersatzteil kommt später", **kw):
    return client.post(f"/auftraege/{auftrag_id}/termin-korrektur", **kw,
                       json={"geschaetztes_fertigstellungsdatum": datum.isoformat(), "grund": grund})


def test_terminkorrektur_nur_fuer_leitung(client, w, db):
    """Auch der zugewiesene Mitarbeiter darf den Termin nicht korrigieren (anders als Stunden/Kosten)."""
    client.headers.update(angemeldet_als(w.mitarbeiter))
    a = api_auftrag(client, w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id))
    neu = date.today() + timedelta(days=30)
    assert _termin_korrigieren(client, a["id"], neu).status_code == 403
    assert db.get(Auftrag, uuid.UUID(a["id"])).geschaetztes_fertigstellungsdatum.isoformat() == a["geschaetztes_fertigstellungsdatum"]
    assert _termin_korrigieren(client, a["id"], neu, headers=OHNE_ANMELDUNG).status_code == 401


def test_terminkorrektur_landet_im_log_und_am_auftrag(client, w, leitung, db):
    a = api_auftrag(client, w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id))
    neu = date.today() + timedelta(days=45)
    antwort = _termin_korrigieren(client, a["id"], neu, grund="  Sonderteil lieferbar ab November  ")
    assert antwort.status_code == 200
    detail = antwort.json()
    assert detail["geschaetztes_fertigstellungsdatum"] == neu.isoformat()
    assert (detail["geschaetzte_bandbreite_von"], detail["geschaetzte_bandbreite_bis"]) == (None, None)

    eintraege = db.scalars(select(SchaetzungsLog).where(SchaetzungsLog.auftrag_id == uuid.UUID(a["id"]))
                           .order_by(SchaetzungsLog.berechnet_am)).all()
    assert len(eintraege) == 2  # der automatische Eintrag bleibt erhalten
    korrektur = eintraege[-1]
    assert (korrektur.methode, korrektur.geschaetztes_datum, korrektur.grund) == \
        ("manuelle_korrektur", neu, "Sonderteil lieferbar ab November")
    assert korrektur.korrigiert_von_mitarbeiter_id == leitung.id
    assert (korrektur.geschaetzte_stunden, korrektur.geschaetzte_kosten) == (None, None)
    assert korrektur.eingabefaktoren["vorher"]["geschaetztes_fertigstellungsdatum"] == a["geschaetztes_fertigstellungsdatum"]
    assert detail["schaetzungen"][-1]["korrigiert_von_name"] == leitung.name


def test_umzuweisung_ueberschreibt_manuelle_terminkorrektur(client, w, leitung, db):
    """Bewusstes Verhalten (4.0a/4.2): die nächste automatische Neuberechnung gilt wieder."""
    a = api_auftrag(client, w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id))
    manuell = date.today() + timedelta(days=200)
    assert _termin_korrigieren(client, a["id"], manuell).status_code == 200

    kollege = konto_anlegen(db, name="Kollege")
    neu = client.patch(f"/auftraege/{a['id']}", json={"zugewiesener_mitarbeiter_id": str(kollege.id)}).json()
    assert neu["geschaetztes_fertigstellungsdatum"] != manuell.isoformat()
    assert neu["geschaetzte_bandbreite_von"] is not None  # wieder berechnet
    assert [s["methode"] for s in neu["schaetzungen"]] == ["regelbasiert", "manuelle_korrektur", "regelbasiert"]


@pytest.mark.parametrize("daten", [
    {"geschaetztes_fertigstellungsdatum": "2030-01-01"},                    # Begründung fehlt
    {"geschaetztes_fertigstellungsdatum": "2030-01-01", "grund": "   "},   # leere Begründung
    {"grund": "ohne Datum"},
    {"geschaetztes_fertigstellungsdatum": "2000-01-01", "grund": "vor dem Eingang"},
])
def test_terminkorrektur_ungueltig(client, w, leitung, daten):
    a = api_auftrag(client, w)
    assert client.post(f"/auftraege/{a['id']}/termin-korrektur", json=daten).status_code == 422


def test_terminkorrektur_unbekannter_auftrag(client, w, leitung):
    assert _termin_korrigieren(client, uuid.uuid4(), date.today()).status_code == 404

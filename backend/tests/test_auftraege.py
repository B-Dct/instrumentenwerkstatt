"""Tests der Auftrags-Endpunkte (Datenmodell 2.7, 2.8, 2.10, 4.2)."""

import itertools
import re
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Arbeitszeiterfassung, Auftrag, Kunde, SchaetzungsLog
from app.routers import auftraege
from tests.beispieldaten import Werkstatt

URL = "/auftraege"


@pytest.fixture
def w(db, monkeypatch):
    # Der Nummernzähler der Datenbank wird beim Rollback nicht zurückgesetzt –
    # Tests sollen keine echten Auftragsnummern verbrauchen.
    zaehler = itertools.count(1)
    monkeypatch.setattr(auftraege, "_neue_auftragsnummer", lambda db: f"TEST-{next(zaehler):05d}")

    werkstatt = Werkstatt(db)
    werkstatt.vorgabe(stunden="0.50", kosten="20.00")                       # allgemein
    werkstatt.vorgabe(werkstatt.kontrabass, stunden="1.50", kosten="60.00")  # Kontrabass
    return werkstatt


def neuer_auftrag(w, **extra):
    instrument = w.instrument(extra.pop("klasse", None))
    return {
        "kunde_id": str(w.kunde.id),
        "instrument_id": str(instrument.id),
        "reparaturart_id": str(w.saitenwechsel.id),
        **extra,
    }


def als(w):
    """Vorläufige Identifikation als Mitarbeiter (bis Login/Rollen)."""
    return {"X-Mitarbeiter-Id": str(w.mitarbeiter.id)}


# --- Anlegen inkl. Schätzung -------------------------------------------------

def test_anlegen_mit_fallback_schaetzung(client, w):
    antwort = client.post(URL, json=neuer_auftrag(
        w, zugewiesener_mitarbeiter_id=str(w.mitarbeiter.id), prioritaet="hoch"
    ))
    assert antwort.status_code == 201
    a = antwort.json()

    # Zu wenig Historie → Vorgabewert Kontrabass
    assert a["geschaetzte_arbeitsstunden"] == 1.5
    assert a["geschaetzte_kosten"] == 60.0
    assert a["status"]["schluessel"] == "angenommen"
    assert a["prioritaet"] == "hoch"
    assert a["zugewiesener_mitarbeiter_name"] == "Test Geigenbauer"
    assert a["komplexitaet"] == 1  # Standard der Reparaturart
    assert re.fullmatch(r"[2-9A-HJ-NP-Z]{12}", a["zugriffstoken"])

    # Startstatus steht bereits im Verlauf
    assert [v["status"]["schluessel"] for v in a["statusverlauf"]] == ["angenommen"]

    # Genau ein automatischer Log-Eintrag mit Eingabefaktoren
    [log] = a["schaetzungen"]
    assert log["methode"] == "regelbasiert"
    assert (log["geschaetzte_stunden"], log["geschaetzte_kosten"]) == (1.5, 60.0)
    assert log["korrigiert_von_mitarbeiter_id"] is None and log["grund"] is None
    faktoren = log["eingabefaktoren"]
    assert faktoren["instrumentenklasse_id"] == str(w.kontrabass.id)
    assert faktoren["mindestanzahl_vergleichsfaelle"] == 5
    assert faktoren["stunden"] == {"wert": "1.50", "quelle": "vorgabe_instrumentenklasse", "anzahl_vergleichsfaelle": 0}
    assert faktoren["kosten"]["quelle"] == "vorgabe_instrumentenklasse"


def test_anlegen_mit_historischer_schaetzung(client, w):
    for _ in range(5):
        w.auftrag(minuten=(120,), kosten="80.00")

    a = client.post(URL, json=neuer_auftrag(w)).json()
    assert (a["geschaetzte_arbeitsstunden"], a["geschaetzte_kosten"]) == (2.0, 80.0)
    faktoren = a["schaetzungen"][0]["eingabefaktoren"]
    assert faktoren["stunden"]["quelle"] == faktoren["kosten"]["quelle"] == "historisch"
    assert faktoren["stunden"]["anzahl_vergleichsfaelle"] == 5


def test_anlegen_ohne_jede_schaetzungsgrundlage(client, w):
    # Violine hat weder Historie noch eigenen Vorgabewert → allgemeiner Wert
    a = client.post(URL, json=neuer_auftrag(w, klasse=w.violine)).json()
    assert (a["geschaetzte_arbeitsstunden"], a["geschaetzte_kosten"]) == (0.5, 20.0)


def test_anlegen_instrument_eines_anderen_kunden(client, w, db):
    anderer = Kunde(kundennummer="TEST-ANDERER", name="Anderer")
    db.add(anderer)
    db.flush()
    antwort = client.post(URL, json=neuer_auftrag(w) | {"kunde_id": str(anderer.id)})
    assert antwort.status_code == 422


def test_auftragsnummer_format():
    class FakeDb:
        def execute(self, _):
            return type("R", (), {"scalar_one": lambda self: 42})()

    assert auftraege._neue_auftragsnummer(FakeDb()) == f"{date.today().year}-00042"


# --- Auflisten / Abrufen -----------------------------------------------------

def test_liste_sortiert_prioritaet_vor_eingang_und_filtert(client, w):
    ids = [client.post(URL, json=neuer_auftrag(w, prioritaet=p)).json()["id"]
           for p in ["normal", "hoch", "normal"]]
    w.auftrag(minuten=(60,))  # abgeschlossener Auftrag – fällt bei nur_offene heraus

    alle = client.get(URL, params={"kunde_id": str(w.kunde.id)}).json()
    assert len(alle) == 4

    offen = client.get(URL, params={"kunde_id": str(w.kunde.id), "nur_offene": True}).json()
    assert [a["id"] for a in offen] == [ids[1], ids[0], ids[2]]

    hoch = client.get(URL, params={"prioritaet": "hoch", "kunde_id": str(w.kunde.id)}).json()
    assert [a["id"] for a in hoch] == [ids[1]]


def test_nicht_gefunden(client, w):
    assert client.get(f"{URL}/{uuid.uuid4()}").status_code == 404
    antwort = client.post(f"{URL}/{uuid.uuid4()}/status", json={"status_id": str(w.in_bearbeitung)})
    assert antwort.status_code == 404


# --- Statuswechsel -----------------------------------------------------------

def test_statuswechsel_erzeugt_historieneintrag(client, w):
    a = client.post(URL, json=neuer_auftrag(w)).json()

    antwort = client.post(f"{URL}/{a['id']}/status", headers=als(w), json={
        "status_id": str(w.in_bearbeitung), "kommentar": "Begonnen",
    })
    assert antwort.status_code == 200
    a = antwort.json()
    assert a["status"]["schluessel"] == "in_bearbeitung"
    verlauf = a["statusverlauf"]
    assert [v["status"]["schluessel"] for v in verlauf] == ["angenommen", "in_bearbeitung"]
    assert verlauf[1]["kommentar"] == "Begonnen"
    assert verlauf[1]["geaendert_von_mitarbeiter_id"] == str(w.mitarbeiter.id)


def test_statuswechsel_in_gleichen_status_abgelehnt(client, w):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    antwort = client.post(f"{URL}/{a['id']}/status", json={"status_id": a["status"]["id"]})
    assert antwort.status_code == 409


def test_fertig_erfordert_arbeitszeit(client, w, db):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    pfad = f"{URL}/{a['id']}/status"

    assert client.post(pfad, headers=als(w), json={"status_id": str(w.fertig)}).status_code == 422
    assert client.post(pfad, json={"status_id": str(w.fertig), "arbeitszeit_minuten": 90}).status_code == 401

    antwort = client.post(pfad, headers=als(w), json={"status_id": str(w.fertig), "arbeitszeit_minuten": 90})
    assert antwort.status_code == 200
    assert antwort.json()["tatsaechliches_fertigstellungsdatum"] == date.today().isoformat()
    [zeit] = db.scalars(select(Arbeitszeiterfassung).where(
        Arbeitszeiterfassung.auftrag_id == uuid.UUID(a["id"])
    )).all()
    assert (zeit.dauer_minuten, zeit.mitarbeiter_id) == (90, w.mitarbeiter.id)

    # Wiederaufnahme leert das Fertigstellungsdatum wieder
    zurueck = client.post(pfad, json={"status_id": str(w.in_bearbeitung)}).json()
    assert zurueck["tatsaechliches_fertigstellungsdatum"] is None
    assert len(zurueck["statusverlauf"]) == 3


def test_unbekannter_mitarbeiter_im_header(client, w):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    antwort = client.post(f"{URL}/{a['id']}/status", headers={"X-Mitarbeiter-Id": str(uuid.uuid4())},
                          json={"status_id": str(w.in_bearbeitung)})
    assert antwort.status_code == 401


# --- Manuelle Korrektur ------------------------------------------------------

def test_korrektur_erzeugt_log_eintrag_und_aktualisiert_auftrag(client, w, db):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    automatisch_vorher = a["schaetzungen"][0]

    antwort = client.post(f"{URL}/{a['id']}/schaetzung-korrektur", headers=als(w), json={
        "geschaetzte_arbeitsstunden": 4.25,
        "grund": "Decke gerissen, deutlich mehr Aufwand",
    })
    assert antwort.status_code == 200
    a = antwort.json()

    # Auftrag: Stunden korrigiert, Kosten unverändert
    assert a["geschaetzte_arbeitsstunden"] == 4.25
    assert a["geschaetzte_kosten"] == 60.0

    # Log: automatischer Eintrag unverändert erhalten, Korrektur als neuer Eintrag
    automatisch, korrektur = a["schaetzungen"]
    assert automatisch == automatisch_vorher
    assert korrektur["methode"] == "manuelle_korrektur"
    assert korrektur["geschaetzte_stunden"] == 4.25
    assert korrektur["geschaetzte_kosten"] is None
    assert korrektur["korrigiert_von_mitarbeiter_id"] == str(w.mitarbeiter.id)
    assert korrektur["grund"] == "Decke gerissen, deutlich mehr Aufwand"
    assert korrektur["eingabefaktoren"] == {"vorher": {"geschaetzte_arbeitsstunden": "1.50",
                                                       "geschaetzte_kosten": "60.00"}}

    # Auch direkt in der Datenbank
    auftrag = db.get(Auftrag, uuid.UUID(a["id"]))
    db.refresh(auftrag)
    assert auftrag.geschaetzte_arbeitsstunden == Decimal("4.25")


def test_korrektur_beide_werte_mehrfach(client, w):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    pfad = f"{URL}/{a['id']}/schaetzung-korrektur"
    client.post(pfad, headers=als(w), json={"geschaetzte_kosten": 90, "grund": "Ersatzteil teurer"})
    a = client.post(pfad, headers=als(w), json={
        "geschaetzte_arbeitsstunden": 3, "geschaetzte_kosten": 120, "grund": "Zusatzschaden"
    }).json()

    assert (a["geschaetzte_arbeitsstunden"], a["geschaetzte_kosten"]) == (3.0, 120.0)
    assert [s["methode"] for s in a["schaetzungen"]] == ["regelbasiert", "manuelle_korrektur", "manuelle_korrektur"]
    assert a["schaetzungen"][2]["eingabefaktoren"]["vorher"]["geschaetzte_kosten"] == "90.00"


@pytest.mark.parametrize("header, daten, erwartet", [
    (False, {"geschaetzte_kosten": 90, "grund": "x"}, 401),  # nicht zugeordnet
    (True, {"geschaetzte_kosten": 90}, 422),                  # Grund fehlt
    (True, {"geschaetzte_kosten": 90, "grund": "   "}, 422),  # Grund nur Leerzeichen
    (True, {"grund": "nichts korrigiert"}, 422),              # kein Wert angegeben
    (True, {"geschaetzte_kosten": -5, "grund": "x"}, 422),    # negativ
])
def test_korrektur_ungueltig(client, w, db, header, daten, erwartet):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    antwort = client.post(f"{URL}/{a['id']}/schaetzung-korrektur", headers=als(w) if header else {}, json=daten)
    assert antwort.status_code == erwartet
    anzahl_logs = len(db.scalars(select(SchaetzungsLog).where(SchaetzungsLog.auftrag_id == uuid.UUID(a["id"]))).all())
    assert anzahl_logs == 1  # nichts protokolliert

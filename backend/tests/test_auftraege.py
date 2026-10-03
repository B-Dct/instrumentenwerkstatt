"""Tests der Auftrags-Endpunkte (Datenmodell 2.7, 2.8, 2.10, 4.2)."""

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Arbeitszeiterfassung, Auftrag, Instrument, Kunde, SchaetzungsLog, Systemrolle
from app.routers.auftraege import _neue_auftragsnummer  # Original (Tests nutzen Ersatz)
from tests.beispieldaten import Werkstatt
from tests.conftest import OHNE_ANMELDUNG, angemeldet_als, konto_anlegen

URL = "/auftraege"


@pytest.fixture
def w(db, client):
    werkstatt = Werkstatt(db)
    werkstatt.vorgabe(stunden="0.50", kosten="20.00")                       # allgemein
    werkstatt.vorgabe(werkstatt.kontrabass, stunden="1.50", kosten="60.00")  # Kontrabass
    # Standard: angemeldet als der (zugewiesene) Mitarbeiter
    client.headers.update(angemeldet_als(werkstatt.mitarbeiter))
    return werkstatt


def neuer_auftrag(w, **extra):
    """Standardmäßig dem angemeldeten Test-Mitarbeiter zugewiesen."""
    instrument = w.instrument(extra.pop("klasse", None))
    return {
        "kunde_id": str(w.kunde.id),
        "instrument_id": str(instrument.id),
        "reparaturart_id": str(w.saitenwechsel.id),
        "zugewiesener_mitarbeiter_id": str(w.mitarbeiter.id),
        **extra,
    }


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

    assert _neue_auftragsnummer(FakeDb()) == f"{date.today().year}-00042"


# --- Auflisten / Abrufen -----------------------------------------------------

def _ids(antwort):
    assert antwort.status_code == 200, antwort.text
    return [a["id"] for a in antwort.json()["eintraege"]]


def test_liste_sortiert_prioritaet_vor_eingang_und_filtert(client, w):
    ids = [client.post(URL, json=neuer_auftrag(w, prioritaet=p)).json()["id"]
           for p in ["normal", "hoch", "normal"]]
    fertig = w.auftrag(minuten=(60,))  # abgeschlossener Auftrag – fällt beim Standard "offen" heraus
    kunde = {"kunde_id": str(w.kunde.id)}

    # Standard: nur offene, Priorität hoch zuerst, dann ältester Eingang zuerst (9.4)
    antwort = client.get(URL, params=kunde)
    assert _ids(antwort) == [ids[1], ids[0], ids[2]]
    assert antwort.json()["gesamt"] > antwort.json()["treffer"]  # der abgeschlossene ist ausgeblendet

    assert len(_ids(client.get(URL, params={**kunde, "status": "alle"}))) == 4
    assert _ids(client.get(URL, params={**kunde, "status": "abgeschlossen"})) == [str(fertig.id)]
    assert _ids(client.get(URL, params={**kunde, "prioritaet": "hoch"})) == [ids[1]]
    # Umgekehrt: normal vor hoch, der Eingang als Nachrang bleibt aufsteigend
    assert _ids(client.get(URL, params={**kunde, "richtung": "auf"})) == [ids[0], ids[2], ids[1]]


def test_liste_filter_status_mitarbeiter_klasse_ueberfaellig(client, w, db):
    kunde = {"kunde_id": str(w.kunde.id)}
    zugewiesen = client.post(URL, json=neuer_auftrag(w)).json()["id"]
    frei = client.post(URL, json=neuer_auftrag(w, zugewiesener_mitarbeiter_id=None, klasse=w.violine)).json()["id"]

    assert _ids(client.get(URL, params={**kunde, "mitarbeiter": str(w.mitarbeiter.id)})) == [zugewiesen]
    assert _ids(client.get(URL, params={**kunde, "mitarbeiter": "keiner"})) == [frei]
    assert _ids(client.get(URL, params={**kunde, "instrumentenklasse_id": str(w.violine.id)})) == [frei]
    assert _ids(client.get(URL, params={**kunde, "status": "angenommen"})) == [zugewiesen, frei]
    assert _ids(client.get(URL, params={**kunde, "status": "in_bearbeitung"})) == []

    assert _ids(client.get(URL, params={**kunde, "termin": "ueberfaellig"})) == []
    db.get(Auftrag, uuid.UUID(frei)).geschaetztes_fertigstellungsdatum = date.today() - timedelta(days=1)
    db.flush()
    assert _ids(client.get(URL, params={**kunde, "termin": "ueberfaellig"})) == [frei]


def test_liste_suche_nummer_kunde_instrument(client, w, db):
    kennung = f"AS{uuid.uuid4().hex[:6]}"
    w.kunde.name = f"{kennung} Musikschule"
    w.kunde.externe_kundennummer = f"{kennung}-EXT"
    a = client.post(URL, json=neuer_auftrag(w)).json()
    instrument = db.get(Instrument, uuid.UUID(a["instrument_id"]))
    instrument.hersteller, instrument.seriennummer = "Höfner 100%_echt", f"SN{kennung}"
    db.flush()

    for suche in (a["auftragsnummer"], f"{kennung} musik", f"{kennung}-ext", "TEST Kontrabass", "höfner", f"sn{kennung}"):
        assert a["id"] in _ids(client.get(URL, params={"suche": suche})), suche
    assert _ids(client.get(URL, params={"suche": "100%_echt"})) == [a["id"]]
    assert _ids(client.get(URL, params={"suche": "Höfner %"})) == []


def test_liste_sortierung_und_seiten(client, w):
    kunde = {"kunde_id": str(w.kunde.id)}
    ids = [client.post(URL, json=neuer_auftrag(w, klasse=k)).json()["id"] for k in (w.violine, w.kontrabass, w.violine)]
    params = {**kunde, "sortierung": "instrument", "richtung": "auf", "seitengroesse": 2}
    seite1, seite2 = (client.get(URL, params={**params, "seite": n}) for n in (1, 2))
    assert _ids(seite1) + _ids(seite2) == [ids[1], ids[0], ids[2]]  # Kontrabass, dann Violinen nach Eingang
    assert seite1.json()["treffer"] == 3


@pytest.mark.parametrize("params", [
    {"sortierung": "zugriffstoken"}, {"status": "gibt_es_nicht"}, {"mitarbeiter": "jemand"}, {"termin": "bald"},
])
def test_liste_ungueltige_parameter(client, w, params):
    assert client.get(URL, params=params).status_code == 422


def test_nicht_gefunden(client, w):
    assert client.get(f"{URL}/{uuid.uuid4()}").status_code == 404
    antwort = client.post(f"{URL}/{uuid.uuid4()}/status", json={"status_id": str(w.in_bearbeitung)})
    assert antwort.status_code == 404


# --- Statuswechsel -----------------------------------------------------------

def test_statuswechsel_erzeugt_historieneintrag(client, w):
    a = client.post(URL, json=neuer_auftrag(w)).json()

    antwort = client.post(f"{URL}/{a['id']}/status", json={
        "status_id": str(w.in_bearbeitung), "kommentar": "Begonnen",
    })
    assert antwort.status_code == 200
    a = antwort.json()
    assert a["status"]["schluessel"] == "in_bearbeitung"
    verlauf = a["statusverlauf"]
    assert [v["status"]["schluessel"] for v in verlauf] == ["angenommen", "in_bearbeitung"]
    assert verlauf[1]["kommentar"] == "Begonnen"
    assert verlauf[1]["geaendert_von_mitarbeiter_id"] == str(w.mitarbeiter.id)


def test_verlauf_nennt_handelnde_auch_nach_deaktivierung(client, w, db):
    """Namen im Statusverlauf und Schätzprotokoll bleiben sichtbar – unabhängig vom Aktivstatus
    des Handelnden und von der Rolle des Betrachters."""
    a = client.post(URL, json=neuer_auftrag(w)).json()
    client.post(f"{URL}/{a['id']}/status", json={"status_id": str(w.in_bearbeitung)})
    client.post(f"{URL}/{a['id']}/schaetzung-korrektur", json={"geschaetzte_kosten": 99, "grund": "Teuer"})
    w.mitarbeiter.aktiv, w.mitarbeiter.deaktiviert_am = False, datetime.now(timezone.utc)
    db.flush()

    betrachter = angemeldet_als(konto_anlegen(db, Systemrolle.mitarbeiter, name="Kollege"))
    detail = client.get(f"{URL}/{a['id']}", headers=betrachter).json()
    assert [v["geaendert_von_name"] for v in detail["statusverlauf"]] == ["Test Geigenbauer", "Test Geigenbauer"]
    korrektur = detail["schaetzungen"][-1]
    assert (korrektur["methode"], korrektur["korrigiert_von_name"]) == ("manuelle_korrektur", "Test Geigenbauer")
    assert detail["schaetzungen"][0]["korrigiert_von_name"] is None  # automatische Schätzung


def test_statuswechsel_in_gleichen_status_abgelehnt(client, w):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    antwort = client.post(f"{URL}/{a['id']}/status", json={"status_id": a["status"]["id"]})
    assert antwort.status_code == 409


def _fehlende_felder(antwort):
    assert antwort.status_code == 422, antwort.text
    return sorted(f["loc"][-1] for f in antwort.json()["detail"])


def test_fertig_erfordert_arbeitszeit_und_betrag(client, w, db):
    """Abschluss (9.8): ohne Arbeitszeit oder ohne abgerechneten Betrag wird abgelehnt – am jeweiligen Feld."""
    a = client.post(URL, json=neuer_auftrag(w)).json()
    pfad = f"{URL}/{a['id']}/status"
    fertig = {"status_id": str(w.fertig)}

    assert _fehlende_felder(client.post(pfad, json=fertig)) == ["abgerechneter_betrag", "arbeitszeit_minuten"]
    assert _fehlende_felder(client.post(pfad, json={**fertig, "arbeitszeit_minuten": 90})) == ["abgerechneter_betrag"]
    assert _fehlende_felder(client.post(pfad, json={**fertig, "abgerechneter_betrag": 20})) == ["arbeitszeit_minuten"]
    assert _fehlende_felder(client.post(pfad, json={**fertig, "arbeitszeit_minuten": 90, "abgerechneter_betrag": -1})) == \
        ["abgerechneter_betrag"]
    # Nach den Ablehnungen ist nichts gespeichert
    db.expire_all()
    auftrag = db.get(Auftrag, uuid.UUID(a["id"]))
    assert (auftrag.tatsaechliche_kosten, auftrag.status_aktuell_id) == (None, uuid.UUID(a["status"]["id"]))
    assert db.scalars(select(Arbeitszeiterfassung).where(Arbeitszeiterfassung.auftrag_id == auftrag.id)).all() == []


def test_abschluss_mit_unveraendert_uebernommenem_vorschlag(client, w, db):
    """Die Oberfläche belegt den Betrag mit der aktuellen Kostenschätzung vor; wird er so bestätigt, steht er als Ist-Wert."""
    a = client.post(URL, json=neuer_auftrag(w)).json()
    assert a["geschaetzte_kosten"] == 60.0  # Vorgabewert Kontrabass
    antwort = client.post(f"{URL}/{a['id']}/status", json={
        "status_id": str(w.fertig), "arbeitszeit_minuten": 90, "abgerechneter_betrag": a["geschaetzte_kosten"]})
    assert antwort.status_code == 200
    assert (antwort.json()["tatsaechliche_kosten"], antwort.json()["geschaetzte_kosten"]) == (60.0, 60.0)
    assert db.get(Auftrag, uuid.UUID(a["id"])).tatsaechliche_kosten == Decimal("60.00")


def test_abschluss_mit_abweichendem_betrag(client, w, db):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    antwort = client.post(f"{URL}/{a['id']}/status", json={
        "status_id": str(w.fertig), "arbeitszeit_minuten": 120, "abgerechneter_betrag": 84.5})
    assert antwort.status_code == 200
    detail = antwort.json()
    assert (detail["tatsaechliche_kosten"], detail["geschaetzte_kosten"]) == (84.5, 60.0)  # die Schätzung bleibt unverändert
    # Weiter zu "Abgeholt": braucht keinen Betrag mehr und behält ihn
    abgeholt = client.post(f"{URL}/{a['id']}/status", json={"status_id": str(w.abgeholt)})
    assert abgeholt.status_code == 200 and abgeholt.json()["tatsaechliche_kosten"] == 84.5
    # Der Ist-Wert fließt in die Kostenschätzung vergleichbarer Aufträge ein (4.1)
    assert db.get(Auftrag, uuid.UUID(a["id"])).tatsaechliche_kosten == Decimal("84.50")


@pytest.mark.parametrize("ausgangsstatus", ["angenommen", "in_bearbeitung", "wartet_auf_ersatzteil", "qualitaetspruefung"])
def test_abgeholt_nur_aus_fertig(client, w, db, ausgangsstatus):
    """Direkter Wechsel auf "Abgeholt" aus einem offenen Status wird abgelehnt (2.7a) – sonst
    ließe sich die Pflichtabfrage von Arbeitszeit und Betrag umgehen."""
    a = client.post(URL, json=neuer_auftrag(w)).json()
    pfad = f"{URL}/{a['id']}/status"
    if ausgangsstatus != "angenommen":
        assert client.post(pfad, json={"status_id": str(w.status[ausgangsstatus])}).status_code == 200

    antwort = client.post(pfad, json={"status_id": str(w.abgeholt)})
    assert antwort.status_code == 409 and "Fertig" in antwort.json()["detail"]
    # Auch mit mitgeschickten Abschlussdaten nicht – die gehören zu "Fertig"
    assert client.post(pfad, json={"status_id": str(w.abgeholt), "arbeitszeit_minuten": 60,
                                   "abgerechneter_betrag": 50}).status_code in (409, 422)
    db.expire_all()
    auftrag = db.get(Auftrag, uuid.UUID(a["id"]))
    assert auftrag.status_aktuell_id == w.status[ausgangsstatus] and auftrag.tatsaechliches_fertigstellungsdatum is None

    # Über "Fertig" geht es
    assert client.post(pfad, json={"status_id": str(w.fertig), "arbeitszeit_minuten": 60, "abgerechneter_betrag": 50}).status_code == 200
    assert client.post(pfad, json={"status_id": str(w.abgeholt)}).status_code == 200


def test_betrag_nur_beim_abschluss_und_wiederaufnahme_leert_ihn(client, w, db):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    pfad = f"{URL}/{a['id']}/status"
    assert _fehlende_felder(client.post(pfad, json={"status_id": str(w.in_bearbeitung), "abgerechneter_betrag": 10})) == \
        ["abgerechneter_betrag"]

    antwort = client.post(pfad, json={"status_id": str(w.fertig), "arbeitszeit_minuten": 90, "abgerechneter_betrag": 70})
    assert antwort.status_code == 200
    assert antwort.json()["tatsaechliches_fertigstellungsdatum"] == date.today().isoformat()
    [zeit] = db.scalars(select(Arbeitszeiterfassung).where(
        Arbeitszeiterfassung.auftrag_id == uuid.UUID(a["id"])
    )).all()
    assert (zeit.dauer_minuten, zeit.mitarbeiter_id) == (90, w.mitarbeiter.id)

    # Wiederaufnahme leert das Fertigstellungsdatum wieder
    zurueck = client.post(pfad, json={"status_id": str(w.in_bearbeitung)}).json()
    assert (zurueck["tatsaechliches_fertigstellungsdatum"], zurueck["tatsaechliche_kosten"]) == (None, None)
    assert len(zurueck["statusverlauf"]) == 3


# --- Manuelle Korrektur ------------------------------------------------------

def test_korrektur_erzeugt_log_eintrag_und_aktualisiert_auftrag(client, w, db):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    automatisch_vorher = a["schaetzungen"][0]

    antwort = client.post(f"{URL}/{a['id']}/schaetzung-korrektur", json={
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
    client.post(pfad, json={"geschaetzte_kosten": 90, "grund": "Ersatzteil teurer"})
    a = client.post(pfad, json={
        "geschaetzte_arbeitsstunden": 3, "geschaetzte_kosten": 120, "grund": "Zusatzschaden"
    }).json()

    assert (a["geschaetzte_arbeitsstunden"], a["geschaetzte_kosten"]) == (3.0, 120.0)
    assert [s["methode"] for s in a["schaetzungen"]] == ["regelbasiert", "manuelle_korrektur", "manuelle_korrektur"]
    assert a["schaetzungen"][2]["eingabefaktoren"]["vorher"]["geschaetzte_kosten"] == "90.00"


@pytest.mark.parametrize("header, daten, erwartet", [
    (False, {"geschaetzte_kosten": 90, "grund": "x"}, 401),  # nicht angemeldet
    (True, {"geschaetzte_kosten": 90}, 422),                  # Grund fehlt
    (True, {"geschaetzte_kosten": 90, "grund": "   "}, 422),  # Grund nur Leerzeichen
    (True, {"grund": "nichts korrigiert"}, 422),              # kein Wert angegeben
    (True, {"geschaetzte_kosten": -5, "grund": "x"}, 422),    # negativ
])
def test_korrektur_ungueltig(client, w, db, header, daten, erwartet):
    a = client.post(URL, json=neuer_auftrag(w)).json()
    antwort = client.post(f"{URL}/{a['id']}/schaetzung-korrektur", headers={} if header else OHNE_ANMELDUNG, json=daten)
    assert antwort.status_code == erwartet
    anzahl_logs = len(db.scalars(select(SchaetzungsLog).where(SchaetzungsLog.auftrag_id == uuid.UUID(a["id"]))).all())
    assert anzahl_logs == 1  # nichts protokolliert

"""Werkstattleiter-Startseite (Datenmodell 9.5): Kennzahlen passen zur gefilterten Auftragsliste."""

from datetime import date, timedelta

import pytest

from app.models import Prioritaet, Systemrolle
from tests.beispieldaten import Werkstatt
from tests.conftest import OHNE_ANMELDUNG, angemeldet_als, konto_anlegen

URL = "/dashboard"


@pytest.fixture
def leitung(db, client):
    person = konto_anlegen(db, Systemrolle.werkstattleiter, name="Leitung")
    client.headers.update(angemeldet_als(person))
    return person


def kennzahlen(client):
    antwort = client.get(URL)
    assert antwort.status_code == 200, antwort.text
    return antwort.json()["kennzahlen"]


def treffer(client, **filter):
    return client.get("/auftraege", params={"seitengroesse": 1, **filter}).json()["treffer"]


def test_nur_leitung_und_admin(client, db):
    assert client.get(URL, headers=angemeldet_als(konto_anlegen(db, Systemrolle.mitarbeiter))).status_code == 403
    assert client.get(URL, headers=OHNE_ANMELDUNG).status_code == 401
    assert client.get(URL, headers=angemeldet_als(konto_anlegen(db, Systemrolle.admin))).status_code == 200


def test_kennzahlen_zaehlen_neue_auftraege(client, db, leitung):
    vorher = kennzahlen(client)
    w = Werkstatt(db)
    w.auftrag(status=w.in_bearbeitung)                                    # offen
    eilig = w.auftrag(status=w.in_bearbeitung)                            # offen, hohe Priorität
    eilig.prioritaet = Prioritaet.hoch
    spaet = w.auftrag(status=w.in_bearbeitung)                            # offen, überfällig
    spaet.geschaetztes_fertigstellungsdatum = date.today() - timedelta(days=1)
    fertig = w.auftrag(status=w.fertig)                                   # abgeschlossen: zählt nirgends
    fertig.prioritaet = Prioritaet.hoch
    fertig.geschaetztes_fertigstellungsdatum = date.today() - timedelta(days=5)
    wartet = w.auftrag(status=w.in_bearbeitung, zugewiesen=w.mitarbeiter)  # wird pausiert
    db.flush()
    antwort = client.post(f"/auftraege/{wartet.id}/status", json={"status_id": str(w.status["wartet_auf_ersatzteil"])})
    assert antwort.status_code == 200

    nachher = kennzahlen(client)
    unterschied = {name: nachher[name] - vorher[name] for name in nachher}
    assert unterschied == {"offen": 4, "ueberfaellig": 1, "priorisiert": 1, "pausiert": 1}

    # Zurück in Bearbeitung: nicht mehr pausiert
    client.post(f"/auftraege/{wartet.id}/status", json={"status_id": str(w.in_bearbeitung)})
    assert kennzahlen(client)["pausiert"] == vorher["pausiert"]


def test_kacheln_stimmen_mit_der_gefilterten_liste_ueberein(client, db, leitung):
    w = Werkstatt(db)
    wartet = w.auftrag(status=w.in_bearbeitung, zugewiesen=w.mitarbeiter)
    wartet.prioritaet = Prioritaet.hoch
    wartet.geschaetztes_fertigstellungsdatum = date.today() - timedelta(days=1)
    db.flush()
    client.post(f"/auftraege/{wartet.id}/status", json={"status_id": str(w.status["wartet_auf_ersatzteil"])})

    k = kennzahlen(client)
    assert k["offen"] == treffer(client)
    assert k["ueberfaellig"] == treffer(client, termin="ueberfaellig")
    assert k["priorisiert"] == treffer(client, prioritaet="hoch")
    assert k["pausiert"] == treffer(client, pausiert="true") >= 1
    assert str(wartet.id) in [a["id"] for a in client.get(
        "/auftraege", params={"pausiert": "true", "kunde_id": str(w.kunde.id)}).json()["eintraege"]]

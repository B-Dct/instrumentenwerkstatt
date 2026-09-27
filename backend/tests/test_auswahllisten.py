"""Tests der Lese-Endpunkte für Auswahllisten."""

from datetime import UTC, datetime

import pytest

from tests.beispieldaten import Werkstatt
from tests.conftest import angemeldet_als, konto_anlegen


@pytest.fixture
def w(db, client):
    werkstatt = Werkstatt(db)
    client.headers.update(angemeldet_als(werkstatt.mitarbeiter))
    return werkstatt


@pytest.mark.parametrize("pfad", ["/kunden", "/instrumente", "/reparaturarten", "/auftragsstatus", "/mitarbeiter"])
def test_nur_mit_anmeldung(client, pfad):
    assert client.get(pfad).status_code == 401


def test_kunden_und_instrumente_je_kunde(client, w):
    violine = w.instrument(w.violine)
    w.instrument(w.kontrabass)

    kunden = client.get("/kunden").json()
    assert str(w.kunde.id) in [k["id"] for k in kunden]

    instrumente = client.get("/instrumente", params={"kunde_id": str(w.kunde.id)}).json()
    assert [i["instrumentenklasse_bezeichnung"] for i in instrumente] == ["TEST Kontrabass", "TEST Violine"]
    assert str(violine.id) in [i["id"] for i in instrumente]


def test_archivierte_und_deaktivierte_ausgeblendet(client, w, db):
    w.saitenwechsel.aktiv = False
    ehemalig = konto_anlegen(db, name="Ehemalig")
    ehemalig.aktiv, ehemalig.deaktiviert_am = False, datetime.now(UTC)
    db.flush()

    assert "TEST Saitenwechsel" not in [r["bezeichnung"] for r in client.get("/reparaturarten").json()]
    namen = [m["name"] for m in client.get("/mitarbeiter").json()]
    assert "Test Geigenbauer" in namen and "Ehemalig" not in namen


def test_status_in_reihenfolge_mit_schaltern(client, w):
    status = client.get("/auftragsstatus").json()
    assert [s["schluessel"] for s in status][:2] == ["angenommen", "in_bearbeitung"]
    fertig = next(s for s in status if s["schluessel"] == "fertig")
    assert fertig["erfordert_zeiterfassung"] and fertig["ist_abgeschlossen"]

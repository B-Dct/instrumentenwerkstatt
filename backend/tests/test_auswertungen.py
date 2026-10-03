"""Auswertungen (Datenmodell 9.14): Jahresstatistik über die im Jahr abgeschlossenen Aufträge."""

from datetime import date

import pytest

from app.models import Instrumentenklasse, Reparaturart, Systemrolle
from tests.beispieldaten import Werkstatt
from tests.conftest import OHNE_ANMELDUNG, angemeldet_als, konto_anlegen

URL = "/auswertungen"
JAHR = 2003  # so früh, dass keine echten Aufträge hineinfallen


@pytest.fixture
def leitung(db, client):
    person = konto_anlegen(db, Systemrolle.werkstattleiter, name="Leitung")
    client.headers.update(angemeldet_als(person))
    return person


@pytest.fixture
def w(db):
    return Werkstatt(db)


def abgeschlossen(w, monat, tag=15, jahr=JAHR, klasse=None, art=None):
    """Ein abgeschlossener Auftrag mit Fertigstellungsdatum im gewünschten Monat."""
    a = w.auftrag(klasse=klasse, status=w.abgeholt)
    a.tatsaechliches_fertigstellungsdatum = date(jahr, monat, tag)
    if art is not None:
        a.reparaturart_id = art.id
    return a


def auswertung(client, jahr=JAHR):
    antwort = client.get(URL, params={"jahr": jahr})
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


# --- Zugriff und Jahresfilter ------------------------------------------------------

def test_nur_leitung_und_admin(client, db):
    assert client.get(URL, headers=angemeldet_als(konto_anlegen(db, Systemrolle.mitarbeiter))).status_code == 403
    assert client.get(URL, headers=OHNE_ANMELDUNG).status_code == 401
    assert client.get(URL, headers=angemeldet_als(konto_anlegen(db, Systemrolle.admin))).status_code == 200


def test_standard_ist_das_laufende_jahr(client, leitung):
    daten = client.get(URL).json()
    assert daten["jahr"] == date.today().year and daten["jahre"][0] == date.today().year


@pytest.mark.parametrize("jahr", [1999, date.today().year + 1, "heuer"])
def test_ungueltiges_jahr(client, leitung, jahr):
    assert client.get(URL, params={"jahr": jahr}).status_code == 422


def test_waehlbare_jahre_reichen_bis_zum_ersten_abschluss(client, db, leitung, w):
    abgeschlossen(w, 6)
    db.flush()
    jahre = auswertung(client)["jahre"]
    assert jahre[0] == date.today().year and jahre[-1] == JAHR and jahre == sorted(jahre, reverse=True)


# --- 9.14.1 Menge ------------------------------------------------------------------

def test_leeres_jahr(client, leitung):
    menge = auswertung(client)["menge"]
    assert menge == {"abgeschlossen": 0, "pro_monat": [0] * 12, "nach_reparaturart": [], "nach_instrumentenklasse": []}


def test_menge_zaehlt_nach_fertigstellungsdatum_nicht_nach_eingang(client, db, leitung, w):
    abgeschlossen(w, 1, 1), abgeschlossen(w, 3), abgeschlossen(w, 3), abgeschlossen(w, 12, 31)
    abgeschlossen(w, 12, 31, jahr=JAHR - 1), abgeschlossen(w, 1, 1, jahr=JAHR + 1)   # Nachbarjahre: zählen nicht
    w.auftrag(status=w.in_bearbeitung)                                                # offen, ohne Datum: zählt nicht
    db.flush()
    menge = auswertung(client)["menge"]
    assert menge["abgeschlossen"] == 4
    assert menge["pro_monat"] == [1, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 1]
    assert auswertung(client, JAHR - 1)["menge"]["abgeschlossen"] == 1


def test_wiederaufgenommener_auftrag_zaehlt_nicht(client, db, leitung, w):
    """Beim Zurückwechseln in einen offenen Status wird das Fertigstellungsdatum geleert."""
    a = w.auftrag(status=w.in_bearbeitung, zugewiesen=w.mitarbeiter)
    db.flush()
    jahr = date.today().year
    vorher = auswertung(client, jahr)["menge"]["abgeschlossen"]
    client.post(f"/auftraege/{a.id}/status", json={"status_id": str(w.fertig), "arbeitszeit_minuten": 30})
    assert auswertung(client, jahr)["menge"]["abgeschlossen"] == vorher + 1
    client.post(f"/auftraege/{a.id}/status", json={"status_id": str(w.in_bearbeitung)})
    assert auswertung(client, jahr)["menge"]["abgeschlossen"] == vorher


def test_verteilung_top_5_und_sonstige(client, db, leitung, w):
    # Sieben Reparaturarten mit 7, 6, … 1 Aufträgen; zwei Instrumentenklassen
    arten = [Reparaturart(bezeichnung=f"TEST Art {n}", standard_komplexitaet=1) for n in range(7)]
    db.add_all(arten)
    db.flush()
    for n, art in enumerate(arten):
        for _ in range(7 - n):
            abgeschlossen(w, 5, art=art, klasse=w.violine if n == 0 else w.kontrabass)
    db.flush()

    menge = auswertung(client)["menge"]
    assert [(v["bezeichnung"], v["anzahl"], v["sonstige"]) for v in menge["nach_reparaturart"]] == [
        ("TEST Art 0", 7, False), ("TEST Art 1", 6, False), ("TEST Art 2", 5, False),
        ("TEST Art 3", 4, False), ("TEST Art 4", 3, False), ("Sonstige", 3, True),   # 2 + 1
    ]
    assert [(v["bezeichnung"], v["anzahl"]) for v in menge["nach_instrumentenklasse"]] == \
        [("TEST Kontrabass", 21), ("TEST Violine", 7)]                               # ohne "Sonstige"
    assert sum(v["anzahl"] for v in menge["nach_reparaturart"]) == menge["abgeschlossen"] == 28


def test_verteilung_gleichstand_alphabetisch_und_archivierte_zaehlen_mit(client, db, leitung, w):
    b = Reparaturart(bezeichnung="TEST B", standard_komplexitaet=1)
    a = Reparaturart(bezeichnung="TEST A", standard_komplexitaet=1, archiviert_am=date(2020, 1, 1))
    harfe = Instrumentenklasse(bezeichnung="TEST Harfe", oberkategorie="Zupf")
    db.add_all([a, b, harfe])
    db.flush()
    abgeschlossen(w, 2, art=b, klasse=harfe), abgeschlossen(w, 2, art=a, klasse=harfe)
    db.flush()
    menge = auswertung(client)["menge"]
    assert [v["bezeichnung"] for v in menge["nach_reparaturart"]] == ["TEST A", "TEST B"]
    assert menge["nach_instrumentenklasse"] == [{"bezeichnung": "TEST Harfe", "anzahl": 2, "sonstige": False}]

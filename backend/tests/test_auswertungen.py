"""Auswertungen (Datenmodell 9.14): Jahresstatistik über die im Jahr abgeschlossenen Aufträge."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Arbeitszeiterfassung, Instrumentenklasse, Reparaturart, SchaetzungsLog, Systemrolle
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


# --- 9.14.2 Zeit -------------------------------------------------------------------

def fertig_nach(w, monat, tage, minuten=(), erste_prognose=None, **extra):
    """Abgeschlossener Auftrag: Eingang `tage` Kalendertage vor der Fertigstellung am 15. des Monats."""
    a = abgeschlossen(w, monat, **extra)
    a.erstellt_am = datetime(JAHR, monat, 15, 9, 0, tzinfo=timezone.utc) - timedelta(days=tage)
    for m in minuten:
        w.db.add(Arbeitszeiterfassung(auftrag_id=a.id, mitarbeiter_id=w.mitarbeiter.id, dauer_minuten=m))
    if erste_prognose is not None:  # Tage relativ zur Fertigstellung: negativ = Prognose lag früher
        prognose(w, a, a.tatsaechliches_fertigstellungsdatum + timedelta(days=erste_prognose), a.erstellt_am)
    return a


def prognose(w, auftrag, datum, zeitpunkt, methode="regelbasiert", **extra):
    w.db.add(SchaetzungsLog(auftrag_id=auftrag.id, methode=methode, geschaetztes_datum=datum, berechnet_am=zeitpunkt, **extra))


def test_zeit_ohne_daten(client, leitung):
    assert auswertung(client)["zeit"] == {
        "bearbeitungsdauer_tage": None, "bearbeitungsdauer_pro_monat": [None] * 12, "arbeitszeit_stunden": None,
        "auftraege_mit_zeiterfassung": 0, "puenktlich": 0, "auftraege_mit_terminprognose": 0, "puenktlichkeit_prozent": None,
    }


def test_bearbeitungsdauer_in_kalendertagen_gesamt_und_pro_monat(client, db, leitung, w):
    fertig_nach(w, 2, tage=4), fertig_nach(w, 2, tage=7)   # Februar: Ø 5,5
    fertig_nach(w, 9, tage=20)                              # September: 20
    fertig_nach(w, 9, tage=0)                               # am selben Tag fertig: 0
    db.flush()
    zeit = auswertung(client)["zeit"]
    assert zeit["bearbeitungsdauer_tage"] == 7.8            # (4 + 7 + 20 + 0) / 4 = 7,75
    assert zeit["bearbeitungsdauer_pro_monat"] == [None, 5.5, None, None, None, None, None, None, 10.0, None, None, None]


def test_reine_arbeitszeit_summe_je_auftrag_nur_mit_zeiterfassung(client, db, leitung, w):
    fertig_nach(w, 3, tage=30, minuten=(60, 30))            # 1,5 Std. in zwei Sitzungen
    fertig_nach(w, 3, tage=2, minuten=(150,))               # 2,5 Std.
    fertig_nach(w, 3, tage=5)                               # ohne Zeiterfassung: nicht im Schnitt
    fertig_nach(w, 3, tage=5, minuten=(600,), jahr=JAHR - 1)  # anderes Jahr
    db.flush()
    zeit = auswertung(client)["zeit"]
    assert (zeit["arbeitszeit_stunden"], zeit["auftraege_mit_zeiterfassung"]) == (2.0, 2)
    # Die Kalenderdauer bleibt davon getrennt (hier durch Wartezeit viel länger)
    assert zeit["bearbeitungsdauer_tage"] == 12.3           # (30 + 2 + 5) / 3


def test_puenktlichkeit_misst_die_erste_automatische_prognose(client, db, leitung, w):
    fertig_nach(w, 4, tage=10, erste_prognose=0)            # genau am Prognosetag: pünktlich
    fertig_nach(w, 4, tage=10, erste_prognose=3)            # früher fertig: pünktlich
    zu_spaet = fertig_nach(w, 4, tage=10, erste_prognose=-2)  # zwei Tage nach der Prognose: nicht pünktlich
    fertig_nach(w, 4, tage=10)                              # ohne Prognose: zählt nicht in die Quote
    # Spätere Neuberechnung und manuelle Korrektur hätten den Termin "gerettet" – zählen aber nicht
    spaeter = zu_spaet.erstellt_am + timedelta(days=5)
    prognose(w, zu_spaet, zu_spaet.tatsaechliches_fertigstellungsdatum + timedelta(days=9), spaeter)
    prognose(w, zu_spaet, zu_spaet.tatsaechliches_fertigstellungsdatum + timedelta(days=9), spaeter + timedelta(days=1),
             methode="manuelle_korrektur", korrigiert_von_mitarbeiter_id=leitung.id, grund="Teil kam später")
    db.flush()
    zeit = auswertung(client)["zeit"]
    assert (zeit["puenktlich"], zeit["auftraege_mit_terminprognose"], zeit["puenktlichkeit_prozent"]) == (2, 3, 67)


def test_puenktlichkeit_ignoriert_manuelle_korrektur_vor_der_ersten_automatik(client, db, leitung, w):
    """Auch wenn zeitlich zuerst eine Korrektur im Protokoll stünde: maßgeblich ist der erste automatische Eintrag."""
    a = fertig_nach(w, 6, tage=10)
    fertig = a.tatsaechliches_fertigstellungsdatum
    prognose(w, a, fertig + timedelta(days=30), a.erstellt_am, methode="manuelle_korrektur",
             korrigiert_von_mitarbeiter_id=leitung.id, grund="vorab")
    prognose(w, a, fertig - timedelta(days=1), a.erstellt_am + timedelta(hours=1))
    db.flush()
    zeit = auswertung(client)["zeit"]
    assert (zeit["puenktlich"], zeit["auftraege_mit_terminprognose"], zeit["puenktlichkeit_prozent"]) == (0, 1, 0)

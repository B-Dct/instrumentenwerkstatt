"""Werkstattleiter-Startseite (Datenmodell 9.5): Kennzahlen passen zur gefilterten Auftragsliste."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Abwesenheit, Abwesenheitstyp, MitarbeiterArbeitszeit, Prioritaet, Systemrolle
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


# --- Nächste fällige Aufträge ------------------------------------------------------

def test_naechste_faellige_nur_offene_mit_termin_frueheste_zuerst(client, db, leitung):
    w = Werkstatt(db)
    weit_zurueck = date(2000, 1, 1)  # vor allen echten Terminen, damit die Test-Aufträge vorn stehen

    def auftrag(tage, status=None):
        a = w.auftrag(status=status or w.in_bearbeitung)
        a.geschaetztes_fertigstellungsdatum = None if tage is None else weit_zurueck + timedelta(days=tage)
        return a

    spaeter, frueher = auftrag(3), auftrag(1)
    ohne_termin, abgeschlossen = auftrag(None), auftrag(0, status=w.fertig)
    weitere = [auftrag(n) for n in (4, 5, 6, 7)]
    db.flush()

    liste = client.get(URL).json()["naechste_faellige"]
    assert [a["id"] for a in liste] == [str(a.id) for a in (frueher, spaeter, *weitere[:3])]  # genau 5
    assert liste[0]["ist_ueberfaellig"] is True and liste[0]["kunde_name"] == "Test Kunde"
    assert not {str(ohne_termin.id), str(abgeschlossen.id)} & {a["id"] for a in liste}


# --- Auslastung (8.2) --------------------------------------------------------------

MONTAG = date.today() - timedelta(days=date.today().weekday())


def auslastung(client, mitarbeiter):
    daten = client.get(URL).json()
    assert daten["woche_von"] == MONTAG.isoformat()
    return next(z for z in daten["auslastung"] if z["mitarbeiter_id"] == str(mitarbeiter.id))


@pytest.fixture
def ohne_betriebsweite_abwesenheit(db):
    """Feiertage/Betriebsschließungen der laufenden Woche würden die Zahlen verschieben."""
    for a in db.scalars(select(Abwesenheit).where(Abwesenheit.mitarbeiter_id.is_(None),
                                                  Abwesenheit.bis_datum >= MONTAG, Abwesenheit.von_datum <= MONTAG + timedelta(days=6))):
        db.delete(a)
    db.flush()


def test_auslastung_standard_ohne_auftraege(client, db, leitung, ohne_betriebsweite_abwesenheit):
    assert auslastung(client, leitung) == {
        "mitarbeiter_id": str(leitung.id), "name": "Leitung", "wochenstunden": 40, "abwesenheitsstunden": 0,
        "auftragsstunden": 0, "offene_auftraege": 0, "freie_stunden": 40, "auslastung_prozent": 0,
    }


def test_auslastung_aus_offenen_auftraegen_und_wochenstunden(client, db, leitung, ohne_betriebsweite_abwesenheit):
    w = Werkstatt(db)
    db.add(MitarbeiterArbeitszeit(mitarbeiter_id=w.mitarbeiter.id, wochenstunden=20, gueltig_ab=date(2020, 1, 1)))
    w.auftrag(status=w.in_bearbeitung, zugewiesen=w.mitarbeiter, stunden="6.00")
    w.auftrag(status=w.in_bearbeitung, zugewiesen=w.mitarbeiter, stunden="9.00")
    w.auftrag(status=w.in_bearbeitung, zugewiesen=w.mitarbeiter)               # ohne Schätzung: zählt als Auftrag, 0 Std.
    w.auftrag(status=w.fertig, zugewiesen=w.mitarbeiter, stunden="50.00")      # abgeschlossen: zählt nicht
    w.auftrag(status=w.in_bearbeitung, stunden="50.00")                        # nicht zugewiesen: zählt nicht
    db.flush()
    z = auslastung(client, w.mitarbeiter)
    assert (z["wochenstunden"], z["auftragsstunden"], z["offene_auftraege"]) == (20, 15, 3)
    assert (z["freie_stunden"], z["auslastung_prozent"]) == (5, 75)


def test_auslastung_abwesenheit_bindet_stunden_und_ueberbuchung(client, db, leitung, ohne_betriebsweite_abwesenheit):
    w = Werkstatt(db)
    m = w.mitarbeiter  # Standard 40 Std. = 8 Std./Tag
    w.auftrag(status=w.in_bearbeitung, zugewiesen=m, stunden="30.00")
    db.add_all([
        Abwesenheit(mitarbeiter_id=m.id, typ=Abwesenheitstyp.urlaub, von_datum=MONTAG, bis_datum=MONTAG + timedelta(days=1)),  # 2 Tage = 16 Std.
        Abwesenheit(mitarbeiter_id=m.id, typ=Abwesenheitstyp.schulung, reduzierte_stunden=20,                                  # halber Tag = 4 Std.
                    von_datum=MONTAG + timedelta(days=2), bis_datum=MONTAG + timedelta(days=2)),
        Abwesenheit(mitarbeiter_id=None, typ=Abwesenheitstyp.betriebsschliessung,                                               # 1 Tag = 8 Std.
                    von_datum=MONTAG + timedelta(days=4), bis_datum=MONTAG + timedelta(days=4)),
        Abwesenheit(mitarbeiter_id=m.id, typ=Abwesenheitstyp.krankheit, von_datum=MONTAG + timedelta(days=3),                   # storniert: zählt nicht
                    bis_datum=MONTAG + timedelta(days=3), storniert_am=datetime.now(timezone.utc)),
        Abwesenheit(mitarbeiter_id=m.id, typ=Abwesenheitstyp.urlaub, von_datum=MONTAG + timedelta(days=7),                      # nächste Woche: zählt nicht
                    bis_datum=MONTAG + timedelta(days=11)),
    ])
    db.flush()
    z = auslastung(client, m)
    assert (z["abwesenheitsstunden"], z["auftragsstunden"]) == (28, 30)
    assert (z["freie_stunden"], z["auslastung_prozent"]) == (-18, 145)  # überbucht


def test_auslastung_nur_aktive_mitarbeiter_nach_name(client, db, leitung):
    ehemalig = konto_anlegen(db, name="Ehemalig", aktiv=False, deaktiviert_am=datetime.now(timezone.utc))
    zeilen = client.get(URL).json()["auslastung"]
    assert str(ehemalig.id) not in [z["mitarbeiter_id"] for z in zeilen]
    assert [z["name"] for z in zeilen] == sorted(z["name"] for z in zeilen)


# --- Heute abwesend (9.13) ---------------------------------------------------------

def test_heute_abwesend(client, db, leitung):
    heute = date.today()
    for a in db.scalars(select(Abwesenheit).where(Abwesenheit.von_datum <= heute, Abwesenheit.bis_datum >= heute)):
        db.delete(a)  # Ausgangslage unabhängig von echten Daten
    db.flush()
    assert client.get(URL).json()["heute_abwesend"] == []

    anna, bernd = konto_anlegen(db, name="AAA Anna"), konto_anlegen(db, name="BBB Bernd")
    ehemalig = konto_anlegen(db, name="Ehemalig", aktiv=False, deaktiviert_am=datetime.now(timezone.utc))
    gestern, morgen = heute - timedelta(days=1), heute + timedelta(days=1)
    db.add_all([
        Abwesenheit(mitarbeiter_id=bernd.id, typ=Abwesenheitstyp.schulung, von_datum=heute, bis_datum=heute,
                    reduzierte_stunden=20, notiz="Vormittags"),
        Abwesenheit(mitarbeiter_id=anna.id, typ=Abwesenheitstyp.urlaub, von_datum=gestern, bis_datum=morgen),
        Abwesenheit(mitarbeiter_id=None, typ=Abwesenheitstyp.betriebsschliessung, von_datum=heute, bis_datum=heute, notiz="Inventur"),
        # Zählen nicht: storniert, erst morgen, schon vorbei, deaktivierter Mitarbeiter
        Abwesenheit(mitarbeiter_id=anna.id, typ=Abwesenheitstyp.krankheit, von_datum=heute, bis_datum=heute,
                    storniert_am=datetime.now(timezone.utc)),
        Abwesenheit(mitarbeiter_id=bernd.id, typ=Abwesenheitstyp.urlaub, von_datum=morgen, bis_datum=morgen),
        Abwesenheit(mitarbeiter_id=bernd.id, typ=Abwesenheitstyp.krankheit, von_datum=gestern, bis_datum=gestern),
        Abwesenheit(mitarbeiter_id=ehemalig.id, typ=Abwesenheitstyp.urlaub, von_datum=heute, bis_datum=heute),
    ])
    db.flush()

    eintraege = client.get(URL).json()["heute_abwesend"]
    assert [(e["name"], e["typ"], e["verfuegbare_tagesstunden"], e["notiz"]) for e in eintraege] == [
        (None, "betriebsschliessung", None, "Inventur"),   # ganze Werkstatt zuerst
        ("AAA Anna", "urlaub", None, None),
        ("BBB Bernd", "schulung", 4, "Vormittags"),         # 20 Wochenstunden = 4 Std. am Tag
    ]
    assert eintraege[1]["bis_datum"] == morgen.isoformat()

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Instrumentenklasse, Reparaturart, Systemrolle, SystemEreignisLog
from tests.conftest import angemeldet_als, konto_anlegen

URL = "/admin/vorgabewerte"


@pytest.fixture
def admin(db, client):
    admin = konto_anlegen(db, Systemrolle.admin, name="Test Admin")
    client.headers.update(angemeldet_als(admin))
    return admin


@pytest.fixture
def stammdaten(db, admin):
    saitenwechsel = Reparaturart(bezeichnung="TEST Saitenwechsel", standard_komplexitaet=1)
    kontrabass = Instrumentenklasse(bezeichnung="TEST Kontrabass", oberkategorie="Streichinstrument")
    db.add_all([saitenwechsel, kontrabass])
    db.flush()
    return {"reparaturart": saitenwechsel.id, "klasse": kontrabass.id, "admin": admin.id}


def _ids(antwort):
    return [e["id"] for e in antwort.json()["eintraege"]]


def neu(stammdaten, **extra):
    return {
        "reparaturart_id": str(stammdaten["reparaturart"]),
        "vorgabe_stunden": 0.5,
        "vorgabe_kosten": 25,
        **extra,
    }


def test_anlegen_und_abrufen(client, stammdaten):
    antwort = client.post(URL, json=neu(stammdaten, notiz="inkl. Saiten"))
    assert antwort.status_code == 201
    daten = antwort.json()
    assert daten["reparaturart_bezeichnung"] == "TEST Saitenwechsel"
    assert daten["instrumentenklasse_id"] is None
    assert daten["vorgabe_stunden"] == 0.5
    assert daten["vorgabe_kosten"] == 25.0
    assert daten["geaendert_von_mitarbeiter_id"] == str(stammdaten["admin"])

    assert client.get(f"{URL}/{daten['id']}").json() == daten


def test_allgemein_und_spezifisch_nebeneinander(client, stammdaten):
    assert client.post(URL, json=neu(stammdaten)).status_code == 201
    spezifisch = neu(stammdaten, instrumentenklasse_id=str(stammdaten["klasse"]), vorgabe_stunden=1.5)
    assert client.post(URL, json=spezifisch).status_code == 201

    liste = client.get(URL, params={"reparaturart_id": str(stammdaten["reparaturart"])}).json()["eintraege"]
    assert [e["instrumentenklasse_bezeichnung"] for e in liste] == [None, "TEST Kontrabass"]

    nur_klasse = client.get(URL, params={"instrumentenklasse_id": str(stammdaten["klasse"])}).json()["eintraege"]
    assert [e["vorgabe_stunden"] for e in nur_klasse] == [1.5]


@pytest.mark.parametrize("mit_klasse", [False, True])
def test_doppelte_kombination_wird_abgelehnt(client, stammdaten, mit_klasse):
    extra = {"instrumentenklasse_id": str(stammdaten["klasse"])} if mit_klasse else {}
    assert client.post(URL, json=neu(stammdaten, **extra)).status_code == 201
    antwort = client.post(URL, json=neu(stammdaten, **extra))
    assert antwort.status_code == 409
    # Danach funktioniert die nächste Anfrage normal weiter
    assert client.get(URL).status_code == 200


@pytest.mark.parametrize("feld, wert", [
    ("vorgabe_stunden", -1),
    ("vorgabe_kosten", -0.01),
    ("vorgabe_kosten", 12.345),  # mehr als 2 Nachkommastellen
])
def test_ungueltige_werte(client, stammdaten, feld, wert):
    assert client.post(URL, json=neu(stammdaten, **{feld: wert})).status_code == 422


def test_unbekannte_reparaturart_oder_klasse(client, stammdaten):
    unbekannt = str(uuid.uuid4())
    assert client.post(URL, json=neu(stammdaten, reparaturart_id=unbekannt)).status_code == 422
    assert client.post(URL, json=neu(stammdaten, instrumentenklasse_id=unbekannt)).status_code == 422


def test_bearbeiten_aendert_nur_mitgeschickte_felder(client, stammdaten, db):
    vorher = client.post(URL, json=neu(stammdaten, notiz="alt")).json()

    antwort = client.patch(f"{URL}/{vorher['id']}", json={"vorgabe_kosten": 30})
    assert antwort.status_code == 200
    nachher = antwort.json()
    assert nachher["vorgabe_kosten"] == 30.0
    assert nachher["vorgabe_stunden"] == 0.5
    assert nachher["notiz"] == "alt"

    log = db.scalars(select(SystemEreignisLog).where(
        SystemEreignisLog.betroffene_id == uuid.UUID(vorher["id"])
    ).order_by(SystemEreignisLog.zeitpunkt)).all()
    assert [e.aktion for e in log] == ["vorgabewert_angelegt", "vorgabewert_geaendert"]
    assert all(e.ausgefuehrt_von_mitarbeiter_id == stammdaten["admin"] for e in log)
    assert log[1].details["alt"]["vorgabe_kosten"] == "25.00"
    assert log[1].details["neu"]["vorgabe_kosten"] == "30.00"


def test_bearbeiten_klasse_auf_allgemein_zuruecksetzen(client, stammdaten):
    eintrag = client.post(URL, json=neu(stammdaten, instrumentenklasse_id=str(stammdaten["klasse"]))).json()
    antwort = client.patch(f"{URL}/{eintrag['id']}", json={"instrumentenklasse_id": None})
    assert antwort.status_code == 200
    assert antwort.json()["instrumentenklasse_id"] is None


def test_bearbeiten_pflichtfeld_nicht_leeren(client, stammdaten):
    eintrag = client.post(URL, json=neu(stammdaten)).json()
    antwort = client.patch(f"{URL}/{eintrag['id']}", json={"vorgabe_kosten": None})
    assert antwort.status_code == 422


def test_bearbeiten_in_bestehende_kombination_abgelehnt(client, stammdaten):
    client.post(URL, json=neu(stammdaten))
    spezifisch = client.post(URL, json=neu(stammdaten, instrumentenklasse_id=str(stammdaten["klasse"]))).json()
    antwort = client.patch(f"{URL}/{spezifisch['id']}", json={"instrumentenklasse_id": None})
    assert antwort.status_code == 409
    # Danach ist die Sitzung sauber: der abgelehnte Wert wurde nicht übernommen
    assert client.get(f"{URL}/{spezifisch['id']}").json()["instrumentenklasse_id"] == str(stammdaten["klasse"])


def test_nicht_gefunden(client, admin):
    assert client.get(f"{URL}/{uuid.uuid4()}").status_code == 404
    assert client.patch(f"{URL}/{uuid.uuid4()}", json={"notiz": "x"}).status_code == 404


# --- Archivieren / Reaktivieren (2.6a) --------------------------------------

def test_archivieren_nimmt_wert_zurueck_ohne_zu_loeschen(client, stammdaten, db):
    from app.models import ReparaturVorgabewert
    from app.schaetzung import Quelle, schaetze_arbeitsstunden

    client.post(URL, json=neu(stammdaten, vorgabe_stunden=0.5))  # allgemein
    spezifisch = client.post(URL, json=neu(stammdaten, instrumentenklasse_id=str(stammdaten["klasse"]),
                                           vorgabe_stunden=9)).json()  # versehentlich angelegt
    assert schaetze_arbeitsstunden(db, stammdaten["klasse"], stammdaten["reparaturart"]).quelle == Quelle.vorgabe_instrumentenklasse

    antwort = client.post(f"{URL}/{spezifisch['id']}/archivieren")
    assert antwort.status_code == 200 and antwort.json()["archiviert_am"] is not None
    assert antwort.json()["geaendert_von_mitarbeiter_id"] == str(stammdaten["admin"])

    # Schätzung ignoriert den archivierten Wert, der allgemeine greift wieder
    s = schaetze_arbeitsstunden(db, stammdaten["klasse"], stammdaten["reparaturart"])
    assert (s.quelle, s.wert) == (Quelle.vorgabe_allgemein, Decimal("0.50"))
    # Nicht gelöscht, nur ausgeblendet
    assert db.get(ReparaturVorgabewert, uuid.UUID(spezifisch["id"])) is not None
    nur_diese_art = {"reparaturart_id": str(stammdaten["reparaturart"])}
    assert spezifisch["id"] not in _ids(client.get(URL, params=nur_diese_art))
    assert spezifisch["id"] in _ids(client.get(URL, params={**nur_diese_art, "status": "archiviert"}))

    aktionen = db.scalars(select(SystemEreignisLog.aktion).where(
        SystemEreignisLog.betroffene_id == uuid.UUID(spezifisch["id"])).order_by(SystemEreignisLog.zeitpunkt)).all()
    assert aktionen == ["vorgabewert_angelegt", "vorgabewert_archiviert"]


def test_eindeutigkeit_nur_unter_aktiven(client, stammdaten):
    erster = client.post(URL, json=neu(stammdaten)).json()
    client.post(f"{URL}/{erster['id']}/archivieren")
    # Gleiche Kombination neu anlegen: erlaubt, weil der alte archiviert ist
    zweiter = client.post(URL, json=neu(stammdaten, vorgabe_kosten=40))
    assert zweiter.status_code == 201
    # Den alten reaktivieren: abgelehnt, solange der neue aktiv ist
    antwort = client.post(f"{URL}/{erster['id']}/reaktivieren")
    assert antwort.status_code == 409
    assert "zuerst archivieren" in antwort.json()["detail"]
    # Nach Archivieren des neuen klappt es
    client.post(f"{URL}/{zweiter.json()['id']}/archivieren")
    assert client.post(f"{URL}/{erster['id']}/reaktivieren").json()["archiviert_am"] is None


def test_archivierten_wert_erst_reaktivieren_dann_bearbeiten(client, stammdaten):
    eintrag = client.post(URL, json=neu(stammdaten)).json()
    client.post(f"{URL}/{eintrag['id']}/archivieren")
    assert client.patch(f"{URL}/{eintrag['id']}", json={"vorgabe_kosten": 99}).status_code == 409
    assert client.post(f"{URL}/{eintrag['id']}/archivieren").status_code == 409  # schon archiviert
    client.post(f"{URL}/{eintrag['id']}/reaktivieren")
    assert client.patch(f"{URL}/{eintrag['id']}", json={"vorgabe_kosten": 99}).status_code == 200


def test_archivieren_nur_admin(client, stammdaten, db):
    from app.models import Systemrolle
    eintrag = client.post(URL, json=neu(stammdaten)).json()
    for rolle in (Systemrolle.mitarbeiter, Systemrolle.werkstattleiter):
        header = angemeldet_als(konto_anlegen(db, rolle))
        assert client.post(f"{URL}/{eintrag['id']}/archivieren", headers=header).status_code == 403


# --- Liste nach 9.11 ----------------------------------------------------------------

@pytest.fixture
def vorgabenkreis(client, db, admin):
    """Eigene Reparaturarten/Klassen mit eindeutiger Kennung, damit echte Daten nicht stören."""
    kennung = f"VW{uuid.uuid4().hex[:6]}"
    arten = {n: Reparaturart(bezeichnung=f"{kennung} {n}", standard_komplexitaet=2) for n in ("Bogen", "Steg")}
    klassen = {n: Instrumentenklasse(bezeichnung=f"{kennung} {n}", oberkategorie="Streich") for n in ("Cello", "Viola")}
    db.add_all([*arten.values(), *klassen.values()])
    db.flush()

    def anlegen(art, klasse=None, stunden=1, notiz=None):
        return client.post(URL, json={"reparaturart_id": str(arten[art].id), "vorgabe_stunden": stunden,
                                      "vorgabe_kosten": 10 * stunden, "notiz": notiz,
                                      **({"instrumentenklasse_id": str(klassen[klasse].id)} if klasse else {})}).json()

    anlegen("Steg", "Viola", stunden=3)
    anlegen("Steg", stunden=2, notiz="mit 5%_Aufschlag")
    anlegen("Bogen", "Cello", stunden=4)
    archiviert = anlegen("Bogen", stunden=1)
    client.post(f"{URL}/{archiviert['id']}/archivieren")
    anlegen("Bogen", stunden=5)  # neuer allgemeiner Wert nach dem Archivieren
    return kennung, arten, klassen


def _zeilen(antwort, kennung):
    return [(e["reparaturart_bezeichnung"].removeprefix(f"{kennung} "),
             (e["instrumentenklasse_bezeichnung"] or "allgemein").removeprefix(f"{kennung} "), e["vorgabe_stunden"])
            for e in antwort.json()["eintraege"]]


def test_liste_standard_reparaturart_dann_allgemein_vor_speziell(client, vorgabenkreis):
    kennung, _, _ = vorgabenkreis
    antwort = client.get(URL, params={"suche": kennung})
    assert _zeilen(antwort, kennung) == [("Bogen", "allgemein", 5), ("Bogen", "Cello", 4),
                                         ("Steg", "allgemein", 2), ("Steg", "Viola", 3)]
    daten = antwort.json()
    assert daten["treffer"] == 4 and daten["gesamt"] > daten["treffer"]


def test_liste_alle_zeigt_aktiven_vor_archiviertem(client, vorgabenkreis):
    kennung, _, _ = vorgabenkreis
    antwort = client.get(URL, params={"suche": kennung, "status": "alle", "richtung": "ab"})
    assert _zeilen(antwort, kennung) == [("Steg", "allgemein", 2), ("Steg", "Viola", 3), ("Bogen", "allgemein", 5),
                                         ("Bogen", "allgemein", 1), ("Bogen", "Cello", 4)]
    assert antwort.json()["eintraege"][3]["archiviert_am"] is not None


def test_liste_sortierung_filter_und_seiten(client, vorgabenkreis):
    kennung, arten, klassen = vorgabenkreis
    params = {"suche": kennung, "sortierung": "vorgabe_stunden", "richtung": "ab", "seitengroesse": 3}
    seite1, seite2 = (client.get(URL, params={**params, "seite": n}) for n in (1, 2))
    assert [z[2] for z in _zeilen(seite1, kennung) + _zeilen(seite2, kennung)] == [5, 4, 3, 2]
    assert _zeilen(client.get(URL, params={"suche": kennung, "sortierung": "gilt_fuer"}), kennung)[2:] == \
        [("Bogen", "Cello", 4), ("Steg", "Viola", 3)]  # allgemeine zuerst
    assert _zeilen(client.get(URL, params={"reparaturart_id": str(arten["Steg"].id)}), kennung) == \
        [("Steg", "allgemein", 2), ("Steg", "Viola", 3)]
    assert _zeilen(client.get(URL, params={"instrumentenklasse_id": str(klassen["Cello"].id)}), kennung) == \
        [("Bogen", "Cello", 4)]


def test_liste_suche_in_klasse_und_notiz_platzhalter_woertlich(client, vorgabenkreis):
    kennung, _, _ = vorgabenkreis
    assert _zeilen(client.get(URL, params={"suche": f"{kennung} Viola"}), kennung) == [("Steg", "Viola", 3)]
    assert _zeilen(client.get(URL, params={"suche": "5%_Aufschlag"}), kennung) == [("Steg", "allgemein", 2)]
    assert _ids(client.get(URL, params={"suche": f"{kennung} %"})) == []


def test_liste_ungueltige_parameter(client, admin):
    assert client.get(URL, params={"sortierung": "notiz"}).status_code == 422
    assert client.get(URL, params={"status": "geloescht"}).status_code == 422

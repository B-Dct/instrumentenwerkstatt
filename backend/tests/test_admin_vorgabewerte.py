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


# --- Ausführung (2.6a) --------------------------------------------------------------

def _anlegen(client, stammdaten, **extra):
    antwort = client.post(URL, json=neu(stammdaten, instrumentenklasse_id=str(stammdaten["klasse"]), **extra))
    assert antwort.status_code == 201, antwort.json()
    return antwort.json()


def _kombination(client, stammdaten):
    liste = client.get(URL, params={"instrumentenklasse_id": str(stammdaten["klasse"])}).json()["eintraege"]
    return [(e["ausfuehrung"], e["ist_standard"]) for e in liste]


def test_zweite_ausfuehrung_erst_nach_benennen_des_bestehenden_werts(client, stammdaten):
    """Entweder genau ein Wert ohne Ausführung oder mehrere benannte, davon genau einer Standard (2.6a)."""
    klasse = {"instrumentenklasse_id": str(stammdaten["klasse"])}
    einziger = _anlegen(client, stammdaten)
    assert (einziger["ausfuehrung"], einziger["ist_standard"]) == (None, False)

    abgelehnt = client.post(URL, json=neu(stammdaten, **klasse, ausfuehrung="versilbert"))
    assert abgelehnt.status_code == 422 and abgelehnt.json()["detail"][0]["loc"][-1] == "ausfuehrung"
    assert client.post(URL, json=neu(stammdaten, **klasse)).status_code == 409            # ohne Namen gibt es schon

    # Der bestehende Wert bekommt einen Namen und wird dabei zum Standard
    benannt = client.patch(f"{URL}/{einziger['id']}", json={"ausfuehrung": " lackiert "}).json()
    assert (benannt["ausfuehrung"], benannt["ist_standard"]) == ("lackiert", True)
    versilbert = _anlegen(client, stammdaten, ausfuehrung="  versilbert ", vorgabe_kosten=50)
    assert (versilbert["ausfuehrung"], versilbert["ist_standard"]) == ("versilbert", False)

    # Neben benannten Ausführungen braucht jede weitere einen Namen; Doppelte werden abgelehnt
    ohne_namen = client.post(URL, json=neu(stammdaten, **klasse))
    assert ohne_namen.status_code == 422 and ohne_namen.json()["detail"][0]["loc"][-1] == "ausfuehrung"
    doppelt = client.post(URL, json=neu(stammdaten, **klasse, ausfuehrung="versilbert"))
    assert doppelt.status_code == 409 and "Ausführung" in doppelt.json()["detail"]
    _anlegen(client, stammdaten, ausfuehrung="vergoldet")
    # Den Namen wieder entfernen geht nur, solange es der einzige Wert ist
    assert client.patch(f"{URL}/{versilbert['id']}", json={"ausfuehrung": None}).status_code == 422

    # Liste: Standard zuerst, dann alphabetisch; Suche findet die Ausführung
    assert _kombination(client, stammdaten) == [("lackiert", True), ("vergoldet", False), ("versilbert", False)]
    treffer = client.get(URL, params={"suche": "vergoldet", "instrumentenklasse_id": str(stammdaten["klasse"])}).json()
    assert [e["ausfuehrung"] for e in treffer["eintraege"]] == ["vergoldet"]


def test_erste_benannte_ausfuehrung_ist_standard_und_standard_wechseln(client, stammdaten, db):
    lackiert = _anlegen(client, stammdaten, ausfuehrung="lackiert")
    assert lackiert["ist_standard"] is True                                               # einzige benannte
    versilbert = _anlegen(client, stammdaten, ausfuehrung="versilbert")
    # Das Kennzeichen lässt sich nicht einfach entfernen – nur an eine andere Ausführung weitergeben
    weg = client.patch(f"{URL}/{lackiert['id']}", json={"ist_standard": False})
    assert weg.status_code == 422 and weg.json()["detail"][0]["loc"][-1] == "ist_standard"
    assert client.patch(f"{URL}/{versilbert['id']}", json={"ist_standard": True}).json()["ist_standard"] is True
    assert _kombination(client, stammdaten) == [("versilbert", True), ("lackiert", False)]
    # Gleich als Standard anlegen: übernimmt das Kennzeichen
    _anlegen(client, stammdaten, ausfuehrung="vergoldet", ist_standard=True)
    assert _kombination(client, stammdaten) == [("vergoldet", True), ("lackiert", False), ("versilbert", False)]
    # Preis ändern lässt den Standard unberührt
    assert client.patch(f"{URL}/{lackiert['id']}", json={"vorgabe_kosten": 30}).json()["ist_standard"] is False
    assert _kombination(client, stammdaten)[0] == ("vergoldet", True)


def test_standard_archivieren_nur_als_letzter_oder_nach_wechsel(client, stammdaten):
    lackiert = _anlegen(client, stammdaten, ausfuehrung="lackiert")
    versilbert = _anlegen(client, stammdaten, ausfuehrung="versilbert")
    gesperrt = client.post(f"{URL}/{lackiert['id']}/archivieren")
    assert gesperrt.status_code == 409 and "Standard" in gesperrt.json()["detail"]
    assert client.post(f"{URL}/{versilbert['id']}/archivieren").status_code == 200        # kein Standard: geht
    assert client.post(f"{URL}/{lackiert['id']}/archivieren").status_code == 200          # einzige verbleibende: geht

    # Reaktivieren: als einzige wieder Standard, neben einer anderen nicht
    assert client.post(f"{URL}/{versilbert['id']}/reaktivieren").json()["ist_standard"] is True
    assert client.post(f"{URL}/{lackiert['id']}/reaktivieren").json()["ist_standard"] is False
    assert _kombination(client, stammdaten) == [("versilbert", True), ("lackiert", False)]


def test_datenbank_erlaubt_nur_einen_aktiven_standard(db, stammdaten):
    from sqlalchemy.exc import IntegrityError
    from app.models import ReparaturVorgabewert
    for name in ("lackiert", "versilbert"):
        db.add(ReparaturVorgabewert(reparaturart_id=stammdaten["reparaturart"], instrumentenklasse_id=stammdaten["klasse"],
                                    ausfuehrung=name, ist_standard=True, vorgabe_stunden=1, vorgabe_kosten=1))
    with pytest.raises(IntegrityError, match="uq_reparatur_vorgabewert_standard"):
        db.flush()
    db.rollback()


def test_ausfuehrung_nur_mit_instrumentenklasse(client, stammdaten):
    antwort = client.post(URL, json=neu(stammdaten, ausfuehrung="versilbert"))  # allgemeiner Wert + Ausführung
    assert antwort.status_code == 422 and antwort.json()["detail"][0]["loc"][-1] == "ausfuehrung"

    v = _anlegen(client, stammdaten, ausfuehrung="   ")
    assert v["ausfuehrung"] is None
    geaendert = client.patch(f"{URL}/{v['id']}", json={"ausfuehrung": "lackiert"})
    assert geaendert.status_code == 200 and geaendert.json()["ausfuehrung"] == "lackiert"
    # Klasse entfernen, solange eine Ausführung gesetzt ist: abgelehnt
    assert client.patch(f"{URL}/{v['id']}", json={"instrumentenklasse_id": None}).status_code == 422
    allgemein = client.patch(f"{URL}/{v['id']}", json={"instrumentenklasse_id": None, "ausfuehrung": None})
    assert allgemein.status_code == 200 and allgemein.json()["ist_standard"] is False     # allgemeine Werte: kein Standard


def test_reaktivieren_prueft_auch_die_ausfuehrung(client, stammdaten):
    klasse = {"instrumentenklasse_id": str(stammdaten["klasse"])}
    alt = client.post(URL, json=neu(stammdaten, **klasse, ausfuehrung="versilbert")).json()
    client.post(f"{URL}/{alt['id']}/archivieren")
    assert client.post(URL, json=neu(stammdaten, **klasse, ausfuehrung="versilbert")).status_code == 201  # Ersatz
    assert client.post(f"{URL}/{alt['id']}/reaktivieren").status_code == 409
    # Eine andere Ausführung stört nicht
    andere = client.post(URL, json=neu(stammdaten, **klasse, ausfuehrung="lackiert")).json()
    client.post(f"{URL}/{andere['id']}/archivieren")
    assert client.post(f"{URL}/{andere['id']}/reaktivieren").status_code == 200


def test_umbenennen_zieht_instrumente_und_andere_richtpreise_der_klasse_mit(client, stammdaten, db):
    """Eine umbenannte Ausführung darf kein Instrument unbemerkt auf den Standard zurückfallen lassen (2.5)."""
    from app.models import Instrument, Kunde, ReparaturVorgabewert
    andere_art = Reparaturart(bezeichnung="TEST Stimmen", standard_komplexitaet=1)
    andere_klasse = Instrumentenklasse(bezeichnung="TEST Violine", oberkategorie="Streichinstrument")
    kunde = Kunde(kundennummer=f"TEST-{uuid.uuid4().hex[:8]}", name="Test Kunde")
    db.add_all([andere_art, andere_klasse, kunde])
    db.flush()
    _anlegen(client, stammdaten, ausfuehrung="lackiert")
    versilbert = _anlegen(client, stammdaten, ausfuehrung="versilbert")
    db.add(ReparaturVorgabewert(reparaturart_id=andere_art.id, instrumentenklasse_id=stammdaten["klasse"],
                                ausfuehrung="versilbert", ist_standard=True, vorgabe_stunden=1, vorgabe_kosten=1))
    instrumente = {name: Instrument(kunde_id=kunde.id, instrumentenklasse_id=klasse, ausfuehrung=ausfuehrung)
                   for name, klasse, ausfuehrung in [("betroffen", stammdaten["klasse"], "versilbert"),
                                                     ("andere_ausfuehrung", stammdaten["klasse"], "lackiert"),
                                                     ("unbekannt", stammdaten["klasse"], None),
                                                     ("andere_klasse", andere_klasse.id, "versilbert")]}
    db.add_all(instrumente.values())
    db.flush()
    liste = client.get(URL, params={"instrumentenklasse_id": str(stammdaten["klasse"])}).json()["eintraege"]
    assert {e["ausfuehrung"]: e["instrumente_mit_ausfuehrung"] for e in liste
            if e["reparaturart_id"] == str(stammdaten["reparaturart"])} == {"lackiert": 1, "versilbert": 1}

    antwort = client.patch(f"{URL}/{versilbert['id']}", json={"ausfuehrung": "Silber"}).json()
    assert (antwort["ausfuehrung"], antwort["umbenannte_instrumente"], antwort["umbenannte_richtpreise"]) == ("Silber", 1, 1)
    assert antwort["instrumente_mit_ausfuehrung"] == 1
    for i in instrumente.values():
        db.refresh(i)
    assert {n: i.ausfuehrung for n, i in instrumente.items()} == {
        "betroffen": "Silber", "andere_ausfuehrung": "lackiert", "unbekannt": None, "andere_klasse": "versilbert"}
    # Der Richtpreis der anderen Reparaturart derselben Klasse heißt jetzt genauso
    assert db.scalar(select(ReparaturVorgabewert.ausfuehrung).where(
        ReparaturVorgabewert.reparaturart_id == andere_art.id)) == "Silber"
    log = db.scalars(select(SystemEreignisLog).where(SystemEreignisLog.betroffene_id == instrumente["betroffen"].id)).one()
    assert (log.aktion, log.details) == ("instrument_geaendert", {
        "alt": {"ausfuehrung": "versilbert"}, "neu": {"ausfuehrung": "Silber"}, "anlass": "ausfuehrung_umbenannt"})
    # Nur der Preis geändert: nichts wird umbenannt
    assert client.patch(f"{URL}/{versilbert['id']}", json={"vorgabe_kosten": 99}).json()["umbenannte_instrumente"] == 0


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

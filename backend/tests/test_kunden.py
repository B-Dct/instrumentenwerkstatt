"""Kunden und Instrumente: anlegen, bearbeiten, archivieren (2.1, 2.5, 7.2)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Kunde, Systemrolle, SystemEreignisLog
from tests.beispieldaten import Werkstatt
from tests.conftest import angemeldet_als, konto_anlegen


@pytest.fixture
def w(db, client):
    werkstatt = Werkstatt(db)
    client.headers.update(angemeldet_als(werkstatt.mitarbeiter))  # Rolle "mitarbeiter"
    return werkstatt


@pytest.fixture
def leitung(db):
    return angemeldet_als(konto_anlegen(db, Systemrolle.werkstattleiter, name="Leitung"))


def kunde_anlegen(client, **daten):
    antwort = client.post("/kunden", json={"name": "Clara Klang", **daten})
    assert antwort.status_code == 201, antwort.json()
    return antwort.json()


def instrument_anlegen(client, w, kunde_id, **daten):
    antwort = client.post("/instrumente", json={
        "kunde_id": kunde_id, "instrumentenklasse_id": str(w.violine.id), **daten,
    })
    assert antwort.status_code == 201, antwort.json()
    return antwort.json()


# --- Kunden -------------------------------------------------------------------

def test_mitarbeiter_legt_kunde_an_und_bearbeitet(client, w, db):
    k = kunde_anlegen(client, email="clara@example.com", telefon=" 0151 123 ")
    assert k["kundennummer"].startswith("TEST-K-")
    assert k["telefon"] == "0151 123"
    assert k["archiviert_am"] is None and k["instrumente"] == []

    k = client.patch(f"/kunden/{k['id']}", json={"name": "Clara Klang-Meier", "telefon": None}).json()
    assert (k["name"], k["telefon"], k["email"]) == ("Clara Klang-Meier", None, "clara@example.com")

    aktionen = db.scalars(select(SystemEreignisLog.aktion).where(
        SystemEreignisLog.betroffene_id == uuid.UUID(k["id"])).order_by(SystemEreignisLog.zeitpunkt)).all()
    assert aktionen == ["kunde_angelegt", "kunde_geaendert"]


@pytest.mark.parametrize("daten", [{"name": ""}, {"name": "   "}, {"name": "X", "email": "keine-mail"}])
def test_kunde_ungueltige_eingaben(client, w, daten):
    assert client.post("/kunden", json=daten).status_code == 422


def test_kunde_name_nicht_leeren(client, w):
    k = kunde_anlegen(client)
    assert client.patch(f"/kunden/{k['id']}", json={"name": None}).status_code == 422


def test_kundensuche(client, w):
    kunde_anlegen(client, name="Zacharias Zupf", email="zz@example.com")
    treffer = client.get("/kunden", params={"suche": "zupf"}).json()["eintraege"]
    assert [k["name"] for k in treffer] == ["Zacharias Zupf"]
    assert [k["name"] for k in client.get("/kunden", params={"suche": "zz@"}).json()["eintraege"]] == ["Zacharias Zupf"]


def test_mitarbeiter_darf_nicht_archivieren(client, w):
    k = kunde_anlegen(client)
    assert client.post(f"/kunden/{k['id']}/archivieren").status_code == 403


def test_archivieren_loescht_nicht(client, w, leitung, db):
    k = kunde_anlegen(client)
    antwort = client.post(f"/kunden/{k['id']}/archivieren", headers=leitung)
    assert antwort.status_code == 200
    assert antwort.json()["archiviert_am"] is not None

    # Datensatz ist noch da …
    assert db.get(Kunde, uuid.UUID(k["id"])) is not None
    assert client.get(f"/kunden/{k['id']}").status_code == 200
    # … erscheint aber nicht mehr in der Standardliste
    ids = [x["id"] for x in client.get("/kunden", params={"suche": "Clara Klang"}).json()["eintraege"]]
    assert k["id"] not in ids
    archiviert = client.get("/kunden", headers=leitung, params={"status": "archiviert", "suche": "Clara Klang"}).json()
    assert k["id"] in [x["id"] for x in archiviert["eintraege"]]

    # Zurückholen geht
    assert client.post(f"/kunden/{k['id']}/reaktivieren", headers=leitung).json()["archiviert_am"] is None


def test_kunde_mit_offenem_auftrag_nicht_archivierbar(client, w, leitung):
    w.auftrag(status=w.in_bearbeitung)  # offener Auftrag für w.kunde
    antwort = client.post(f"/kunden/{w.kunde.id}/archivieren", headers=leitung)
    assert antwort.status_code == 409
    assert "offene" in antwort.json()["detail"]


def test_archivierter_kunde_nicht_fuer_neue_auftraege(client, w, leitung):
    k = kunde_anlegen(client)
    i = instrument_anlegen(client, w, k["id"])
    client.post(f"/kunden/{k['id']}/archivieren", headers=leitung)
    antwort = client.post("/auftraege", json={
        "kunde_id": k["id"], "instrument_id": i["id"], "reparaturart_id": str(w.saitenwechsel.id),
    })
    assert antwort.status_code == 422
    assert client.post("/instrumente", json={
        "kunde_id": k["id"], "instrumentenklasse_id": str(w.violine.id)}).status_code == 422


# --- Instrumente --------------------------------------------------------------

def test_instrument_anlegen_und_bearbeiten(client, w):
    k = kunde_anlegen(client)
    i = instrument_anlegen(client, w, k["id"], hersteller=" Höfner ", baujahr=1998, seriennummer="S-1")
    assert (i["hersteller"], i["instrumentenklasse_bezeichnung"], i["baujahr"]) == ("Höfner", "TEST Violine", 1998)

    i = client.patch(f"/instrumente/{i['id']}", json={
        "instrumentenklasse_id": str(w.kontrabass.id), "notizen": "Riss am Boden",
    }).json()
    assert (i["instrumentenklasse_bezeichnung"], i["notizen"], i["seriennummer"]) == ("TEST Kontrabass", "Riss am Boden", "S-1")
    assert client.get(f"/instrumente/{i['id']}").json() == i
    assert [x["id"] for x in client.get(f"/kunden/{k['id']}").json()["instrumente"]] == [i["id"]]


@pytest.mark.parametrize("daten", [{"baujahr": 1200}, {"instrumentenklasse_id": None}])
def test_instrument_ungueltig(client, w, daten):
    k = kunde_anlegen(client)
    i = instrument_anlegen(client, w, k["id"])
    assert client.patch(f"/instrumente/{i['id']}", json=daten).status_code == 422


def test_instrument_ausfuehrung(client, w, db):
    """Die Ausführung muss es bei der Klasse als Ausführung eines Richtpreises geben (2.5)."""
    from decimal import Decimal
    from app.models import ReparaturVorgabewert
    for name in ("versilbert", "lackiert"):
        db.add(ReparaturVorgabewert(reparaturart_id=w.saitenwechsel.id, instrumentenklasse_id=w.violine.id, ausfuehrung=name,
                                    vorgabe_stunden=Decimal("1.00"), vorgabe_kosten=Decimal("40.00")))
    db.flush()
    liste = client.get("/instrumentenklassen/ausfuehrungen").json()
    assert liste[str(w.violine.id)] == ["lackiert", "versilbert"] and str(w.kontrabass.id) not in liste

    kunde = kunde_anlegen(client)
    instrument = instrument_anlegen(client, w, kunde["id"], ausfuehrung=" versilbert ")
    assert instrument["ausfuehrung"] == "versilbert"
    unbekannt = client.post("/instrumente", json={"kunde_id": kunde["id"], "instrumentenklasse_id": str(w.violine.id),
                                                  "ausfuehrung": "vergoldet"})
    assert unbekannt.status_code == 422 and unbekannt.json()["detail"][0]["loc"][-1] == "ausfuehrung"

    url = f"/instrumente/{instrument['id']}"
    assert client.patch(url, json={"ausfuehrung": "lackiert"}).json()["ausfuehrung"] == "lackiert"
    assert client.patch(url, json={"hersteller": "Stainer"}).json()["ausfuehrung"] == "lackiert"   # bleibt erhalten
    assert client.patch(url, json={"ausfuehrung": ""}).json()["ausfuehrung"] is None               # leeren
    client.patch(url, json={"ausfuehrung": "lackiert"})
    # Andere Klasse: Die Ausführung gehört zur alten Klasse und wird geleert
    assert client.patch(url, json={"instrumentenklasse_id": str(w.kontrabass.id)}).json()["ausfuehrung"] is None


def test_instrument_archivieren(client, w, leitung):
    k = kunde_anlegen(client)
    i = instrument_anlegen(client, w, k["id"])
    assert client.post(f"/instrumente/{i['id']}/archivieren").status_code == 403  # Mitarbeiter
    assert client.post(f"/instrumente/{i['id']}/archivieren", headers=leitung).status_code == 200
    assert client.get("/instrumente", params={"kunde_id": k["id"]}).json() == []
    alle = client.get("/instrumente", params={"kunde_id": k["id"], "archivierte": True}).json()
    assert alle[0]["archiviert_am"] is not None
    # Im Kundendetail bleibt es (mit Archiv-Kennzeichen) sichtbar
    assert client.get(f"/kunden/{k['id']}").json()["instrumente"][0]["id"] == i["id"]


def test_instrument_mit_offenem_auftrag_nicht_archivierbar(client, w, leitung):
    instrument = w.instrument()
    w.db.flush()
    from app.models import Auftrag
    import secrets
    w.db.add(Auftrag(auftragsnummer=f"T-{secrets.token_hex(4)}", zugriffstoken=secrets.token_hex(6),
                     kunde_id=w.kunde.id, instrument_id=instrument.id, reparaturart_id=w.saitenwechsel.id,
                     komplexitaet=1, status_aktuell_id=w.in_bearbeitung))
    w.db.flush()
    assert client.post(f"/instrumente/{instrument.id}/archivieren", headers=leitung).status_code == 409


def test_instrument_reaktivieren_nur_mit_aktivem_kunden(client, w, leitung):
    k = kunde_anlegen(client)
    i = instrument_anlegen(client, w, k["id"])
    client.post(f"/instrumente/{i['id']}/archivieren", headers=leitung)
    client.post(f"/kunden/{k['id']}/archivieren", headers=leitung)
    assert client.post(f"/instrumente/{i['id']}/reaktivieren", headers=leitung).status_code == 409


def test_nicht_gefunden(client, w):
    assert client.get(f"/kunden/{uuid.uuid4()}").status_code == 404
    assert client.patch(f"/instrumente/{uuid.uuid4()}", json={}).status_code == 404


def test_ohne_anmeldung(client):
    assert client.get("/kunden").status_code == 401
    assert client.post("/kunden", json={"name": "X"}).status_code == 401


# --- Externe Kundennummer (2.1) -------------------------------------------------

def test_mehrere_kunden_ohne_externe_nummer(client, w, db):
    a = kunde_anlegen(client, name="Ohne Nummer A")
    b = kunde_anlegen(client, name="Ohne Nummer B", externe_kundennummer="")
    c = kunde_anlegen(client, name="Ohne Nummer C", externe_kundennummer="   ")
    assert a["externe_kundennummer"] is None and b["externe_kundennummer"] is None and c["externe_kundennummer"] is None
    # Wirklich NULL in der Datenbank, nicht leerer Text
    for k in (a, b, c):
        assert db.get(Kunde, uuid.UUID(k["id"])).externe_kundennummer is None


def test_externe_nummer_wird_getrimmt_und_ist_eindeutig(client, w, leitung):
    erster = kunde_anlegen(client, name="Erster", externe_kundennummer="  BH-4711 ")
    assert erster["externe_kundennummer"] == "BH-4711"

    antwort = client.post("/kunden", json={"name": "Zweiter", "externe_kundennummer": "BH-4711"})
    assert antwort.status_code == 409
    assert antwort.json()["detail"] == f"Diese externe Kundennummer ist bereits vergeben (Kunde {erster['kundennummer']})"

    # Auch beim Bearbeiten, und auch wenn der andere Kunde archiviert ist
    zweiter = kunde_anlegen(client, name="Zweiter")
    client.post(f"/kunden/{erster['id']}/archivieren", headers=leitung)
    antwort = client.patch(f"/kunden/{zweiter['id']}", json={"externe_kundennummer": "BH-4711"})
    assert antwort.status_code == 409
    assert antwort.json()["detail"].endswith(f"(Kunde {erster['kundennummer']}, archiviert)")
    # Abgelehnter Wert wurde nicht übernommen, weitere Änderung klappt
    assert client.get(f"/kunden/{zweiter['id']}").json()["externe_kundennummer"] is None
    assert client.patch(f"/kunden/{zweiter['id']}", json={"externe_kundennummer": "BH-0815"}).status_code == 200


def test_externe_nummer_bearbeiten_und_leeren(client, w, db):
    k = kunde_anlegen(client, externe_kundennummer="BH-1")
    k = client.patch(f"/kunden/{k['id']}", json={"externe_kundennummer": "BH-2"}).json()
    assert k["externe_kundennummer"] == "BH-2"
    # Eigene Nummer erneut speichern ist kein Konflikt
    assert client.patch(f"/kunden/{k['id']}", json={"externe_kundennummer": "BH-2", "name": "Neu"}).status_code == 200
    k = client.patch(f"/kunden/{k['id']}", json={"externe_kundennummer": " "}).json()
    assert k["externe_kundennummer"] is None

    eintraege = db.scalars(select(SystemEreignisLog).where(
        SystemEreignisLog.betroffene_id == uuid.UUID(k["id"]), SystemEreignisLog.aktion == "kunde_geaendert"
    ).order_by(SystemEreignisLog.zeitpunkt)).all()
    assert [(e.details["alt"]["externe_kundennummer"], e.details["neu"]["externe_kundennummer"]) for e in eintraege] \
        == [("BH-1", "BH-2"), ("BH-2", "BH-2"), ("BH-2", None)]


def test_suche_findet_ueber_externe_nummer(client, w):
    kunde_anlegen(client, name="Buchhaltungs-Kunde", externe_kundennummer="FIBU-99231")
    assert [k["name"] for k in client.get("/kunden", params={"suche": "99231"}).json()["eintraege"]] == ["Buchhaltungs-Kunde"]
    assert [k["name"] for k in client.get("/kunden", params={"suche": "fibu-99"}).json()["eintraege"]] == ["Buchhaltungs-Kunde"]


def test_externe_nummer_zu_lang(client, w):
    assert client.post("/kunden", json={"name": "X", "externe_kundennummer": "1" * 51}).status_code == 422


@pytest.mark.parametrize("anlegen", [True, False], ids=["anlegen", "bearbeiten"])
def test_externe_nummer_ohne_gross_kleinschreibung_eindeutig(client, w, anlegen):
    vorhanden = kunde_anlegen(client, name="Groß", externe_kundennummer="FIBU-1")
    if anlegen:
        antwort = client.post("/kunden", json={"name": "Klein", "externe_kundennummer": "fibu-1"})
    else:
        anderer = kunde_anlegen(client, name="Klein")
        antwort = client.patch(f"/kunden/{anderer['id']}", json={"externe_kundennummer": "Fibu-1"})
    assert antwort.status_code == 409
    assert antwort.json()["detail"] == f"Diese externe Kundennummer ist bereits vergeben (Kunde {vorhanden['kundennummer']})"


def test_eigene_nummer_in_anderer_schreibweise_speichern(client, w):
    k = kunde_anlegen(client, externe_kundennummer="FIBU-7")
    antwort = client.patch(f"/kunden/{k['id']}", json={"externe_kundennummer": "fibu-7"})
    assert antwort.status_code == 200
    assert antwort.json()["externe_kundennummer"] == "fibu-7"  # Schreibweise wird wie eingegeben gespeichert



# --- Kundenliste nach 9.11 -------------------------------------------------------

@pytest.fixture
def kundenkreis(client, w, leitung):
    """Eigene Test-Kunden mit eindeutiger Kennung, damit echte Daten nicht stören."""
    kennung = f"KL{uuid.uuid4().hex[:6]}"
    kunden = {n: kunde_anlegen(client, name=f"{kennung} {n}", externe_kundennummer=f"{kennung}-{i}")
              for i, n in enumerate(["Berta", "Anton", "Carla 50%_Rabatt"])}
    archiviert = kunde_anlegen(client, name=f"{kennung} Dieter")
    client.post(f"/kunden/{archiviert['id']}/archivieren", headers=leitung)
    return kennung, kunden


def _namen(antwort):
    return [k["name"].split(" ", 1)[1] for k in antwort.json()["eintraege"]]


def test_kundenliste_standard_aktiv_nach_name_mit_trefferzahl(client, kundenkreis):
    kennung, _ = kundenkreis
    antwort = client.get("/kunden", params={"suche": kennung})
    assert _namen(antwort) == ["Anton", "Berta", "Carla 50%_Rabatt"]
    daten = antwort.json()
    assert daten["treffer"] == 3 and daten["gesamt"] > daten["treffer"]  # Suche + "nur aktive" blenden aus


def test_kundenliste_status_filter_nur_fuer_leitung(client, kundenkreis, leitung):
    kennung, _ = kundenkreis
    for status in ("archiviert", "alle"):
        assert client.get("/kunden", params={"suche": kennung, "status": status}).status_code == 403  # Mitarbeiter
    assert _namen(client.get("/kunden", headers=leitung, params={"suche": kennung, "status": "archiviert"})) == ["Dieter"]
    assert len(_namen(client.get("/kunden", headers=leitung, params={"suche": kennung, "status": "alle"}))) == 4


def test_kundenliste_sortierung_und_seiten(client, kundenkreis):
    kennung, _ = kundenkreis
    params = {"suche": kennung, "sortierung": "externe_kundennummer", "richtung": "ab", "seitengroesse": 2}
    seite1, seite2 = (client.get("/kunden", params={**params, "seite": n}).json() for n in (1, 2))
    namen = [k["name"].split(" ", 1)[1] for k in seite1["eintraege"] + seite2["eintraege"]]
    assert namen == ["Carla 50%_Rabatt", "Anton", "Berta"]  # -2, -1, -0 absteigend
    assert (seite1["treffer"], seite1["seitengroesse"]) == (3, 2)


def test_kundenliste_platzhalter_woertlich(client, kundenkreis):
    kennung, _ = kundenkreis
    assert _namen(client.get("/kunden", params={"suche": "50%_Rabatt"})) == ["Carla 50%_Rabatt"]
    assert _namen(client.get("/kunden", params={"suche": f"{kennung} %"})) == []


def test_kundenliste_ungueltige_sortierung(client, w):
    assert client.get("/kunden", params={"sortierung": "archiviert_am"}).status_code == 422

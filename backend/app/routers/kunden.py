"""Kunden (2.1) und Instrumente (2.5): auflisten, anlegen, bearbeiten, archivieren.

Berechtigungen (7.2):
- Auflisten, Anlegen, Bearbeiten: alle angemeldeten Mitarbeiter (gehört zur Auftragsannahme)
- Archivieren und Reaktivieren: Werkstattleitung und Admin

Archivieren entfernt nichts: Es setzt nur archiviert_am. Archivierte Einträge erscheinen
standardmäßig nicht mehr in Listen und können nicht für neue Aufträge verwendet werden,
bleiben aber für bestehende Aufträge und die Historie vollständig erhalten.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter, aktueller_mitarbeiter_id, rolle_mindestens
from app.db import get_db
from app.ereignisse import protokollieren, werte
from app.speichern import sicher_speichern
from app.models import Auftrag, Auftragsstatus, Instrument, Instrumentenklasse, Kunde, Systemrolle
from app.schemas import (
    InstrumentAenderung,
    InstrumentKurz,
    InstrumentNeu,
    KundeAenderung,
    KundeDetail,
    KundeEintrag,
    KundeNeu,
)

router = APIRouter(tags=["Kunden und Instrumente"], dependencies=[Depends(aktueller_mitarbeiter)])
nur_leitung = Depends(rolle_mindestens(Systemrolle.werkstattleiter))

KUNDE_FELDER = ["name", "externe_kundennummer", "email", "telefon"]
INSTRUMENT_FELDER = ["instrumentenklasse_id", "hersteller", "typenbezeichnung", "baujahr", "seriennummer", "notizen"]


def _externe_nummer_vergeben(db: Session, nummer: str | None, eigene_id: uuid.UUID | None = None):
    """Meldung für den Konfliktfall, die den Kunden nennt, der die Nummer schon hat."""
    def meldung() -> str | None:
        if nummer is None:
            return None
        # Wie der Datenbank-Index: ohne Beachtung der Groß-/Kleinschreibung
        anderer = db.scalar(select(Kunde).where(
            func.lower(Kunde.externe_kundennummer) == nummer.lower(), Kunde.id != eigene_id))
        if anderer is None:
            return None
        archiviert = ", archiviert" if anderer.archiviert_am else ""
        return f"Diese externe Kundennummer ist bereits vergeben (Kunde {anderer.kundennummer}{archiviert})"
    return {"uq_kunde_externe_kundennummer": meldung}


def _neue_kundennummer(db: Session) -> str:
    return f"K-{db.execute(text("SELECT nextval('kundennummer_seq')")).scalar_one():05d}"


def _offene_auftraege(db: Session, *bedingung) -> int:
    return db.scalar(
        select(func.count()).select_from(Auftrag)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(Auftragsstatus.ist_abgeschlossen.is_(False), *bedingung)
    )


def _jetzt(db: Session) -> datetime:
    return db.scalar(select(func.clock_timestamp()))


# --- Kunden -------------------------------------------------------------------

def _kunde_laden(db: Session, kunde_id: uuid.UUID) -> Kunde:
    kunde = db.get(Kunde, kunde_id)
    if kunde is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kunde nicht gefunden")
    return kunde


def _kunde_detail(db: Session, kunde: Kunde) -> KundeDetail:
    return KundeDetail(
        **KundeEintrag.model_validate(kunde).model_dump(),
        instrumente=_instrumente(db, kunde_id=kunde.id, archivierte=True),
    )


@router.get("/kunden", response_model=list[KundeEintrag])
def kunden_auflisten(
    suche: str | None = Query(None, description="Teil von Name, Kundennummer, externer Kundennummer, E-Mail oder Telefon"),
    archivierte: bool = Query(False, description="Auch archivierte Kunden anzeigen"),
    db: Session = Depends(get_db),
) -> list[Kunde]:
    abfrage = select(Kunde).order_by(Kunde.name, Kunde.kundennummer)
    if not archivierte:
        abfrage = abfrage.where(Kunde.archiviert_am.is_(None))
    if suche:
        muster = f"%{suche.strip()}%"
        abfrage = abfrage.where(
            Kunde.name.ilike(muster) | Kunde.kundennummer.ilike(muster)
            | Kunde.externe_kundennummer.ilike(muster)
            | Kunde.email.ilike(muster) | Kunde.telefon.ilike(muster)
        )
    return list(db.scalars(abfrage))


@router.get("/kunden/{kunde_id}", response_model=KundeDetail)
def kunde_abrufen(kunde_id: uuid.UUID, db: Session = Depends(get_db)) -> KundeDetail:
    return _kunde_detail(db, _kunde_laden(db, kunde_id))


@router.post("/kunden", response_model=KundeDetail, status_code=status.HTTP_201_CREATED)
def kunde_anlegen(
    daten: KundeNeu, db: Session = Depends(get_db), mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> KundeDetail:
    kunde = Kunde(kundennummer=_neue_kundennummer(db), **daten.model_dump())
    with sicher_speichern(db, _externe_nummer_vergeben(db, kunde.externe_kundennummer)):
        db.add(kunde)
    protokollieren(db, mitarbeiter_id, "kunde_angelegt", "kunde", kunde.id, {"neu": werte(kunde, KUNDE_FELDER)})
    db.commit()
    return _kunde_detail(db, kunde)


@router.patch("/kunden/{kunde_id}", response_model=KundeDetail)
def kunde_bearbeiten(
    kunde_id: uuid.UUID, daten: KundeAenderung,
    db: Session = Depends(get_db), mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> KundeDetail:
    kunde = _kunde_laden(db, kunde_id)
    aenderungen = daten.model_dump(exclude_unset=True)
    if "name" in aenderungen and aenderungen["name"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Name darf nicht leer sein")
    alt = werte(kunde, KUNDE_FELDER)
    neu = {**alt, **werte(daten, list(aenderungen))}
    if neu != alt:
        meldungen = _externe_nummer_vergeben(db, aenderungen.get("externe_kundennummer"), kunde.id)
        with sicher_speichern(db, meldungen):
            for feld, wert in aenderungen.items():
                setattr(kunde, feld, wert)
        protokollieren(db, mitarbeiter_id, "kunde_geaendert", "kunde", kunde.id, {"alt": alt, "neu": neu})
        db.commit()
    return _kunde_detail(db, kunde)


@router.post("/kunden/{kunde_id}/archivieren", response_model=KundeDetail, dependencies=[nur_leitung])
def kunde_archivieren(
    kunde_id: uuid.UUID, db: Session = Depends(get_db), mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> KundeDetail:
    kunde = _kunde_laden(db, kunde_id)
    if kunde.archiviert_am is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Kunde ist bereits archiviert")
    offen = _offene_auftraege(db, Auftrag.kunde_id == kunde.id)
    if offen:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Kunde hat noch {offen} offene(n) Auftrag/Aufträge – erst abschließen, dann archivieren")
    kunde.archiviert_am = _jetzt(db)
    protokollieren(db, mitarbeiter_id, "kunde_archiviert", "kunde", kunde.id)
    db.commit()
    return _kunde_detail(db, kunde)


@router.post("/kunden/{kunde_id}/reaktivieren", response_model=KundeDetail, dependencies=[nur_leitung])
def kunde_reaktivieren(
    kunde_id: uuid.UUID, db: Session = Depends(get_db), mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> KundeDetail:
    kunde = _kunde_laden(db, kunde_id)
    if kunde.archiviert_am is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Kunde ist nicht archiviert")
    kunde.archiviert_am = None
    protokollieren(db, mitarbeiter_id, "kunde_reaktiviert", "kunde", kunde.id)
    db.commit()
    return _kunde_detail(db, kunde)


# --- Instrumente --------------------------------------------------------------

def _instrumente(db: Session, kunde_id: uuid.UUID | None = None, archivierte: bool = False,
                 instrument_id: uuid.UUID | None = None) -> list[InstrumentKurz]:
    abfrage = (
        select(Instrument, Instrumentenklasse.bezeichnung)
        .join(Instrumentenklasse, Instrument.instrumentenklasse_id == Instrumentenklasse.id)
        .order_by(Instrumentenklasse.bezeichnung, Instrument.hersteller, Instrument.typenbezeichnung)
    )
    if kunde_id is not None:
        abfrage = abfrage.where(Instrument.kunde_id == kunde_id)
    if instrument_id is not None:
        abfrage = abfrage.where(Instrument.id == instrument_id)
    if not archivierte:
        abfrage = abfrage.where(Instrument.archiviert_am.is_(None))
    return [
        InstrumentKurz(
            id=i.id, kunde_id=i.kunde_id, instrumentenklasse_id=i.instrumentenklasse_id,
            instrumentenklasse_bezeichnung=klasse, hersteller=i.hersteller, typenbezeichnung=i.typenbezeichnung,
            baujahr=i.baujahr, seriennummer=i.seriennummer, notizen=i.notizen, archiviert_am=i.archiviert_am,
        )
        for i, klasse in db.execute(abfrage).all()
    ]


def _instrument_laden(db: Session, instrument_id: uuid.UUID) -> Instrument:
    instrument = db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instrument nicht gefunden")
    return instrument


def _instrument_antwort(db: Session, instrument: Instrument) -> InstrumentKurz:
    return _instrumente(db, instrument_id=instrument.id, archivierte=True)[0]


def _klasse_pruefen(db: Session, klasse_id: uuid.UUID) -> None:
    klasse = db.get(Instrumentenklasse, klasse_id)
    if klasse is None or klasse.archiviert_am is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Instrumentenklasse existiert nicht oder ist archiviert")


@router.get("/instrumente", response_model=list[InstrumentKurz])
def instrumente_auflisten(
    kunde_id: uuid.UUID | None = Query(None, description="Nur Instrumente dieses Kunden"),
    archivierte: bool = Query(False, description="Auch archivierte Instrumente anzeigen"),
    db: Session = Depends(get_db),
) -> list[InstrumentKurz]:
    return _instrumente(db, kunde_id=kunde_id, archivierte=archivierte)


@router.get("/instrumente/{instrument_id}", response_model=InstrumentKurz)
def instrument_abrufen(instrument_id: uuid.UUID, db: Session = Depends(get_db)) -> InstrumentKurz:
    return _instrument_antwort(db, _instrument_laden(db, instrument_id))


@router.post("/instrumente", response_model=InstrumentKurz, status_code=status.HTTP_201_CREATED)
def instrument_anlegen(
    daten: InstrumentNeu, db: Session = Depends(get_db), mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> InstrumentKurz:
    kunde = db.get(Kunde, daten.kunde_id)
    if kunde is None or kunde.archiviert_am is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Kunde existiert nicht oder ist archiviert")
    _klasse_pruefen(db, daten.instrumentenklasse_id)
    instrument = Instrument(**daten.model_dump())
    db.add(instrument)
    db.flush()
    protokollieren(db, mitarbeiter_id, "instrument_angelegt", "instrument", instrument.id,
                   {"kunde_id": str(kunde.id), "neu": werte(instrument, INSTRUMENT_FELDER)})
    db.commit()
    return _instrument_antwort(db, instrument)


@router.patch("/instrumente/{instrument_id}", response_model=InstrumentKurz)
def instrument_bearbeiten(
    instrument_id: uuid.UUID, daten: InstrumentAenderung,
    db: Session = Depends(get_db), mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> InstrumentKurz:
    instrument = _instrument_laden(db, instrument_id)
    aenderungen = daten.model_dump(exclude_unset=True)
    if "instrumentenklasse_id" in aenderungen:
        if aenderungen["instrumentenklasse_id"] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Instrumentenklasse darf nicht leer sein")
        if aenderungen["instrumentenklasse_id"] != instrument.instrumentenklasse_id:
            _klasse_pruefen(db, aenderungen["instrumentenklasse_id"])
    alt = werte(instrument, INSTRUMENT_FELDER)
    for feld, wert in aenderungen.items():
        setattr(instrument, feld, wert)
    neu = werte(instrument, INSTRUMENT_FELDER)
    if neu != alt:
        protokollieren(db, mitarbeiter_id, "instrument_geaendert", "instrument", instrument.id, {"alt": alt, "neu": neu})
        db.commit()
    return _instrument_antwort(db, instrument)


@router.post("/instrumente/{instrument_id}/archivieren", response_model=InstrumentKurz, dependencies=[nur_leitung])
def instrument_archivieren(
    instrument_id: uuid.UUID, db: Session = Depends(get_db), mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> InstrumentKurz:
    instrument = _instrument_laden(db, instrument_id)
    if instrument.archiviert_am is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Instrument ist bereits archiviert")
    offen = _offene_auftraege(db, Auftrag.instrument_id == instrument.id)
    if offen:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Instrument hat noch {offen} offene(n) Auftrag/Aufträge – erst abschließen, dann archivieren")
    instrument.archiviert_am = _jetzt(db)
    protokollieren(db, mitarbeiter_id, "instrument_archiviert", "instrument", instrument.id)
    db.commit()
    return _instrument_antwort(db, instrument)


@router.post("/instrumente/{instrument_id}/reaktivieren", response_model=InstrumentKurz, dependencies=[nur_leitung])
def instrument_reaktivieren(
    instrument_id: uuid.UUID, db: Session = Depends(get_db), mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> InstrumentKurz:
    instrument = _instrument_laden(db, instrument_id)
    if instrument.archiviert_am is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Instrument ist nicht archiviert")
    kunde = db.get(Kunde, instrument.kunde_id)
    if kunde.archiviert_am is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Kunde ist archiviert – zuerst den Kunden reaktivieren")
    instrument.archiviert_am = None
    protokollieren(db, mitarbeiter_id, "instrument_reaktiviert", "instrument", instrument.id)
    db.commit()
    return _instrument_antwort(db, instrument)

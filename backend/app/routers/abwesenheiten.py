"""Abwesenheiten pflegen (Datenmodell 2.3) – nur Werkstattleitung und Admin (7.2).

Urlaub, Krankheit, Schulung und reduzierte Stunden gehören zu einem Mitarbeiter; Feiertag und
Betriebsschließung gelten für die ganze Werkstatt (mitarbeiter_id = NULL). Die Terminschätzung
(app/terminschaetzung.py) überspringt diese Tage bzw. rechnet mit den reduzierten Stunden.

Kein Löschen: Eine falsch eingetragene oder abgesagte Abwesenheit wird storniert (storniert_am)
und zählt dann nicht mehr; sie lässt sich wiederherstellen. Bereits berechnete Termine offener
Aufträge werden bei Änderungen NICHT automatisch neu berechnet (4.0a) – dafür gibt es
`app.termine_nachrechnen --alle`.
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id, rolle_mindestens
from app.db import get_db
from app.eingabe import feldfehler
from app.ereignisse import protokollieren, werte
from app.listen import ListenParameter, Seite, enthaelt, listen_parameter, seite_abfragen
from app.models import Abwesenheit, Abwesenheitstyp, Mitarbeiter, Systemrolle
from app.schemas import AbwesenheitAenderung, AbwesenheitEintrag, AbwesenheitNeu

router = APIRouter(prefix="/abwesenheiten", tags=["Abwesenheiten"],
                   dependencies=[Depends(rolle_mindestens(Systemrolle.werkstattleiter))])

FELDER = ["mitarbeiter_id", "typ", "von_datum", "bis_datum", "reduzierte_stunden"]
# Diese Typen gelten für die ganze Werkstatt, alle anderen für genau einen Mitarbeiter
BETRIEBSWEIT = {Abwesenheitstyp.feiertag, Abwesenheitstyp.betriebsschliessung}


def _abfrage() -> Select:
    return select(Abwesenheit, Mitarbeiter.name).outerjoin(Mitarbeiter, Abwesenheit.mitarbeiter_id == Mitarbeiter.id)


def _antwort(zeile) -> AbwesenheitEintrag:
    a, name = zeile
    return AbwesenheitEintrag(
        id=a.id, mitarbeiter_id=a.mitarbeiter_id, mitarbeiter_name=name, typ=a.typ,
        von_datum=a.von_datum, bis_datum=a.bis_datum, reduzierte_stunden=a.reduzierte_stunden,
        storniert_am=a.storniert_am,
    )


def _eintrag(db: Session, abwesenheit_id: uuid.UUID) -> AbwesenheitEintrag:
    return _antwort(db.execute(_abfrage().where(Abwesenheit.id == abwesenheit_id)).one())


def _laden(db: Session, abwesenheit_id: uuid.UUID) -> Abwesenheit:
    abwesenheit = db.get(Abwesenheit, abwesenheit_id, with_for_update=True)
    if abwesenheit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Abwesenheit nicht gefunden")
    return abwesenheit


def _entwurf(abwesenheit: Abwesenheit, **aenderungen) -> Abwesenheit:
    """Kopie mit den neuen Werten, die nicht in der Sitzung liegt (nur zum Prüfen)."""
    return Abwesenheit(id=abwesenheit.id, **{**{f: getattr(abwesenheit, f) for f in FELDER}, **aenderungen})


def _pruefen(db: Session, a: Abwesenheit, mitarbeiter_neu_gewaehlt: bool) -> None:
    """Fachliche Regeln für den (neuen) Stand einer Abwesenheit. `a` ist dabei immer ein Entwurf,
    der noch nicht in der Sitzung liegt – so bleibt nach einer Ablehnung nichts Halbes zurück."""
    if a.bis_datum < a.von_datum:
        raise feldfehler(bis_datum="Das Ende liegt vor dem Beginn")
    if a.typ in BETRIEBSWEIT:
        if a.mitarbeiter_id is not None:
            raise feldfehler(mitarbeiter_id="Feiertag und Betriebsschließung gelten für die ganze Werkstatt")
    elif a.mitarbeiter_id is None:
        raise feldfehler(mitarbeiter_id="Bitte einen Mitarbeiter wählen")
    elif mitarbeiter_neu_gewaehlt:
        m = db.get(Mitarbeiter, a.mitarbeiter_id)
        if m is None or not m.aktiv:
            raise feldfehler(mitarbeiter_id="Mitarbeiter existiert nicht oder ist deaktiviert")
    if a.typ == Abwesenheitstyp.reduzierte_stunden:
        if a.reduzierte_stunden is None:
            raise feldfehler(reduzierte_stunden="Bitte die verfügbaren Wochenstunden angeben")
    elif a.reduzierte_stunden is not None:
        raise feldfehler(reduzierte_stunden="Nur beim Typ „Reduzierte Stunden“ möglich")

    # Schutz gegen versehentliche Doppeleinträge: gleicher Typ, gleiche Person, überschneidender Zeitraum
    wer = Abwesenheit.mitarbeiter_id.is_(None) if a.mitarbeiter_id is None else Abwesenheit.mitarbeiter_id == a.mitarbeiter_id
    doppelt = db.scalar(select(Abwesenheit).where(
        wer, Abwesenheit.typ == a.typ, Abwesenheit.storniert_am.is_(None), Abwesenheit.id != a.id,
        Abwesenheit.von_datum <= a.bis_datum, Abwesenheit.bis_datum >= a.von_datum,
    ).limit(1))
    if doppelt is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Überschneidet sich mit einem vorhandenen Eintrag gleichen Typs "
            f"({doppelt.von_datum:%d.%m.%Y} – {doppelt.bis_datum:%d.%m.%Y}). Diesen bearbeiten oder stornieren.",
        )


SORTIERUNG = {
    "von_datum": (Abwesenheit.von_datum, Abwesenheit.bis_datum),
    "bis_datum": (Abwesenheit.bis_datum, Abwesenheit.von_datum),
    # Betriebsweite Einträge (ohne Mitarbeiter) zuerst
    "mitarbeiter": (func.coalesce(Mitarbeiter.name, ""), Abwesenheit.von_datum),
    "typ": (Abwesenheit.typ, Abwesenheit.von_datum),
}


@router.get("", response_model=Seite[AbwesenheitEintrag])
def abwesenheiten_auflisten(
    liste: ListenParameter = Depends(listen_parameter(SORTIERUNG, standard="von_datum")),
    mitarbeiter: Literal["werkstatt"] | uuid.UUID | None = Query(
        None, description="ID eines Mitarbeiters oder 'werkstatt' für betriebsweite Einträge"),
    typ: Abwesenheitstyp | None = Query(None),
    zeitraum: Literal["ab_heute", "vergangen", "alle"] = Query(
        "ab_heute", description="ab_heute = laufende und künftige (Standard), vergangen = bereits beendete"),
    status_: Literal["aktiv", "storniert", "alle"] = Query("aktiv", alias="status"),
    db: Session = Depends(get_db),
) -> Seite[AbwesenheitEintrag]:
    """Liste nach 9.11. Suche über den Namen des Mitarbeiters. Standard: laufende und künftige,
    nicht stornierte Abwesenheiten, die nächste zuerst."""
    basis = _abfrage()
    gefiltert = basis
    if (muster := liste.suchmuster()) is not None:
        gefiltert = gefiltert.where(enthaelt(muster, Mitarbeiter.name))
    if mitarbeiter == "werkstatt":
        gefiltert = gefiltert.where(Abwesenheit.mitarbeiter_id.is_(None))
    elif mitarbeiter is not None:
        gefiltert = gefiltert.where(Abwesenheit.mitarbeiter_id == mitarbeiter)
    if typ is not None:
        gefiltert = gefiltert.where(Abwesenheit.typ == typ)
    if zeitraum == "ab_heute":
        gefiltert = gefiltert.where(Abwesenheit.bis_datum >= date.today())
    elif zeitraum == "vergangen":
        gefiltert = gefiltert.where(Abwesenheit.bis_datum < date.today())
    if status_ == "aktiv":
        gefiltert = gefiltert.where(Abwesenheit.storniert_am.is_(None))
    elif status_ == "storniert":
        gefiltert = gefiltert.where(Abwesenheit.storniert_am.is_not(None))
    return seite_abfragen(db, basis, gefiltert, liste, SORTIERUNG, umwandeln=_antwort, eindeutig=Abwesenheit.id)


@router.post("", response_model=AbwesenheitEintrag, status_code=status.HTTP_201_CREATED)
def abwesenheit_anlegen(
    daten: AbwesenheitNeu,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> AbwesenheitEintrag:
    abwesenheit = Abwesenheit(id=uuid.uuid4(), **daten.model_dump())
    _pruefen(db, abwesenheit, mitarbeiter_neu_gewaehlt=True)
    db.add(abwesenheit)
    db.flush()
    protokollieren(db, mitarbeiter_id, "abwesenheit_angelegt", "abwesenheit", abwesenheit.id,
                   {"neu": werte(abwesenheit, FELDER)})
    db.commit()
    return _eintrag(db, abwesenheit.id)


@router.patch("/{abwesenheit_id}", response_model=AbwesenheitEintrag)
def abwesenheit_bearbeiten(
    abwesenheit_id: uuid.UUID,
    daten: AbwesenheitAenderung,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> AbwesenheitEintrag:
    abwesenheit = _laden(db, abwesenheit_id)
    if abwesenheit.storniert_am is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Stornierte Abwesenheit – zum Bearbeiten zuerst wiederherstellen")
    aenderungen = daten.model_dump(exclude_unset=True)
    leer = [f for f in ("typ", "von_datum", "bis_datum") if f in aenderungen and aenderungen[f] is None]
    if leer:
        raise feldfehler(**{f: "Pflichtfeld" for f in leer})
    alt = werte(abwesenheit, FELDER)
    entwurf = _entwurf(abwesenheit, **aenderungen)
    neu = werte(entwurf, FELDER)
    if neu != alt:
        # Erst den Entwurf prüfen, dann schreiben
        _pruefen(db, entwurf, mitarbeiter_neu_gewaehlt=entwurf.mitarbeiter_id != abwesenheit.mitarbeiter_id)
        for feld, wert in aenderungen.items():
            setattr(abwesenheit, feld, wert)
        protokollieren(db, mitarbeiter_id, "abwesenheit_geaendert", "abwesenheit", abwesenheit.id,
                       {"alt": alt, "neu": neu})
        db.commit()
    return _eintrag(db, abwesenheit.id)


def _storno_setzen(db: Session, abwesenheit_id: uuid.UUID, mitarbeiter_id: uuid.UUID, stornieren: bool) -> AbwesenheitEintrag:
    abwesenheit = _laden(db, abwesenheit_id)
    if (abwesenheit.storniert_am is not None) == stornieren:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Abwesenheit ist {'bereits' if stornieren else 'nicht'} storniert")
    if stornieren:
        abwesenheit.storniert_am = db.scalar(select(func.clock_timestamp()))
    else:
        _pruefen(db, _entwurf(abwesenheit), mitarbeiter_neu_gewaehlt=False)  # inzwischen ein Doppeleintrag?
        abwesenheit.storniert_am = None
    protokollieren(db, mitarbeiter_id, f"abwesenheit_{'storniert' if stornieren else 'wiederhergestellt'}",
                   "abwesenheit", abwesenheit.id)
    db.commit()
    return _eintrag(db, abwesenheit.id)


@router.post("/{abwesenheit_id}/stornieren", response_model=AbwesenheitEintrag)
def abwesenheit_stornieren(abwesenheit_id: uuid.UUID, db: Session = Depends(get_db),
                           mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)) -> AbwesenheitEintrag:
    return _storno_setzen(db, abwesenheit_id, mitarbeiter_id, stornieren=True)


@router.post("/{abwesenheit_id}/wiederherstellen", response_model=AbwesenheitEintrag)
def abwesenheit_wiederherstellen(abwesenheit_id: uuid.UUID, db: Session = Depends(get_db),
                                 mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)) -> AbwesenheitEintrag:
    return _storno_setzen(db, abwesenheit_id, mitarbeiter_id, stornieren=False)

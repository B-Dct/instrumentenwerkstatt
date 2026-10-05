"""Ausführungen je Instrumentenklasse pflegen (Datenmodell 2.4b) – nur Admin (7.2).

Eine Ausführung (z. B. "Perinet, versilbert") gehört zur Instrumentenklasse, nicht zur einzelnen
Reparaturart: Richtpreise und Instrumente verweisen auf sie. Umbenennen, Standard und Archivieren
geschehen deshalb genau hier, einmal – alles, was auf die Ausführung verweist, folgt automatisch.

Regeln:
- Hat eine Klasse Ausführungen, ist genau eine aktive der Standard. Die erste Ausführung einer Klasse
  wird Standard; ihr werden die vorhandenen (bisher unbenannten) Richtpreise der Klasse zugeordnet.
- Das Standard-Kennzeichen lässt sich nicht entfernen, nur an eine andere Ausführung weitergeben.
- Der Standard lässt sich nur archivieren, wenn er die letzte aktive Ausführung ist.
- Kein hartes Löschen: Richtpreise einer archivierten Ausführung ignoriert die Schätzung, Instrumente
  behalten den Verweis und gelten bei der Schätzung als "unbekannt".
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id
from app.db import get_db
from app.eingabe import feldfehler
from app.ereignisse import protokollieren, werte
from app.models import Ausfuehrung, Instrument, Instrumentenklasse, ReparaturVorgabewert
from app.schemas import AusfuehrungAenderung, AusfuehrungEintrag, AusfuehrungNeu
from app.speichern import sicher_speichern

router = APIRouter(prefix="/ausfuehrungen", tags=["Admin: Ausführungen"])

FELDER = ["instrumentenklasse_id", "bezeichnung", "ist_standard"]

# Was eine Ausführung verwendet: aktive Instrumente und aktive Richtpreise (Anzeige vor dem Archivieren)
_INSTRUMENTE = (select(func.count()).select_from(Instrument)
                .where(Instrument.ausfuehrung_id == Ausfuehrung.id, Instrument.archiviert_am.is_(None))
                .correlate(Ausfuehrung).scalar_subquery())
_RICHTPREISE = (select(func.count()).select_from(ReparaturVorgabewert)
                .where(ReparaturVorgabewert.ausfuehrung_id == Ausfuehrung.id, ReparaturVorgabewert.archiviert_am.is_(None))
                .correlate(Ausfuehrung).scalar_subquery())


def _eintraege(db: Session, *bedingungen) -> list[AusfuehrungEintrag]:
    """Aktive zuerst, darin der Standard zuerst, dann alphabetisch."""
    zeilen = db.execute(
        select(Ausfuehrung, _INSTRUMENTE, _RICHTPREISE).where(*bedingungen)
        .order_by(Ausfuehrung.archiviert_am.is_not(None), Ausfuehrung.ist_standard.desc(), func.lower(Ausfuehrung.bezeichnung))
    ).all()
    return [AusfuehrungEintrag(
        id=a.id, instrumentenklasse_id=a.instrumentenklasse_id, bezeichnung=a.bezeichnung,
        ist_standard=a.ist_standard and a.archiviert_am is None, archiviert_am=a.archiviert_am,
        instrumente=instrumente, richtpreise=richtpreise,
    ) for a, instrumente, richtpreise in zeilen]


def _antwort(db: Session, ausfuehrung: Ausfuehrung) -> AusfuehrungEintrag:
    return _eintraege(db, Ausfuehrung.id == ausfuehrung.id)[0]


def _laden(db: Session, ausfuehrung_id: uuid.UUID) -> Ausfuehrung:
    ausfuehrung = db.get(Ausfuehrung, ausfuehrung_id, with_for_update=True)
    if ausfuehrung is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ausführung nicht gefunden")
    return ausfuehrung


def _andere_aktive(db: Session, klasse_id: uuid.UUID, ausser: uuid.UUID | None = None) -> list[Ausfuehrung]:
    """Die übrigen aktiven Ausführungen der Klasse (gesperrt, damit sich der Standard nicht nebenher ändert)."""
    abfrage = select(Ausfuehrung).where(Ausfuehrung.instrumentenklasse_id == klasse_id,
                                        Ausfuehrung.archiviert_am.is_(None)).with_for_update()
    if ausser is not None:
        abfrage = abfrage.where(Ausfuehrung.id != ausser)
    return list(db.scalars(abfrage))


def _standard_abgeben(db: Session, andere: list[Ausfuehrung]) -> None:
    """Der bisherige Standard verliert das Kennzeichen – vor dem Speichern des neuen (Datenbank-Index)."""
    for a in andere:
        a.ist_standard = False
    db.flush()


def _unbenannte_richtpreise_zuordnen(db: Session, standard: Ausfuehrung) -> int:
    """Die aktiven Richtpreise der Klasse ohne Ausführung gehören ab jetzt zur Standardausführung (2.4b)."""
    return db.execute(
        update(ReparaturVorgabewert).where(
            ReparaturVorgabewert.instrumentenklasse_id == standard.instrumentenklasse_id,
            ReparaturVorgabewert.ausfuehrung_id.is_(None), ReparaturVorgabewert.archiviert_am.is_(None),
        ).values(ausfuehrung_id=standard.id)
    ).rowcount


@router.get("", response_model=list[AusfuehrungEintrag])
def ausfuehrungen_auflisten(
    instrumentenklasse_id: uuid.UUID | None = Query(None, description="Nur Ausführungen dieser Instrumentenklasse"),
    status_: Literal["aktiv", "archiviert", "alle"] = Query("aktiv", alias="status"),
    db: Session = Depends(get_db),
) -> list[AusfuehrungEintrag]:
    """Ausführungen samt der Zahl der Instrumente und Richtpreise, die sie verwenden."""
    bedingungen = []
    if instrumentenklasse_id is not None:
        bedingungen.append(Ausfuehrung.instrumentenklasse_id == instrumentenklasse_id)
    if status_ == "aktiv":
        bedingungen.append(Ausfuehrung.archiviert_am.is_(None))
    elif status_ == "archiviert":
        bedingungen.append(Ausfuehrung.archiviert_am.is_not(None))
    return _eintraege(db, *bedingungen)


@router.post("", response_model=AusfuehrungEintrag, status_code=status.HTTP_201_CREATED)
def ausfuehrung_anlegen(daten: AusfuehrungNeu, db: Session = Depends(get_db),
                        mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)) -> AusfuehrungEintrag:
    """Die erste Ausführung einer Klasse ist ihre Standardausführung: Sie übernimmt die vorhandenen
    Richtpreise der Klasse. Erst danach lassen sich weitere anlegen."""
    klasse = db.get(Instrumentenklasse, daten.instrumentenklasse_id)
    if klasse is None or klasse.archiviert_am is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Instrumentenklasse existiert nicht oder ist archiviert")
    ausfuehrung = Ausfuehrung(instrumentenklasse_id=klasse.id, bezeichnung=daten.bezeichnung)
    zugeordnet = 0
    with sicher_speichern(db):
        andere = _andere_aktive(db, klasse.id)
        ausfuehrung.ist_standard = daten.ist_standard or not andere
        if ausfuehrung.ist_standard:
            _standard_abgeben(db, andere)
        db.add(ausfuehrung)
        db.flush()
        if not andere:
            zugeordnet = _unbenannte_richtpreise_zuordnen(db, ausfuehrung)
    protokollieren(db, mitarbeiter_id, "ausfuehrung_angelegt", "ausfuehrung", ausfuehrung.id,
                   {"neu": werte(ausfuehrung, FELDER), "zugeordnete_richtpreise": zugeordnet})
    db.commit()
    return _antwort(db, ausfuehrung)


@router.patch("/{ausfuehrung_id}", response_model=AusfuehrungEintrag)
def ausfuehrung_bearbeiten(ausfuehrung_id: uuid.UUID, daten: AusfuehrungAenderung, db: Session = Depends(get_db),
                           mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)) -> AusfuehrungEintrag:
    """Umbenennen und Standard bestimmen. Richtpreise und Instrumente verweisen auf die Ausführung und
    folgen automatisch – es wird nichts mitumbenannt."""
    ausfuehrung = _laden(db, ausfuehrung_id)
    if ausfuehrung.archiviert_am is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ausführung ist archiviert – zum Bearbeiten erst reaktivieren")
    aenderungen = daten.model_dump(exclude_unset=True)
    if "bezeichnung" in aenderungen and aenderungen["bezeichnung"] is None:
        raise feldfehler(bezeichnung="Pflichtfeld")
    alt = werte(ausfuehrung, FELDER)
    with sicher_speichern(db):
        gewuenscht = aenderungen.get("ist_standard")
        if gewuenscht is False and ausfuehrung.ist_standard:
            raise feldfehler(ist_standard="Genau eine Ausführung ist Standard – bitte stattdessen eine andere zum Standard machen")
        if gewuenscht and not ausfuehrung.ist_standard:
            _standard_abgeben(db, _andere_aktive(db, ausfuehrung.instrumentenklasse_id, ausser=ausfuehrung.id))
            ausfuehrung.ist_standard = True
        if aenderungen.get("bezeichnung") is not None:
            ausfuehrung.bezeichnung = aenderungen["bezeichnung"]
    neu = werte(ausfuehrung, FELDER)
    if neu != alt:
        protokollieren(db, mitarbeiter_id, "ausfuehrung_geaendert", "ausfuehrung", ausfuehrung.id, {"alt": alt, "neu": neu})
        db.commit()
    return _antwort(db, ausfuehrung)


@router.post("/{ausfuehrung_id}/archivieren", response_model=AusfuehrungEintrag)
def ausfuehrung_archivieren(ausfuehrung_id: uuid.UUID, db: Session = Depends(get_db),
                            mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)) -> AusfuehrungEintrag:
    """Ihre Richtpreise ignoriert die Schätzung danach; Instrumente behalten den Verweis und gelten als "unbekannt"."""
    ausfuehrung = _laden(db, ausfuehrung_id)
    if ausfuehrung.archiviert_am is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ausführung ist bereits archiviert")
    if ausfuehrung.ist_standard and _andere_aktive(db, ausfuehrung.instrumentenklasse_id, ausser=ausfuehrung.id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Das ist die Standardausführung – bitte zuerst eine andere Ausführung zum Standard machen")
    vorher = _antwort(db, ausfuehrung)
    with sicher_speichern(db):
        ausfuehrung.archiviert_am = db.scalar(select(func.clock_timestamp()))
    protokollieren(db, mitarbeiter_id, "ausfuehrung_archiviert", "ausfuehrung", ausfuehrung.id,
                   {"bezeichnung": ausfuehrung.bezeichnung, "instrumente": vorher.instrumente, "richtpreise": vorher.richtpreise})
    db.commit()
    return _antwort(db, ausfuehrung)


@router.post("/{ausfuehrung_id}/reaktivieren", response_model=AusfuehrungEintrag)
def ausfuehrung_reaktivieren(ausfuehrung_id: uuid.UUID, db: Session = Depends(get_db),
                             mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)) -> AusfuehrungEintrag:
    """Als einzige aktive Ausführung der Klasse wird sie wieder Standard, neben anderen nicht."""
    ausfuehrung = _laden(db, ausfuehrung_id)
    if ausfuehrung.archiviert_am is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ausführung ist nicht archiviert")
    with sicher_speichern(db):
        andere = _andere_aktive(db, ausfuehrung.instrumentenklasse_id, ausser=ausfuehrung.id)
        ausfuehrung.ist_standard = not andere
        ausfuehrung.archiviert_am = None
        db.flush()
        if not andere:
            # Inzwischen ohne Ausführung angelegte Richtpreise der Klasse gehören wieder zum Standard –
            # außer er hat für dieselbe Reparaturart schon einen eigenen aktiven Wert
            doppelt = db.scalar(select(func.count()).select_from(ReparaturVorgabewert).where(
                ReparaturVorgabewert.instrumentenklasse_id == ausfuehrung.instrumentenklasse_id,
                ReparaturVorgabewert.ausfuehrung_id.is_(None), ReparaturVorgabewert.archiviert_am.is_(None),
                ReparaturVorgabewert.reparaturart_id.in_(select(ReparaturVorgabewert.reparaturart_id).where(
                    ReparaturVorgabewert.ausfuehrung_id == ausfuehrung.id, ReparaturVorgabewert.archiviert_am.is_(None))),
            ))
            if doppelt:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "Für diese Instrumentenklasse gibt es inzwischen Richtpreise ohne Ausführung, die sich mit "
                                    "denen dieser Ausführung überschneiden – bitte zuerst in der Preisliste bereinigen")
            _unbenannte_richtpreise_zuordnen(db, ausfuehrung)
    protokollieren(db, mitarbeiter_id, "ausfuehrung_reaktiviert", "ausfuehrung", ausfuehrung.id,
                   {"bezeichnung": ausfuehrung.bezeichnung})
    db.commit()
    return _antwort(db, ausfuehrung)

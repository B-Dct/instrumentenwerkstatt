"""Stammdaten: Instrumentenklassen (2.4) und Reparaturarten (2.6) – nur Admin (7.2).

Der Admin-Router (routers/admin/__init__.py) prüft die Rolle für alle Endpunkte hier.
Archivieren entfernt nichts (archiviert_am); archivierte Einträge stehen für neue
Instrumente, Aufträge und Vorgabewerte nicht mehr zur Auswahl, bestehende bleiben gültig.
"""

import uuid
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id
from app.db import get_db
from app.ereignisse import protokollieren, werte
from app.speichern import sicher_speichern
from app.models import Instrumentenklasse, Reparaturart
from app.schemas import (
    InstrumentenklasseAenderung,
    InstrumentenklasseEintrag,
    InstrumentenklasseNeu,
    ReparaturartAenderung,
    ReparaturartEintrag,
    ReparaturartNeu,
)

router = APIRouter(tags=["Admin: Stammdaten"])

M = TypeVar("M", Instrumentenklasse, Reparaturart)


# --- Gemeinsame Abläufe ----------------------------------------------------------

def _laden(db: Session, modell: type[M], eintrag_id: uuid.UUID, name: str) -> M:
    eintrag = db.get(modell, eintrag_id)
    if eintrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{name} nicht gefunden")
    return eintrag


def _auflisten(db: Session, modell, archivierte: bool, *sortierung):
    abfrage = select(modell).order_by(*sortierung)
    if not archivierte:
        abfrage = abfrage.where(modell.archiviert_am.is_(None))
    return list(db.scalars(abfrage))


def _anlegen(db: Session, modell, daten, felder, entitaet, name, mitarbeiter_id):
    eintrag = modell(**daten.model_dump())
    with sicher_speichern(db):
        db.add(eintrag)
    protokollieren(db, mitarbeiter_id, f"{entitaet}_angelegt", entitaet, eintrag.id, {"neu": werte(eintrag, felder)})
    db.commit()
    return eintrag


def _bearbeiten(db: Session, eintrag, daten, felder, entitaet, name, mitarbeiter_id):
    aenderungen = daten.model_dump(exclude_unset=True)
    leer = [f for f, w in aenderungen.items() if w is None]
    if leer:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Darf nicht leer sein: {', '.join(leer)}")
    alt = werte(eintrag, felder)
    neu = {**alt, **werte(daten, list(aenderungen))}
    if neu != alt:
        with sicher_speichern(db):
            for feld, wert in aenderungen.items():
                setattr(eintrag, feld, wert)
        protokollieren(db, mitarbeiter_id, f"{entitaet}_geaendert", entitaet, eintrag.id, {"alt": alt, "neu": neu})
        db.commit()
    return eintrag


def _archivieren(db: Session, eintrag, entitaet, name, mitarbeiter_id, archivieren: bool):
    if (eintrag.archiviert_am is not None) == archivieren:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{name} ist {'bereits' if archivieren else 'nicht'} archiviert")
    zeitpunkt = db.scalar(select(func.clock_timestamp())) if archivieren else None
    with sicher_speichern(db):
        eintrag.archiviert_am = zeitpunkt
    protokollieren(db, mitarbeiter_id, f"{entitaet}_{'archiviert' if archivieren else 'reaktiviert'}",
                   entitaet, eintrag.id)
    db.commit()
    return eintrag


# --- Instrumentenklassen ------------------------------------------------------------

KLASSE, KLASSE_FELDER = "Instrumentenklasse", ["bezeichnung", "oberkategorie"]


@router.get("/instrumentenklassen", response_model=list[InstrumentenklasseEintrag])
def klassen_auflisten(archivierte: bool = Query(False), db: Session = Depends(get_db)):
    return _auflisten(db, Instrumentenklasse, archivierte, Instrumentenklasse.oberkategorie, Instrumentenklasse.bezeichnung)


@router.post("/instrumentenklassen", response_model=InstrumentenklasseEintrag, status_code=status.HTTP_201_CREATED)
def klasse_anlegen(daten: InstrumentenklasseNeu, db: Session = Depends(get_db),
                   mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)):
    return _anlegen(db, Instrumentenklasse, daten, KLASSE_FELDER, "instrumentenklasse", KLASSE, mitarbeiter_id)


@router.patch("/instrumentenklassen/{klasse_id}", response_model=InstrumentenklasseEintrag)
def klasse_bearbeiten(klasse_id: uuid.UUID, daten: InstrumentenklasseAenderung, db: Session = Depends(get_db),
                      mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)):
    eintrag = _laden(db, Instrumentenklasse, klasse_id, KLASSE)
    return _bearbeiten(db, eintrag, daten, KLASSE_FELDER, "instrumentenklasse", KLASSE, mitarbeiter_id)


@router.post("/instrumentenklassen/{klasse_id}/archivieren", response_model=InstrumentenklasseEintrag)
def klasse_archivieren(klasse_id: uuid.UUID, db: Session = Depends(get_db),
                       mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)):
    eintrag = _laden(db, Instrumentenklasse, klasse_id, KLASSE)
    return _archivieren(db, eintrag, "instrumentenklasse", KLASSE, mitarbeiter_id, archivieren=True)


@router.post("/instrumentenklassen/{klasse_id}/reaktivieren", response_model=InstrumentenklasseEintrag)
def klasse_reaktivieren(klasse_id: uuid.UUID, db: Session = Depends(get_db),
                        mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)):
    eintrag = _laden(db, Instrumentenklasse, klasse_id, KLASSE)
    return _archivieren(db, eintrag, "instrumentenklasse", KLASSE, mitarbeiter_id, archivieren=False)


# --- Reparaturarten -----------------------------------------------------------------

ART, ART_FELDER = "Reparaturart", ["bezeichnung", "standard_komplexitaet"]


@router.get("/reparaturarten", response_model=list[ReparaturartEintrag])
def arten_auflisten(archivierte: bool = Query(False), db: Session = Depends(get_db)):
    return _auflisten(db, Reparaturart, archivierte, Reparaturart.bezeichnung)


@router.post("/reparaturarten", response_model=ReparaturartEintrag, status_code=status.HTTP_201_CREATED)
def art_anlegen(daten: ReparaturartNeu, db: Session = Depends(get_db),
                mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)):
    return _anlegen(db, Reparaturart, daten, ART_FELDER, "reparaturart", ART, mitarbeiter_id)


@router.patch("/reparaturarten/{art_id}", response_model=ReparaturartEintrag)
def art_bearbeiten(art_id: uuid.UUID, daten: ReparaturartAenderung, db: Session = Depends(get_db),
                   mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)):
    eintrag = _laden(db, Reparaturart, art_id, ART)
    return _bearbeiten(db, eintrag, daten, ART_FELDER, "reparaturart", ART, mitarbeiter_id)


@router.post("/reparaturarten/{art_id}/archivieren", response_model=ReparaturartEintrag)
def art_archivieren(art_id: uuid.UUID, db: Session = Depends(get_db),
                    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)):
    eintrag = _laden(db, Reparaturart, art_id, ART)
    return _archivieren(db, eintrag, "reparaturart", ART, mitarbeiter_id, archivieren=True)


@router.post("/reparaturarten/{art_id}/reaktivieren", response_model=ReparaturartEintrag)
def art_reaktivieren(art_id: uuid.UUID, db: Session = Depends(get_db),
                     mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id)):
    eintrag = _laden(db, Reparaturart, art_id, ART)
    return _archivieren(db, eintrag, "reparaturart", ART, mitarbeiter_id, archivieren=False)

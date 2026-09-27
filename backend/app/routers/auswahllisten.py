"""Einfache Lese-Endpunkte für Auswahllisten (z. B. im Formular "Auftrag anlegen").

Nur Auflisten – Anlegen/Bearbeiten dieser Daten kommt später. Alle angemeldeten
Mitarbeiter dürfen lesen. Archivierte/deaktivierte Einträge werden nicht angezeigt.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter
from app.db import get_db
from app.models import Auftragsstatus, Instrument, Instrumentenklasse, Kunde, Mitarbeiter, Reparaturart
from app.schemas import InstrumentKurz, KundeKurz, MitarbeiterKurz, ReparaturartKurz, StatusEintrag

router = APIRouter(tags=["Auswahllisten"], dependencies=[Depends(aktueller_mitarbeiter)])


@router.get("/kunden", response_model=list[KundeKurz])
def kunden_auflisten(db: Session = Depends(get_db)) -> list[Kunde]:
    return list(db.scalars(select(Kunde).order_by(Kunde.name)))


@router.get("/instrumente", response_model=list[InstrumentKurz])
def instrumente_auflisten(
    kunde_id: uuid.UUID | None = Query(None, description="Nur Instrumente dieses Kunden"),
    db: Session = Depends(get_db),
) -> list[InstrumentKurz]:
    abfrage = (
        select(Instrument, Instrumentenklasse.bezeichnung)
        .join(Instrumentenklasse, Instrument.instrumentenklasse_id == Instrumentenklasse.id)
        .order_by(Instrumentenklasse.bezeichnung, Instrument.hersteller, Instrument.typenbezeichnung)
    )
    if kunde_id is not None:
        abfrage = abfrage.where(Instrument.kunde_id == kunde_id)
    return [
        InstrumentKurz(
            id=i.id, kunde_id=i.kunde_id, instrumentenklasse_id=i.instrumentenklasse_id,
            instrumentenklasse_bezeichnung=klasse, hersteller=i.hersteller,
            typenbezeichnung=i.typenbezeichnung, seriennummer=i.seriennummer,
        )
        for i, klasse in db.execute(abfrage).all()
    ]


@router.get("/reparaturarten", response_model=list[ReparaturartKurz])
def reparaturarten_auflisten(db: Session = Depends(get_db)) -> list[Reparaturart]:
    return list(db.scalars(select(Reparaturart).where(Reparaturart.aktiv).order_by(Reparaturart.bezeichnung)))


@router.get("/auftragsstatus", response_model=list[StatusEintrag])
def status_auflisten(db: Session = Depends(get_db)) -> list[Auftragsstatus]:
    return list(db.scalars(select(Auftragsstatus).where(Auftragsstatus.aktiv).order_by(Auftragsstatus.reihenfolge)))


@router.get("/mitarbeiter", response_model=list[MitarbeiterKurz])
def mitarbeiter_auflisten(db: Session = Depends(get_db)) -> list[Mitarbeiter]:
    """Aktive Mitarbeiter (für die Zuweisung). Bewusst ohne E-Mail/Rolle – nur Name."""
    return list(db.scalars(select(Mitarbeiter).where(Mitarbeiter.aktiv).order_by(Mitarbeiter.name)))

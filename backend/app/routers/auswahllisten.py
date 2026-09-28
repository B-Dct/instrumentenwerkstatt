"""Einfache Lese-Endpunkte für Auswahllisten (z. B. im Formular "Auftrag anlegen").
Kunden und Instrumente: siehe routers/kunden.py.

Nur Auflisten – Anlegen/Bearbeiten dieser Daten kommt später. Alle angemeldeten
Mitarbeiter dürfen lesen. Archivierte/deaktivierte Einträge werden nicht angezeigt.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter
from app.db import get_db
from app.models import Auftragsstatus, Mitarbeiter, Reparaturart
from app.schemas import MitarbeiterKurz, ReparaturartKurz, StatusEintrag

router = APIRouter(tags=["Auswahllisten"], dependencies=[Depends(aktueller_mitarbeiter)])


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

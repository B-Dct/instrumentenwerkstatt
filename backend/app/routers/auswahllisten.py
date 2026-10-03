"""Einfache Lese-Endpunkte für Auswahllisten (z. B. im Formular "Auftrag anlegen").
Kunden und Instrumente: siehe routers/kunden.py.

Nur Auflisten – Anlegen/Bearbeiten dieser Daten kommt später. Alle angemeldeten
Mitarbeiter dürfen lesen. Archivierte/deaktivierte Einträge werden nicht angezeigt.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter
from app.db import get_db
from app.models import Auftragsstatus, Instrumentenklasse, Mitarbeiter, Reparaturart
from app.schaetzung import ausfuehrungen
from app.schemas import AusfuehrungAuswahl, InstrumentenklasseEintrag, MitarbeiterKurz, ReparaturartKurz, StatusEintrag

router = APIRouter(tags=["Auswahllisten"], dependencies=[Depends(aktueller_mitarbeiter)])


@router.get("/instrumentenklassen", response_model=list[InstrumentenklasseEintrag])
def instrumentenklassen_auflisten(db: Session = Depends(get_db)) -> list[Instrumentenklasse]:
    return list(db.scalars(select(Instrumentenklasse).where(Instrumentenklasse.archiviert_am.is_(None))
                           .order_by(Instrumentenklasse.oberkategorie, Instrumentenklasse.bezeichnung)))


@router.get("/reparaturarten", response_model=list[ReparaturartKurz])
def reparaturarten_auflisten(db: Session = Depends(get_db)) -> list[Reparaturart]:
    return list(db.scalars(select(Reparaturart).where(Reparaturart.archiviert_am.is_(None)).order_by(Reparaturart.bezeichnung)))


@router.get("/ausfuehrungen", response_model=list[AusfuehrungAuswahl])
def ausfuehrungen_auflisten(
    reparaturart_id: uuid.UUID = Query(), instrumentenklasse_id: uuid.UUID = Query(), db: Session = Depends(get_db),
) -> list[AusfuehrungAuswahl]:
    """Wählbare Ausführungen für Reparaturart + Instrumentenklasse (2.6a). Das Auftragsformular
    zeigt die Auswahl nur, wenn es mehr als einen Eintrag gibt; None ist die Standardausführung."""
    return [AusfuehrungAuswahl(ausfuehrung=v.ausfuehrung, vorgabe_stunden=v.vorgabe_stunden, vorgabe_kosten=v.vorgabe_kosten)
            for v in ausfuehrungen(db, reparaturart_id, instrumentenklasse_id)]


@router.get("/auftragsstatus", response_model=list[StatusEintrag])
def status_auflisten(db: Session = Depends(get_db)) -> list[Auftragsstatus]:
    return list(db.scalars(select(Auftragsstatus).where(Auftragsstatus.aktiv).order_by(Auftragsstatus.reihenfolge)))


@router.get("/mitarbeiter", response_model=list[MitarbeiterKurz])
def mitarbeiter_auflisten(db: Session = Depends(get_db)) -> list[Mitarbeiter]:
    """Aktive Mitarbeiter (für die Zuweisung). Bewusst ohne E-Mail/Rolle – nur Name."""
    return list(db.scalars(select(Mitarbeiter).where(Mitarbeiter.aktiv).order_by(Mitarbeiter.name)))

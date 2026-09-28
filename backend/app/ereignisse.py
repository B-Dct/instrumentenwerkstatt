"""Protokoll für Verwaltungsänderungen (system_ereignis_log, Datenmodell 7.3)."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import SystemEreignisLog


def _json(wert):
    if isinstance(wert, (uuid.UUID, Decimal)):
        return str(wert)
    if isinstance(wert, (date, datetime)):
        return wert.isoformat()
    if hasattr(wert, "value"):  # Enum
        return wert.value
    return wert


def werte(objekt, felder: list[str]) -> dict:
    """Ausgewählte Felder eines Datensatzes als JSON-taugliches Dict (für alt/neu)."""
    return {f: _json(getattr(objekt, f)) for f in felder}


def protokollieren(
    db: Session, mitarbeiter_id: uuid.UUID | None, aktion: str, entitaet: str,
    betroffene_id: uuid.UUID, details: dict | None = None,
) -> None:
    db.add(SystemEreignisLog(
        ausgefuehrt_von_mitarbeiter_id=mitarbeiter_id,
        aktion=aktion,
        betroffene_entitaet=entitaet,
        betroffene_id=betroffene_id,
        details=details,
    ))

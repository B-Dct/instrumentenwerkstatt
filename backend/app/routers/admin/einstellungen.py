"""Werkstatt-Einstellungen lesen und setzen (Datenmodell 7.5) – nur Admin (über den Admin-Router).

Erlaubte Schlüssel und Werte stehen in app/einstellungen.py; Änderungen landen im
Änderungsprotokoll (7.3).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id
from app.db import get_db
from app.eingabe import feldfehler
from app.einstellungen import EINSTELLUNGEN
from app.ereignisse import protokollieren
from app.models import Einstellung, Mitarbeiter
from app.schemas import EinstellungEintrag, EinstellungWert
from app.speichern import sicher_speichern

router = APIRouter(prefix="/einstellungen", tags=["Admin: Einstellungen"])


def _eintrag(db: Session, schluessel: str) -> EinstellungEintrag:
    definition = EINSTELLUNGEN[schluessel]
    zeile = db.execute(
        select(Einstellung, Mitarbeiter.name)
        .outerjoin(Mitarbeiter, Einstellung.geaendert_von_mitarbeiter_id == Mitarbeiter.id)
        .where(Einstellung.schluessel == schluessel)
    ).one_or_none()
    gespeichert, name = zeile if zeile else (None, None)
    return EinstellungEintrag(
        schluessel=schluessel, bezeichnung=definition.bezeichnung, beschreibung=definition.beschreibung,
        optionen=list(definition.optionen), wert=gespeichert.wert if gespeichert else None,
        geaendert_von_name=name, geaendert_am=gespeichert.geaendert_am if gespeichert else None,
    )


@router.get("", response_model=list[EinstellungEintrag])
def einstellungen_auflisten(db: Session = Depends(get_db)) -> list[EinstellungEintrag]:
    """Alle bekannten Einstellungen, auch noch nicht festgelegte (wert = null)."""
    return [_eintrag(db, schluessel) for schluessel in EINSTELLUNGEN]


@router.put("/{schluessel}", response_model=EinstellungEintrag)
def einstellung_setzen(
    schluessel: str,
    daten: EinstellungWert,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> EinstellungEintrag:
    definition = EINSTELLUNGEN.get(schluessel)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Diese Einstellung gibt es nicht")
    if daten.wert not in definition.optionen:
        raise feldfehler(wert="Bitte einen Wert aus der Auswahl wählen")

    gespeichert = db.scalar(select(Einstellung).where(Einstellung.schluessel == schluessel).with_for_update())
    alt = gespeichert.wert if gespeichert else None
    if alt != daten.wert:
        with sicher_speichern(db):
            if gespeichert is None:
                gespeichert = Einstellung(schluessel=schluessel, wert=daten.wert)
                db.add(gespeichert)
            gespeichert.wert = daten.wert
            gespeichert.geaendert_von_mitarbeiter_id = mitarbeiter_id
            gespeichert.geaendert_am = func.clock_timestamp()
        protokollieren(db, mitarbeiter_id, "einstellung_geaendert", "einstellung", gespeichert.id,
                       {"schluessel": schluessel, "alt": alt, "neu": daten.wert})
        db.commit()
    return _eintrag(db, schluessel)

"""Feiertage erzeugen (Datenmodell 9.13.1) – Admin-Aktion "Feiertage für Jahr X erzeugen".

Legt nur fehlende Feiertage an und überschreibt nichts (Regeln in app/feiertage.py).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id
from app.db import get_db
from app.eingabe import feldfehler
from app.einstellungen import wert
from app.feiertage import BundeslandFehlt, Ergebnis, erzeugte_jahre, feiertage_erzeugen
from app.schemas import FeiertageErgebnis, FeiertageJahr, FeiertageNeu, FeiertageStand, FeiertagTag

router = APIRouter(prefix="/feiertage", tags=["Admin: Feiertage"])

JAHRE_ZURUECK, JAHRE_VORAUS = 1, 5


def _tage(tage: list[tuple[date, str]]) -> list[FeiertagTag]:
    return [FeiertagTag(datum=tag, name=name) for tag, name in tage]


def _antwort(e: Ergebnis) -> FeiertageErgebnis:
    return FeiertageErgebnis(jahr=e.jahr, bundesland=e.bundesland, angelegt=_tage(e.angelegt), uebersprungen=_tage(e.uebersprungen))


@router.get("", response_model=FeiertageStand)
def feiertage_stand(db: Session = Depends(get_db)) -> FeiertageStand:
    """Für welche Jahre schon Feiertage erzeugt wurden (und mit welchem Bundesland)."""
    jahr = date.today().year
    return FeiertageStand(
        bundesland=wert(db, "bundesland"),
        jahr_von=jahr - JAHRE_ZURUECK, jahr_bis=jahr + JAHRE_VORAUS,
        jahre=[
            FeiertageJahr(jahr=j, bundesland=laeufe[0].details["bundesland"], erzeugt_am=laeufe[0].zeitpunkt,
                          anzahl=sum(len(lauf.details["angelegt"]) for lauf in laeufe))
            for j, laeufe in sorted(erzeugte_jahre(db).items())
        ],
    )


@router.post("", response_model=FeiertageErgebnis)
def feiertage_fuer_jahr_erzeugen(
    daten: FeiertageNeu,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> FeiertageErgebnis:
    heute = date.today().year
    if not heute - JAHRE_ZURUECK <= daten.jahr <= heute + JAHRE_VORAUS:
        raise feldfehler(jahr=f"Bitte ein Jahr zwischen {heute - JAHRE_ZURUECK} und {heute + JAHRE_VORAUS} wählen")
    try:
        ergebnis = feiertage_erzeugen(db, daten.jahr, mitarbeiter_id)
    except BundeslandFehlt:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bitte zuerst das Bundesland in den Einstellungen festlegen") from None
    db.commit()
    return _antwort(ergebnis)

"""Werkstattleiter-Startseite (Datenmodell 9.5) – nur Werkstattleitung und Admin (7.2).

Die Kennzahlen zählen genau das, was die Auftragsliste mit dem jeweiligen Filter zeigt
(gleiche Regeln wie in routers/auftraege.py), damit Kachel und Liste nie voneinander abweichen.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import rolle_mindestens
from app.db import get_db
from app.models import Auftrag, Auftragsstatus, Prioritaet, Systemrolle
from app.routers.auftraege import ist_pausiert, ist_ueberfaellig
from app.schemas import Dashboard, DashboardKennzahlen

router = APIRouter(prefix="/dashboard", tags=["Dashboard"],
                   dependencies=[Depends(rolle_mindestens(Systemrolle.werkstattleiter))])


def _kennzahlen(db: Session) -> DashboardKennzahlen:
    offen = Auftragsstatus.ist_abgeschlossen.is_(False)
    zeile = db.execute(
        select(
            func.count().filter(offen),
            func.count().filter(ist_ueberfaellig()),
            func.count().filter(offen, Auftrag.prioritaet == Prioritaet.hoch),
            func.count().filter(offen, ist_pausiert()),
        ).select_from(Auftrag).join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
    ).one()
    return DashboardKennzahlen(offen=zeile[0], ueberfaellig=zeile[1], priorisiert=zeile[2], pausiert=zeile[3])


@router.get("", response_model=Dashboard)
def dashboard(db: Session = Depends(get_db)) -> Dashboard:
    return Dashboard(kennzahlen=_kennzahlen(db))

"""Werkstattleiter-Startseite (Datenmodell 9.5) – nur Werkstattleitung und Admin (7.2).

Die Kennzahlen zählen genau das, was die Auftragsliste mit dem jeweiligen Filter zeigt
(gleiche Regeln wie in routers/auftraege.py), damit Kachel und Liste nie voneinander abweichen.
"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import rolle_mindestens
from app.db import get_db
from app.models import Auftrag, Auftragsstatus, Mitarbeiter, Prioritaet, Systemrolle
from app.routers.auftraege import _kurz_felder, _listen_abfrage, ist_pausiert, ist_ueberfaellig
from app.schemas import AuftragKurz, Auslastung, Dashboard, DashboardKennzahlen
from app.terminschaetzung import ARBEITSTAGE_PRO_WOCHE, _kalender

NAECHSTE_FAELLIGE = 5

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


def _naechste_faellige(db: Session) -> list[AuftragKurz]:
    """Die offenen Aufträge mit dem nächstgelegenen Termin – überfällige stehen damit ganz vorn."""
    zeilen = db.execute(
        _listen_abfrage()
        .where(Auftragsstatus.ist_abgeschlossen.is_(False), Auftrag.geschaetztes_fertigstellungsdatum.is_not(None))
        .order_by(Auftrag.geschaetztes_fertigstellungsdatum, Auftrag.prioritaet.desc(), Auftrag.erstellt_am, Auftrag.id)
        .limit(NAECHSTE_FAELLIGE)
    ).all()
    return [AuftragKurz(**_kurz_felder(z)) for z in zeilen]


def _auslastung(db: Session, heute: date) -> list[Auslastung]:
    """Auslastung je aktivem Mitarbeiter in der laufenden Woche (Formel aus 8.2):
    gebunden = Abwesenheitsstunden der Woche + geschätzte Stunden aller zugewiesenen offenen Aufträge."""
    montag = heute - timedelta(days=heute.weekday())
    arbeitstage = [montag + timedelta(days=n) for n in range(ARBEITSTAGE_PRO_WOCHE)]
    auftraege = {
        mitarbeiter_id: (anzahl, stunden)
        for mitarbeiter_id, anzahl, stunden in db.execute(
            select(Auftrag.zugewiesener_mitarbeiter_id, func.count(),
                   func.coalesce(func.sum(Auftrag.geschaetzte_arbeitsstunden), 0))
            .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
            .where(Auftragsstatus.ist_abgeschlossen.is_(False), Auftrag.zugewiesener_mitarbeiter_id.is_not(None))
            .group_by(Auftrag.zugewiesener_mitarbeiter_id)
        )
    }
    ergebnis = []
    for m in db.scalars(select(Mitarbeiter).where(Mitarbeiter.aktiv).order_by(Mitarbeiter.name, Mitarbeiter.id)):
        # Derselbe Kalender wie in der Terminschätzung: Wochenstunden (sonst Standard) und Abwesenheiten
        kalender = _kalender(db, m.id, montag)
        wochenstunden = sum((kalender._wochenstunden_am(tag) for tag in arbeitstage), Decimal(0)) / ARBEITSTAGE_PRO_WOCHE
        anwesend = sum((kalender.stunden_am(tag) for tag in arbeitstage), Decimal(0))
        abwesend = wochenstunden - anwesend
        anzahl, auftragsstunden = auftraege.get(m.id, (0, Decimal(0)))
        gebunden = abwesend + auftragsstunden
        ergebnis.append(Auslastung(
            mitarbeiter_id=m.id, name=m.name, wochenstunden=wochenstunden, abwesenheitsstunden=abwesend,
            auftragsstunden=auftragsstunden, offene_auftraege=anzahl, freie_stunden=wochenstunden - gebunden,
            auslastung_prozent=round(gebunden / wochenstunden * 100) if wochenstunden else 0,
        ))
    return ergebnis


@router.get("", response_model=Dashboard)
def dashboard(db: Session = Depends(get_db)) -> Dashboard:
    heute = date.today()
    return Dashboard(
        kennzahlen=_kennzahlen(db),
        naechste_faellige=_naechste_faellige(db),
        woche_von=heute - timedelta(days=heute.weekday()),
        auslastung=_auslastung(db, heute),
    )

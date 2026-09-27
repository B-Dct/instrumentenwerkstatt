"""Stufe-1-Schätzung von Arbeitsaufwand und Kosten (Datenmodell Abschnitte 4 und 4.1).

Reine Berechnung: liest nur aus der Datenbank, speichert nichts und ist (noch)
nicht mit Auftragserstellung oder Statuswechsel verbunden.

Vorgehen für eine Kombination aus Instrumentenklasse + Reparaturart:
1. Mindestens MINDESTANZAHL_VERGLEICHSFAELLE passende, abgeschlossene Aufträge
   mit Ist-Wert vorhanden → historischer Durchschnitt.
2. Sonst Vorgabewert (reparatur_vorgabewert): erst der spezifische Wert für die
   Instrumentenklasse, sonst der allgemeine Wert der Reparaturart.
3. Sonst: keine Schätzung möglich (wert = None).
"""

import enum
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    Arbeitszeiterfassung,
    Auftrag,
    Auftragsstatus,
    Instrument,
    ReparaturVorgabewert,
)

# Ab so vielen abgeschlossenen Vergleichsaufträgen gilt der historische Durchschnitt
# (Datenmodell Abschnitt 4: "sobald z. B. 5 abgeschlossene Vergleichsfälle vorliegen").
# Später ggf. im Adminbereich einstellbar (Berechtigungsmatrix 7.2, letzte Zeile).
MINDESTANZAHL_VERGLEICHSFAELLE = 5

ZWEI_STELLEN = Decimal("0.01")


class Quelle(str, enum.Enum):
    historisch = "historisch"
    vorgabe_instrumentenklasse = "vorgabe_instrumentenklasse"
    vorgabe_allgemein = "vorgabe_allgemein"
    keine = "keine"


@dataclass(frozen=True)
class Schaetzung:
    wert: Decimal | None  # auf 2 Nachkommastellen gerundet; None = keine Schätzung möglich
    quelle: Quelle
    anzahl_vergleichsfaelle: int  # gefundene abgeschlossene Aufträge mit Ist-Wert (auch wenn < Schwelle)


def _passende_abgeschlossene_auftraege(
    instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID
) -> list[ColumnElement[bool]]:
    """Filter: gleiche Kombination und Auftrag steht in einem abgeschlossenen Status."""
    return [
        Instrument.instrumentenklasse_id == instrumentenklasse_id,
        Auftrag.reparaturart_id == reparaturart_id,
        Auftragsstatus.ist_abgeschlossen.is_(True),
    ]


def _historisch_stunden(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID
) -> tuple[int, Decimal | None]:
    # Erst je Auftrag alle Zeiteinträge aufsummieren (mehrere Sitzungen/Mitarbeiter),
    # dann über die Aufträge mitteln – sonst würden Einzeleinträge gemittelt.
    je_auftrag = (
        select(func.sum(Arbeitszeiterfassung.dauer_minuten).label("minuten"))
        .select_from(Auftrag)
        .join(Arbeitszeiterfassung, Arbeitszeiterfassung.auftrag_id == Auftrag.id)
        .join(Instrument, Auftrag.instrument_id == Instrument.id)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(*_passende_abgeschlossene_auftraege(instrumentenklasse_id, reparaturart_id))
        .group_by(Auftrag.id)
        .subquery()
    )
    anzahl, durchschnitt_minuten = db.execute(
        select(func.count(), func.avg(je_auftrag.c.minuten))
    ).one()
    return anzahl, None if durchschnitt_minuten is None else Decimal(durchschnitt_minuten) / 60


def _historisch_kosten(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID
) -> tuple[int, Decimal | None]:
    anzahl, durchschnitt = db.execute(
        select(func.count(), func.avg(Auftrag.tatsaechliche_kosten))
        .join(Instrument, Auftrag.instrument_id == Instrument.id)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(
            *_passende_abgeschlossene_auftraege(instrumentenklasse_id, reparaturart_id),
            Auftrag.tatsaechliche_kosten.is_not(None),
        )
    ).one()
    return anzahl, durchschnitt


def _vorgabe(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, spalte: str
) -> tuple[Quelle, Decimal] | None:
    """Spezifischen Vorgabewert der Instrumentenklasse bevorzugen, sonst den allgemeinen."""
    eintraege = db.scalars(
        select(ReparaturVorgabewert).where(
            ReparaturVorgabewert.reparaturart_id == reparaturart_id,
            (ReparaturVorgabewert.instrumentenklasse_id == instrumentenklasse_id)
            | ReparaturVorgabewert.instrumentenklasse_id.is_(None),
        )
    ).all()
    spezifisch = next((e for e in eintraege if e.instrumentenklasse_id is not None), None)
    if spezifisch is not None:
        return Quelle.vorgabe_instrumentenklasse, getattr(spezifisch, spalte)
    allgemein = next((e for e in eintraege if e.instrumentenklasse_id is None), None)
    if allgemein is not None:
        return Quelle.vorgabe_allgemein, getattr(allgemein, spalte)
    return None


def _schaetzen(
    anzahl: int, durchschnitt: Decimal | None, vorgabe: tuple[Quelle, Decimal] | None
) -> Schaetzung:
    if anzahl >= MINDESTANZAHL_VERGLEICHSFAELLE and durchschnitt is not None:
        return Schaetzung(durchschnitt.quantize(ZWEI_STELLEN, ROUND_HALF_UP), Quelle.historisch, anzahl)
    if vorgabe is not None:
        quelle, wert = vorgabe
        return Schaetzung(Decimal(wert).quantize(ZWEI_STELLEN, ROUND_HALF_UP), quelle, anzahl)
    return Schaetzung(None, Quelle.keine, anzahl)


def schaetze_arbeitsstunden(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID
) -> Schaetzung:
    """Geschätzter reiner Arbeitsaufwand in Stunden (Grundlage für auftrag.geschaetzte_arbeitsstunden)."""
    anzahl, durchschnitt = _historisch_stunden(db, instrumentenklasse_id, reparaturart_id)
    vorgabe = _vorgabe(db, instrumentenklasse_id, reparaturart_id, "vorgabe_stunden")
    return _schaetzen(anzahl, durchschnitt, vorgabe)


def schaetze_kosten(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID
) -> Schaetzung:
    """Geschätzter Preis in Euro (Grundlage für auftrag.geschaetzte_kosten)."""
    anzahl, durchschnitt = _historisch_kosten(db, instrumentenklasse_id, reparaturart_id)
    vorgabe = _vorgabe(db, instrumentenklasse_id, reparaturart_id, "vorgabe_kosten")
    return _schaetzen(anzahl, durchschnitt, vorgabe)

"""Stufe-1-Schätzung von Arbeitsaufwand und Kosten (Datenmodell Abschnitte 4 und 4.1).

Reine Berechnung: liest nur aus der Datenbank, speichert nichts und ist (noch)
nicht mit Auftragserstellung oder Statuswechsel verbunden.

Vorgehen für eine Kombination aus Instrumentenklasse + Reparaturart:
1. Mindestens MINDESTANZAHL_VERGLEICHSFAELLE passende, abgeschlossene Aufträge
   mit Ist-Wert vorhanden → historischer Durchschnitt.
2. Sonst Vorgabewert (reparatur_vorgabewert): erst der spezifische Wert für die
   Instrumentenklasse, sonst der allgemeine Wert der Reparaturart.
3. Sonst: keine Schätzung möglich (wert = None).

Zwei Reihenfolgen (Abschnitt 4), je nachdem ob am Instrument eine Ausführung hinterlegt ist (2.5):
- Bekannte Ausführung: historischer Durchschnitt nur über Aufträge mit Instrumenten DERSELBEN
  Ausführung, sonst der Vorgabewert dieser Ausführung, sonst der Standard der Kombination
  (ist_standard), sonst der allgemeine Wert. Verschiedene Ausführungen werden nie vermischt.
- Unbekannte Ausführung: historischer Durchschnitt über alle Aufträge der Klasse, sonst der
  Standard der Kombination bzw. ihr einziger Wert, sonst der allgemeine Wert.
Auch die Standardausführung trägt einen Namen – ein Instrument mit bewusst eingetragener
Standardausführung ist deshalb etwas anderes als eines mit unbekannter Ausführung.
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
    instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung: str | None
) -> list[ColumnElement[bool]]:
    """Filter: gleiche Kombination und Auftrag steht in einem abgeschlossenen Status.
    Mit Ausführung zählen nur Aufträge, deren Instrument dieselbe Ausführung hat."""
    filter_ = [
        Instrument.instrumentenklasse_id == instrumentenklasse_id,
        Auftrag.reparaturart_id == reparaturart_id,
        Auftragsstatus.ist_abgeschlossen.is_(True),
    ]
    if ausfuehrung is not None:
        filter_.append(Instrument.ausfuehrung == ausfuehrung)
    return filter_


def _historisch_stunden(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung: str | None
) -> tuple[int, Decimal | None]:
    # Erst je Auftrag alle Zeiteinträge aufsummieren (mehrere Sitzungen/Mitarbeiter),
    # dann über die Aufträge mitteln – sonst würden Einzeleinträge gemittelt.
    je_auftrag = (
        select(func.sum(Arbeitszeiterfassung.dauer_minuten).label("minuten"))
        .select_from(Auftrag)
        .join(Arbeitszeiterfassung, Arbeitszeiterfassung.auftrag_id == Auftrag.id)
        .join(Instrument, Auftrag.instrument_id == Instrument.id)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(*_passende_abgeschlossene_auftraege(instrumentenklasse_id, reparaturart_id, ausfuehrung))
        .group_by(Auftrag.id)
        .subquery()
    )
    anzahl, durchschnitt_minuten = db.execute(
        select(func.count(), func.avg(je_auftrag.c.minuten))
    ).one()
    return anzahl, None if durchschnitt_minuten is None else Decimal(durchschnitt_minuten) / 60


def _historisch_kosten(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung: str | None
) -> tuple[int, Decimal | None]:
    anzahl, durchschnitt = db.execute(
        select(func.count(), func.avg(Auftrag.tatsaechliche_kosten))
        .join(Instrument, Auftrag.instrument_id == Instrument.id)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(
            *_passende_abgeschlossene_auftraege(instrumentenklasse_id, reparaturart_id, ausfuehrung),
            Auftrag.tatsaechliche_kosten.is_not(None),
        )
    ).one()
    return anzahl, durchschnitt


def _vorgabe(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, spalte: str,
    ausfuehrung: str | None = None,
) -> tuple[Quelle, Decimal] | None:
    """Spezifischen Vorgabewert der Instrumentenklasse bevorzugen, sonst den allgemeinen.
    Innerhalb der Instrumentenklasse: die Ausführung des Instruments, sonst der Standard (ist_standard),
    sonst der Wert ohne Namen (einziger Wert der Kombination bzw. Altdaten ohne Kennzeichen)."""
    eintraege = db.scalars(
        select(ReparaturVorgabewert).where(
            ReparaturVorgabewert.archiviert_am.is_(None),  # archivierte Vorgabewerte zählen nicht
            ReparaturVorgabewert.reparaturart_id == reparaturart_id,
            (ReparaturVorgabewert.instrumentenklasse_id == instrumentenklasse_id)
            | ReparaturVorgabewert.instrumentenklasse_id.is_(None),
        )
    ).all()
    der_klasse = [e for e in eintraege if e.instrumentenklasse_id is not None]
    spezifisch = (
        next((e for e in der_klasse if ausfuehrung is not None and e.ausfuehrung == ausfuehrung), None)
        or next((e for e in der_klasse if e.ist_standard), None)
        or next((e for e in der_klasse if e.ausfuehrung is None), None)
    )
    if spezifisch is not None:
        return Quelle.vorgabe_instrumentenklasse, getattr(spezifisch, spalte)
    allgemein = next((e for e in eintraege if e.instrumentenklasse_id is None and e.ausfuehrung is None), None)
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
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung: str | None = None
) -> Schaetzung:
    """Geschätzter reiner Arbeitsaufwand in Stunden (Grundlage für auftrag.geschaetzte_arbeitsstunden).
    `ausfuehrung` ist die Ausführung des Instruments (2.5): Sie grenzt den historischen Durchschnitt ein
    und wählt den Vorgabewert (2.6a)."""
    anzahl, durchschnitt = _historisch_stunden(db, instrumentenklasse_id, reparaturart_id, ausfuehrung)
    vorgabe = _vorgabe(db, instrumentenklasse_id, reparaturart_id, "vorgabe_stunden", ausfuehrung)
    return _schaetzen(anzahl, durchschnitt, vorgabe)


def schaetze_kosten(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung: str | None = None
) -> Schaetzung:
    """Geschätzter Preis in Euro (Grundlage für auftrag.geschaetzte_kosten)."""
    anzahl, durchschnitt = _historisch_kosten(db, instrumentenklasse_id, reparaturart_id, ausfuehrung)
    vorgabe = _vorgabe(db, instrumentenklasse_id, reparaturart_id, "vorgabe_kosten", ausfuehrung)
    return _schaetzen(anzahl, durchschnitt, vorgabe)


def ausfuehrungen(db: Session, reparaturart_id: uuid.UUID, instrumentenklasse_id: uuid.UUID) -> list[ReparaturVorgabewert]:
    """Aktive Vorgabewerte genau dieser Kombination – der Standard zuerst, dann alphabetisch.
    Gibt es mehr als einen, kann beim Anlegen eines Auftrags eine Ausführung gewählt werden (2.6a)."""
    return list(db.scalars(
        select(ReparaturVorgabewert).where(
            ReparaturVorgabewert.archiviert_am.is_(None),
            ReparaturVorgabewert.reparaturart_id == reparaturart_id,
            ReparaturVorgabewert.instrumentenklasse_id == instrumentenklasse_id,
        ).order_by(ReparaturVorgabewert.ist_standard.desc(), ReparaturVorgabewert.ausfuehrung.asc().nulls_first())
    ))


def ausfuehrungen_je_klasse(
    db: Session, instrumentenklasse_id: uuid.UUID | None = None
) -> dict[uuid.UUID, list[tuple[str, bool]]]:
    """Benannte Ausführungen je Instrumentenklasse als (Name, ist Standard) – über alle Reparaturarten,
    nur aktive Vorgabewerte; der Standard zuerst, dann alphabetisch. Das sind die Werte, die ein
    Instrument als Ausführung tragen kann (2.5)."""
    standard = func.bool_or(ReparaturVorgabewert.ist_standard)
    abfrage = select(ReparaturVorgabewert.instrumentenklasse_id, ReparaturVorgabewert.ausfuehrung, standard).where(
        ReparaturVorgabewert.archiviert_am.is_(None),
        ReparaturVorgabewert.instrumentenklasse_id.is_not(None),
        ReparaturVorgabewert.ausfuehrung.is_not(None),
    ).group_by(ReparaturVorgabewert.instrumentenklasse_id, ReparaturVorgabewert.ausfuehrung).order_by(
        standard.desc(), ReparaturVorgabewert.ausfuehrung)
    if instrumentenklasse_id is not None:
        abfrage = abfrage.where(ReparaturVorgabewert.instrumentenklasse_id == instrumentenklasse_id)
    ergebnis: dict[uuid.UUID, list[tuple[str, bool]]] = {}
    for klasse_id, ausfuehrung, ist_standard in db.execute(abfrage):
        ergebnis.setdefault(klasse_id, []).append((ausfuehrung, ist_standard))
    return ergebnis

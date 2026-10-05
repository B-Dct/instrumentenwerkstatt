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
  Ausführung, sonst der Vorgabewert dieser Ausführung, sonst der Vorgabewert der Standardausführung
  der Klasse (2.4b), sonst der allgemeine Wert. Verschiedene Ausführungen werden nie vermischt.
- Unbekannte Ausführung: historischer Durchschnitt über alle Aufträge der Klasse, sonst der
  Vorgabewert der Standardausführung bzw. – hat die Klasse keine Ausführungen – ihr einziger Wert,
  sonst der allgemeine Wert.
Auch die Standardausführung trägt einen Namen – ein Instrument mit bewusst eingetragener
Standardausführung ist deshalb etwas anderes als eines mit unbekannter Ausführung.
Ist die Ausführung eines Instruments archiviert, gilt es als "unbekannt"; Vorgabewerte archivierter
Ausführungen werden ignoriert (siehe `bekannte_ausfuehrung`).
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
    Ausfuehrung,
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
    instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung_id: uuid.UUID | None
) -> list[ColumnElement[bool]]:
    """Filter: gleiche Kombination und Auftrag steht in einem abgeschlossenen Status.
    Mit Ausführung zählen nur Aufträge, deren Instrument dieselbe Ausführung hat."""
    filter_ = [
        Instrument.instrumentenklasse_id == instrumentenklasse_id,
        Auftrag.reparaturart_id == reparaturart_id,
        Auftragsstatus.ist_abgeschlossen.is_(True),
    ]
    if ausfuehrung_id is not None:
        filter_.append(Instrument.ausfuehrung_id == ausfuehrung_id)
    return filter_


def _historisch_stunden(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung_id: uuid.UUID | None
) -> tuple[int, Decimal | None]:
    # Erst je Auftrag alle Zeiteinträge aufsummieren (mehrere Sitzungen/Mitarbeiter),
    # dann über die Aufträge mitteln – sonst würden Einzeleinträge gemittelt.
    je_auftrag = (
        select(func.sum(Arbeitszeiterfassung.dauer_minuten).label("minuten"))
        .select_from(Auftrag)
        .join(Arbeitszeiterfassung, Arbeitszeiterfassung.auftrag_id == Auftrag.id)
        .join(Instrument, Auftrag.instrument_id == Instrument.id)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(*_passende_abgeschlossene_auftraege(instrumentenklasse_id, reparaturart_id, ausfuehrung_id))
        .group_by(Auftrag.id)
        .subquery()
    )
    anzahl, durchschnitt_minuten = db.execute(
        select(func.count(), func.avg(je_auftrag.c.minuten))
    ).one()
    return anzahl, None if durchschnitt_minuten is None else Decimal(durchschnitt_minuten) / 60


def _historisch_kosten(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung_id: uuid.UUID | None
) -> tuple[int, Decimal | None]:
    anzahl, durchschnitt = db.execute(
        select(func.count(), func.avg(Auftrag.tatsaechliche_kosten))
        .join(Instrument, Auftrag.instrument_id == Instrument.id)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(
            *_passende_abgeschlossene_auftraege(instrumentenklasse_id, reparaturart_id, ausfuehrung_id),
            Auftrag.tatsaechliche_kosten.is_not(None),
        )
    ).one()
    return anzahl, durchschnitt


def bekannte_ausfuehrung(db: Session, ausfuehrung_id: uuid.UUID | None) -> uuid.UUID | None:
    """Die Ausführung eines Instruments, wie die Schätzung sie sieht: Eine archivierte gilt als unbekannt (2.4b)."""
    if ausfuehrung_id is None:
        return None
    ausfuehrung = db.get(Ausfuehrung, ausfuehrung_id)
    return ausfuehrung.id if ausfuehrung is not None and ausfuehrung.archiviert_am is None else None


def _vorgabe(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, spalte: str,
    ausfuehrung_id: uuid.UUID | None = None,
) -> tuple[Quelle, Decimal] | None:
    """Spezifischen Vorgabewert der Instrumentenklasse bevorzugen, sonst den allgemeinen.
    Innerhalb der Instrumentenklasse: die Ausführung des Instruments, sonst die Standardausführung der
    Klasse, sonst der Wert ohne Ausführung (Klasse ohne Ausführungen)."""
    eintraege = db.execute(
        select(ReparaturVorgabewert, func.coalesce(Ausfuehrung.ist_standard, False))
        .outerjoin(Ausfuehrung, ReparaturVorgabewert.ausfuehrung_id == Ausfuehrung.id)
        .where(
            ReparaturVorgabewert.archiviert_am.is_(None),  # archivierte Vorgabewerte zählen nicht
            Ausfuehrung.archiviert_am.is_(None),           # … und auch nicht die archivierter Ausführungen
            ReparaturVorgabewert.reparaturart_id == reparaturart_id,
            (ReparaturVorgabewert.instrumentenklasse_id == instrumentenklasse_id)
            | ReparaturVorgabewert.instrumentenklasse_id.is_(None),
        )
    ).all()
    der_klasse = [(e, standard) for e, standard in eintraege if e.instrumentenklasse_id is not None]
    spezifisch = (
        next((e for e, _ in der_klasse if ausfuehrung_id is not None and e.ausfuehrung_id == ausfuehrung_id), None)
        or next((e for e, standard in der_klasse if standard), None)
        or next((e for e, _ in der_klasse if e.ausfuehrung_id is None), None)
    )
    if spezifisch is not None:
        return Quelle.vorgabe_instrumentenklasse, getattr(spezifisch, spalte)
    allgemein = next((e for e, _ in eintraege if e.instrumentenklasse_id is None), None)
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
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung_id: uuid.UUID | None = None
) -> Schaetzung:
    """Geschätzter reiner Arbeitsaufwand in Stunden (Grundlage für auftrag.geschaetzte_arbeitsstunden).
    `ausfuehrung_id` ist die Ausführung des Instruments (2.5): Sie grenzt den historischen Durchschnitt ein
    und wählt den Vorgabewert (2.6a). None oder eine archivierte Ausführung = unbekannt."""
    ausfuehrung_id = bekannte_ausfuehrung(db, ausfuehrung_id)
    anzahl, durchschnitt = _historisch_stunden(db, instrumentenklasse_id, reparaturart_id, ausfuehrung_id)
    vorgabe = _vorgabe(db, instrumentenklasse_id, reparaturart_id, "vorgabe_stunden", ausfuehrung_id)
    return _schaetzen(anzahl, durchschnitt, vorgabe)


def schaetze_kosten(
    db: Session, instrumentenklasse_id: uuid.UUID, reparaturart_id: uuid.UUID, ausfuehrung_id: uuid.UUID | None = None
) -> Schaetzung:
    """Geschätzter Preis in Euro (Grundlage für auftrag.geschaetzte_kosten)."""
    ausfuehrung_id = bekannte_ausfuehrung(db, ausfuehrung_id)
    anzahl, durchschnitt = _historisch_kosten(db, instrumentenklasse_id, reparaturart_id, ausfuehrung_id)
    vorgabe = _vorgabe(db, instrumentenklasse_id, reparaturart_id, "vorgabe_kosten", ausfuehrung_id)
    return _schaetzen(anzahl, durchschnitt, vorgabe)


def aktive_ausfuehrungen(db: Session, instrumentenklasse_id: uuid.UUID | None = None) -> list[Ausfuehrung]:
    """Aktive Ausführungen (einer Klasse oder aller Klassen) – der Standard zuerst, dann alphabetisch (2.4b)."""
    abfrage = select(Ausfuehrung).where(Ausfuehrung.archiviert_am.is_(None)).order_by(
        Ausfuehrung.instrumentenklasse_id, Ausfuehrung.ist_standard.desc(), func.lower(Ausfuehrung.bezeichnung))
    if instrumentenklasse_id is not None:
        abfrage = abfrage.where(Ausfuehrung.instrumentenklasse_id == instrumentenklasse_id)
    return list(db.scalars(abfrage))


def richtpreise_je_ausfuehrung(
    db: Session, reparaturart_id: uuid.UUID, instrumentenklasse_id: uuid.UUID
) -> dict[uuid.UUID, ReparaturVorgabewert]:
    """Die aktiven Vorgabewerte genau dieser Kombination je Ausführung (für die Auswahl im Auftragsformular)."""
    return {v.ausfuehrung_id: v for v in db.scalars(select(ReparaturVorgabewert).where(
        ReparaturVorgabewert.archiviert_am.is_(None),
        ReparaturVorgabewert.reparaturart_id == reparaturart_id,
        ReparaturVorgabewert.instrumentenklasse_id == instrumentenklasse_id,
        ReparaturVorgabewert.ausfuehrung_id.is_not(None),
    ))}

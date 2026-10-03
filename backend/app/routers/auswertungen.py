"""Auswertungen / Jahresstatistik (Datenmodell 9.14) – nur Werkstattleitung und Admin (7.2).

Grundlage sind immer die im gewählten Jahr ABGESCHLOSSENEN Aufträge: `tatsaechliches_fertigstellungsdatum`
liegt im Jahr (nicht der Auftragseingang). Das Datum wird beim Wiederaufnehmen eines Auftrags
geleert, ein gesetztes Datum heißt also "abgeschlossen".
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, extract, func, select
from sqlalchemy.orm import Session

from app.auth import rolle_mindestens
from app.db import get_db
from app.eingabe import feldfehler
from app.models import (
    Arbeitszeiterfassung, Auftrag, Instrument, Instrumentenklasse, Reparaturart, SchaetzungsLog, Systemrolle,
)
from app.schemas import (
    Abweichung, Auswertung, AuswertungGeld, AuswertungMenge, AuswertungSchaetzgenauigkeit, AuswertungZeit, Verteilung,
)

router = APIRouter(prefix="/auswertungen", tags=["Auswertungen"],
                   dependencies=[Depends(rolle_mindestens(Systemrolle.werkstattleiter))])

FRUEHESTES_JAHR = 2000
TOP = 5
SONSTIGE = "Sonstige"


def _im_jahr(jahr: int) -> ColumnElement[bool]:
    return Auftrag.tatsaechliches_fertigstellungsdatum.between(date(jahr, 1, 1), date(jahr, 12, 31))


def _verteilung(db: Session, jahr: int, bezeichnung, verknuepfung) -> list[Verteilung]:
    """Anzahl je Gruppe, die größten TOP einzeln, der Rest zusammen als "Sonstige"."""
    zeilen = db.execute(
        verknuepfung(select(bezeichnung, func.count()).select_from(Auftrag))
        .where(_im_jahr(jahr)).group_by(bezeichnung).order_by(func.count().desc(), bezeichnung)
    ).all()
    ergebnis = [Verteilung(bezeichnung=name, anzahl=anzahl) for name, anzahl in zeilen[:TOP]]
    rest = sum(anzahl for _, anzahl in zeilen[TOP:])
    if rest:
        ergebnis.append(Verteilung(bezeichnung=SONSTIGE, anzahl=rest, sonstige=True))
    return ergebnis


def _menge(db: Session, jahr: int) -> AuswertungMenge:
    monat = extract("month", Auftrag.tatsaechliches_fertigstellungsdatum)
    je_monat = dict(db.execute(select(monat, func.count()).where(_im_jahr(jahr)).group_by(monat)).all())
    pro_monat = [je_monat.get(m, 0) for m in range(1, 13)]
    return AuswertungMenge(
        abgeschlossen=sum(pro_monat),
        pro_monat=pro_monat,
        nach_reparaturart=_verteilung(
            db, jahr, Reparaturart.bezeichnung,
            lambda abfrage: abfrage.join(Reparaturart, Auftrag.reparaturart_id == Reparaturart.id)),
        nach_instrumentenklasse=_verteilung(
            db, jahr, Instrumentenklasse.bezeichnung,
            lambda abfrage: abfrage.join(Instrument, Auftrag.instrument_id == Instrument.id)
            .join(Instrumentenklasse, Instrument.instrumentenklasse_id == Instrumentenklasse.id)),
    )


def _durchschnitt(werte: list, stellen: int = 1) -> float | None:
    return round(float(sum(werte)) / len(werte), stellen) if werte else None


def erste_automatische_schaetzungen(db: Session, jahr: int) -> dict:
    """Je im Jahr abgeschlossenem Auftrag der ERSTE automatische Eintrag im Schätzprotokoll
    (methode = "regelbasiert", entsteht beim Anlegen) – bewusst nicht spätere Neuberechnungen
    oder manuelle Korrekturen: gemessen wird die ursprüngliche Prognose (9.14.2, 9.14.4)."""
    zeilen = db.scalars(
        select(SchaetzungsLog)
        .where(SchaetzungsLog.methode == "regelbasiert",
               SchaetzungsLog.auftrag_id.in_(select(Auftrag.id).where(_im_jahr(jahr))))
        .order_by(SchaetzungsLog.auftrag_id, SchaetzungsLog.berechnet_am, SchaetzungsLog.id)
    )
    erste: dict = {}
    for eintrag in zeilen:
        erste.setdefault(eintrag.auftrag_id, eintrag)  # der früheste je Auftrag bleibt stehen
    return erste


def _zeit(db: Session, jahr: int) -> AuswertungZeit:
    auftraege = db.execute(
        select(Auftrag.id, Auftrag.erstellt_am, Auftrag.tatsaechliches_fertigstellungsdatum).where(_im_jahr(jahr))
    ).all()
    # Bearbeitungsdauer in Kalendertagen: Eingang bis Fertigstellung
    dauer = {a.id: (a.tatsaechliches_fertigstellungsdatum - a.erstellt_am.date()).days for a in auftraege}
    je_monat: dict[int, list[int]] = {}
    for a in auftraege:
        je_monat.setdefault(a.tatsaechliches_fertigstellungsdatum.month, []).append(dauer[a.id])

    # Reine Arbeitszeit: Summe der erfassten Minuten je Auftrag (nur Aufträge mit Zeiterfassung)
    minuten = db.scalars(
        select(func.sum(Arbeitszeiterfassung.dauer_minuten))
        .where(Arbeitszeiterfassung.auftrag_id.in_(select(Auftrag.id).where(_im_jahr(jahr))))
        .group_by(Arbeitszeiterfassung.auftrag_id)
    ).all()

    # Pünktlichkeit gegenüber der ersten automatischen Terminschätzung
    erste = erste_automatische_schaetzungen(db, jahr)
    mit_prognose = [a for a in auftraege if a.id in erste and erste[a.id].geschaetztes_datum is not None]
    puenktlich = sum(a.tatsaechliches_fertigstellungsdatum <= erste[a.id].geschaetztes_datum for a in mit_prognose)

    return AuswertungZeit(
        bearbeitungsdauer_tage=_durchschnitt(list(dauer.values())),
        bearbeitungsdauer_pro_monat=[_durchschnitt(je_monat.get(m, [])) for m in range(1, 13)],
        arbeitszeit_stunden=_durchschnitt([m / 60 for m in minuten], stellen=2),
        auftraege_mit_zeiterfassung=len(minuten),
        puenktlich=puenktlich,
        auftraege_mit_terminprognose=len(mit_prognose),
        puenktlichkeit_prozent=round(puenktlich / len(mit_prognose) * 100) if mit_prognose else None,
    )


def _geld(db: Session, jahr: int) -> AuswertungGeld:
    """Umsatz = Summe der tatsächlich abgerechneten Kosten der im Jahr abgeschlossenen Aufträge.
    Aufträge ohne eingetragene Kosten haben einen unbekannten, keinen Null-Betrag: Sie fehlen
    im Umsatz und zählen nicht in den Durchschnitt."""
    monat = extract("month", Auftrag.tatsaechliches_fertigstellungsdatum)
    je_monat = {
        m: (anzahl, summe) for m, anzahl, summe in db.execute(
            select(monat, func.count(), func.sum(Auftrag.tatsaechliche_kosten))
            .where(_im_jahr(jahr), Auftrag.tatsaechliche_kosten.is_not(None)).group_by(monat)
        )
    }
    anzahl = sum(n for n, _ in je_monat.values())
    umsatz = sum((summe for _, summe in je_monat.values()), Decimal(0))
    return AuswertungGeld(
        umsatz=umsatz,
        auftragswert=round(umsatz / anzahl, 2) if anzahl else None,
        auftraege_mit_kosten=anzahl,
        umsatz_pro_monat=[je_monat.get(m, (0, Decimal(0)))[1] for m in range(1, 13)],
    )


def _abweichung(paare: list[tuple[Decimal, Decimal]]) -> Abweichung:
    """paare = (geschätzt, tatsächlich). Abweichung je Auftrag in Prozent der Schätzung:
    - mittlere Abweichung ohne Vorzeichen (wie weit daneben, egal in welche Richtung)
    - Tendenz mit Vorzeichen (positiv = tatsächlich mehr als geschätzt, also zu niedrig geschätzt)"""
    prozente = [(ist - geschaetzt) / geschaetzt * 100 for geschaetzt, ist in paare]
    return Abweichung(
        abweichung_prozent=_durchschnitt([abs(p) for p in prozente], stellen=0) if prozente else None,
        tendenz_prozent=_durchschnitt(prozente, stellen=0) if prozente else None,
        auftraege=len(prozente),
    )


def _schaetzgenauigkeit(db: Session, jahr: int) -> AuswertungSchaetzgenauigkeit:
    """Vergleicht die ERSTE automatische Schätzung (nicht spätere Korrekturen) mit den Ist-Werten:
    erfasste Arbeitszeit bzw. abgerechneter Betrag. Zeigt, wie gut das automatische Modell selbst ist."""
    erste = erste_automatische_schaetzungen(db, jahr)
    im_jahr = select(Auftrag.id).where(_im_jahr(jahr))
    ist_stunden = {
        auftrag_id: Decimal(minuten) / 60 for auftrag_id, minuten in db.execute(
            select(Arbeitszeiterfassung.auftrag_id, func.sum(Arbeitszeiterfassung.dauer_minuten))
            .where(Arbeitszeiterfassung.auftrag_id.in_(im_jahr)).group_by(Arbeitszeiterfassung.auftrag_id))
    }
    ist_kosten = dict(db.execute(
        select(Auftrag.id, Auftrag.tatsaechliche_kosten).where(_im_jahr(jahr), Auftrag.tatsaechliche_kosten.is_not(None))
    ).all())

    def paare(ist: dict, feld: str) -> list[tuple[Decimal, Decimal]]:
        # Ohne Schätzung oder mit Schätzung 0 lässt sich keine prozentuale Abweichung bilden
        return [(getattr(erste[a], feld), wert) for a, wert in ist.items()
                if a in erste and getattr(erste[a], feld)]

    return AuswertungSchaetzgenauigkeit(
        stunden=_abweichung(paare(ist_stunden, "geschaetzte_stunden")),
        kosten=_abweichung(paare(ist_kosten, "geschaetzte_kosten")),
    )


def _jahre(db: Session, heute: date) -> list[int]:
    """Wählbare Jahre: vom ersten Jahr mit einem abgeschlossenen Auftrag bis heute, neuestes zuerst."""
    erstes = db.scalar(select(func.min(Auftrag.tatsaechliches_fertigstellungsdatum)))
    start = min(erstes.year, heute.year) if erstes else heute.year
    return list(range(heute.year, max(start, FRUEHESTES_JAHR) - 1, -1))


@router.get("", response_model=Auswertung)
def auswertung(
    jahr: int | None = Query(None, description="Kalenderjahr; Standard: das laufende Jahr"),
    db: Session = Depends(get_db),
) -> Auswertung:
    heute = date.today()
    jahr = heute.year if jahr is None else jahr
    if not FRUEHESTES_JAHR <= jahr <= heute.year:
        raise feldfehler(jahr=f"Bitte ein Jahr zwischen {FRUEHESTES_JAHR} und {heute.year} wählen")
    return Auswertung(jahr=jahr, jahre=_jahre(db, heute), menge=_menge(db, jahr), zeit=_zeit(db, jahr), geld=_geld(db, jahr),
                      schaetzgenauigkeit=_schaetzgenauigkeit(db, jahr))

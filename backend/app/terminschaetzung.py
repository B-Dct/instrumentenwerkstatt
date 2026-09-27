"""Stufe-1-Terminschätzung: voraussichtliches Fertigstellungsdatum (Datenmodell Abschnitt 4).

Bewusst einfache, nachvollziehbare erste Version:

1. Zu erledigende Stunden = Stunden der Aufträge, die beim selben Mitarbeiter VOR diesem
   Auftrag an der Reihe sind (offen, Reihenfolge wie im Mitarbeiter-Dashboard 9.4:
   Priorität hoch zuerst, dann ältester Eingang) + die geschätzten Stunden dieses Auftrags.
2. Ab dem nächsten Arbeitstag werden diese Stunden Tag für Tag "abgearbeitet":
   Stunden pro Tag = Wochenstunden / 5. Übersprungen werden Wochenenden, betriebsweite
   Abwesenheiten (Feiertag, Betriebsschließung) und ganztägige Abwesenheiten des Mitarbeiters.
   Bei reduzierter Verfügbarkeit gilt reduzierte_stunden / 5 pro Tag.
3. Der Tag, an dem nichts mehr übrig ist, ist das voraussichtliche Fertigstellungsdatum.
4. Bandbreite: ± 20 % der benötigten Arbeitstage, mindestens ± 1 Arbeitstag.

Ohne zugewiesenen Mitarbeiter: Warteschlange = durchschnittliche offene Stunden je aktivem
Mitarbeiter, Wochenstunden = Durchschnitt der aktiven Mitarbeiter.

Reine Berechnung – speichert nichts. Speichern und Protokollieren macht der Aufrufer.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Abwesenheit, Auftrag, Auftragsstatus, Mitarbeiter, MitarbeiterArbeitszeit

# Gilt, solange für einen Mitarbeiter keine Wochenarbeitszeit hinterlegt ist (2.12)
STANDARD_WOCHENSTUNDEN = Decimal("40")
ARBEITSTAGE_PRO_WOCHE = 5
BANDBREITE_ANTEIL = Decimal("0.2")
BANDBREITE_MINDESTENS_TAGE = 1
MAX_TAGE_VORAUS = 3 * 365  # Sicherheitsgrenze, falls keinerlei Kapazität vorhanden ist


@dataclass
class Terminschaetzung:
    datum: date | None  # None = keine Schätzung möglich (z. B. keine Stunden bekannt)
    bandbreite_von: date | None
    bandbreite_bis: date | None
    eingabefaktoren: dict = field(default_factory=dict)


@dataclass
class _Kalender:
    """Verfügbare Stunden je Tag für einen Mitarbeiter (oder die Werkstatt allgemein)."""

    wochenstunden: list[MitarbeiterArbeitszeit]
    standard_wochenstunden: Decimal
    abwesenheiten: list[Abwesenheit]
    uebersprungen: dict = field(default_factory=lambda: {"wochenende": 0, "betrieb": 0, "persoenlich": 0})

    def _wochenstunden_am(self, tag: date) -> Decimal:
        for eintrag in self.wochenstunden:
            if eintrag.gueltig_ab <= tag and (eintrag.gueltig_bis is None or tag <= eintrag.gueltig_bis):
                return eintrag.wochenstunden
        return self.standard_wochenstunden

    def stunden_am(self, tag: date, zaehlen: bool = False) -> Decimal:
        if tag.weekday() >= 5:
            if zaehlen:
                self.uebersprungen["wochenende"] += 1
            return Decimal(0)
        stunden = self._wochenstunden_am(tag) / ARBEITSTAGE_PRO_WOCHE
        for a in self.abwesenheiten:
            if not (a.von_datum <= tag <= a.bis_datum):
                continue
            if a.reduzierte_stunden is None:  # ganztägig abwesend
                if zaehlen:
                    self.uebersprungen["betrieb" if a.mitarbeiter_id is None else "persoenlich"] += 1
                return Decimal(0)
            stunden = min(stunden, a.reduzierte_stunden / ARBEITSTAGE_PRO_WOCHE)
        return stunden

    def ist_arbeitstag(self, tag: date) -> bool:
        return self.stunden_am(tag) > 0

    def arbeitstage_verschieben(self, tag: date, anzahl: int) -> date:
        """`anzahl` Arbeitstage vor (positiv) oder zurück (negativ)."""
        schritt = 1 if anzahl > 0 else -1
        for _ in range(abs(anzahl)):
            tag += timedelta(days=schritt)
            for _ in range(MAX_TAGE_VORAUS):
                if self.ist_arbeitstag(tag):
                    break
                tag += timedelta(days=schritt)
        return tag


def _offen():
    return Auftragsstatus.ist_abgeschlossen.is_(False)


def _warteschlange_mitarbeiter(db: Session, auftrag: Auftrag) -> tuple[Decimal, int]:
    """Offene Stunden der Aufträge desselben Mitarbeiters, die vor diesem an der Reihe sind."""
    vorher = or_(
        Auftrag.prioritaet > auftrag.prioritaet,
        and_(
            Auftrag.prioritaet == auftrag.prioritaet,
            or_(Auftrag.erstellt_am < auftrag.erstellt_am,
                and_(Auftrag.erstellt_am == auftrag.erstellt_am, Auftrag.id < auftrag.id)),
        ),
    )
    anzahl, stunden = db.execute(
        select(func.count(), func.coalesce(func.sum(Auftrag.geschaetzte_arbeitsstunden), 0))
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(
            Auftrag.zugewiesener_mitarbeiter_id == auftrag.zugewiesener_mitarbeiter_id,
            Auftrag.id != auftrag.id,
            _offen(),
            vorher,
        )
    ).one()
    return Decimal(stunden), anzahl


def _warteschlange_durchschnitt(db: Session, auftrag: Auftrag) -> tuple[Decimal, int]:
    """Fallback ohne Zuweisung: durchschnittliche offene Stunden je aktivem Mitarbeiter."""
    aktive = db.scalar(select(func.count()).select_from(Mitarbeiter).where(Mitarbeiter.aktiv))
    gesamt = db.scalar(
        select(func.coalesce(func.sum(Auftrag.geschaetzte_arbeitsstunden), 0))
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .join(Mitarbeiter, Auftrag.zugewiesener_mitarbeiter_id == Mitarbeiter.id)
        .where(Mitarbeiter.aktiv, _offen(), Auftrag.id != auftrag.id)
    )
    return (Decimal(gesamt) / aktive if aktive else Decimal(0)), aktive


def _kalender(db: Session, mitarbeiter_id, start: date) -> _Kalender:
    ende = start + timedelta(days=MAX_TAGE_VORAUS)
    wer = (Abwesenheit.mitarbeiter_id.is_(None) if mitarbeiter_id is None
           else or_(Abwesenheit.mitarbeiter_id.is_(None), Abwesenheit.mitarbeiter_id == mitarbeiter_id))
    abwesenheiten = list(db.scalars(select(Abwesenheit).where(
        wer, Abwesenheit.bis_datum >= start, Abwesenheit.von_datum <= ende
    )))
    if mitarbeiter_id is not None:
        wochenstunden = list(db.scalars(select(MitarbeiterArbeitszeit).where(
            MitarbeiterArbeitszeit.mitarbeiter_id == mitarbeiter_id
        )))
        return _Kalender(wochenstunden, STANDARD_WOCHENSTUNDEN, abwesenheiten)

    # Ohne Zuweisung: Durchschnitt der aktuell gültigen Wochenstunden aller aktiven Mitarbeiter
    aktive = list(db.scalars(select(Mitarbeiter.id).where(Mitarbeiter.aktiv)))
    werte = []
    for m_id in aktive:
        eintrag = db.scalar(select(MitarbeiterArbeitszeit.wochenstunden).where(
            MitarbeiterArbeitszeit.mitarbeiter_id == m_id,
            MitarbeiterArbeitszeit.gueltig_ab <= start,
            or_(MitarbeiterArbeitszeit.gueltig_bis.is_(None), MitarbeiterArbeitszeit.gueltig_bis >= start),
        ).limit(1))
        werte.append(eintrag if eintrag is not None else STANDARD_WOCHENSTUNDEN)
    durchschnitt = sum(werte, Decimal(0)) / len(werte) if werte else STANDARD_WOCHENSTUNDEN
    return _Kalender([], durchschnitt, abwesenheiten)


def schaetze_fertigstellung(db: Session, auftrag: Auftrag, heute: date | None = None) -> Terminschaetzung:
    """Voraussichtliches Fertigstellungsdatum samt Bandbreite für einen (gespeicherten) Auftrag."""
    heute = heute or date.today()
    if auftrag.geschaetzte_arbeitsstunden is None:
        return Terminschaetzung(None, None, None, {"hinweis": "keine geschätzten Arbeitsstunden"})

    zugewiesen = auftrag.zugewiesener_mitarbeiter_id is not None
    if zugewiesen:
        warteschlange, anzahl_vorher = _warteschlange_mitarbeiter(db, auftrag)
    else:
        warteschlange, anzahl_aktive = _warteschlange_durchschnitt(db, auftrag)
    start = heute + timedelta(days=1)  # Arbeit beginnt frühestens am nächsten Tag
    kalender = _kalender(db, auftrag.zugewiesener_mitarbeiter_id, start)

    rest = warteschlange + auftrag.geschaetzte_arbeitsstunden
    tag, arbeitstage = start, 0
    for _ in range(MAX_TAGE_VORAUS):
        stunden = kalender.stunden_am(tag, zaehlen=True)
        if stunden > 0:
            arbeitstage += 1
            rest -= stunden
            if rest <= 0:
                break
        tag += timedelta(days=1)
    else:
        return Terminschaetzung(None, None, None, {"hinweis": f"keine Kapazität in {MAX_TAGE_VORAUS} Tagen"})

    spanne = max(BANDBREITE_MINDESTENS_TAGE, int((arbeitstage * BANDBREITE_ANTEIL).to_integral_value()))
    von = max(kalender.arbeitstage_verschieben(tag, -spanne), start)
    bis = kalender.arbeitstage_verschieben(tag, spanne)

    wochenstunden_hinterlegt = any(
        e.gueltig_ab <= start and (e.gueltig_bis is None or start <= e.gueltig_bis) for e in kalender.wochenstunden
    )
    faktoren = {
        "berechnet_ab": start.isoformat(),
        "eigene_stunden": str(auftrag.geschaetzte_arbeitsstunden),
        "warteschlange_stunden": str(warteschlange.quantize(Decimal("0.01"))),
        "arbeitstage": arbeitstage,
        "stunden_pro_tag": str((kalender._wochenstunden_am(start) / ARBEITSTAGE_PRO_WOCHE).quantize(Decimal("0.01"))),
        "wochenstunden_quelle": "mitarbeiter_arbeitszeit" if wochenstunden_hinterlegt else (
            f"Standard {STANDARD_WOCHENSTUNDEN}" if zugewiesen else "Durchschnitt aktiver Mitarbeiter"),
        "uebersprungene_tage": kalender.uebersprungen,
        "bandbreite_arbeitstage": spanne,
    }
    if zugewiesen:
        faktoren["auftraege_davor"] = anzahl_vorher
    else:
        faktoren["ohne_zuweisung"] = {"verfahren": "durchschnittliche Warteschlange", "aktive_mitarbeiter": anzahl_aktive}
    return Terminschaetzung(tag, von, bis, faktoren)

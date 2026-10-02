"""Mitarbeiter-Verwaltung (2.2, 2.12, 7.2, 7.4) – nur Admin (über den Admin-Router).

Neue Konten entstehen weiterhin über das Kommandozeilen-Skript app/konto_anlegen.py.

Schutzregeln gegen Aussperren:
- Ein Admin kann sich nicht selbst deaktivieren oder sich selbst die Admin-Rolle entziehen.
- Der letzte aktive Admin kann weder deaktiviert noch herabgestuft werden.
- Wer noch offene zugewiesene Aufträge hat, kann erst nach Neuzuweisung deaktiviert werden.

Wochenstunden (2.12): Ein neuer Eintrag schließt den bisher gültigen ab (gültig_bis = Tag
davor), statt ihn zu überschreiben. Termine werden dabei NICHT neu berechnet (4.0a) –
dafür gibt es `app.termine_nachrechnen --alle`.
"""

import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id
from app.db import get_db
from app.ereignisse import protokollieren
from app.listen import ListenParameter, Seite, enthaelt, listen_parameter, seite_abfragen
from app.models import Auftrag, Auftragsstatus, Mitarbeiter, MitarbeiterArbeitszeit, Systemrolle
from app.schemas import (
    AktuelleWochenstunden,
    MitarbeiterVerwaltung,
    SystemrolleAenderung,
    WochenstundenEintrag,
    WochenstundenNeu,
    WochenstundenVerlauf,
)
from app.terminschaetzung import STANDARD_WOCHENSTUNDEN

router = APIRouter(prefix="/mitarbeiter", tags=["Admin: Mitarbeiter"])


# --- Hilfsfunktionen ----------------------------------------------------------------

def _laden(db: Session, mitarbeiter_id: uuid.UUID, sperren: bool = False) -> Mitarbeiter:
    mitarbeiter = db.get(Mitarbeiter, mitarbeiter_id, with_for_update=sperren)
    if mitarbeiter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mitarbeiter nicht gefunden")
    return mitarbeiter


def _konflikt(meldung: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, meldung)


def _aktuelle_wochenstunden(db: Session, mitarbeiter_id: uuid.UUID, stichtag: date | None = None) -> AktuelleWochenstunden:
    stichtag = stichtag or date.today()
    eintrag = db.scalar(select(MitarbeiterArbeitszeit).where(
        MitarbeiterArbeitszeit.mitarbeiter_id == mitarbeiter_id,
        MitarbeiterArbeitszeit.gueltig_ab <= stichtag,
        (MitarbeiterArbeitszeit.gueltig_bis.is_(None)) | (MitarbeiterArbeitszeit.gueltig_bis >= stichtag),
    ))
    if eintrag is None:
        return AktuelleWochenstunden(wochenstunden=STANDARD_WOCHENSTUNDEN, quelle="standard", gueltig_ab=None)
    return AktuelleWochenstunden(wochenstunden=eintrag.wochenstunden, quelle="hinterlegt", gueltig_ab=eintrag.gueltig_ab)


def _offene_auftraege(db: Session, mitarbeiter_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(Auftrag)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(Auftrag.zugewiesener_mitarbeiter_id == mitarbeiter_id, Auftragsstatus.ist_abgeschlossen.is_(False))
    )


def _antwort(db: Session, m: Mitarbeiter) -> MitarbeiterVerwaltung:
    return MitarbeiterVerwaltung(
        id=m.id, name=m.name, email=m.email, rolle=m.rolle, systemrolle=m.systemrolle, aktiv=m.aktiv,
        erstellt_am=m.erstellt_am, deaktiviert_am=m.deaktiviert_am,
        wochenstunden=_aktuelle_wochenstunden(db, m.id), offene_auftraege=_offene_auftraege(db, m.id),
    )


def letzter_aktiver_admin_pruefen(db: Session, betroffen: Mitarbeiter) -> None:
    """Verhindert, dass der letzte aktive Admin wegfällt. Sperrt die Admin-Zeilen, damit zwei
    gleichzeitige Änderungen nicht beide durchgehen und am Ende niemand mehr Admin ist."""
    admins = db.scalars(
        select(Mitarbeiter.id).where(Mitarbeiter.systemrolle == Systemrolle.admin, Mitarbeiter.aktiv)
        .with_for_update()
    ).all()
    if betroffen.id in admins and len(admins) <= 1:
        raise _konflikt("Das ist der letzte aktive Admin – zuerst einen weiteren Admin bestimmen")


# --- Endpunkte ---------------------------------------------------------------------

SORTIERUNG = {
    "name": Mitarbeiter.name,
    "email": Mitarbeiter.email,
    "rolle": Mitarbeiter.rolle,
    "systemrolle": Mitarbeiter.systemrolle,
    "status": Mitarbeiter.aktiv,
    "erstellt_am": Mitarbeiter.erstellt_am,
}


@router.get("", response_model=Seite[MitarbeiterVerwaltung])
def mitarbeiter_auflisten(
    liste: ListenParameter = Depends(listen_parameter(SORTIERUNG, standard="name")),
    systemrolle: Systemrolle | None = Query(None, description="Nur diese Systemrolle"),
    status_: Literal["aktiv", "deaktiviert", "alle"] = Query("aktiv", alias="status"),
    db: Session = Depends(get_db),
) -> Seite[MitarbeiterVerwaltung]:
    """Liste nach 9.11: Suche (Name, E-Mail, fachliche Rolle), Filter, Sortierung, seitenweise."""
    basis = select(Mitarbeiter)
    gefiltert = basis
    if (muster := liste.suchmuster()) is not None:
        gefiltert = gefiltert.where(enthaelt(muster, Mitarbeiter.name, Mitarbeiter.email, Mitarbeiter.rolle))
    if systemrolle is not None:
        gefiltert = gefiltert.where(Mitarbeiter.systemrolle == systemrolle)
    if status_ != "alle":
        gefiltert = gefiltert.where(Mitarbeiter.aktiv.is_(status_ == "aktiv"))
    return seite_abfragen(db, basis, gefiltert, liste, SORTIERUNG,
                          umwandeln=lambda zeile: _antwort(db, zeile[0]), eindeutig=Mitarbeiter.id)


@router.get("/{mitarbeiter_id}", response_model=MitarbeiterVerwaltung)
def mitarbeiter_abrufen(mitarbeiter_id: uuid.UUID, db: Session = Depends(get_db)) -> MitarbeiterVerwaltung:
    return _antwort(db, _laden(db, mitarbeiter_id))


@router.post("/{mitarbeiter_id}/deaktivieren", response_model=MitarbeiterVerwaltung)
def mitarbeiter_deaktivieren(
    mitarbeiter_id: uuid.UUID, db: Session = Depends(get_db), admin_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> MitarbeiterVerwaltung:
    m = _laden(db, mitarbeiter_id, sperren=True)
    if not m.aktiv:
        raise _konflikt("Mitarbeiter ist bereits deaktiviert")
    if m.id == admin_id:
        raise _konflikt("Du kannst dich nicht selbst deaktivieren")
    letzter_aktiver_admin_pruefen(db, m)
    offen = _offene_auftraege(db, m.id)
    if offen:
        raise _konflikt(f"{m.name} hat noch {offen} offene(n) zugewiesene(n) Auftrag/Aufträge – erst neu zuweisen")
    m.aktiv = False
    m.deaktiviert_am = db.scalar(select(func.clock_timestamp()))
    protokollieren(db, admin_id, "mitarbeiter_deaktiviert", "mitarbeiter", m.id,
                   {"alt": {"aktiv": True}, "neu": {"aktiv": False}})
    db.commit()
    return _antwort(db, m)


@router.post("/{mitarbeiter_id}/aktivieren", response_model=MitarbeiterVerwaltung)
def mitarbeiter_aktivieren(
    mitarbeiter_id: uuid.UUID, db: Session = Depends(get_db), admin_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> MitarbeiterVerwaltung:
    m = _laden(db, mitarbeiter_id, sperren=True)
    if m.aktiv:
        raise _konflikt("Mitarbeiter ist bereits aktiv")
    alt_deaktiviert = m.deaktiviert_am.isoformat()
    m.aktiv = True
    m.deaktiviert_am = None
    protokollieren(db, admin_id, "mitarbeiter_aktiviert", "mitarbeiter", m.id,
                   {"alt": {"aktiv": False, "deaktiviert_am": alt_deaktiviert}, "neu": {"aktiv": True}})
    db.commit()
    return _antwort(db, m)


@router.patch("/{mitarbeiter_id}/systemrolle", response_model=MitarbeiterVerwaltung)
def systemrolle_aendern(
    mitarbeiter_id: uuid.UUID, daten: SystemrolleAenderung,
    db: Session = Depends(get_db), admin_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> MitarbeiterVerwaltung:
    m = _laden(db, mitarbeiter_id, sperren=True)
    if daten.systemrolle == m.systemrolle:
        return _antwort(db, m)
    if m.systemrolle == Systemrolle.admin:  # Herabstufung eines Admins
        if m.id == admin_id:
            raise _konflikt("Du kannst dir nicht selbst die Admin-Rolle entziehen")
        letzter_aktiver_admin_pruefen(db, m)
    alt = m.systemrolle
    m.systemrolle = daten.systemrolle
    protokollieren(db, admin_id, "rolle_geaendert", "mitarbeiter", m.id,
                   {"alt": {"systemrolle": alt.value}, "neu": {"systemrolle": daten.systemrolle.value}})
    db.commit()
    return _antwort(db, m)


def _verlauf(db: Session, mitarbeiter_id: uuid.UUID) -> WochenstundenVerlauf:
    # Name des Ändernden direkt mitliefern (auch deaktivierte Admins)
    eintraege = db.execute(select(MitarbeiterArbeitszeit, Mitarbeiter.name)
                           .outerjoin(Mitarbeiter, MitarbeiterArbeitszeit.geaendert_von_mitarbeiter_id == Mitarbeiter.id)
                           .where(MitarbeiterArbeitszeit.mitarbeiter_id == mitarbeiter_id)
                           .order_by(MitarbeiterArbeitszeit.gueltig_ab.desc())).all()
    return WochenstundenVerlauf(
        aktuell=_aktuelle_wochenstunden(db, mitarbeiter_id),
        eintraege=[WochenstundenEintrag.model_validate(e).model_copy(update={"geaendert_von_name": name})
                   for e, name in eintraege],
    )


@router.get("/{mitarbeiter_id}/wochenstunden", response_model=WochenstundenVerlauf)
def wochenstunden_verlauf(mitarbeiter_id: uuid.UUID, db: Session = Depends(get_db)) -> WochenstundenVerlauf:
    _laden(db, mitarbeiter_id)
    return _verlauf(db, mitarbeiter_id)


@router.post("/{mitarbeiter_id}/wochenstunden", response_model=WochenstundenVerlauf,
             status_code=status.HTTP_201_CREATED)
def wochenstunden_festlegen(
    mitarbeiter_id: uuid.UUID, daten: WochenstundenNeu,
    db: Session = Depends(get_db), admin_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> WochenstundenVerlauf:
    m = _laden(db, mitarbeiter_id, sperren=True)  # Sperre: keine zwei gleichzeitigen Einträge
    if not m.aktiv:
        raise _konflikt("Mitarbeiter ist deaktiviert")
    bisher = db.scalar(select(MitarbeiterArbeitszeit).where(
        MitarbeiterArbeitszeit.mitarbeiter_id == m.id, MitarbeiterArbeitszeit.gueltig_bis.is_(None)))
    if bisher is not None:
        if daten.gueltig_ab <= bisher.gueltig_ab:
            raise _konflikt(
                f"Der bisherige Wert gilt ab {bisher.gueltig_ab:%d.%m.%Y} – ein neuer Wert muss später beginnen"
            )
        bisher.gueltig_bis = daten.gueltig_ab - timedelta(days=1)
        db.flush()  # zuerst abschließen – es darf nur einen offenen Eintrag geben
    neu = MitarbeiterArbeitszeit(
        mitarbeiter_id=m.id, wochenstunden=daten.wochenstunden, gueltig_ab=daten.gueltig_ab,
        geaendert_von_mitarbeiter_id=admin_id,
    )
    db.add(neu)
    db.flush()
    protokollieren(db, admin_id, "wochenstunden_festgelegt", "mitarbeiter", m.id, {
        "alt": None if bisher is None else {"wochenstunden": f"{bisher.wochenstunden:.2f}",
                                            "gueltig_ab": bisher.gueltig_ab.isoformat(),
                                            "gueltig_bis": bisher.gueltig_bis.isoformat()},
        "neu": {"wochenstunden": f"{neu.wochenstunden:.2f}", "gueltig_ab": neu.gueltig_ab.isoformat()},
    })
    db.commit()
    return _verlauf(db, m.id)

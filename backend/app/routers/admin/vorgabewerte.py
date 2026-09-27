"""Pflege der Reparatur-Vorgabewerte (Datenmodell 2.6a) – nur Admin (7.2).

Bewusst ohne Löschen (Grundsatz "kein hartes Löschen"): falsche Werte werden korrigiert.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id
from app.db import get_db
from app.models import Instrumentenklasse, Reparaturart, ReparaturVorgabewert, SystemEreignisLog
from app.schemas import Vorgabewert, VorgabewertAenderung, VorgabewertNeu

router = APIRouter(prefix="/vorgabewerte", tags=["Admin: Vorgabewerte"])

# Felder, die beim Bearbeiten nicht auf null gesetzt werden dürfen
_PFLICHTFELDER = {"reparaturart_id", "vorgabe_stunden", "vorgabe_kosten"}


def _abfrage() -> Select:
    """Vorgabewerte inkl. Bezeichnungen von Reparaturart und Instrumentenklasse."""
    return (
        select(
            ReparaturVorgabewert,
            Reparaturart.bezeichnung.label("reparaturart_bezeichnung"),
            Instrumentenklasse.bezeichnung.label("instrumentenklasse_bezeichnung"),
        )
        .join(Reparaturart, ReparaturVorgabewert.reparaturart_id == Reparaturart.id)
        .outerjoin(Instrumentenklasse, ReparaturVorgabewert.instrumentenklasse_id == Instrumentenklasse.id)
    )


def _als_antwort(zeile) -> Vorgabewert:
    eintrag, reparaturart, instrumentenklasse = zeile
    return Vorgabewert.model_validate(
        {
            **{c.key: getattr(eintrag, c.key) for c in ReparaturVorgabewert.__table__.columns},
            "reparaturart_bezeichnung": reparaturart,
            "instrumentenklasse_bezeichnung": instrumentenklasse,
        }
    )


def _laden(db: Session, vorgabewert_id: uuid.UUID) -> Vorgabewert:
    zeile = db.execute(_abfrage().where(ReparaturVorgabewert.id == vorgabewert_id)).one_or_none()
    if zeile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vorgabewert nicht gefunden")
    return _als_antwort(zeile)


def _verweise_pruefen(db: Session, reparaturart_id: uuid.UUID, instrumentenklasse_id: uuid.UUID | None) -> None:
    if db.get(Reparaturart, reparaturart_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Reparaturart existiert nicht")
    if instrumentenklasse_id is not None and db.get(Instrumentenklasse, instrumentenklasse_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Instrumentenklasse existiert nicht")


@contextmanager
def _doppelte_kombination_abfangen(db: Session) -> Iterator[None]:
    """Wandelt Verstöße gegen "eine Kombination nur einmal" in eine verständliche 409 um."""
    try:
        yield
    except IntegrityError as e:
        db.rollback()
        if "uq_reparatur_vorgabewert_kombination" in str(e.orig):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Für diese Kombination aus Reparaturart und Instrumentenklasse gibt es bereits "
                "einen Vorgabewert – bitte den bestehenden bearbeiten.",
            ) from e
        raise


def _werte(eintrag: ReparaturVorgabewert) -> dict:
    """Protokollierbare Felder als JSON-taugliches Dict."""
    return {
        "reparaturart_id": str(eintrag.reparaturart_id),
        "instrumentenklasse_id": str(eintrag.instrumentenklasse_id) if eintrag.instrumentenklasse_id else None,
        "vorgabe_stunden": f"{eintrag.vorgabe_stunden:.2f}",
        "vorgabe_kosten": f"{eintrag.vorgabe_kosten:.2f}",
        "notiz": eintrag.notiz,
    }


@router.get("", response_model=list[Vorgabewert])
def vorgabewerte_auflisten(
    reparaturart_id: uuid.UUID | None = Query(None, description="Nur Werte dieser Reparaturart"),
    instrumentenklasse_id: uuid.UUID | None = Query(None, description="Nur Werte dieser Instrumentenklasse"),
    db: Session = Depends(get_db),
) -> list[Vorgabewert]:
    abfrage = _abfrage().order_by(
        Reparaturart.bezeichnung, Instrumentenklasse.bezeichnung.asc().nulls_first()
    )
    if reparaturart_id is not None:
        abfrage = abfrage.where(ReparaturVorgabewert.reparaturart_id == reparaturart_id)
    if instrumentenklasse_id is not None:
        abfrage = abfrage.where(ReparaturVorgabewert.instrumentenklasse_id == instrumentenklasse_id)
    return [_als_antwort(z) for z in db.execute(abfrage).all()]


@router.get("/{vorgabewert_id}", response_model=Vorgabewert)
def vorgabewert_abrufen(vorgabewert_id: uuid.UUID, db: Session = Depends(get_db)) -> Vorgabewert:
    return _laden(db, vorgabewert_id)


@router.post("", response_model=Vorgabewert, status_code=status.HTTP_201_CREATED)
def vorgabewert_anlegen(
    daten: VorgabewertNeu,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID | None = Depends(aktueller_mitarbeiter_id),
) -> Vorgabewert:
    _verweise_pruefen(db, daten.reparaturart_id, daten.instrumentenklasse_id)
    eintrag = ReparaturVorgabewert(**daten.model_dump(), geaendert_von_mitarbeiter_id=mitarbeiter_id)
    db.add(eintrag)
    with _doppelte_kombination_abfangen(db):
        db.flush()  # erzeugt die ID
    db.add(SystemEreignisLog(
        ausgefuehrt_von_mitarbeiter_id=mitarbeiter_id,
        aktion="vorgabewert_angelegt",
        betroffene_entitaet="reparatur_vorgabewert",
        betroffene_id=eintrag.id,
        details={"neu": _werte(eintrag)},
    ))
    db.commit()
    return _laden(db, eintrag.id)


@router.patch("/{vorgabewert_id}", response_model=Vorgabewert)
def vorgabewert_bearbeiten(
    vorgabewert_id: uuid.UUID,
    daten: VorgabewertAenderung,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID | None = Depends(aktueller_mitarbeiter_id),
) -> Vorgabewert:
    eintrag = db.get(ReparaturVorgabewert, vorgabewert_id)
    if eintrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vorgabewert nicht gefunden")

    aenderungen = daten.model_dump(exclude_unset=True)
    leer = sorted(f for f in _PFLICHTFELDER if f in aenderungen and aenderungen[f] is None)
    if leer:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Darf nicht leer sein: {', '.join(leer)}")

    _verweise_pruefen(
        db,
        aenderungen.get("reparaturart_id", eintrag.reparaturart_id),
        aenderungen.get("instrumentenklasse_id", eintrag.instrumentenklasse_id),
    )
    alt = _werte(eintrag)
    for feld, wert in aenderungen.items():
        setattr(eintrag, feld, wert)
    eintrag.geaendert_von_mitarbeiter_id = mitarbeiter_id
    with _doppelte_kombination_abfangen(db):
        db.flush()

    db.add(SystemEreignisLog(
        ausgefuehrt_von_mitarbeiter_id=mitarbeiter_id,
        aktion="vorgabewert_geaendert",
        betroffene_entitaet="reparatur_vorgabewert",
        betroffene_id=eintrag.id,
        details={"alt": alt, "neu": _werte(eintrag)},
    ))
    db.commit()
    return _laden(db, eintrag.id)

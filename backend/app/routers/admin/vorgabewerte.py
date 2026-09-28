"""Pflege der Reparatur-Vorgabewerte (Datenmodell 2.6a) – nur Admin (7.2).

Kein hartes Löschen: Ein Wert wird archiviert (archiviert_am) und von der Schätzung dann
ignoriert, z. B. um einen versehentlich angelegten spezifischen Wert zurückzunehmen.
Jede Kombination Reparaturart + Instrumentenklasse gibt es höchstens einmal unter den AKTIVEN
Einträgen; archivierte Einträge lassen sich nur bearbeiten, nachdem sie reaktiviert wurden.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
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


def _verweise_pruefen(db: Session, reparaturart_id: uuid.UUID | None, instrumentenklasse_id: uuid.UUID | None) -> None:
    """Prüft neu gewählte Verknüpfungen (None = nicht prüfen). Bestehende Verknüpfungen zu
    inzwischen archivierten Einträgen bleiben bearbeitbar."""
    if reparaturart_id is not None:
        art = db.get(Reparaturart, reparaturart_id)
        if art is None or art.archiviert_am is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Reparaturart existiert nicht oder ist archiviert")
    if instrumentenklasse_id is not None:
        klasse = db.get(Instrumentenklasse, instrumentenklasse_id)
        if klasse is None or klasse.archiviert_am is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Instrumentenklasse existiert nicht oder ist archiviert")


@contextmanager
def _doppelte_kombination_abfangen(db: Session, reaktivieren: bool = False) -> Iterator[None]:
    """Wandelt Verstöße gegen "eine Kombination nur einmal" in eine verständliche 409 um."""
    try:
        with db.begin_nested():  # bei Fehler nur diesen Speicherversuch zurücknehmen
            yield
    except IntegrityError as e:
        if "uq_reparatur_vorgabewert_kombination" in str(e.orig):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Für diese Kombination aus Reparaturart und Instrumentenklasse ist bereits ein anderer "
                "Vorgabewert aktiv – diesen zuerst archivieren." if reaktivieren else
                "Für diese Kombination aus Reparaturart und Instrumentenklasse gibt es bereits "
                "einen aktiven Vorgabewert – bitte den bestehenden bearbeiten.",
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
    archivierte: bool = Query(False, description="Auch archivierte Vorgabewerte anzeigen"),
    db: Session = Depends(get_db),
) -> list[Vorgabewert]:
    abfrage = _abfrage().order_by(
        Reparaturart.bezeichnung, Instrumentenklasse.bezeichnung.asc().nulls_first(),
        ReparaturVorgabewert.archiviert_am.asc().nulls_first(),
    )
    if not archivierte:
        abfrage = abfrage.where(ReparaturVorgabewert.archiviert_am.is_(None))
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
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> Vorgabewert:
    _verweise_pruefen(db, daten.reparaturart_id, daten.instrumentenklasse_id)
    eintrag = ReparaturVorgabewert(**daten.model_dump(), geaendert_von_mitarbeiter_id=mitarbeiter_id)
    with _doppelte_kombination_abfangen(db):
        db.add(eintrag)  # innerhalb des Speicherpunkts: bei Fehler wieder entfernt
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
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> Vorgabewert:
    eintrag = db.get(ReparaturVorgabewert, vorgabewert_id)
    if eintrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vorgabewert nicht gefunden")
    if eintrag.archiviert_am is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Vorgabewert ist archiviert – zum Bearbeiten erst reaktivieren")

    aenderungen = daten.model_dump(exclude_unset=True)
    leer = sorted(f for f in _PFLICHTFELDER if f in aenderungen and aenderungen[f] is None)
    if leer:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Darf nicht leer sein: {', '.join(leer)}")

    _verweise_pruefen(
        db,
        aenderungen.get("reparaturart_id") if aenderungen.get("reparaturart_id") != eintrag.reparaturart_id else None,
        aenderungen.get("instrumentenklasse_id")
        if aenderungen.get("instrumentenklasse_id") != eintrag.instrumentenklasse_id else None,
    )
    alt = _werte(eintrag)
    with _doppelte_kombination_abfangen(db):  # Änderungen innerhalb: bei Fehler wieder verworfen
        for feld, wert in aenderungen.items():
            setattr(eintrag, feld, wert)
        eintrag.geaendert_von_mitarbeiter_id = mitarbeiter_id
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


def _archiv_umschalten(db: Session, vorgabewert_id: uuid.UUID, mitarbeiter_id: uuid.UUID, archivieren: bool) -> Vorgabewert:
    eintrag = db.get(ReparaturVorgabewert, vorgabewert_id, with_for_update=True)
    if eintrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vorgabewert nicht gefunden")
    if (eintrag.archiviert_am is not None) == archivieren:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Vorgabewert ist {'bereits' if archivieren else 'nicht'} archiviert")
    alt = eintrag.archiviert_am
    zeitpunkt = db.scalar(select(func.clock_timestamp())) if archivieren else None
    with _doppelte_kombination_abfangen(db, reaktivieren=not archivieren):
        eintrag.archiviert_am = zeitpunkt
        eintrag.geaendert_von_mitarbeiter_id = mitarbeiter_id
        db.flush()  # beim Reaktivieren prüft die Datenbank, ob die Kombination schon aktiv vergeben ist
    db.add(SystemEreignisLog(
        ausgefuehrt_von_mitarbeiter_id=mitarbeiter_id,
        aktion="vorgabewert_archiviert" if archivieren else "vorgabewert_reaktiviert",
        betroffene_entitaet="reparatur_vorgabewert",
        betroffene_id=eintrag.id,
        details={"alt": {"archiviert_am": alt.isoformat() if alt else None},
                 "neu": {"archiviert_am": eintrag.archiviert_am.isoformat() if eintrag.archiviert_am else None},
                 **_werte(eintrag)},
    ))
    db.commit()
    return _laden(db, eintrag.id)


@router.post("/{vorgabewert_id}/archivieren", response_model=Vorgabewert)
def vorgabewert_archivieren(
    vorgabewert_id: uuid.UUID,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> Vorgabewert:
    """Nimmt einen Wert zurück: Die Schätzung ignoriert ihn, es greift wieder der allgemeine Wert
    bzw. der historische Durchschnitt. Nichts wird gelöscht."""
    return _archiv_umschalten(db, vorgabewert_id, mitarbeiter_id, archivieren=True)


@router.post("/{vorgabewert_id}/reaktivieren", response_model=Vorgabewert)
def vorgabewert_reaktivieren(
    vorgabewert_id: uuid.UUID,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> Vorgabewert:
    """Nur möglich, wenn für dieselbe Kombination kein anderer Wert aktiv ist."""
    return _archiv_umschalten(db, vorgabewert_id, mitarbeiter_id, archivieren=False)

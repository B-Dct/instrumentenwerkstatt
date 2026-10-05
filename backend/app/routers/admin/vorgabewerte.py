"""Pflege der Reparatur-Vorgabewerte (Datenmodell 2.6a) – nur Admin (7.2).

Kein hartes Löschen: Ein Wert wird archiviert (archiviert_am) und von der Schätzung dann
ignoriert, z. B. um einen versehentlich angelegten spezifischen Wert zurückzunehmen.
Jede Kombination Reparaturart + Instrumentenklasse + Ausführung gibt es höchstens einmal unter den
AKTIVEN Einträgen; archivierte Einträge lassen sich nur bearbeiten, nachdem sie reaktiviert wurden.

Ausführungen (2.4b, 2.6a): Hat die Instrumentenklasse Ausführungen, verweist jeder ihrer Richtpreise auf
eine davon (ausfuehrung_id); hat sie keine, verweisen ihre Richtpreise auf keine. Allgemeine Werte haben
nie eine Ausführung. Benennen, Standard und Archivieren geschehen an der Ausführung selbst
(routers/admin/ausfuehrungen.py), nicht am einzelnen Richtpreis.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id
from app.db import get_db
from app.eingabe import feldfehler
from app.listen import ListenParameter, Seite, enthaelt, listen_parameter, seite_abfragen
from app.speichern import sicher_speichern
from app.models import Ausfuehrung, Instrumentenklasse, Reparaturart, ReparaturVorgabewert, SystemEreignisLog
from app.schaetzung import aktive_ausfuehrungen
from app.schemas import Vorgabewert, VorgabewertAenderung, VorgabewertNeu

router = APIRouter(prefix="/vorgabewerte", tags=["Admin: Vorgabewerte"])

# Felder, die beim Bearbeiten nicht auf null gesetzt werden dürfen
_PFLICHTFELDER = {"reparaturart_id", "vorgabe_stunden", "vorgabe_kosten"}


def _abfrage() -> Select:
    """Vorgabewerte inkl. Bezeichnungen von Reparaturart, Instrumentenklasse und Ausführung."""
    return (
        select(
            ReparaturVorgabewert,
            Reparaturart.bezeichnung.label("reparaturart_bezeichnung"),
            Instrumentenklasse.bezeichnung.label("instrumentenklasse_bezeichnung"),
            Ausfuehrung,
        )
        .join(Reparaturart, ReparaturVorgabewert.reparaturart_id == Reparaturart.id)
        .outerjoin(Instrumentenklasse, ReparaturVorgabewert.instrumentenklasse_id == Instrumentenklasse.id)
        .outerjoin(Ausfuehrung, ReparaturVorgabewert.ausfuehrung_id == Ausfuehrung.id)
    )


def _als_antwort(zeile) -> Vorgabewert:
    eintrag, reparaturart, instrumentenklasse, ausfuehrung = zeile
    return Vorgabewert.model_validate(
        {
            **{c.key: getattr(eintrag, c.key) for c in ReparaturVorgabewert.__table__.columns},
            "reparaturart_bezeichnung": reparaturart,
            "instrumentenklasse_bezeichnung": instrumentenklasse,
            "ausfuehrung": ausfuehrung.bezeichnung if ausfuehrung else None,
            "ausfuehrung_ist_standard": bool(ausfuehrung and ausfuehrung.ist_standard and ausfuehrung.archiviert_am is None),
            "ausfuehrung_archiviert": bool(ausfuehrung and ausfuehrung.archiviert_am),
        }
    )


def _laden(db: Session, vorgabewert_id: uuid.UUID) -> Vorgabewert:
    zeile = db.execute(_abfrage().where(ReparaturVorgabewert.id == vorgabewert_id)).one_or_none()
    if zeile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richtpreis nicht gefunden")
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


def _ausfuehrung_pruefen(db: Session, instrumentenklasse_id: uuid.UUID | None, ausfuehrung_id: uuid.UUID | None) -> None:
    """Hat die Klasse (aktive) Ausführungen, gehört jeder ihrer Richtpreise zu einer davon – sonst zu keiner (2.4b)."""
    if instrumentenklasse_id is None:
        if ausfuehrung_id is not None:
            raise feldfehler(ausfuehrung_id="Eine Ausführung ist nur zusammen mit einer Instrumentenklasse möglich")
        return
    aktive = {a.id for a in aktive_ausfuehrungen(db, instrumentenklasse_id)}
    if ausfuehrung_id is None and aktive:
        raise feldfehler(ausfuehrung_id="Diese Instrumentenklasse hat Ausführungen – bitte eine auswählen")
    if ausfuehrung_id is not None and ausfuehrung_id not in aktive:
        raise feldfehler(ausfuehrung_id="Diese Ausführung gibt es für die Instrumentenklasse nicht (oder sie ist archiviert)")


# Passendere Meldung beim Reaktivieren (sonst gilt die zentrale aus app/speichern.py)
REAKTIVIEREN_MELDUNGEN = {
    "uq_reparatur_vorgabewert_kombination":
        "Für diese Kombination aus Reparaturart, Instrumentenklasse und Ausführung ist bereits ein anderer "
        "Richtpreis aktiv – diesen zuerst archivieren.",
}


def _werte(eintrag: ReparaturVorgabewert) -> dict:
    """Protokollierbare Felder als JSON-taugliches Dict."""
    return {
        "reparaturart_id": str(eintrag.reparaturart_id),
        "instrumentenklasse_id": str(eintrag.instrumentenklasse_id) if eintrag.instrumentenklasse_id else None,
        "ausfuehrung_id": str(eintrag.ausfuehrung_id) if eintrag.ausfuehrung_id else None,
        "vorgabe_stunden": f"{eintrag.vorgabe_stunden:.2f}",
        "vorgabe_kosten": f"{eintrag.vorgabe_kosten:.2f}",
        "notiz": eintrag.notiz,
    }


# "Gilt für": allgemeine Werte (ohne Klasse) vor den speziellen
_GILT_FUER = func.coalesce(Instrumentenklasse.bezeichnung, "")
# Bei gleicher Kombination (nur mit "alle"/"archiviert" möglich): der aktive vor den archivierten
_AKTIVE_ZUERST = ReparaturVorgabewert.archiviert_am.is_not(None)

_AUSFUEHRUNG = func.coalesce(func.lower(Ausfuehrung.bezeichnung), "")
_STANDARD_ZUERST = func.coalesce(Ausfuehrung.ist_standard, False).is_(False)

SORTIERUNG = {
    # Innerhalb der Instrumentenklasse: Standardausführung zuerst, dann die Ausführungen alphabetisch
    "reparaturart": (Reparaturart.bezeichnung, _GILT_FUER, _STANDARD_ZUERST, _AUSFUEHRUNG, _AKTIVE_ZUERST),
    "gilt_fuer": (_GILT_FUER, Reparaturart.bezeichnung, _STANDARD_ZUERST, _AUSFUEHRUNG, _AKTIVE_ZUERST),
    "vorgabe_stunden": (ReparaturVorgabewert.vorgabe_stunden, Reparaturart.bezeichnung, _GILT_FUER),
    "vorgabe_kosten": (ReparaturVorgabewert.vorgabe_kosten, Reparaturart.bezeichnung, _GILT_FUER),
    "geaendert_am": ReparaturVorgabewert.geaendert_am,
}


@router.get("", response_model=Seite[Vorgabewert])
def vorgabewerte_auflisten(
    liste: ListenParameter = Depends(listen_parameter(SORTIERUNG, standard="reparaturart")),
    reparaturart_id: uuid.UUID | None = Query(None, description="Nur Werte dieser Reparaturart"),
    instrumentenklasse_id: uuid.UUID | None = Query(None, description="Nur Werte dieser Instrumentenklasse"),
    status_: Literal["aktiv", "archiviert", "alle"] = Query("aktiv", alias="status"),
    db: Session = Depends(get_db),
) -> Seite[Vorgabewert]:
    """Liste nach 9.11: Suche (Reparaturart, Instrumentenklasse, Notiz), Filter, Sortierung, seitenweise.
    Standard: nach Reparaturart, darin der allgemeine Wert vor den speziellen."""
    basis = _abfrage()
    gefiltert = basis
    if (muster := liste.suchmuster()) is not None:
        gefiltert = gefiltert.where(enthaelt(muster, Reparaturart.bezeichnung, Instrumentenklasse.bezeichnung,
                                             Ausfuehrung.bezeichnung, ReparaturVorgabewert.notiz))
    if status_ == "aktiv":
        gefiltert = gefiltert.where(ReparaturVorgabewert.archiviert_am.is_(None))
    elif status_ == "archiviert":
        gefiltert = gefiltert.where(ReparaturVorgabewert.archiviert_am.is_not(None))
    if reparaturart_id is not None:
        gefiltert = gefiltert.where(ReparaturVorgabewert.reparaturart_id == reparaturart_id)
    if instrumentenklasse_id is not None:
        gefiltert = gefiltert.where(ReparaturVorgabewert.instrumentenklasse_id == instrumentenklasse_id)
    return seite_abfragen(db, basis, gefiltert, liste, SORTIERUNG, umwandeln=_als_antwort,
                          eindeutig=ReparaturVorgabewert.id)


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
    _ausfuehrung_pruefen(db, daten.instrumentenklasse_id, daten.ausfuehrung_id)
    eintrag = ReparaturVorgabewert(**daten.model_dump(), geaendert_von_mitarbeiter_id=mitarbeiter_id)
    with sicher_speichern(db):
        db.add(eintrag)  # erzeugt beim Speichern die ID
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richtpreis nicht gefunden")
    if eintrag.archiviert_am is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Richtpreis ist archiviert – zum Bearbeiten erst reaktivieren")

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
    klasse_id = aenderungen.get("instrumentenklasse_id", eintrag.instrumentenklasse_id)
    ausfuehrung_id = aenderungen.get("ausfuehrung_id", eintrag.ausfuehrung_id)
    # Nur prüfen, wenn sich an Klasse oder Ausführung etwas ändert – Preis und Notiz bleiben auch dann
    # bearbeitbar, wenn die Ausführung inzwischen archiviert ist
    if (klasse_id, ausfuehrung_id) != (eintrag.instrumentenklasse_id, eintrag.ausfuehrung_id):
        _ausfuehrung_pruefen(db, klasse_id, ausfuehrung_id)
    alt = _werte(eintrag)
    with sicher_speichern(db):
        for feld, wert in aenderungen.items():
            setattr(eintrag, feld, wert)
        eintrag.geaendert_von_mitarbeiter_id = mitarbeiter_id

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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richtpreis nicht gefunden")
    if (eintrag.archiviert_am is not None) == archivieren:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Richtpreis ist {'bereits' if archivieren else 'nicht'} archiviert")
    alt = eintrag.archiviert_am
    if not archivieren:  # die Regeln aus 2.4b müssen auch für den zurückgeholten Wert gelten
        try:
            _ausfuehrung_pruefen(db, eintrag.instrumentenklasse_id, eintrag.ausfuehrung_id)
        except HTTPException:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Die Ausführungen dieser Instrumentenklasse haben sich inzwischen geändert – "
                                "bitte den Wert in der Preisliste neu anlegen") from None
    zeitpunkt = db.scalar(select(func.clock_timestamp())) if archivieren else None
    # Beim Reaktivieren prüft die Datenbank, ob die Kombination schon aktiv vergeben ist
    with sicher_speichern(db, None if archivieren else REAKTIVIEREN_MELDUNGEN):
        eintrag.archiviert_am = zeitpunkt
        eintrag.geaendert_von_mitarbeiter_id = mitarbeiter_id
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

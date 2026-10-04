"""Pflege der Reparatur-Vorgabewerte (Datenmodell 2.6a) – nur Admin (7.2).

Kein hartes Löschen: Ein Wert wird archiviert (archiviert_am) und von der Schätzung dann
ignoriert, z. B. um einen versehentlich angelegten spezifischen Wert zurückzunehmen.
Jede Kombination Reparaturart + Instrumentenklasse + Ausführung gibt es höchstens einmal unter den
AKTIVEN Einträgen; archivierte Einträge lassen sich nur bearbeiten, nachdem sie reaktiviert wurden.

Ausführungen und Standard (2.6a): Eine Kombination aus Reparaturart und Instrumentenklasse hat entweder
genau einen Wert ohne Ausführung (keine Varianten) oder mehrere, die alle einen Namen tragen
(z. B. "Perinet, versilbert") – genau einer davon ist der Standard (ist_standard). Wird eine Ausführung
umbenannt, ziehen die übrigen Richtpreise der Klasse mit diesem Namen und die Instrumente der Klasse
in derselben Transaktion mit (2.5).
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id
from app.db import get_db
from app.eingabe import feldfehler
from app.listen import ListenParameter, Seite, enthaelt, listen_parameter, seite_abfragen
from app.speichern import sicher_speichern
from app.ereignisse import protokollieren
from app.models import Instrument, Instrumentenklasse, Reparaturart, ReparaturVorgabewert, SystemEreignisLog
from app.schemas import Vorgabewert, VorgabewertAenderung, VorgabewertNeu

router = APIRouter(prefix="/vorgabewerte", tags=["Admin: Vorgabewerte"])

# Felder, die beim Bearbeiten nicht auf null gesetzt werden dürfen
_PFLICHTFELDER = {"reparaturart_id", "vorgabe_stunden", "vorgabe_kosten"}


# Aktive Instrumente der Klasse, an denen genau diese Ausführung hinterlegt ist (2.5)
_INSTRUMENTE = (
    select(func.count()).select_from(Instrument)
    .where(Instrument.instrumentenklasse_id == ReparaturVorgabewert.instrumentenklasse_id,
           Instrument.ausfuehrung == ReparaturVorgabewert.ausfuehrung,
           Instrument.archiviert_am.is_(None))
    .correlate(ReparaturVorgabewert).scalar_subquery()
)


def _abfrage() -> Select:
    """Vorgabewerte inkl. Bezeichnungen von Reparaturart und Instrumentenklasse."""
    return (
        select(
            ReparaturVorgabewert,
            Reparaturart.bezeichnung.label("reparaturart_bezeichnung"),
            Instrumentenklasse.bezeichnung.label("instrumentenklasse_bezeichnung"),
            _INSTRUMENTE.label("instrumente_mit_ausfuehrung"),
        )
        .join(Reparaturart, ReparaturVorgabewert.reparaturart_id == Reparaturart.id)
        .outerjoin(Instrumentenklasse, ReparaturVorgabewert.instrumentenklasse_id == Instrumentenklasse.id)
    )


def _als_antwort(zeile) -> Vorgabewert:
    eintrag, reparaturart, instrumentenklasse, instrumente = zeile
    return Vorgabewert.model_validate(
        {
            **{c.key: getattr(eintrag, c.key) for c in ReparaturVorgabewert.__table__.columns},
            "reparaturart_bezeichnung": reparaturart,
            "instrumentenklasse_bezeichnung": instrumentenklasse,
            "instrumente_mit_ausfuehrung": instrumente,
        }
    )


def _laden(db: Session, vorgabewert_id: uuid.UUID, **zusatz) -> Vorgabewert:
    zeile = db.execute(_abfrage().where(ReparaturVorgabewert.id == vorgabewert_id)).one_or_none()
    if zeile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richtpreis nicht gefunden")
    return _als_antwort(zeile).model_copy(update=zusatz)


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


def _ausfuehrung_pruefen(instrumentenklasse_id: uuid.UUID | None, ausfuehrung: str | None) -> None:
    """Eine Ausführung verfeinert innerhalb einer Instrumentenklasse – ohne Klasse ergibt sie keinen Sinn."""
    if ausfuehrung is not None and instrumentenklasse_id is None:
        raise feldfehler(ausfuehrung="Eine Ausführung ist nur zusammen mit einer Instrumentenklasse möglich")


def _andere_aktive(db: Session, reparaturart_id: uuid.UUID, instrumentenklasse_id: uuid.UUID,
                   ausser: uuid.UUID | None = None) -> list[ReparaturVorgabewert]:
    """Die übrigen aktiven Werte derselben Kombination aus Reparaturart und Instrumentenklasse (gesperrt)."""
    abfrage = select(ReparaturVorgabewert).where(
        ReparaturVorgabewert.archiviert_am.is_(None),
        ReparaturVorgabewert.reparaturart_id == reparaturart_id,
        ReparaturVorgabewert.instrumentenklasse_id == instrumentenklasse_id,
    ).with_for_update()
    if ausser is not None:
        abfrage = abfrage.where(ReparaturVorgabewert.id != ausser)
    return list(db.scalars(abfrage))


def _namen_pruefen(ausfuehrung: str | None, andere: list[ReparaturVorgabewert]) -> None:
    """Sobald es mehrere Ausführungen gibt, trägt jede einen Namen (2.6a)."""
    if ausfuehrung is None and andere:
        raise feldfehler(ausfuehrung="Diese Kombination hat mehrere Ausführungen – bitte einen Namen angeben")
    if ausfuehrung is not None and any(a.ausfuehrung is None for a in andere):
        raise feldfehler(ausfuehrung="Der bestehende Wert dieser Kombination hat noch keinen Namen – "
                                     "bitte zuerst ihm eine Ausführung geben (er wird der Standard)")


def _standard_uebernehmen(db: Session, andere: list[ReparaturVorgabewert], mitarbeiter_id: uuid.UUID) -> None:
    """Der bisherige Standard verliert das Kennzeichen – vor dem Speichern des neuen (Datenbank-Index)."""
    for a in andere:
        if a.ist_standard:
            a.ist_standard = False
            a.geaendert_von_mitarbeiter_id = mitarbeiter_id
    db.flush()


def _ausfuehrung_umbenennen(db: Session, eintrag: ReparaturVorgabewert, alt: str, neu: str,
                            mitarbeiter_id: uuid.UUID) -> dict[str, int]:
    """Eine Ausführung heißt in der ganzen Instrumentenklasse gleich: Die übrigen aktiven Richtpreise der
    Klasse mit dem alten Namen und die Instrumente der Klasse ziehen mit, damit kein Instrument unbemerkt
    auf den Standard zurückfällt (2.5)."""
    richtpreise = db.execute(
        update(ReparaturVorgabewert).where(
            ReparaturVorgabewert.instrumentenklasse_id == eintrag.instrumentenklasse_id,
            ReparaturVorgabewert.ausfuehrung == alt, ReparaturVorgabewert.archiviert_am.is_(None),
            ReparaturVorgabewert.id != eintrag.id,
        ).values(ausfuehrung=neu, geaendert_von_mitarbeiter_id=mitarbeiter_id)
    ).rowcount
    instrumente = list(db.scalars(select(Instrument).where(
        Instrument.instrumentenklasse_id == eintrag.instrumentenklasse_id, Instrument.ausfuehrung == alt)))
    for instrument in instrumente:
        instrument.ausfuehrung = neu
        protokollieren(db, mitarbeiter_id, "instrument_geaendert", "instrument", instrument.id,
                       {"alt": {"ausfuehrung": alt}, "neu": {"ausfuehrung": neu}, "anlass": "ausfuehrung_umbenannt"})
    return {"umbenannte_instrumente": len(instrumente), "umbenannte_richtpreise": richtpreise}


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
        "ausfuehrung": eintrag.ausfuehrung,
        "ist_standard": eintrag.ist_standard,
        "vorgabe_stunden": f"{eintrag.vorgabe_stunden:.2f}",
        "vorgabe_kosten": f"{eintrag.vorgabe_kosten:.2f}",
        "notiz": eintrag.notiz,
    }


# "Gilt für": allgemeine Werte (ohne Klasse) vor den speziellen
_GILT_FUER = func.coalesce(Instrumentenklasse.bezeichnung, "")
# Bei gleicher Kombination (nur mit "alle"/"archiviert" möglich): der aktive vor den archivierten
_AKTIVE_ZUERST = ReparaturVorgabewert.archiviert_am.is_not(None)

_AUSFUEHRUNG = func.coalesce(ReparaturVorgabewert.ausfuehrung, "")
_STANDARD_ZUERST = ReparaturVorgabewert.ist_standard.is_(False)

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
                                             ReparaturVorgabewert.ausfuehrung, ReparaturVorgabewert.notiz))
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
    _ausfuehrung_pruefen(daten.instrumentenklasse_id, daten.ausfuehrung)
    eintrag = ReparaturVorgabewert(**daten.model_dump(), geaendert_von_mitarbeiter_id=mitarbeiter_id)
    eintrag.ist_standard = False
    with sicher_speichern(db):
        if daten.instrumentenklasse_id is not None:
            andere = _andere_aktive(db, daten.reparaturart_id, daten.instrumentenklasse_id)
            if not (daten.ausfuehrung is None and any(a.ausfuehrung is None for a in andere)):  # sonst: "gibt es bereits"
                _namen_pruefen(daten.ausfuehrung, andere)
            # Die erste benannte Ausführung einer Kombination ist ihr Standard
            eintrag.ist_standard = daten.ausfuehrung is not None and (daten.ist_standard or not andere)
            if eintrag.ist_standard:
                _standard_uebernehmen(db, andere, mitarbeiter_id)
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
    art_id = aenderungen.get("reparaturart_id", eintrag.reparaturart_id)
    klasse_id = aenderungen.get("instrumentenklasse_id", eintrag.instrumentenklasse_id)
    ausfuehrung = aenderungen.get("ausfuehrung", eintrag.ausfuehrung)
    _ausfuehrung_pruefen(klasse_id, ausfuehrung)
    gewuenscht = aenderungen.pop("ist_standard", None)
    verschoben = (art_id, klasse_id) != (eintrag.reparaturart_id, eintrag.instrumentenklasse_id)
    alt = _werte(eintrag)
    umbenannt: dict[str, int] = {}
    with sicher_speichern(db):
        if verschoben and eintrag.ist_standard and _andere_aktive(
                db, eintrag.reparaturart_id, eintrag.instrumentenklasse_id, ausser=eintrag.id):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Das ist die Standardausführung – bitte zuerst eine andere Ausführung zum Standard machen")
        andere = _andere_aktive(db, art_id, klasse_id, ausser=eintrag.id) if klasse_id is not None else []
        if klasse_id is not None:
            _namen_pruefen(ausfuehrung, andere)
        if ausfuehrung is None:
            ist_standard = False
        elif not andere or gewuenscht:
            ist_standard = True  # die einzige benannte Ausführung ist zwangsläufig der Standard
        elif gewuenscht is False and eintrag.ist_standard and not verschoben:
            raise feldfehler(ist_standard="Genau eine Ausführung ist Standard – bitte stattdessen eine andere zum Standard machen")
        else:
            ist_standard = eintrag.ist_standard and not verschoben
        if ist_standard and not (eintrag.ist_standard and not verschoben):
            _standard_uebernehmen(db, andere, mitarbeiter_id)
        if not verschoben and eintrag.ausfuehrung is not None and ausfuehrung not in (None, eintrag.ausfuehrung):
            umbenannt = _ausfuehrung_umbenennen(db, eintrag, eintrag.ausfuehrung, ausfuehrung, mitarbeiter_id)
        for feld, wert in aenderungen.items():
            setattr(eintrag, feld, wert)
        eintrag.ist_standard = ist_standard
        eintrag.geaendert_von_mitarbeiter_id = mitarbeiter_id

    db.add(SystemEreignisLog(
        ausgefuehrt_von_mitarbeiter_id=mitarbeiter_id,
        aktion="vorgabewert_geaendert",
        betroffene_entitaet="reparatur_vorgabewert",
        betroffene_id=eintrag.id,
        details={"alt": alt, "neu": _werte(eintrag), **umbenannt},
    ))
    db.commit()
    return _laden(db, eintrag.id, **umbenannt)


def _archiv_umschalten(db: Session, vorgabewert_id: uuid.UUID, mitarbeiter_id: uuid.UUID, archivieren: bool) -> Vorgabewert:
    eintrag = db.get(ReparaturVorgabewert, vorgabewert_id, with_for_update=True)
    if eintrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richtpreis nicht gefunden")
    if (eintrag.archiviert_am is not None) == archivieren:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Richtpreis ist {'bereits' if archivieren else 'nicht'} archiviert")
    alt = eintrag.archiviert_am
    andere = (_andere_aktive(db, eintrag.reparaturart_id, eintrag.instrumentenklasse_id, ausser=eintrag.id)
              if eintrag.instrumentenklasse_id is not None else [])
    if archivieren and eintrag.ist_standard and andere:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Das ist die Standardausführung – bitte zuerst eine andere Ausführung zum Standard machen")
    if not archivieren and andere and not any(a.ausfuehrung == eintrag.ausfuehrung for a in andere):  # sonst: Index-Meldung
        if eintrag.ausfuehrung is None or any(a.ausfuehrung is None for a in andere):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Für diese Kombination gibt es inzwischen andere aktive Werte – bei mehreren "
                                "Ausführungen muss jede einen Namen tragen. Bitte dort als neue Ausführung anlegen.")
    zeitpunkt = db.scalar(select(func.clock_timestamp())) if archivieren else None
    # Beim Reaktivieren prüft die Datenbank, ob die Kombination schon aktiv vergeben ist
    with sicher_speichern(db, None if archivieren else REAKTIVIEREN_MELDUNGEN):
        eintrag.archiviert_am = zeitpunkt
        if not archivieren:  # als einzige benannte Ausführung Standard, neben anderen nicht
            eintrag.ist_standard = eintrag.ausfuehrung is not None and not andere
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

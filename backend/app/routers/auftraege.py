"""Auftragsverwaltung (Datenmodell 2.7 auftrag, 2.8 statusverlauf, 2.10 schaetzungs_log, 4.2).

Grundsätze:
- Status wird nie einfach überschrieben: jeder Wechsel erzeugt einen Eintrag im
  auftrag_statusverlauf; auftrag.status_aktuell_id ist nur die schnelle Kopie.
- Schätzungen werden nie überschrieben: jede automatische Schätzung und jede manuelle
  Korrektur ist ein eigener Eintrag im schaetzungs_log.

TODO: Sobald Login/Rollen implementiert sind (siehe ARCHITECTURE.md, Abschnitt 4
"Berechtigungskonzept") – Liste für Systemrolle "mitarbeiter" auf eigene Aufträge
einschränken; Zugriffe auf einzelne Aufträge über darf_auftrag_bearbeiten prüfen.
Derzeit sind alle Endpunkte hier UNGESCHÜTZT.
"""

import secrets
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, select, text
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter_id, angemeldeter_mitarbeiter_id, darf_auftrag_bearbeiten
from app.db import get_db
from app.models import (
    Arbeitszeiterfassung,
    Auftrag,
    Auftragsstatus,
    AuftragStatusverlauf,
    Instrument,
    Instrumentenklasse,
    Kunde,
    Mitarbeiter,
    Prioritaet,
    Reparaturart,
    SchaetzungsLog,
)
from app.schaetzung import MINDESTANZAHL_VERGLEICHSFAELLE, Schaetzung, schaetze_arbeitsstunden, schaetze_kosten
from app.schemas import (
    AuftragDetail,
    AuftragKurz,
    AuftragNeu,
    SchaetzungKorrektur,
    SchaetzungsLogEintrag,
    StatusKurz,
    StatusverlaufEintrag,
    Statuswechsel,
)

router = APIRouter(prefix="/auftraege", tags=["Aufträge"])

STARTSTATUS = "angenommen"
METHODE_REGELBASIERT = "regelbasiert"
METHODE_KORREKTUR = "manuelle_korrektur"

# Ohne leicht verwechselbare Zeichen (0/O, 1/l/I) – Kunden tippen den Code ab.
# 12 Zeichen aus 31 → ca. 59 Bit Zufall, kryptografisch sicher (Datenmodell 6.2).
_TOKEN_ZEICHEN = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_TOKEN_LAENGE = 12


def _neues_zugriffstoken() -> str:
    return "".join(secrets.choice(_TOKEN_ZEICHEN) for _ in range(_TOKEN_LAENGE))


def _neue_auftragsnummer(db: Session) -> str:
    laufende_nr = db.execute(text("SELECT nextval('auftragsnummer_seq')")).scalar_one()
    return f"{date.today().year}-{laufende_nr:05d}"


def _schaetzung_als_faktor(s: Schaetzung) -> dict:
    return {
        "wert": None if s.wert is None else str(s.wert),
        "quelle": s.quelle.value,
        "anzahl_vergleichsfaelle": s.anzahl_vergleichsfaelle,
    }


# --- Lesen ------------------------------------------------------------------

def _listen_abfrage() -> Select:
    return (
        select(
            Auftrag,
            Kunde.name,
            Instrumentenklasse.bezeichnung,
            Reparaturart.bezeichnung,
            Mitarbeiter.name,
            Auftragsstatus,
        )
        .join(Kunde, Auftrag.kunde_id == Kunde.id)
        .join(Instrument, Auftrag.instrument_id == Instrument.id)
        .join(Instrumentenklasse, Instrument.instrumentenklasse_id == Instrumentenklasse.id)
        .join(Reparaturart, Auftrag.reparaturart_id == Reparaturart.id)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .outerjoin(Mitarbeiter, Auftrag.zugewiesener_mitarbeiter_id == Mitarbeiter.id)
    )


def _status_kurz(s: Auftragsstatus) -> StatusKurz:
    return StatusKurz(id=s.id, schluessel=s.schluessel, bezeichnung=s.bezeichnung, farbe=s.farbe)


def _kurz_felder(zeile) -> dict:
    a, kunde_name, klasse, reparaturart, mitarbeiter_name, status_ = zeile
    return {
        "id": a.id,
        "auftragsnummer": a.auftragsnummer,
        "kunde_id": a.kunde_id,
        "kunde_name": kunde_name,
        "instrument_id": a.instrument_id,
        "instrumentenklasse_bezeichnung": klasse,
        "reparaturart_id": a.reparaturart_id,
        "reparaturart_bezeichnung": reparaturart,
        "zugewiesener_mitarbeiter_id": a.zugewiesener_mitarbeiter_id,
        "zugewiesener_mitarbeiter_name": mitarbeiter_name,
        "prioritaet": a.prioritaet,
        "komplexitaet": a.komplexitaet,
        "status": _status_kurz(status_),
        "erstellt_am": a.erstellt_am,
        "geschaetzte_arbeitsstunden": a.geschaetzte_arbeitsstunden,
        "geschaetzte_kosten": a.geschaetzte_kosten,
        "geschaetztes_fertigstellungsdatum": a.geschaetztes_fertigstellungsdatum,
    }


def _detail(db: Session, auftrag_id: uuid.UUID) -> AuftragDetail:
    zeile = db.execute(_listen_abfrage().where(Auftrag.id == auftrag_id)).one_or_none()
    if zeile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Auftrag nicht gefunden")
    a = zeile[0]
    verlauf = db.execute(
        select(AuftragStatusverlauf, Auftragsstatus)
        .join(Auftragsstatus, AuftragStatusverlauf.status_id == Auftragsstatus.id)
        .where(AuftragStatusverlauf.auftrag_id == auftrag_id)
        .order_by(AuftragStatusverlauf.geaendert_am, AuftragStatusverlauf.id)
    ).all()
    schaetzungen = db.scalars(
        select(SchaetzungsLog)
        .where(SchaetzungsLog.auftrag_id == auftrag_id)
        .order_by(SchaetzungsLog.berechnet_am, SchaetzungsLog.id)
    ).all()
    return AuftragDetail(
        **_kurz_felder(zeile),
        zugriffstoken=a.zugriffstoken,
        geschaetzte_bandbreite_von=a.geschaetzte_bandbreite_von,
        geschaetzte_bandbreite_bis=a.geschaetzte_bandbreite_bis,
        tatsaechliches_fertigstellungsdatum=a.tatsaechliches_fertigstellungsdatum,
        tatsaechliche_kosten=a.tatsaechliche_kosten,
        notizen=a.notizen,
        statusverlauf=[
            StatusverlaufEintrag(
                status=_status_kurz(s),
                geaendert_am=v.geaendert_am,
                geaendert_von_mitarbeiter_id=v.geaendert_von_mitarbeiter_id,
                kommentar=v.kommentar,
            )
            for v, s in verlauf
        ],
        schaetzungen=[SchaetzungsLogEintrag.model_validate(s) for s in schaetzungen],
    )


def _auftrag_laden(db: Session, auftrag_id: uuid.UUID) -> Auftrag:
    # FOR UPDATE: gleichzeitige Änderungen am selben Auftrag laufen nacheinander
    auftrag = db.get(Auftrag, auftrag_id, with_for_update=True)
    if auftrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Auftrag nicht gefunden")
    return auftrag


@router.get("", response_model=list[AuftragKurz])
def auftraege_auflisten(
    status_id: uuid.UUID | None = Query(None, description="Nur Aufträge in diesem Status"),
    nur_offene: bool = Query(False, description="Nur nicht abgeschlossene Aufträge"),
    zugewiesener_mitarbeiter_id: uuid.UUID | None = Query(None),
    kunde_id: uuid.UUID | None = Query(None),
    prioritaet: Prioritaet | None = Query(None),
    db: Session = Depends(get_db),
) -> list[AuftragKurz]:
    """Standard-Sortierung (Datenmodell 9.4): Priorität hoch zuerst, dann älteste zuerst."""
    abfrage = _listen_abfrage().order_by(Auftrag.prioritaet.desc(), Auftrag.erstellt_am, Auftrag.id)
    if status_id is not None:
        abfrage = abfrage.where(Auftrag.status_aktuell_id == status_id)
    if nur_offene:
        abfrage = abfrage.where(Auftragsstatus.ist_abgeschlossen.is_(False))
    if zugewiesener_mitarbeiter_id is not None:
        abfrage = abfrage.where(Auftrag.zugewiesener_mitarbeiter_id == zugewiesener_mitarbeiter_id)
    if kunde_id is not None:
        abfrage = abfrage.where(Auftrag.kunde_id == kunde_id)
    if prioritaet is not None:
        abfrage = abfrage.where(Auftrag.prioritaet == prioritaet)
    return [AuftragKurz(**_kurz_felder(z)) for z in db.execute(abfrage).all()]


@router.get("/{auftrag_id}", response_model=AuftragDetail)
def auftrag_abrufen(auftrag_id: uuid.UUID, db: Session = Depends(get_db)) -> AuftragDetail:
    return _detail(db, auftrag_id)


# --- Anlegen ----------------------------------------------------------------

@router.post("", response_model=AuftragDetail, status_code=status.HTTP_201_CREATED)
def auftrag_anlegen(
    daten: AuftragNeu,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID | None = Depends(aktueller_mitarbeiter_id),
) -> AuftragDetail:
    if db.get(Kunde, daten.kunde_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Kunde existiert nicht")
    instrument = db.get(Instrument, daten.instrument_id)
    if instrument is None or instrument.kunde_id != daten.kunde_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Instrument existiert nicht oder gehört nicht zum Kunden")
    reparaturart = db.get(Reparaturart, daten.reparaturart_id)
    if reparaturart is None or not reparaturart.aktiv:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Reparaturart existiert nicht oder ist archiviert")
    if daten.zugewiesener_mitarbeiter_id is not None:
        zugewiesen = db.get(Mitarbeiter, daten.zugewiesener_mitarbeiter_id)
        if zugewiesen is None or not zugewiesen.aktiv:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Mitarbeiter existiert nicht oder ist deaktiviert")
    startstatus = db.scalar(select(Auftragsstatus).where(Auftragsstatus.schluessel == STARTSTATUS))
    if startstatus is None:
        raise RuntimeError(f"Startstatus '{STARTSTATUS}' fehlt in auftragsstatus")

    # Stufe-1-Schätzung (Datenmodell 4 / 4.1)
    stunden = schaetze_arbeitsstunden(db, instrument.instrumentenklasse_id, reparaturart.id)
    kosten = schaetze_kosten(db, instrument.instrumentenklasse_id, reparaturart.id)

    auftrag = Auftrag(
        auftragsnummer=_neue_auftragsnummer(db),
        zugriffstoken=_neues_zugriffstoken(),
        kunde_id=daten.kunde_id,
        instrument_id=instrument.id,
        reparaturart_id=reparaturart.id,
        zugewiesener_mitarbeiter_id=daten.zugewiesener_mitarbeiter_id,
        prioritaet=daten.prioritaet,
        komplexitaet=daten.komplexitaet or reparaturart.standard_komplexitaet,
        status_aktuell_id=startstatus.id,
        geschaetzte_arbeitsstunden=stunden.wert,
        geschaetzte_kosten=kosten.wert,
        notizen=daten.notizen,
    )
    db.add(auftrag)
    db.flush()  # erzeugt die ID

    db.add(AuftragStatusverlauf(
        auftrag_id=auftrag.id,
        status_id=startstatus.id,
        geaendert_von_mitarbeiter_id=mitarbeiter_id,
        kommentar="Auftrag angelegt",
    ))
    db.add(SchaetzungsLog(
        auftrag_id=auftrag.id,
        methode=METHODE_REGELBASIERT,
        geschaetzte_stunden=stunden.wert,
        geschaetzte_kosten=kosten.wert,
        eingabefaktoren={
            "instrumentenklasse_id": str(instrument.instrumentenklasse_id),
            "reparaturart_id": str(reparaturart.id),
            "komplexitaet": auftrag.komplexitaet,
            "mindestanzahl_vergleichsfaelle": MINDESTANZAHL_VERGLEICHSFAELLE,
            "stunden": _schaetzung_als_faktor(stunden),
            "kosten": _schaetzung_als_faktor(kosten),
        },
    ))
    db.commit()
    return _detail(db, auftrag.id)


# --- Statuswechsel ----------------------------------------------------------

@router.post("/{auftrag_id}/status", response_model=AuftragDetail,
             dependencies=[Depends(darf_auftrag_bearbeiten)])
def status_wechseln(
    auftrag_id: uuid.UUID,
    daten: Statuswechsel,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID | None = Depends(aktueller_mitarbeiter_id),
) -> AuftragDetail:
    auftrag = _auftrag_laden(db, auftrag_id)
    neu = db.get(Auftragsstatus, daten.status_id)
    if neu is None or not neu.aktiv:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Status existiert nicht oder ist archiviert")
    if neu.id == auftrag.status_aktuell_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Auftrag ist bereits im Status \"{neu.bezeichnung}\"")

    # Pflicht-Zeiterfassung beim Abschluss (Datenmodell 9.8)
    if neu.erfordert_zeiterfassung and daten.arbeitszeit_minuten is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Für den Status \"{neu.bezeichnung}\" muss die Arbeitszeit angegeben werden")
    if daten.arbeitszeit_minuten is not None:
        if mitarbeiter_id is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                "Arbeitszeit muss einem Mitarbeiter zugeordnet werden (vorläufig: Header X-Mitarbeiter-Id)")
        db.add(Arbeitszeiterfassung(
            auftrag_id=auftrag.id,
            mitarbeiter_id=mitarbeiter_id,
            dauer_minuten=daten.arbeitszeit_minuten,
            kommentar=daten.kommentar,
        ))

    # Fertigstellungsdatum = Trainingslabel für Stufe 2: beim ersten Abschluss setzen,
    # bei Wiederaufnahme (zurück in einen offenen Status) wieder leeren
    if neu.ist_abgeschlossen:
        if auftrag.tatsaechliches_fertigstellungsdatum is None:
            auftrag.tatsaechliches_fertigstellungsdatum = date.today()
    else:
        auftrag.tatsaechliches_fertigstellungsdatum = None

    db.add(AuftragStatusverlauf(
        auftrag_id=auftrag.id,
        status_id=neu.id,
        geaendert_von_mitarbeiter_id=mitarbeiter_id,
        kommentar=daten.kommentar,
    ))
    auftrag.status_aktuell_id = neu.id
    db.commit()
    return _detail(db, auftrag.id)


# --- Manuelle Korrektur der Schätzung (Datenmodell 4.2) ---------------------

@router.post("/{auftrag_id}/schaetzung-korrektur", response_model=AuftragDetail,
             dependencies=[Depends(darf_auftrag_bearbeiten)])
def schaetzung_korrigieren(
    auftrag_id: uuid.UUID,
    daten: SchaetzungKorrektur,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(angemeldeter_mitarbeiter_id),
) -> AuftragDetail:
    if daten.geschaetzte_arbeitsstunden is None and daten.geschaetzte_kosten is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                      "Mindestens geschaetzte_arbeitsstunden oder geschaetzte_kosten angeben")
    auftrag = _auftrag_laden(db, auftrag_id)

    vorher = {
        "geschaetzte_arbeitsstunden": None if auftrag.geschaetzte_arbeitsstunden is None
        else f"{auftrag.geschaetzte_arbeitsstunden:.2f}",
        "geschaetzte_kosten": None if auftrag.geschaetzte_kosten is None
        else f"{auftrag.geschaetzte_kosten:.2f}",
    }
    # Neuer Log-Eintrag – vorherige (automatische) Einträge bleiben unverändert
    db.add(SchaetzungsLog(
        auftrag_id=auftrag.id,
        methode=METHODE_KORREKTUR,
        geschaetzte_stunden=daten.geschaetzte_arbeitsstunden,
        geschaetzte_kosten=daten.geschaetzte_kosten,
        eingabefaktoren={"vorher": vorher},
        korrigiert_von_mitarbeiter_id=mitarbeiter_id,
        grund=daten.grund,
    ))
    if daten.geschaetzte_arbeitsstunden is not None:
        auftrag.geschaetzte_arbeitsstunden = daten.geschaetzte_arbeitsstunden
    if daten.geschaetzte_kosten is not None:
        auftrag.geschaetzte_kosten = daten.geschaetzte_kosten
    db.commit()
    return _detail(db, auftrag.id)

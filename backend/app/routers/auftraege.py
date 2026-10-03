"""Auftragsverwaltung (Datenmodell 2.7 auftrag, 2.8 statusverlauf, 2.10 schaetzungs_log, 4.2).

Grundsätze:
- Status wird nie einfach überschrieben: jeder Wechsel erzeugt einen Eintrag im
  auftrag_statusverlauf; auftrag.status_aktuell_id ist nur die schnelle Kopie.
- Schätzungen werden nie überschrieben: jede automatische Schätzung und jede manuelle
  Korrektur ist ein eigener Eintrag im schaetzungs_log.

Berechtigungen (7.2): Alle Endpunkte erfordern Anmeldung. Anlegen, Liste und Details
für alle Mitarbeiter; Statuswechsel und Korrektur nur für den zugewiesenen Mitarbeiter
oder Werkstattleiter/Admin (darf_auftrag_bearbeiten).

TODO (Fahrplan 10.4): Liste/Details für Systemrolle "mitarbeiter" auf eigene Aufträge einschränken
(Berechtigungsmatrix 7.2: "Alle Aufträge werkstattweit einsehen" nur Werkstattleiter/Admin).
Dann gehört die Einschränkung in die Basisabfrage der Liste (auch "gesamt" zählt nur eigene),
und ein Mitarbeiter-Filter auf Kollegen wird abgelehnt (403).
"""

import secrets
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter, aktueller_mitarbeiter_id, darf_auftrag_bearbeiten, rolle_mindestens
from app.db import get_db
from app.eingabe import feldfehler
from app.listen import ListenParameter, Seite, enthaelt, listen_parameter, seite_abfragen
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
    Systemrolle,
    Unterbrechung,
)
from app.schaetzung import MINDESTANZAHL_VERGLEICHSFAELLE, Schaetzung, schaetze_arbeitsstunden, schaetze_kosten
from app.terminschaetzung import termin_neu_berechnen, termin_uebernehmen
from app.schemas import (
    AuftragAenderung,
    AuftragDetail,
    AuftragKurz,
    AuftragNeu,
    SchaetzungKorrektur,
    SchaetzungsLogEintrag,
    StatusKurz,
    StatusverlaufEintrag,
    Statuswechsel,
    TerminKorrektur,
    UnterbrechungEintrag,
)

router = APIRouter(prefix="/auftraege", tags=["Aufträge"], dependencies=[Depends(aktueller_mitarbeiter)])

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
    return StatusKurz(
        id=s.id, schluessel=s.schluessel, bezeichnung=s.bezeichnung,
        farbe=s.farbe, symbol=s.symbol, ist_abgeschlossen=s.ist_abgeschlossen,
    )


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
        "ist_ueberfaellig": (
            a.geschaetztes_fertigstellungsdatum is not None
            and a.geschaetztes_fertigstellungsdatum < date.today()
            and not status_.ist_abgeschlossen
        ),
    }


def _detail(db: Session, auftrag_id: uuid.UUID) -> AuftragDetail:
    zeile = db.execute(_listen_abfrage().where(Auftrag.id == auftrag_id)).one_or_none()
    if zeile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Auftrag nicht gefunden")
    a = zeile[0]
    # Namen der Handelnden direkt mitliefern (auch deaktivierte, unabhängig von der Rolle des Betrachters)
    verlauf = db.execute(
        select(AuftragStatusverlauf, Auftragsstatus, Mitarbeiter.name)
        .join(Auftragsstatus, AuftragStatusverlauf.status_id == Auftragsstatus.id)
        .outerjoin(Mitarbeiter, AuftragStatusverlauf.geaendert_von_mitarbeiter_id == Mitarbeiter.id)
        .where(AuftragStatusverlauf.auftrag_id == auftrag_id)
        .order_by(AuftragStatusverlauf.geaendert_am, AuftragStatusverlauf.id)
    ).all()
    schaetzungen = db.execute(
        select(SchaetzungsLog, Mitarbeiter.name)
        .outerjoin(Mitarbeiter, SchaetzungsLog.korrigiert_von_mitarbeiter_id == Mitarbeiter.id)
        .where(SchaetzungsLog.auftrag_id == auftrag_id)
        .order_by(SchaetzungsLog.berechnet_am, SchaetzungsLog.id)
    ).all()
    unterbrechungen = db.scalars(
        select(Unterbrechung)
        .where(Unterbrechung.auftrag_id == auftrag_id)
        .order_by(Unterbrechung.von_datum, Unterbrechung.id)
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
                geaendert_von_name=name,
                kommentar=v.kommentar,
            )
            for v, s, name in verlauf
        ],
        schaetzungen=[
            SchaetzungsLogEintrag.model_validate(s).model_copy(update={"korrigiert_von_name": name})
            for s, name in schaetzungen
        ],
        unterbrechungen=[UnterbrechungEintrag.model_validate(u) for u in unterbrechungen],
    )


def _auftrag_laden(db: Session, auftrag_id: uuid.UUID) -> Auftrag:
    # FOR UPDATE: gleichzeitige Änderungen am selben Auftrag laufen nacheinander
    auftrag = db.get(Auftrag, auftrag_id, with_for_update=True)
    if auftrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Auftrag nicht gefunden")
    return auftrag


# Bei Gleichstand entscheidet der Eingang (älteste zuerst), wie bei der Standardsortierung (9.4)
SORTIERUNG = {
    "prioritaet": (Auftrag.prioritaet, Auftrag.erstellt_am),
    "auftragsnummer": Auftrag.auftragsnummer,
    "status": (Auftragsstatus.reihenfolge, Auftrag.erstellt_am),
    "kunde": (Kunde.name, Auftrag.erstellt_am),
    "instrument": (Instrumentenklasse.bezeichnung, Auftrag.erstellt_am),
    "reparaturart": (Reparaturart.bezeichnung, Auftrag.erstellt_am),
    "mitarbeiter": (Mitarbeiter.name, Auftrag.erstellt_am),
    "geschaetzte_arbeitsstunden": (Auftrag.geschaetzte_arbeitsstunden, Auftrag.erstellt_am),
    "geschaetzte_kosten": (Auftrag.geschaetzte_kosten, Auftrag.erstellt_am),
    "fertigstellung": (Auftrag.geschaetztes_fertigstellungsdatum, Auftrag.erstellt_am),
    "erstellt_am": Auftrag.erstellt_am,
}


def ist_ueberfaellig():
    """Gleiche Regel wie ist_ueberfaellig in _kurz_felder: Termin vorbei und nicht abgeschlossen."""
    return (Auftrag.geschaetztes_fertigstellungsdatum < date.today()) & Auftragsstatus.ist_abgeschlossen.is_(False)


def ist_pausiert():
    """Auftrag hat eine laufende Unterbrechung (2.9), z. B. "Wartet auf Ersatzteil"."""
    return select(Unterbrechung.id).where(
        Unterbrechung.auftrag_id == Auftrag.id, Unterbrechung.bis_datum.is_(None)).exists()


@router.get("", response_model=Seite[AuftragKurz])
def auftraege_auflisten(
    liste: ListenParameter = Depends(listen_parameter(SORTIERUNG, standard="prioritaet", richtung="ab")),
    status_: str = Query("offen", alias="status",
                         description="offen (Standard), abgeschlossen, alle oder der Schlüssel eines Status"),
    mitarbeiter: Literal["keiner"] | uuid.UUID | None = Query(
        None, description="ID des zugewiesenen Mitarbeiters oder 'keiner' für nicht zugewiesene"),
    instrumentenklasse_id: uuid.UUID | None = Query(None),
    prioritaet: Prioritaet | None = Query(None),
    termin: Literal["alle", "ueberfaellig"] = Query("alle", description="ueberfaellig = Termin vorbei, nicht abgeschlossen"),
    pausiert: bool = Query(False, description="Nur Aufträge mit laufender Unterbrechung (2.9)"),
    kunde_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> Seite[AuftragKurz]:
    """Liste nach 9.11. Suche: Auftragsnummer, Kunde (Name, externe Nr.), Instrument (Klasse,
    Hersteller, Typ, Seriennummer). Standard (9.4): Priorität hoch zuerst, dann älteste zuerst."""
    basis = _listen_abfrage()
    gefiltert = basis
    if (muster := liste.suchmuster()) is not None:
        gefiltert = gefiltert.where(enthaelt(
            muster, Auftrag.auftragsnummer, Kunde.name, Kunde.externe_kundennummer, Instrumentenklasse.bezeichnung,
            Instrument.hersteller, Instrument.typenbezeichnung, Instrument.seriennummer,
        ))
    if status_ == "offen":
        gefiltert = gefiltert.where(Auftragsstatus.ist_abgeschlossen.is_(False))
    elif status_ == "abgeschlossen":
        gefiltert = gefiltert.where(Auftragsstatus.ist_abgeschlossen.is_(True))
    elif status_ != "alle":
        if db.scalar(select(Auftragsstatus.id).where(Auftragsstatus.schluessel == status_)) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unbekannter Status '{status_}'")
        gefiltert = gefiltert.where(Auftragsstatus.schluessel == status_)
    if mitarbeiter == "keiner":
        gefiltert = gefiltert.where(Auftrag.zugewiesener_mitarbeiter_id.is_(None))
    elif mitarbeiter is not None:
        gefiltert = gefiltert.where(Auftrag.zugewiesener_mitarbeiter_id == mitarbeiter)
    if instrumentenklasse_id is not None:
        gefiltert = gefiltert.where(Instrument.instrumentenklasse_id == instrumentenklasse_id)
    if prioritaet is not None:
        gefiltert = gefiltert.where(Auftrag.prioritaet == prioritaet)
    if termin == "ueberfaellig":
        gefiltert = gefiltert.where(ist_ueberfaellig())
    if pausiert:
        gefiltert = gefiltert.where(ist_pausiert())
    if kunde_id is not None:
        gefiltert = gefiltert.where(Auftrag.kunde_id == kunde_id)
    return seite_abfragen(db, basis, gefiltert, liste, SORTIERUNG,
                          umwandeln=lambda zeile: AuftragKurz(**_kurz_felder(zeile)), eindeutig=Auftrag.id)


@router.get("/{auftrag_id}", response_model=AuftragDetail)
def auftrag_abrufen(auftrag_id: uuid.UUID, db: Session = Depends(get_db)) -> AuftragDetail:
    return _detail(db, auftrag_id)


# --- Anlegen ----------------------------------------------------------------

@router.post("", response_model=AuftragDetail, status_code=status.HTTP_201_CREATED)
def auftrag_anlegen(
    daten: AuftragNeu,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> AuftragDetail:
    kunde = db.get(Kunde, daten.kunde_id)
    if kunde is None or kunde.archiviert_am is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Kunde existiert nicht oder ist archiviert")
    instrument = db.get(Instrument, daten.instrument_id)
    if instrument is None or instrument.kunde_id != daten.kunde_id or instrument.archiviert_am is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Instrument existiert nicht, gehört nicht zum Kunden oder ist archiviert")
    reparaturart = db.get(Reparaturart, daten.reparaturart_id)
    if reparaturart is None or reparaturart.archiviert_am is not None:
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
    db.refresh(auftrag, ["erstellt_am"])  # für die Position in der Warteschlange
    termin = termin_uebernehmen(db, auftrag)

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
        geschaetztes_datum=termin.datum,
        eingabefaktoren={
            "anlass": "auftrag_angelegt",
            "instrumentenklasse_id": str(instrument.instrumentenklasse_id),
            "reparaturart_id": str(reparaturart.id),
            "komplexitaet": auftrag.komplexitaet,
            "mindestanzahl_vergleichsfaelle": MINDESTANZAHL_VERGLEICHSFAELLE,
            "stunden": _schaetzung_als_faktor(stunden),
            "kosten": _schaetzung_als_faktor(kosten),
            "termin": termin.eingabefaktoren,
        },
    ))
    db.commit()
    return _detail(db, auftrag.id)


@router.post("/{auftrag_id}/termin-korrektur", response_model=AuftragDetail,
             dependencies=[Depends(rolle_mindestens(Systemrolle.werkstattleiter))])
def termin_korrigieren(
    auftrag_id: uuid.UUID,
    daten: TerminKorrektur,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> AuftragDetail:
    """Fertigstellungstermin manuell festlegen (4.2, 7.2: nur Werkstattleitung/Admin – der Termin
    ist die Zusage an den Kunden). Die nächste automatische Neuberechnung (Umzuweisung,
    Prioritätsänderung) überschreibt die Korrektur wieder – bewusste Vereinfachung, siehe 4.0a/4.2."""
    auftrag = _auftrag_laden(db, auftrag_id)
    neu = daten.geschaetztes_fertigstellungsdatum
    if neu < auftrag.erstellt_am.date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Der Termin kann nicht vor dem Auftragseingang liegen")

    def iso(wert: date | None) -> str | None:
        return None if wert is None else wert.isoformat()

    # Neuer Log-Eintrag – vorherige Einträge bleiben unverändert
    db.add(SchaetzungsLog(
        auftrag_id=auftrag.id,
        methode=METHODE_KORREKTUR,
        geschaetztes_datum=neu,
        eingabefaktoren={"vorher": {
            "geschaetztes_fertigstellungsdatum": iso(auftrag.geschaetztes_fertigstellungsdatum),
            "geschaetzte_bandbreite_von": iso(auftrag.geschaetzte_bandbreite_von),
            "geschaetzte_bandbreite_bis": iso(auftrag.geschaetzte_bandbreite_bis),
        }},
        korrigiert_von_mitarbeiter_id=mitarbeiter_id,
        grund=daten.grund,
    ))
    auftrag.geschaetztes_fertigstellungsdatum = neu
    # Ein festgelegter Termin hat keine berechnete Bandbreite mehr (sonst stünde ein veralteter Zeitraum daneben)
    auftrag.geschaetzte_bandbreite_von = None
    auftrag.geschaetzte_bandbreite_bis = None
    db.commit()
    return _detail(db, auftrag.id)


# --- Zuweisung/Priorität ändern (löst Terminschätzung aus, Datenmodell 4) -----

@router.patch("/{auftrag_id}", response_model=AuftragDetail,
              dependencies=[Depends(rolle_mindestens(Systemrolle.werkstattleiter))])
def auftrag_aendern(
    auftrag_id: uuid.UUID,
    daten: AuftragAenderung,
    db: Session = Depends(get_db),
) -> AuftragDetail:
    """Zuweisung und/oder Priorität ändern (7.2: Werkstattleitung/Admin). Löst eine
    Neuberechnung des Termins aus, wenn sich etwas geändert hat."""
    auftrag = _auftrag_laden(db, auftrag_id)
    aenderungen = daten.model_dump(exclude_unset=True)
    if "prioritaet" in aenderungen and aenderungen["prioritaet"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Priorität darf nicht leer sein")
    neu_zugewiesen = aenderungen.get("zugewiesener_mitarbeiter_id")
    if neu_zugewiesen is not None:
        m = db.get(Mitarbeiter, neu_zugewiesen)
        if m is None or not m.aktiv:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Mitarbeiter existiert nicht oder ist deaktiviert")

    anlaesse = []
    if "zugewiesener_mitarbeiter_id" in aenderungen and neu_zugewiesen != auftrag.zugewiesener_mitarbeiter_id:
        auftrag.zugewiesener_mitarbeiter_id = neu_zugewiesen
        anlaesse.append("zuweisung_geaendert")
    if "prioritaet" in aenderungen and aenderungen["prioritaet"] != auftrag.prioritaet:
        auftrag.prioritaet = aenderungen["prioritaet"]
        anlaesse.append("prioritaet_geaendert")

    if anlaesse:
        db.flush()
        termin_neu_berechnen(db, auftrag, "+".join(anlaesse))
        db.commit()
    return _detail(db, auftrag.id)


# --- Statuswechsel ----------------------------------------------------------

@router.post("/{auftrag_id}/status", response_model=AuftragDetail,
             dependencies=[Depends(darf_auftrag_bearbeiten)])
def status_wechseln(
    auftrag_id: uuid.UUID,
    daten: Statuswechsel,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
) -> AuftragDetail:
    auftrag = _auftrag_laden(db, auftrag_id)
    neu = db.get(Auftragsstatus, daten.status_id)
    if neu is None or not neu.aktiv:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Status existiert nicht oder ist archiviert")
    if neu.id == auftrag.status_aktuell_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Auftrag ist bereits im Status \"{neu.bezeichnung}\"")

    # Ein Abschluss-Status ohne eigene Pflichtabfrage (derzeit "Abgeholt") ist nur aus einem bereits
    # abgeschlossenen Status erreichbar (derzeit "Fertig") – sonst ließe sich die Abfrage von
    # Arbeitszeit und Betrag umgehen (Datenmodell 2.7a, 9.8)
    if neu.ist_abgeschlossen and not neu.erfordert_abschlussdaten:
        aktuell = db.get(Auftragsstatus, auftrag.status_aktuell_id)
        if not aktuell.ist_abgeschlossen:
            vorher = db.scalars(select(Auftragsstatus.bezeichnung).where(
                Auftragsstatus.erfordert_abschlussdaten, Auftragsstatus.aktiv).order_by(Auftragsstatus.reihenfolge)).all()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"„{neu.bezeichnung}“ ist erst nach „{'“ oder „'.join(vorher)}“ möglich – "
                "dort werden Arbeitszeit und abgerechneter Betrag erfasst",
            )

    if daten.unterbrechungsgrund and neu.unterbrechungsgrund is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Der Status \"{neu.bezeichnung}\" ist keine Unterbrechung – Grund nicht möglich")

    # Pflichtangaben beim Abschluss (Datenmodell 9.8): Arbeitszeit und abgerechneter Betrag
    if neu.erfordert_abschlussdaten:
        fehlend = {
            feld: f"Pflichtangabe für den Status „{neu.bezeichnung}“"
            for feld in ("arbeitszeit_minuten", "abgerechneter_betrag") if getattr(daten, feld) is None
        }
        if fehlend:
            raise feldfehler(**fehlend)
        # Ohne diesen Wert bliebe die historische Kostenschätzung (4.1) und der Umsatz (9.14.3) leer
        auftrag.tatsaechliche_kosten = daten.abgerechneter_betrag
    elif daten.abgerechneter_betrag is not None:
        raise feldfehler(abgerechneter_betrag=f"Der Betrag wird beim Abschluss erfasst, nicht im Status „{neu.bezeichnung}“")
    if daten.arbeitszeit_minuten is not None:
        db.add(Arbeitszeiterfassung(
            auftrag_id=auftrag.id,
            mitarbeiter_id=mitarbeiter_id,
            dauer_minuten=daten.arbeitszeit_minuten,
            kommentar=daten.kommentar,
        ))

    _unterbrechung_fortschreiben(db, auftrag, neu, daten.unterbrechungsgrund)

    # Fertigstellungsdatum = Trainingslabel für Stufe 2: beim ersten Abschluss setzen,
    # bei Wiederaufnahme (zurück in einen offenen Status) wieder leeren
    if neu.ist_abgeschlossen:
        if auftrag.tatsaechliches_fertigstellungsdatum is None:
            auftrag.tatsaechliches_fertigstellungsdatum = date.today()
    else:
        auftrag.tatsaechliches_fertigstellungsdatum = None
        auftrag.tatsaechliche_kosten = None  # wird beim erneuten Abschluss neu erfasst

    db.add(AuftragStatusverlauf(
        auftrag_id=auftrag.id,
        status_id=neu.id,
        geaendert_von_mitarbeiter_id=mitarbeiter_id,
        kommentar=daten.kommentar,
    ))
    auftrag.status_aktuell_id = neu.id
    db.commit()
    return _detail(db, auftrag.id)


def _unterbrechung_fortschreiben(
    db: Session, auftrag: Auftrag, neu: Auftragsstatus, grund: str | None
) -> None:
    """Unterbrechungen (Datenmodell 2.9) aus dem Statuswechsel ableiten.

    - Eine offene Unterbrechung wird beim Verlassen des pausierenden Status abgeschlossen
      (bis_datum = jetzt) – auch beim Wechsel in einen anderen pausierenden Status.
    - Ist der neue Status pausierend (auftragsstatus.unterbrechungsgrund gesetzt), beginnt eine
      neue Unterbrechung mit dem angegebenen oder dem Standardgrund.
    Die Einträge sind die Grundlage, um Wartezeiten später aus der Bearbeitungsdauer
    herauszurechnen (Terminschätzung, Abschnitt 4).
    """
    offen = db.scalar(
        select(Unterbrechung).where(Unterbrechung.auftrag_id == auftrag.id, Unterbrechung.bis_datum.is_(None))
    )
    if offen is not None:
        offen.bis_datum = func.clock_timestamp()
        db.flush()  # zuerst schließen – es darf nur eine offene Unterbrechung geben
    if neu.unterbrechungsgrund is not None:
        db.add(Unterbrechung(
            auftrag_id=auftrag.id,
            grund=grund or neu.unterbrechungsgrund,
            von_datum=func.clock_timestamp(),
        ))


# --- Manuelle Korrektur der Schätzung (Datenmodell 4.2) ---------------------

@router.post("/{auftrag_id}/schaetzung-korrektur", response_model=AuftragDetail,
             dependencies=[Depends(darf_auftrag_bearbeiten)])
def schaetzung_korrigieren(
    auftrag_id: uuid.UUID,
    daten: SchaetzungKorrektur,
    db: Session = Depends(get_db),
    mitarbeiter_id: uuid.UUID = Depends(aktueller_mitarbeiter_id),
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

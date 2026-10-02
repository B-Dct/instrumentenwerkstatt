"""Tabellen-Definitionen gemäß docs/datenmodell.md.

Konventionen:
- Primärschlüssel sind UUIDs (von PostgreSQL erzeugt).
- Umlaute in Namen werden umgeschrieben (prioritaet, schaetzungs_log, ...).
- Nichts wird hart gelöscht: Stammdaten haben `archiviert_am`, Mitarbeiter `aktiv`/`deaktiviert_am`.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# --- Hilfsbausteine ---------------------------------------------------------

def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def fk(target: str, *, nullable: bool = False, index: bool = True) -> Mapped:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{target}.id"), nullable=nullable, index=index
    )


def zeitstempel_jetzt() -> Mapped[datetime]:
    """Echte Uhrzeit des Eintrags (clock_timestamp), nicht der Transaktionsbeginn (now()) –
    sonst hätten mehrere Einträge einer Transaktion denselben Zeitstempel und ihre
    Reihenfolge (Statusverlauf, Logs, "älteste zuerst") wäre nicht mehr erkennbar."""
    return mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False)


def pg_enum(py_enum: type[enum.Enum], name: str) -> Enum:
    # Speichert die (kleingeschriebenen) Werte, nicht die Python-Namen
    return Enum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


# --- Feste Auswahllisten ----------------------------------------------------

class Systemrolle(str, enum.Enum):
    mitarbeiter = "mitarbeiter"
    werkstattleiter = "werkstattleiter"
    admin = "admin"


class Prioritaet(str, enum.Enum):
    normal = "normal"
    hoch = "hoch"


class Abwesenheitstyp(str, enum.Enum):
    urlaub = "urlaub"
    krankheit = "krankheit"
    feiertag = "feiertag"
    betriebsschliessung = "betriebsschliessung"
    schulung = "schulung"
    reduzierte_stunden = "reduzierte_stunden"


# --- 2.1 Kunde --------------------------------------------------------------

class Kunde(Base):
    __tablename__ = "kunde"
    __table_args__ = (
        # Externe Nummer eindeutig ohne Beachtung der Groß-/Kleinschreibung ("fibu-1" = "FIBU-1"),
        # nur falls gesetzt (NULL bleibt mehrfach erlaubt), auch gegenüber archivierten Kunden
        Index("uq_kunde_externe_kundennummer", func.lower(text("externe_kundennummer")), unique=True),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kundennummer: Mapped[str] = mapped_column(String(30), unique=True)
    # Nummer aus dem Buchhaltungssystem; Eindeutigkeit siehe Index oben
    externe_kundennummer: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    telefon: Mapped[str | None] = mapped_column(String(50))
    erstellt_am: Mapped[datetime] = zeitstempel_jetzt()
    archiviert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = aktiv


# --- 2.2 Mitarbeiter --------------------------------------------------------

class Mitarbeiter(Base):
    __tablename__ = "mitarbeiter"
    __table_args__ = (
        CheckConstraint(
            "(aktiv AND deaktiviert_am IS NULL) OR (NOT aktiv AND deaktiviert_am IS NOT NULL)",
            name="deaktiviert_am_passt_zu_aktiv",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    rolle: Mapped[str | None] = mapped_column(String(100))  # fachlich, z. B. Geigenbauer
    systemrolle: Mapped[Systemrolle] = mapped_column(
        pg_enum(Systemrolle, "systemrolle"), server_default=Systemrolle.mitarbeiter.value
    )
    email: Mapped[str] = mapped_column(String(254), unique=True)
    passwort_hash: Mapped[str] = mapped_column(String(255))
    aktiv: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    erstellt_am: Mapped[datetime] = zeitstempel_jetzt()
    deaktiviert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- 2.3 Abwesenheit --------------------------------------------------------

class Abwesenheit(Base):
    __tablename__ = "abwesenheit"
    __table_args__ = (
        CheckConstraint("bis_datum >= von_datum", name="zeitraum_gueltig"),
        CheckConstraint("reduzierte_stunden IS NULL OR reduzierte_stunden >= 0",
                        name="reduzierte_stunden_positiv"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    mitarbeiter_id: Mapped[uuid.UUID | None] = fk("mitarbeiter", nullable=True)  # NULL = ganze Werkstatt
    von_datum: Mapped[date] = mapped_column(Date)
    bis_datum: Mapped[date] = mapped_column(Date)
    typ: Mapped[Abwesenheitstyp] = mapped_column(pg_enum(Abwesenheitstyp, "abwesenheitstyp"))
    reduzierte_stunden: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # NULL = ganztägig
    notiz: Mapped[str | None] = mapped_column(Text)  # optional, z. B. "Betriebsurlaub Weihnachten"
    # Stornieren statt Löschen: gesetzt = zählt nicht mehr für die Terminschätzung, bleibt aber erhalten
    storniert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- 2.4 Instrumentenklasse / 2.6 Reparaturart / Auftragsstatus (Stammdaten) -

class Instrumentenklasse(Base):
    __tablename__ = "instrumentenklasse"

    id: Mapped[uuid.UUID] = uuid_pk()
    bezeichnung: Mapped[str] = mapped_column(String(100), unique=True)
    oberkategorie: Mapped[str] = mapped_column(String(100))
    archiviert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = aktiv


class Reparaturart(Base):
    __tablename__ = "reparaturart"
    __table_args__ = (
        CheckConstraint("standard_komplexitaet BETWEEN 1 AND 5", name="komplexitaet_1_bis_5"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    bezeichnung: Mapped[str] = mapped_column(String(150), unique=True)
    standard_komplexitaet: Mapped[int] = mapped_column(SmallInteger)
    archiviert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = aktiv


class ReparaturVorgabewert(Base):
    """2.6a: Vorgabewerte für Dauer/Kosten je Reparaturart (optional je Instrumentenklasse).

    instrumentenklasse_id = NULL bedeutet: allgemeiner Wert für die Reparaturart.
    Pro Kombination (auch "allgemein") gibt es höchstens einen AKTIVEN Eintrag.
    """

    __tablename__ = "reparatur_vorgabewert"
    __table_args__ = (
        # Jede Kombination (auch "allgemein" = NULL) höchstens einmal unter den AKTIVEN Einträgen
        Index(
            "uq_reparatur_vorgabewert_kombination", "reparaturart_id", "instrumentenklasse_id",
            unique=True, postgresql_nulls_not_distinct=True, postgresql_where=text("archiviert_am IS NULL"),
        ),
        CheckConstraint("vorgabe_stunden >= 0", name="stunden_nicht_negativ"),
        CheckConstraint("vorgabe_kosten >= 0", name="kosten_nicht_negativ"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    reparaturart_id: Mapped[uuid.UUID] = fk("reparaturart")
    instrumentenklasse_id: Mapped[uuid.UUID | None] = fk("instrumentenklasse", nullable=True, index=False)
    vorgabe_stunden: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    vorgabe_kosten: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # in Euro
    notiz: Mapped[str | None] = mapped_column(Text)
    # NULL = aktiv; archivierte Vorgabewerte ignoriert die Schätzung
    archiviert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    geaendert_von_mitarbeiter_id: Mapped[uuid.UUID | None] = fk("mitarbeiter", nullable=True, index=False)
    geaendert_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), onupdate=func.clock_timestamp()
    )


class Auftragsstatus(Base):
    """Pflegbare Liste der Auftragsstatus (statt fester Werte im Code)."""

    __tablename__ = "auftragsstatus"

    id: Mapped[uuid.UUID] = uuid_pk()
    schluessel: Mapped[str] = mapped_column(String(50), unique=True)  # stabil, für Code: "fertig"
    bezeichnung: Mapped[str] = mapped_column(String(100), unique=True)  # Anzeige: "Fertig"
    reihenfolge: Mapped[int] = mapped_column(SmallInteger)
    farbe: Mapped[str] = mapped_column(String(7))  # Hex, z. B. #4B6B4F (Design-System 9.6)
    symbol: Mapped[str] = mapped_column(String(4), server_default="○")  # Farbe nie allein (9.3)
    # Beim Wechsel in diesen Status muss Arbeitszeit erfasst werden (Datenmodell 9.8)
    erfordert_zeiterfassung: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Auftrag gilt in diesem Status als abgeschlossen (zählt nicht mehr zur Auslastung)
    ist_abgeschlossen: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Gesetzt = dieser Status pausiert den Auftrag (z. B. "Wartet auf Ersatzteil"): Beim Wechsel
    # hinein entsteht automatisch ein offener unterbrechung-Eintrag mit diesem Standardgrund,
    # beim Wechsel heraus wird er abgeschlossen (Datenmodell 2.9)
    unterbrechungsgrund: Mapped[str | None] = mapped_column(String(200))
    aktiv: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


# --- 2.5 Instrument ---------------------------------------------------------

class Instrument(Base):
    __tablename__ = "instrument"

    id: Mapped[uuid.UUID] = uuid_pk()
    kunde_id: Mapped[uuid.UUID] = fk("kunde")
    instrumentenklasse_id: Mapped[uuid.UUID] = fk("instrumentenklasse")
    hersteller: Mapped[str | None] = mapped_column(String(150))
    typenbezeichnung: Mapped[str | None] = mapped_column(String(150))
    baujahr: Mapped[int | None] = mapped_column(Integer)
    seriennummer: Mapped[str | None] = mapped_column(String(100))
    notizen: Mapped[str | None] = mapped_column(Text)
    archiviert_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = aktiv


# --- 2.7 Auftrag ------------------------------------------------------------

class Auftrag(Base):
    __tablename__ = "auftrag"
    __table_args__ = (
        CheckConstraint("komplexitaet BETWEEN 1 AND 5", name="komplexitaet_1_bis_5"),
        CheckConstraint("geschaetzte_kosten IS NULL OR geschaetzte_kosten >= 0",
                        name="geschaetzte_kosten_nicht_negativ"),
        CheckConstraint("tatsaechliche_kosten IS NULL OR tatsaechliche_kosten >= 0",
                        name="tatsaechliche_kosten_nicht_negativ"),
        CheckConstraint(
            "geschaetzte_bandbreite_bis IS NULL OR geschaetzte_bandbreite_von IS NULL "
            "OR geschaetzte_bandbreite_bis >= geschaetzte_bandbreite_von",
            name="bandbreite_gueltig",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    auftragsnummer: Mapped[str] = mapped_column(String(30), unique=True)
    zugriffstoken: Mapped[str] = mapped_column(String(64), unique=True)
    kunde_id: Mapped[uuid.UUID] = fk("kunde")
    instrument_id: Mapped[uuid.UUID] = fk("instrument")
    reparaturart_id: Mapped[uuid.UUID] = fk("reparaturart")
    zugewiesener_mitarbeiter_id: Mapped[uuid.UUID | None] = fk("mitarbeiter", nullable=True)
    prioritaet: Mapped[Prioritaet] = mapped_column(
        pg_enum(Prioritaet, "prioritaet"), server_default=Prioritaet.normal.value
    )
    komplexitaet: Mapped[int] = mapped_column(SmallInteger)
    # Redundant zur schnellen Anzeige – Quelle der Wahrheit ist auftrag_statusverlauf
    status_aktuell_id: Mapped[uuid.UUID] = fk("auftragsstatus")
    erstellt_am: Mapped[datetime] = zeitstempel_jetzt()
    geschaetztes_fertigstellungsdatum: Mapped[date | None] = mapped_column(Date)
    geschaetzte_bandbreite_von: Mapped[date | None] = mapped_column(Date)
    geschaetzte_bandbreite_bis: Mapped[date | None] = mapped_column(Date)
    geschaetzte_arbeitsstunden: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    geschaetzte_kosten: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # in Euro
    tatsaechliche_kosten: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # NULL bis Abschluss
    tatsaechliches_fertigstellungsdatum: Mapped[date | None] = mapped_column(Date)
    notizen: Mapped[str | None] = mapped_column(Text)


# --- 2.8 Auftrag-Statusverlauf ----------------------------------------------

class AuftragStatusverlauf(Base):
    __tablename__ = "auftrag_statusverlauf"

    id: Mapped[uuid.UUID] = uuid_pk()
    auftrag_id: Mapped[uuid.UUID] = fk("auftrag")
    status_id: Mapped[uuid.UUID] = fk("auftragsstatus")
    geaendert_am: Mapped[datetime] = zeitstempel_jetzt()
    geaendert_von_mitarbeiter_id: Mapped[uuid.UUID | None] = fk("mitarbeiter", nullable=True)
    kommentar: Mapped[str | None] = mapped_column(Text)


# --- 2.9 Unterbrechung ------------------------------------------------------

class Unterbrechung(Base):
    __tablename__ = "unterbrechung"
    __table_args__ = (
        CheckConstraint("bis_datum IS NULL OR bis_datum >= von_datum", name="zeitraum_gueltig"),
        # Höchstens eine offene Unterbrechung je Auftrag
        Index("uq_unterbrechung_offen_je_auftrag", "auftrag_id", unique=True,
              postgresql_where=text("bis_datum IS NULL")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    auftrag_id: Mapped[uuid.UUID] = fk("auftrag")
    grund: Mapped[str] = mapped_column(String(200))
    von_datum: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bis_datum: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = ungelöst


# --- 2.10 Schätzungs-Log ----------------------------------------------------

class SchaetzungsLog(Base):
    """Jede automatische Schätzung und jede manuelle Korrektur (nie überschrieben)."""

    __tablename__ = "schaetzungs_log"
    __table_args__ = (
        CheckConstraint(
            "methode <> 'manuelle_korrektur' OR "
            "(korrigiert_von_mitarbeiter_id IS NOT NULL AND grund IS NOT NULL AND btrim(grund) <> '')",
            name="korrektur_mit_mitarbeiter_und_grund",
        ),
        CheckConstraint("geschaetzte_stunden IS NULL OR geschaetzte_stunden >= 0",
                        name="stunden_nicht_negativ"),
        CheckConstraint("geschaetzte_kosten IS NULL OR geschaetzte_kosten >= 0",
                        name="kosten_nicht_negativ"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    auftrag_id: Mapped[uuid.UUID] = fk("auftrag")
    berechnet_am: Mapped[datetime] = zeitstempel_jetzt()
    methode: Mapped[str] = mapped_column(String(50))  # "regelbasiert" / "ml_modell_v1" / "manuelle_korrektur"
    # Je nach Eintrag ist nur ein Teil gefüllt (was geschätzt bzw. korrigiert wurde)
    geschaetztes_datum: Mapped[date | None] = mapped_column(Date)
    geschaetzte_stunden: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    geschaetzte_kosten: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    eingabefaktoren: Mapped[dict | None] = mapped_column(JSONB)
    korrigiert_von_mitarbeiter_id: Mapped[uuid.UUID | None] = fk("mitarbeiter", nullable=True, index=False)
    grund: Mapped[str | None] = mapped_column(Text)  # nur bei manueller Korrektur


# --- 2.11 Arbeitszeiterfassung ----------------------------------------------

class Arbeitszeiterfassung(Base):
    __tablename__ = "arbeitszeiterfassung"
    __table_args__ = (CheckConstraint("dauer_minuten > 0", name="dauer_positiv"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    auftrag_id: Mapped[uuid.UUID] = fk("auftrag")
    mitarbeiter_id: Mapped[uuid.UUID] = fk("mitarbeiter")
    dauer_minuten: Mapped[int] = mapped_column(Integer)
    erfasst_am: Mapped[datetime] = zeitstempel_jetzt()
    kommentar: Mapped[str | None] = mapped_column(Text)


# --- 2.12 Mitarbeiter-Arbeitszeit (Wochenstunden mit Gültigkeit) ------------

class MitarbeiterArbeitszeit(Base):
    __tablename__ = "mitarbeiter_arbeitszeit"
    __table_args__ = (
        CheckConstraint("wochenstunden >= 0", name="wochenstunden_positiv"),
        CheckConstraint("gueltig_bis IS NULL OR gueltig_bis >= gueltig_ab", name="zeitraum_gueltig"),
        # Je Mitarbeiter höchstens ein aktuell gültiger (offener) Eintrag
        Index("uq_mitarbeiter_arbeitszeit_aktuell", "mitarbeiter_id", unique=True,
              postgresql_where=text("gueltig_bis IS NULL")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    mitarbeiter_id: Mapped[uuid.UUID] = fk("mitarbeiter")
    wochenstunden: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    gueltig_ab: Mapped[date] = mapped_column(Date)
    gueltig_bis: Mapped[date | None] = mapped_column(Date)  # NULL = aktuell gültig
    geaendert_von_mitarbeiter_id: Mapped[uuid.UUID | None] = fk("mitarbeiter", nullable=True, index=False)
    geaendert_am: Mapped[datetime] = zeitstempel_jetzt()


# --- 2.13 Mitarbeiter-Qualifikation -----------------------------------------

class MitarbeiterQualifikation(Base):
    __tablename__ = "mitarbeiter_qualifikation"

    id: Mapped[uuid.UUID] = uuid_pk()
    mitarbeiter_id: Mapped[uuid.UUID] = fk("mitarbeiter")
    reparaturart_id: Mapped[uuid.UUID | None] = fk("reparaturart", nullable=True, index=False)
    instrumentenklasse_id: Mapped[uuid.UUID | None] = fk("instrumentenklasse", nullable=True, index=False)
    bezeichnung: Mapped[str] = mapped_column(String(200))
    erworben_am: Mapped[date | None] = mapped_column(Date)
    gueltig_bis: Mapped[date | None] = mapped_column(Date)  # NULL = unbefristet


# --- 2.14 Arbeitszeit-Anpassung (Gleitzeit) ---------------------------------

class ArbeitszeitAnpassung(Base):
    __tablename__ = "arbeitszeit_anpassung"
    __table_args__ = (
        CheckConstraint("EXTRACT(ISODOW FROM woche_start_datum) = 1", name="woche_beginnt_montags"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    mitarbeiter_id: Mapped[uuid.UUID] = fk("mitarbeiter")
    woche_start_datum: Mapped[date] = mapped_column(Date)
    anpassung_stunden: Mapped[Decimal] = mapped_column(Numeric(5, 2))  # + mehr, − weniger
    grund: Mapped[str | None] = mapped_column(String(200))
    erfasst_von_mitarbeiter_id: Mapped[uuid.UUID | None] = fk("mitarbeiter", nullable=True, index=False)
    erfasst_am: Mapped[datetime] = zeitstempel_jetzt()


# --- 7.3 System-Ereignis-Log ------------------------------------------------

class SystemEreignisLog(Base):
    __tablename__ = "system_ereignis_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    ausgefuehrt_von_mitarbeiter_id: Mapped[uuid.UUID | None] = fk("mitarbeiter", nullable=True)
    aktion: Mapped[str] = mapped_column(String(100))
    betroffene_entitaet: Mapped[str] = mapped_column(String(100))
    betroffene_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    details: Mapped[dict | None] = mapped_column(JSONB)
    zeitpunkt: Mapped[datetime] = zeitstempel_jetzt()


# --- 7.5 Werkstatt-Einstellungen ------------------------------------------------

class Einstellung(Base):
    """Schlüssel-Wert-Tabelle für werkstattweite Einstellungen (z. B. Bundesland für Feiertage).
    Welche Schlüssel und Werte erlaubt sind, legt app/einstellungen.py fest."""

    __tablename__ = "einstellung"

    id: Mapped[uuid.UUID] = uuid_pk()
    schluessel: Mapped[str] = mapped_column(String(50), unique=True)
    wert: Mapped[str] = mapped_column(String(200))
    geaendert_von_mitarbeiter_id: Mapped[uuid.UUID | None] = fk("mitarbeiter", nullable=True, index=False)
    geaendert_am: Mapped[datetime] = zeitstempel_jetzt()

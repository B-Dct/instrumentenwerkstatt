"""Datenformate der API (was hinein- und herausgeht)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

from app.models import Prioritaet

# Dezimalwerte als JSON-Zahl ausgeben (statt als Text "12.50")
Stunden = Annotated[
    Decimal, Field(ge=0, max_digits=6, decimal_places=2), PlainSerializer(float, return_type=float)
]
Euro = Annotated[
    Decimal, Field(ge=0, max_digits=10, decimal_places=2), PlainSerializer(float, return_type=float)
]


# --- Reparatur-Vorgabewerte (Datenmodell 2.6a) ------------------------------

class VorgabewertNeu(BaseModel):
    reparaturart_id: uuid.UUID
    instrumentenklasse_id: uuid.UUID | None = None  # None = gilt allgemein für die Reparaturart
    vorgabe_stunden: Stunden
    vorgabe_kosten: Euro
    notiz: str | None = None


class VorgabewertAenderung(BaseModel):
    """Nur mitgeschickte Felder werden geändert."""

    reparaturart_id: uuid.UUID | None = None
    instrumentenklasse_id: uuid.UUID | None = None  # explizit null = auf "allgemein" setzen
    vorgabe_stunden: Stunden | None = None
    vorgabe_kosten: Euro | None = None
    notiz: str | None = None


class Vorgabewert(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reparaturart_id: uuid.UUID
    reparaturart_bezeichnung: str
    instrumentenklasse_id: uuid.UUID | None
    instrumentenklasse_bezeichnung: str | None
    vorgabe_stunden: Stunden
    vorgabe_kosten: Euro
    notiz: str | None
    geaendert_von_mitarbeiter_id: uuid.UUID | None
    geaendert_am: datetime


# --- Aufträge (Datenmodell 2.7, 2.8, 2.10, 4.2) -----------------------------

class AuftragNeu(BaseModel):
    kunde_id: uuid.UUID
    instrument_id: uuid.UUID  # muss dem Kunden gehören
    reparaturart_id: uuid.UUID
    zugewiesener_mitarbeiter_id: uuid.UUID | None = None
    prioritaet: Prioritaet = Prioritaet.normal
    # Weggelassen = Standard-Komplexität der Reparaturart
    komplexitaet: int | None = Field(None, ge=1, le=5)
    notizen: str | None = None


class StatusKurz(BaseModel):
    id: uuid.UUID
    schluessel: str
    bezeichnung: str
    farbe: str


class AuftragKurz(BaseModel):
    """Eintrag in der Auftragsliste."""

    id: uuid.UUID
    auftragsnummer: str
    kunde_id: uuid.UUID
    kunde_name: str
    instrument_id: uuid.UUID
    instrumentenklasse_bezeichnung: str
    reparaturart_id: uuid.UUID
    reparaturart_bezeichnung: str
    zugewiesener_mitarbeiter_id: uuid.UUID | None
    zugewiesener_mitarbeiter_name: str | None
    prioritaet: Prioritaet
    komplexitaet: int
    status: StatusKurz
    erstellt_am: datetime
    geschaetzte_arbeitsstunden: Stunden | None
    geschaetzte_kosten: Euro | None
    geschaetztes_fertigstellungsdatum: date | None


class StatusverlaufEintrag(BaseModel):
    status: StatusKurz
    geaendert_am: datetime
    geaendert_von_mitarbeiter_id: uuid.UUID | None
    kommentar: str | None


class SchaetzungsLogEintrag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    berechnet_am: datetime
    methode: str
    geschaetzte_stunden: Stunden | None
    geschaetzte_kosten: Euro | None
    geschaetztes_datum: date | None
    eingabefaktoren: dict | None
    korrigiert_von_mitarbeiter_id: uuid.UUID | None
    grund: str | None


class AuftragDetail(AuftragKurz):
    zugriffstoken: str  # für den Abgabebeleg (Kunden-Dashboard, Abschnitt 6)
    geschaetzte_bandbreite_von: date | None
    geschaetzte_bandbreite_bis: date | None
    tatsaechliches_fertigstellungsdatum: date | None
    tatsaechliche_kosten: Euro | None
    notizen: str | None
    statusverlauf: list[StatusverlaufEintrag]  # älteste zuerst
    schaetzungen: list[SchaetzungsLogEintrag]  # älteste zuerst


class Statuswechsel(BaseModel):
    status_id: uuid.UUID
    kommentar: str | None = None
    # Pflicht, wenn der Zielstatus Zeiterfassung erfordert (z. B. "Fertig", Datenmodell 9.8)
    arbeitszeit_minuten: int | None = Field(None, gt=0)


class SchaetzungKorrektur(BaseModel):
    geschaetzte_arbeitsstunden: Stunden | None = None
    geschaetzte_kosten: Euro | None = None
    grund: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        description="Begründung der Korrektur (Pflicht)"
    )

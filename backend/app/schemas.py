"""Datenformate der API (was hinein- und herausgeht)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

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

"""Gemeinsamer Baustein für Listen (Datenmodell 9.11): Suche, Sortierung, seitenweise Abfrage
im Backend statt im Browser – einheitlich für alle Listen-Endpunkte.

Verwendung in einem Endpunkt:

    SORTIERUNG = {"name": Mitarbeiter.name, "erstellt_am": Mitarbeiter.erstellt_am}

    @router.get("", response_model=Seite[MitarbeiterVerwaltung])
    def auflisten(liste: ListenParameter = Depends(listen_parameter(SORTIERUNG, standard="name")), …):
        basis = select(Mitarbeiter)                         # ohne Suche/Filter → "gesamt"
        gefiltert = basis.where(…Suche/Filter…)              # → "treffer"
        return seite_abfragen(db, basis, gefiltert, liste, SORTIERUNG, umwandeln=…)

Ein Sortierschlüssel darf auch ein Tupel von Spalten sein, z. B.
`"oberkategorie": (Klasse.oberkategorie, Klasse.bezeichnung)`: die erste Spalte folgt der
gewählten Richtung, die weiteren ordnen gleiche Werte immer aufsteigend.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from fastapi import HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

T = TypeVar("T")

Sortierspalten = ColumnElement | tuple[ColumnElement, ...]

SEITENGROESSE_STANDARD = 25
SEITENGROESSE_MAX = 100


class Seite(BaseModel, Generic[T]):
    """Antwort einer Liste: Einträge der aktuellen Seite + Zahlen für "12 von 348"."""

    eintraege: list[T]
    treffer: int  # Anzahl nach Suche und Filtern
    gesamt: int  # Anzahl ohne Suche und Filter
    seite: int
    seitengroesse: int
    sortierung: str
    richtung: Literal["auf", "ab"]


@dataclass
class ListenParameter:
    suche: str | None
    sortierung: str
    richtung: Literal["auf", "ab"]
    seite: int
    seitengroesse: int

    def suchmuster(self) -> str | None:
        """Für ILIKE: Teiltreffer, Groß-/Kleinschreibung egal; Platzhalterzeichen maskiert."""
        if not self.suche or not self.suche.strip():
            return None
        text = self.suche.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        return f"%{text}%"


def listen_parameter(sortierbar: dict[str, Sortierspalten], standard: str, richtung: Literal["auf", "ab"] = "auf"):
    """Dependency-Fabrik für die gemeinsamen Listen-Parameter einer Liste."""

    def parameter(
        suche: str | None = Query(None, max_length=200, description="Freitextsuche"),
        sortierung: str = Query(standard, description=f"Spalte: {', '.join(sortierbar)}"),
        richtung_: Literal["auf", "ab"] = Query(richtung, alias="richtung"),
        seite: int = Query(1, ge=1),
        seitengroesse: int = Query(SEITENGROESSE_STANDARD, ge=1, le=SEITENGROESSE_MAX),
    ) -> ListenParameter:
        if sortierung not in sortierbar:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                f"Sortierung nach '{sortierung}' nicht möglich (erlaubt: {', '.join(sortierbar)})")
        return ListenParameter(suche, sortierung, richtung_, seite, seitengroesse)

    return parameter


def enthaelt(muster: str, *spalten: ColumnElement) -> ColumnElement:
    """Suchbedingung: Muster kommt in mindestens einer der Spalten vor (maskierte Platzhalter)."""
    return or_(*(spalte.ilike(muster, escape="\\") for spalte in spalten))


def _anzahl(db: Session, abfrage: Select) -> int:
    return db.scalar(select(func.count()).select_from(abfrage.order_by(None).subquery()))


def seite_abfragen(
    db: Session,
    basis: Select,
    gefiltert: Select,
    liste: ListenParameter,
    sortierbar: dict[str, Sortierspalten],
    umwandeln: Callable,
    eindeutig: ColumnElement | None = None,
) -> Seite:
    """Zählt, sortiert und liefert eine Seite. `eindeutig` (z. B. die ID) macht die Reihenfolge
    bei gleichen Sortierwerten stabil, damit beim Blättern nichts doppelt erscheint oder fehlt."""
    spalten = sortierbar[liste.sortierung]
    erste, *weitere = spalten if isinstance(spalten, tuple) else (spalten,)
    ordnung = [erste.desc().nulls_last() if liste.richtung == "ab" else erste.asc().nulls_last()]
    ordnung += [spalte.asc().nulls_last() for spalte in weitere]
    if eindeutig is not None:
        ordnung.append(eindeutig)
    treffer = _anzahl(db, gefiltert)
    zeilen = db.execute(
        gefiltert.order_by(*ordnung).offset((liste.seite - 1) * liste.seitengroesse).limit(liste.seitengroesse)
    ).all()
    return Seite(
        eintraege=[umwandeln(z) for z in zeilen],
        treffer=treffer,
        gesamt=_anzahl(db, basis),
        seite=liste.seite,
        seitengroesse=liste.seitengroesse,
        sortierung=liste.sortierung,
        richtung=liste.richtung,
    )

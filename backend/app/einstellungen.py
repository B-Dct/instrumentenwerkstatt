"""Werkstatt-Einstellungen (Datenmodell 7.5): welche Schlüssel es gibt und welche Werte erlaubt sind.

Bisher einziger Schlüssel: `bundesland` (für die automatische Feiertagserzeugung, 9.13.1).
Gespeichert wird der ausgeschriebene Name; das Kürzel braucht nur die Feiertagsbibliothek.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Einstellung

# Name → amtliches Kürzel (ISO 3166-2:DE)
BUNDESLAENDER: dict[str, str] = {
    "Baden-Württemberg": "BW",
    "Bayern": "BY",
    "Berlin": "BE",
    "Brandenburg": "BB",
    "Bremen": "HB",
    "Hamburg": "HH",
    "Hessen": "HE",
    "Mecklenburg-Vorpommern": "MV",
    "Niedersachsen": "NI",
    "Nordrhein-Westfalen": "NW",
    "Rheinland-Pfalz": "RP",
    "Saarland": "SL",
    "Sachsen": "SN",
    "Sachsen-Anhalt": "ST",
    "Schleswig-Holstein": "SH",
    "Thüringen": "TH",
}


@dataclass(frozen=True)
class Definition:
    bezeichnung: str
    beschreibung: str
    optionen: tuple[str, ...]  # erlaubte Werte (Auswahl, kein Freitext)


EINSTELLUNGEN: dict[str, Definition] = {
    "bundesland": Definition(
        bezeichnung="Bundesland",
        beschreibung="Bestimmt, welche gesetzlichen Feiertage automatisch als werkstattweite Abwesenheit angelegt werden.",
        optionen=tuple(BUNDESLAENDER),
    ),
}


def wert(db: Session, schluessel: str) -> str | None:
    """Aktueller Wert einer Einstellung oder None, wenn noch nichts festgelegt wurde."""
    return db.scalar(select(Einstellung.wert).where(Einstellung.schluessel == schluessel))

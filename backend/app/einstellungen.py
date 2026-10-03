"""Werkstatt-Einstellungen (Datenmodell 7.5): welche Schlüssel es gibt und welche Werte erlaubt sind.

Schlüssel: `bundesland` (für die automatische Feiertagserzeugung, 9.13.1; gespeichert wird der
ausgeschriebene Name, das Kürzel braucht nur die Feiertagsbibliothek) und `stundensatz`
(€/Std., Grundlage der aus Preisen abgeleiteten Vorgabewerte – reine Information, die
Schätzlogik rechnet nicht damit).
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

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
    optionen: tuple[str, ...] = ()  # Auswahl: erlaubte Werte (kein Freitext)
    zahl_bis: Decimal | None = None  # Zahl: größer als 0 und höchstens dieser Wert
    einheit: str | None = None

    @property
    def art(self) -> str:
        return "auswahl" if self.optionen else "zahl"

    def pruefen(self, wert: str) -> str | None:
        """Gibt den zu speichernden Wert zurück oder None, wenn die Eingabe nicht erlaubt ist."""
        if self.optionen:
            return wert if wert in self.optionen else None
        try:
            zahl = Decimal(wert.strip().replace(",", "."))
        except InvalidOperation:
            return None
        if not zahl.is_finite() or zahl <= 0 or zahl > self.zahl_bis or zahl != round(zahl, 2):
            return None
        return format(zahl.normalize(), "f")  # "45,00" → "45", "45,5" → "45.5"


EINSTELLUNGEN: dict[str, Definition] = {
    "bundesland": Definition(
        bezeichnung="Bundesland",
        beschreibung="Bestimmt, welche gesetzlichen Feiertage automatisch als werkstattweite Abwesenheit angelegt werden.",
        optionen=tuple(BUNDESLAENDER),
    ),
    "stundensatz": Definition(
        bezeichnung="Stundensatz",
        beschreibung="Richtwert in Euro je Arbeitsstunde. Aus ihm sind die Stunden der Vorgabewerte abgeleitet, "
                     "die aus einer Preisliste stammen (Preis ÷ Stundensatz). Die Schätzung rechnet nicht damit.",
        zahl_bis=Decimal(1000), einheit="€/Std.",
    ),
}


def wert(db: Session, schluessel: str) -> str | None:
    """Aktueller Wert einer Einstellung oder None, wenn noch nichts festgelegt wurde."""
    return db.scalar(select(Einstellung.wert).where(Einstellung.schluessel == schluessel))

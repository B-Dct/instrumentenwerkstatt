"""Gesetzliche Feiertage automatisch als werkstattweite Abwesenheit anlegen (Datenmodell 9.13.1).

Das Bundesland kommt aus den Werkstatt-Einstellungen (7.5). Die Feiertage liefert die Bibliothek
`holidays`; angelegt werden sie als Abwesenheit "Ganze Werkstatt", Typ Feiertag, mit dem Namen
des Feiertags als Notiz – und erscheinen damit wie jeder andere Eintrag im Raster (9.13).

Nichts wird überschrieben: Ein Tag wird übersprungen, wenn
- dort schon ein Feiertags-Eintrag liegt (auch ein stornierter oder von Hand angelegter), oder
- für diesen Tag früher schon einmal ein Feiertag erzeugt wurde (auch wenn der Eintrag seitdem
  verschoben, geändert oder storniert wurde) – das steht im Änderungsprotokoll.

Automatisch (ohne Zutun) werden nur Jahre erzeugt, für die noch nie etwas erzeugt wurde. Ändert
sich später das Bundesland, bleiben bereits erzeugte Jahre deshalb, wie sie sind.
"""

from dataclasses import dataclass
from datetime import date

import holidays
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.einstellungen import BUNDESLAENDER, wert
from app.ereignisse import protokollieren, werte
from app.models import Abwesenheit, Abwesenheitstyp, SystemEreignisLog

AKTION = "feiertage_erzeugt"
FELDER = ["mitarbeiter_id", "typ", "von_datum", "bis_datum", "reduzierte_stunden", "notiz"]


class BundeslandFehlt(Exception):
    """In den Werkstatt-Einstellungen ist noch kein Bundesland festgelegt."""


@dataclass
class Ergebnis:
    jahr: int
    bundesland: str
    angelegt: list[tuple[date, str]]       # (Datum, Name des Feiertags)
    uebersprungen: list[tuple[date, str]]  # schon vorhanden oder früher erzeugt


def gesetzliche_feiertage(bundesland: str, jahr: int) -> dict[date, str]:
    """Feiertage eines Bundeslands (ausgeschriebener Name wie in den Einstellungen) für ein Jahr."""
    return dict(sorted(holidays.Germany(subdiv=BUNDESLAENDER[bundesland], years=jahr, language="de").items()))


def _laeufe(db: Session) -> list[SystemEreignisLog]:
    return list(db.scalars(select(SystemEreignisLog).where(SystemEreignisLog.aktion == AKTION)
                           .order_by(SystemEreignisLog.zeitpunkt)))


def erzeugte_jahre(db: Session) -> dict[int, list[SystemEreignisLog]]:
    """Jahr → Protokolleinträge der bisherigen Erzeugungsläufe."""
    jahre: dict[int, list[SystemEreignisLog]] = {}
    for lauf in _laeufe(db):
        jahre.setdefault(lauf.details["jahr"], []).append(lauf)
    return jahre


def feiertage_erzeugen(db: Session, jahr: int, mitarbeiter_id=None) -> Ergebnis:
    """Legt die fehlenden Feiertage eines Jahres an (ohne commit). mitarbeiter_id = None: automatisch."""
    bundesland = wert(db, "bundesland")
    if bundesland is None:
        raise BundeslandFehlt
    frueher_erzeugt = {date.fromisoformat(tag) for lauf in erzeugte_jahre(db).get(jahr, []) for tag in lauf.details["angelegt"]}
    vorhandene = db.scalars(select(Abwesenheit).where(
        Abwesenheit.typ == Abwesenheitstyp.feiertag, Abwesenheit.mitarbeiter_id.is_(None),
        Abwesenheit.von_datum <= date(jahr, 12, 31), Abwesenheit.bis_datum >= date(jahr, 1, 1),
    )).all()  # bewusst auch stornierte: ein stornierter Feiertag wird nicht wieder angelegt

    ergebnis = Ergebnis(jahr, bundesland, [], [])
    for tag, name in gesetzliche_feiertage(bundesland, jahr).items():
        if tag in frueher_erzeugt or any(a.von_datum <= tag <= a.bis_datum for a in vorhandene):
            ergebnis.uebersprungen.append((tag, name))
            continue
        eintrag = Abwesenheit(mitarbeiter_id=None, typ=Abwesenheitstyp.feiertag, von_datum=tag, bis_datum=tag, notiz=name)
        db.add(eintrag)
        db.flush()
        protokollieren(db, mitarbeiter_id, "abwesenheit_angelegt", "abwesenheit", eintrag.id,
                       {"neu": werte(eintrag, FELDER), "quelle": "feiertags_automatik"})
        ergebnis.angelegt.append((tag, name))

    # Ein Eintrag je Lauf: hält fest, dass (und womit) dieses Jahr erzeugt wurde
    protokollieren(db, mitarbeiter_id, AKTION, "abwesenheit", None, {
        "jahr": jahr, "bundesland": bundesland,
        "angelegt": [tag.isoformat() for tag, _ in ergebnis.angelegt],
        "uebersprungen": [tag.isoformat() for tag, _ in ergebnis.uebersprungen],
    })
    return ergebnis


# Schon geprüfte Jahre dieses Serverprozesses – spart die Abfrage bei jedem Aufruf des Rasters
_geprueft: set[int] = set()


def automatik_zuruecksetzen() -> None:
    _geprueft.clear()


def feiertage_sicherstellen(db: Session, heute: date | None = None) -> list[Ergebnis]:
    """Automatik: erzeugt das laufende und das kommende Jahr, falls für sie noch nie etwas erzeugt
    wurde und ein Bundesland festgelegt ist. Wird beim Öffnen des Rasters und beim Festlegen des
    Bundeslands aufgerufen; speichert selbst (commit), wenn etwas angelegt wurde."""
    jahr = (heute or date.today()).year
    offen = [j for j in (jahr, jahr + 1) if j not in _geprueft]
    if not offen or wert(db, "bundesland") is None:
        return []
    schon_erzeugt = erzeugte_jahre(db)
    ergebnisse = [feiertage_erzeugen(db, j) for j in offen if j not in schon_erzeugt]
    if ergebnisse:
        db.commit()
    _geprueft.update(offen)
    return ergebnisse

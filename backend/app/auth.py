"""Identifikation und Berechtigungsprüfung – derzeit nur Platzhalter.

Login und Rollen (Systemrolle mitarbeiter/werkstattleiter/admin) sind noch nicht
implementiert. Die Dependencies hier sind bereits an den richtigen Stellen
eingehängt (z. B. am gesamten Admin-Router), prüfen aber noch nichts.
Beim Nachrüsten muss nur diese Datei angepasst werden, nicht die Endpunkte.
"""

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Mitarbeiter


def aktueller_mitarbeiter_id(
    x_mitarbeiter_id: uuid.UUID | None = Header(
        None,
        description="VORLÄUFIG bis Login/Rollen: ID des handelnden Mitarbeiters. "
        "Wird ungeprüft geglaubt – keine Sicherheit, nur Zuordnung.",
    ),
    db: Session = Depends(get_db),
) -> uuid.UUID | None:
    """ID des handelnden Mitarbeiters, falls bekannt.

    TODO: Sobald Login/Rollen implementiert sind (siehe ARCHITECTURE.md, Abschnitt 4
    "Berechtigungskonzept") – Mitarbeiter aus dem Login-Token ermitteln statt aus dem
    Header X-Mitarbeiter-Id, und bei fehlender/ungültiger Anmeldung mit 401 abbrechen.
    """
    if x_mitarbeiter_id is None:
        return None
    mitarbeiter = db.get(Mitarbeiter, x_mitarbeiter_id)
    if mitarbeiter is None or not mitarbeiter.aktiv:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unbekannter oder deaktivierter Mitarbeiter")
    return mitarbeiter.id


def angemeldeter_mitarbeiter_id(
    mitarbeiter_id: uuid.UUID | None = Depends(aktueller_mitarbeiter_id),
) -> uuid.UUID:
    """Wie aktueller_mitarbeiter_id, aber für Aktionen, die zwingend einer Person zugeordnet
    werden müssen (z. B. manuelle Korrektur, Arbeitszeiterfassung)."""
    if mitarbeiter_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Diese Aktion muss einem Mitarbeiter zugeordnet werden (vorläufig: Header X-Mitarbeiter-Id)",
        )
    return mitarbeiter_id


def require_admin(mitarbeiter_id: uuid.UUID | None = Depends(aktueller_mitarbeiter_id)) -> None:
    """Lässt nur Mitarbeiter mit Systemrolle "admin" durch.

    TODO: Sobald Login/Rollen implementiert sind (siehe ARCHITECTURE.md, Abschnitt 4
    "Berechtigungskonzept") – Zugriff auf Systemrolle "admin" beschränken (sonst 403).
    ACHTUNG: Derzeit wird NICHTS geprüft – alle Admin-Endpunkte sind ungeschützt.
    """
    return None


def darf_auftrag_bearbeiten(mitarbeiter_id: uuid.UUID | None = Depends(aktueller_mitarbeiter_id)) -> None:
    """Zugriff auf einen einzelnen Auftrag (Statuswechsel, Korrektur der Schätzung).

    TODO: Sobald Login/Rollen implementiert sind (siehe ARCHITECTURE.md, Abschnitt 4
    "Berechtigungskonzept") – nur der zugewiesene Mitarbeiter oder Systemrolle
    "werkstattleiter"/"admin" (Berechtigungsmatrix 7.2), sonst 403.
    Braucht dann zusätzlich die auftrag_id aus dem Pfad.
    ACHTUNG: Derzeit wird NICHTS geprüft.
    """
    return None

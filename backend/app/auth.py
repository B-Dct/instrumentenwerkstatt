"""Berechtigungsprüfung – derzeit nur Platzhalter.

Login und Rollen (Systemrolle mitarbeiter/werkstattleiter/admin) sind noch nicht
implementiert. Die Dependencies hier sind bereits an den richtigen Stellen
eingehängt (z. B. am gesamten Admin-Router), prüfen aber noch nichts.
Beim Nachrüsten muss nur diese Datei angepasst werden, nicht die Endpunkte.
"""

import uuid

from fastapi import Depends


def aktueller_mitarbeiter_id() -> uuid.UUID | None:
    """ID des angemeldeten Mitarbeiters.

    TODO: Sobald Login/Rollen implementiert sind (siehe ARCHITECTURE.md, Abschnitt 4
    "Berechtigungskonzept") – Mitarbeiter aus dem Login-Token ermitteln und bei
    fehlender/ungültiger Anmeldung mit 401 abbrechen. Bis dahin: None (unbekannt).
    """
    return None


def require_admin(mitarbeiter_id: uuid.UUID | None = Depends(aktueller_mitarbeiter_id)) -> None:
    """Lässt nur Mitarbeiter mit Systemrolle "admin" durch.

    TODO: Sobald Login/Rollen implementiert sind (siehe ARCHITECTURE.md, Abschnitt 4
    "Berechtigungskonzept") – Zugriff auf Systemrolle "admin" beschränken (sonst 403).
    ACHTUNG: Derzeit wird NICHTS geprüft – alle Admin-Endpunkte sind ungeschützt.
    """
    return None

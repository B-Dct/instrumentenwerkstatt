"""Eingabefehler mit Bezug zu einem Feld (Datenmodell 9.1: Fehlermeldung direkt am Feld).

Für fachliche Prüfungen, die erst im Endpunkt möglich sind (z. B. "Mitarbeiter ist deaktiviert").
Die Antwort hat dieselbe Form wie die automatische Eingabeprüfung, das Frontend zeigt die
Meldung deshalb am genannten Feld an.
"""

from fastapi import HTTPException, status


def feldfehler(**meldungen: str) -> HTTPException:
    """422 mit Meldung je Feld, z. B. `raise feldfehler(bis_datum="Liegt vor dem Beginn")`."""
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        [{"loc": ["body", feld], "msg": meldung, "type": "fachlich"} for feld, meldung in meldungen.items()],
    )

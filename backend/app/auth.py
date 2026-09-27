"""Login, Identifikation und Berechtigungsprüfung (Datenmodell 2.2 und 7.2).

- Passwörter werden mit Argon2 gehasht (nie im Klartext gespeichert).
- Nach dem Login erhält der Mitarbeiter ein signiertes Token (JWT) mit
  mitarbeiter_id und systemrolle, das er bei jeder Anfrage mitschickt
  (Header "Authorization: Bearer <token>").
- Für die Berechtigung zählen Rolle und Aktiv-Status aus der DATENBANK, nicht aus dem
  Token: Wird jemand deaktiviert oder seine Rolle geändert, gilt das sofort – auch
  für bereits ausgestellte Tokens.
- Rollen sind kumulativ: admin ⊇ werkstattleiter ⊇ mitarbeiter (7.1).
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Auftrag, Mitarbeiter, Systemrolle

_passwort_hash = PasswordHash.recommended()  # Argon2
_ALGORITHMUS = "HS256"

# Liefert /docs den "Authorize"-Knopf; liest "Authorization: Bearer <token>"
oauth2_schema = OAuth2PasswordBearer(tokenUrl="auth/login")

_RANG = {Systemrolle.mitarbeiter: 1, Systemrolle.werkstattleiter: 2, Systemrolle.admin: 3}


# --- Passwörter -------------------------------------------------------------

def passwort_hashen(passwort: str) -> str:
    return _passwort_hash.hash(passwort)


def passwort_pruefen(passwort: str, passwort_hash: str) -> bool:
    return _passwort_hash.verify(passwort, passwort_hash)


# Zum Zeitausgleich bei unbekannter E-Mail (siehe anmelden)
_DUMMY_HASH = passwort_hashen("dummy-passwort-zum-zeitausgleich")


def email_normalisieren(email: str) -> str:
    return email.strip().lower()


def anmelden(db: Session, email: str, passwort: str) -> Mitarbeiter | None:
    """Prüft E-Mail + Passwort. None bei jedem Fehler (bewusst ohne Unterscheidung)."""
    mitarbeiter = db.query(Mitarbeiter).filter(Mitarbeiter.email == email_normalisieren(email)).one_or_none()
    if mitarbeiter is None:
        # Trotzdem einen Hash prüfen, damit die Antwortzeit nicht verrät,
        # ob die E-Mail-Adresse existiert
        passwort_pruefen(passwort, _DUMMY_HASH)
        return None
    if not passwort_pruefen(passwort, mitarbeiter.passwort_hash) or not mitarbeiter.aktiv:
        return None
    return mitarbeiter


# --- Tokens -----------------------------------------------------------------

def token_erstellen(mitarbeiter: Mitarbeiter) -> str:
    jetzt = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(mitarbeiter.id),
            "systemrolle": mitarbeiter.systemrolle.value,
            "iat": jetzt,
            "exp": jetzt + timedelta(minutes=settings.token_gueltigkeit_minuten),
        },
        settings.jwt_secret,
        algorithm=_ALGORITHMUS,
    )


def _nicht_angemeldet(meldung: str = "Nicht angemeldet oder Anmeldung abgelaufen") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, meldung, headers={"WWW-Authenticate": "Bearer"})


def _keine_berechtigung() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "Keine Berechtigung für diese Aktion")


# --- Dependencies für Endpunkte ---------------------------------------------

def aktueller_mitarbeiter(
    token: str = Depends(oauth2_schema), db: Session = Depends(get_db)
) -> Mitarbeiter:
    """Prüft das Token und liefert den angemeldeten, aktiven Mitarbeiter (sonst 401)."""
    try:
        inhalt = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHMUS], options={"require": ["sub", "exp"]})
        mitarbeiter_id = uuid.UUID(inhalt["sub"])
    except (jwt.PyJWTError, ValueError):
        raise _nicht_angemeldet() from None
    mitarbeiter = db.get(Mitarbeiter, mitarbeiter_id)
    if mitarbeiter is None or not mitarbeiter.aktiv:
        raise _nicht_angemeldet()
    return mitarbeiter


def aktueller_mitarbeiter_id(mitarbeiter: Mitarbeiter = Depends(aktueller_mitarbeiter)) -> uuid.UUID:
    return mitarbeiter.id


def hat_mindestens(mitarbeiter: Mitarbeiter, rolle: Systemrolle) -> bool:
    return _RANG[mitarbeiter.systemrolle] >= _RANG[rolle]


def rolle_mindestens(rolle: Systemrolle):
    """Dependency-Fabrik: nur Mitarbeiter mit dieser oder einer höheren Systemrolle (sonst 403).

    Beispiel: dependencies=[Depends(rolle_mindestens(Systemrolle.werkstattleiter))]
    """

    def pruefen(mitarbeiter: Mitarbeiter = Depends(aktueller_mitarbeiter)) -> Mitarbeiter:
        if not hat_mindestens(mitarbeiter, rolle):
            raise _keine_berechtigung()
        return mitarbeiter

    return pruefen


require_admin = rolle_mindestens(Systemrolle.admin)


def darf_auftrag_bearbeiten(
    auftrag_id: uuid.UUID,
    mitarbeiter: Mitarbeiter = Depends(aktueller_mitarbeiter),
    db: Session = Depends(get_db),
) -> None:
    """Statuswechsel/Korrektur (7.2): zugewiesener Mitarbeiter oder Werkstattleiter/Admin.

    Existiert der Auftrag nicht, wird hier nichts entschieden – der Endpunkt meldet 404.
    """
    if hat_mindestens(mitarbeiter, Systemrolle.werkstattleiter):
        return
    auftrag = db.get(Auftrag, auftrag_id)
    if auftrag is None:
        return
    if auftrag.zugewiesener_mitarbeiter_id != mitarbeiter.id:
        raise _keine_berechtigung()

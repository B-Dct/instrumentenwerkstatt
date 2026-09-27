"""Login (Datenmodell 2.2)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import aktueller_mitarbeiter, anmelden, token_erstellen
from app.db import get_db
from app.models import Mitarbeiter, Systemrolle

router = APIRouter(prefix="/auth", tags=["Login"])


class AngemeldeterMitarbeiter(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    systemrolle: Systemrolle


class LoginAntwort(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mitarbeiter: AngemeldeterMitarbeiter


def _mitarbeiter_info(m: Mitarbeiter) -> AngemeldeterMitarbeiter:
    return AngemeldeterMitarbeiter(id=m.id, name=m.name, email=m.email, systemrolle=m.systemrolle)


@router.post("/login", response_model=LoginAntwort)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> LoginAntwort:
    """Anmeldung mit E-Mail (Feld "username") und Passwort.

    Formular-Format nach OAuth2-Standard, damit der "Authorize"-Knopf in /docs funktioniert.
    """
    mitarbeiter = anmelden(db, form.username, form.password)
    if mitarbeiter is None:
        # Bewusst keine Unterscheidung, ob E-Mail oder Passwort falsch war
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "E-Mail oder Passwort ungültig",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return LoginAntwort(access_token=token_erstellen(mitarbeiter), mitarbeiter=_mitarbeiter_info(mitarbeiter))


@router.get("/ich", response_model=AngemeldeterMitarbeiter)
def ich(mitarbeiter: Mitarbeiter = Depends(aktueller_mitarbeiter)) -> AngemeldeterMitarbeiter:
    """Wer bin ich? (zum Prüfen, ob die Anmeldung funktioniert)"""
    return _mitarbeiter_info(mitarbeiter)

"""Test-Setup: Jeder Test läuft gegen die echte Datenbank, aber in einer Transaktion,
die am Ende zurückgerollt wird – es bleiben keine Testdaten zurück."""

import itertools
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import passwort_hashen, token_erstellen
from app.db import engine, get_db
from app.main import app
from app.models import Mitarbeiter, Systemrolle
from app.routers import auftraege, kunden

TEST_PASSWORT = "richtig-langes-passwort"
_TEST_PASSWORT_HASH = passwort_hashen(TEST_PASSWORT)  # einmal hashen (Argon2 ist absichtlich langsam)


def konto_anlegen(db, rolle: Systemrolle = Systemrolle.mitarbeiter, name: str = "Test Konto", **extra) -> Mitarbeiter:
    mitarbeiter = Mitarbeiter(
        name=name,
        email=f"{secrets.token_hex(4)}@test.invalid",
        systemrolle=rolle,
        passwort_hash=_TEST_PASSWORT_HASH,
        **extra,
    )
    db.add(mitarbeiter)
    db.flush()
    return mitarbeiter


def angemeldet_als(mitarbeiter: Mitarbeiter) -> dict:
    """Header für Anfragen als dieser Mitarbeiter."""
    return {"Authorization": f"Bearer {token_erstellen(mitarbeiter)}"}


# Header-Wert, der die Standard-Anmeldung des Test-Clients aufhebt
OHNE_ANMELDUNG = {"Authorization": ""}


@pytest.fixture(autouse=True)
def keine_echten_nummern(monkeypatch):
    """Nummernzähler der Datenbank werden beim Rollback NICHT zurückgesetzt –
    Tests dürfen deshalb keine echten Auftrags-/Kundennummern verbrauchen (gilt für alle Tests)."""
    zaehler = itertools.count(1)
    monkeypatch.setattr(auftraege, "_neue_auftragsnummer", lambda db: f"TEST-{next(zaehler):05d}")
    # Gleiches gilt für Kundennummern
    kunden_zaehler = itertools.count(1)
    monkeypatch.setattr(kunden, "_neue_kundennummer", lambda db: f"TEST-K-{next(kunden_zaehler):05d}")


@pytest.fixture
def db():
    verbindung = engine.connect()
    transaktion = verbindung.begin()
    # autoflush=False wie in app/db.py (SessionLocal)
    session = Session(bind=verbindung, join_transaction_mode="create_savepoint", autoflush=False)
    try:
        yield session
    finally:
        session.close()
        transaktion.rollback()
        verbindung.close()


@pytest.fixture
def client(db):
    """Test-Client ohne Anmeldung (Tests setzen client.headers bei Bedarf)."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()

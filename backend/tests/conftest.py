"""Test-Setup: Jeder Test läuft gegen die echte Datenbank, aber in einer Transaktion,
die am Ende zurückgerollt wird – es bleiben keine Testdaten zurück."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.main import app


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
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()

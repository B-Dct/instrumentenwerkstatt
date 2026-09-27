"""Datenbankverbindung (SQLAlchemy). Tabellen werden hier noch NICHT angelegt."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _sqlalchemy_url(url: str) -> str:
    # "postgresql://" auf den psycopg-3-Treiber umbiegen
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


engine = create_engine(_sqlalchemy_url(settings.database_url), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """Basisklasse für alle künftigen Tabellen-Modelle."""


def get_db() -> Iterator[Session]:
    """FastAPI-Dependency: eine DB-Session pro Anfrage."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""Datenbankverbindung (SQLAlchemy). Tabellen werden hier noch NICHT angelegt."""

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
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
    """Basisklasse für alle Tabellen-Modelle (siehe app/models.py)."""

    # Einheitliche Namen für Indizes/Constraints – wichtig für saubere Migrationen
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def get_db() -> Iterator[Session]:
    """FastAPI-Dependency: eine DB-Session pro Anfrage."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

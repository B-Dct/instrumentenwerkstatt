"""Zeitstempel mit clock_timestamp

Revision ID: a87059afdfe2
Revises: 77294ab78d7a
Create Date: 2026-09-27 19:14:51.562027

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a87059afdfe2'
down_revision: Union[str, Sequence[str], None] = '77294ab78d7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SPALTEN = [
    ("arbeitszeit_anpassung", "erfasst_am"),
    ("arbeitszeiterfassung", "erfasst_am"),
    ("auftrag", "erstellt_am"),
    ("auftrag_statusverlauf", "geaendert_am"),
    ("kunde", "erstellt_am"),
    ("mitarbeiter", "erstellt_am"),
    ("mitarbeiter_arbeitszeit", "geaendert_am"),
    ("reparatur_vorgabewert", "geaendert_am"),
    ("schaetzungs_log", "berechnet_am"),
    ("system_ereignis_log", "zeitpunkt"),
]


def upgrade() -> None:
    """Zeitstempel bekommen die echte Uhrzeit des Eintrags statt des Transaktionsbeginns."""
    for tabelle, spalte in SPALTEN:
        op.alter_column(tabelle, spalte, server_default=sa.text("clock_timestamp()"))


def downgrade() -> None:
    for tabelle, spalte in SPALTEN:
        op.alter_column(tabelle, spalte, server_default=sa.text("now()"))

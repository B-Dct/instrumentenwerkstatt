"""Instrumentenklassen und Reparaturarten mit archiviert_am

Revision ID: 29fba7051bcf
Revises: 22b61f44d096
Create Date: 2026-09-28 17:36:14.203546

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29fba7051bcf'
down_revision: Union[str, Sequence[str], None] = '22b61f44d096'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABELLEN = ("instrumentenklasse", "reparaturart")


def upgrade() -> None:
    """aktiv (ja/nein) → archiviert_am (Datum), wie bei Kunden/Instrumenten."""
    for tabelle in TABELLEN:
        op.add_column(tabelle, sa.Column("archiviert_am", sa.DateTime(timezone=True), nullable=True))
        op.execute(f"UPDATE {tabelle} SET archiviert_am = clock_timestamp() WHERE NOT aktiv")
        op.drop_column(tabelle, "aktiv")


def downgrade() -> None:
    for tabelle in TABELLEN:
        op.add_column(tabelle, sa.Column("aktiv", sa.Boolean(), server_default=sa.text("true"), nullable=False))
        op.execute(f"UPDATE {tabelle} SET aktiv = (archiviert_am IS NULL)")
        op.drop_column(tabelle, "archiviert_am")

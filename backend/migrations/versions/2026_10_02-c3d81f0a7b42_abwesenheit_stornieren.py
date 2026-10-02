"""Abwesenheit stornieren statt löschen

Revision ID: c3d81f0a7b42
Revises: bc925ae19616
Create Date: 2026-10-02 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d81f0a7b42'
down_revision: Union[str, Sequence[str], None] = 'bc925ae19616'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('abwesenheit', sa.Column('storniert_am', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('abwesenheit', 'storniert_am')

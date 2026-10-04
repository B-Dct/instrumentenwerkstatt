"""Instrument: optionales Feld ausfuehrung

Oberfläche und Ventilmechanik sind Eigenschaften des Instruments, nicht des einzelnen Auftrags
(Datenmodell 2.5). Die Ausführung wird einmal am Instrument hinterlegt und wählt bei jedem
Auftrag den passenden Richtpreis (2.6a) und den passenden historischen Durchschnitt (Abschnitt 4).

Revision ID: a4e7c1d95f30
Revises: 8c1f4a6e2b90
Create Date: 2026-10-04 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4e7c1d95f30'
down_revision: Union[str, Sequence[str], None] = '8c1f4a6e2b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('instrument', sa.Column('ausfuehrung', sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('instrument', 'ausfuehrung')

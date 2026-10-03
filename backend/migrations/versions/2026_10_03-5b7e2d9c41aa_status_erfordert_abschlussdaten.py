"""Status-Merkmal erfordert_zeiterfassung heißt jetzt erfordert_abschlussdaten

Das Merkmal steuert beim Wechsel in den Status die Pflichtabfrage aus 9.8 – inzwischen
Arbeitszeit UND abgerechneter Betrag, daher der allgemeinere Name (Datenmodell 2.7a).

Revision ID: 5b7e2d9c41aa
Revises: 910c0f03c1d8
Create Date: 2026-10-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5b7e2d9c41aa'
down_revision: Union[str, Sequence[str], None] = '910c0f03c1d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('auftragsstatus', 'erfordert_zeiterfassung', new_column_name='erfordert_abschlussdaten')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('auftragsstatus', 'erfordert_abschlussdaten', new_column_name='erfordert_zeiterfassung')

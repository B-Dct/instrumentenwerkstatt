"""Vorgabewert: optionales Feld ausfuehrung

Verfeinerung innerhalb derselben Instrumentenklasse für reine Ausführungsunterschiede
(Oberfläche, Ventilmechanik), statt dafür eigene Instrumentenklassen anzulegen (Datenmodell 2.6a).
Die Eindeutigkeit unter den aktiven Einträgen gilt jetzt für Reparaturart + Instrumentenklasse
+ Ausführung.

Revision ID: 6d2a9f3b7c15
Revises: 5b7e2d9c41aa
Create Date: 2026-10-03 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d2a9f3b7c15'
down_revision: Union[str, Sequence[str], None] = '5b7e2d9c41aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = 'uq_reparatur_vorgabewert_kombination'
NUR_AKTIVE = dict(unique=True, postgresql_nulls_not_distinct=True, postgresql_where=sa.text('archiviert_am IS NULL'))


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('reparatur_vorgabewert', sa.Column('ausfuehrung', sa.String(length=100), nullable=True))
    op.drop_index(INDEX, table_name='reparatur_vorgabewert')
    op.create_index(INDEX, 'reparatur_vorgabewert', ['reparaturart_id', 'instrumentenklasse_id', 'ausfuehrung'], **NUR_AKTIVE)


def downgrade() -> None:
    """Downgrade schema. Bricht ab, falls es mehrere aktive Ausführungen einer Kombination gibt."""
    op.drop_index(INDEX, table_name='reparatur_vorgabewert')
    op.create_index(INDEX, 'reparatur_vorgabewert', ['reparaturart_id', 'instrumentenklasse_id'], **NUR_AKTIVE)
    op.drop_column('reparatur_vorgabewert', 'ausfuehrung')

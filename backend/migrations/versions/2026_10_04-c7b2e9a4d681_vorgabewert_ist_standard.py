"""Vorgabewert: Kennzeichen ist_standard, Standardausführungen bekommen einen Namen

Bei mehreren Ausführungen derselben Kombination aus Reparaturart und Instrumentenklasse trägt jede
einen Namen, genau eine ist Standard (Datenmodell 2.6a). Die Datenbank sichert ab, dass es je
Kombination höchstens einen aktiven Standard gibt. Die Umstellung der Bestandsdaten steht in
app/grunddaten/ausfuehrung_standard_2026_10.py (mehrfach ausführbar, rät nicht).

Revision ID: c7b2e9a4d681
Revises: a4e7c1d95f30
Create Date: 2026-10-04 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.grunddaten import ausfuehrung_standard_2026_10


# revision identifiers, used by Alembic.
revision: str = 'c7b2e9a4d681'
down_revision: Union[str, Sequence[str], None] = 'a4e7c1d95f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = 'uq_reparatur_vorgabewert_standard'


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('reparatur_vorgabewert',
                  sa.Column('ist_standard', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_index(INDEX, 'reparatur_vorgabewert', ['reparaturart_id', 'instrumentenklasse_id'], unique=True,
                    postgresql_where=sa.text('archiviert_am IS NULL AND ist_standard'))
    ergebnis = ausfuehrung_standard_2026_10.anwenden(op.get_bind())
    print(f"Standardausführungen: {ergebnis['benannt']} benannt, {ergebnis['standard_gesetzt']} als Standard gekennzeichnet")
    for klasse, reparaturart in ergebnis["offen"]:
        print(f"  OHNE ERKENNBAREN STANDARD (bitte in der Preisliste festlegen): {klasse} / {reparaturart}")


def downgrade() -> None:
    """Downgrade schema. Die vergebenen Namen der Standardausführungen bleiben erhalten."""
    op.drop_index(INDEX, table_name='reparatur_vorgabewert')
    op.drop_column('reparatur_vorgabewert', 'ist_standard')

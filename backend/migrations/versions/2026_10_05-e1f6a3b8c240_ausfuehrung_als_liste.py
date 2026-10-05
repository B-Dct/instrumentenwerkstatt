"""Ausführungen als eigene Liste je Instrumentenklasse

Neue Tabelle ausfuehrung (Datenmodell 2.4b). Richtpreis und Instrument verweisen darauf
(ausfuehrung_id) statt die Bezeichnung als Text zu tragen; das Standard-Kennzeichen wandert vom
Richtpreis an die Ausführung der Klasse. Die Übertragung der Bestandsdaten steht in
app/grunddaten/ausfuehrung_liste_2026_10.py – sie rät nicht und bricht bei uneindeutigen Daten ab,
ohne etwas zu ändern (die ganze Migration läuft in einer Transaktion).

Revision ID: e1f6a3b8c240
Revises: c7b2e9a4d681
Create Date: 2026-10-05 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.grunddaten import ausfuehrung_liste_2026_10


# revision identifiers, used by Alembic.
revision: str = 'e1f6a3b8c240'
down_revision: Union[str, Sequence[str], None] = 'c7b2e9a4d681'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KOMBINATION = 'uq_reparatur_vorgabewert_kombination'
STANDARD_ALT = 'uq_reparatur_vorgabewert_standard'
NUR_AKTIVE = sa.text('archiviert_am IS NULL')


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ausfuehrung',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('instrumentenklasse_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('bezeichnung', sa.String(length=100), nullable=False),
        sa.Column('ist_standard', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('archiviert_am', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['instrumentenklasse_id'], ['instrumentenklasse.id'],
                                name=op.f('fk_ausfuehrung_instrumentenklasse_id_instrumentenklasse')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ausfuehrung')),
    )
    op.execute('ALTER TABLE "ausfuehrung" ENABLE ROW LEVEL SECURITY')
    op.create_index(op.f('ix_ausfuehrung_instrumentenklasse_id'), 'ausfuehrung', ['instrumentenklasse_id'])
    op.create_index('uq_ausfuehrung_bezeichnung', 'ausfuehrung', ['instrumentenklasse_id', sa.text('lower(bezeichnung)')],
                    unique=True, postgresql_where=NUR_AKTIVE)
    op.create_index('uq_ausfuehrung_standard', 'ausfuehrung', ['instrumentenklasse_id'], unique=True,
                    postgresql_where=sa.text('archiviert_am IS NULL AND ist_standard'))

    for tabelle in ('reparatur_vorgabewert', 'instrument'):
        op.add_column(tabelle, sa.Column('ausfuehrung_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(op.f(f'fk_{tabelle}_ausfuehrung_id_ausfuehrung'), tabelle, 'ausfuehrung',
                              ['ausfuehrung_id'], ['id'])
        op.create_index(op.f(f'ix_{tabelle}_ausfuehrung_id'), tabelle, ['ausfuehrung_id'])

    # Die alte Eindeutigkeit (über den Text) würde das Zuordnen zum Standard nicht stören, wird aber ohnehin ersetzt
    op.drop_index(KOMBINATION, table_name='reparatur_vorgabewert')
    op.drop_index(STANDARD_ALT, table_name='reparatur_vorgabewert')
    ergebnis = ausfuehrung_liste_2026_10.uebertragen(op.get_bind())
    print(f"Ausführungen: {ergebnis['ausfuehrungen']} angelegt, {ergebnis['richtpreise']} Richtpreise und "
          f"{ergebnis['instrumente']} Instrumente verknüpft, {ergebnis['dem_standard_zugeordnet']} bisher unbenannte "
          f"Richtpreise der Standardausführung zugeordnet")
    for hinweis in ergebnis['hinweise']:
        print(f"  BITTE PRÜFEN (nicht zusammengeführt): {hinweis}")

    op.create_index(KOMBINATION, 'reparatur_vorgabewert', ['reparaturart_id', 'instrumentenklasse_id', 'ausfuehrung_id'],
                    unique=True, postgresql_nulls_not_distinct=True, postgresql_where=NUR_AKTIVE)
    op.drop_column('reparatur_vorgabewert', 'ausfuehrung')
    op.drop_column('reparatur_vorgabewert', 'ist_standard')
    op.drop_column('instrument', 'ausfuehrung')


def downgrade() -> None:
    """Downgrade schema: Die Bezeichnungen wandern als Text zurück an Richtpreis und Instrument."""
    op.add_column('instrument', sa.Column('ausfuehrung', sa.String(length=100), nullable=True))
    op.add_column('reparatur_vorgabewert', sa.Column('ausfuehrung', sa.String(length=100), nullable=True))
    op.add_column('reparatur_vorgabewert',
                  sa.Column('ist_standard', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.execute("UPDATE instrument i SET ausfuehrung = a.bezeichnung FROM ausfuehrung a WHERE a.id = i.ausfuehrung_id")
    op.execute("UPDATE reparatur_vorgabewert v SET ausfuehrung = a.bezeichnung, ist_standard = a.ist_standard "
               "FROM ausfuehrung a WHERE a.id = v.ausfuehrung_id")
    op.drop_index(KOMBINATION, table_name='reparatur_vorgabewert')
    for tabelle in ('reparatur_vorgabewert', 'instrument'):
        op.drop_index(op.f(f'ix_{tabelle}_ausfuehrung_id'), table_name=tabelle)
        op.drop_constraint(op.f(f'fk_{tabelle}_ausfuehrung_id_ausfuehrung'), tabelle, type_='foreignkey')
        op.drop_column(tabelle, 'ausfuehrung_id')
    op.create_index(KOMBINATION, 'reparatur_vorgabewert', ['reparaturart_id', 'instrumentenklasse_id', 'ausfuehrung'],
                    unique=True, postgresql_nulls_not_distinct=True, postgresql_where=NUR_AKTIVE)
    op.create_index(STANDARD_ALT, 'reparatur_vorgabewert', ['reparaturart_id', 'instrumentenklasse_id'], unique=True,
                    postgresql_where=sa.text('archiviert_am IS NULL AND ist_standard'))
    op.drop_table('ausfuehrung')

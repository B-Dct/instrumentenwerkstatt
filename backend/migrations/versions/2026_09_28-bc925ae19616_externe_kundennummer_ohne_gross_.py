"""Externe Kundennummer ohne Gross-Kleinschreibung eindeutig

Revision ID: bc925ae19616
Revises: fb55558b75f2
Create Date: 2026-09-28 20:27:14.076413

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc925ae19616'
down_revision: Union[str, Sequence[str], None] = 'fb55558b75f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Externe Kundennummer eindeutig ohne Beachtung der Groß-/Kleinschreibung.

    Bricht mit klarer Meldung ab (ohne etwas zu ändern), falls es schon Nummern gibt, die sich
    nur in der Schreibweise unterscheiden – diese müssen vorher von Hand bereinigt werden.
    """
    konflikte = op.get_bind().execute(sa.text("""
        SELECT lower(externe_kundennummer) AS nummer,
               string_agg(kundennummer || ' (' || externe_kundennummer || ')', ', ' ORDER BY kundennummer) AS kunden
        FROM kunde
        WHERE externe_kundennummer IS NOT NULL
        GROUP BY lower(externe_kundennummer)
        HAVING count(*) > 1
    """)).all()
    if konflikte:
        details = "; ".join(f"{k.kunden}" for k in konflikte)
        raise RuntimeError(
            "Migration abgebrochen, nichts wurde geändert: Folgende externe Kundennummern unterscheiden "
            f"sich nur in der Groß-/Kleinschreibung und müssen zuerst bereinigt werden: {details}"
        )
    op.drop_constraint("uq_kunde_externe_kundennummer", "kunde", type_="unique")
    op.create_index("uq_kunde_externe_kundennummer", "kunde", [sa.text("lower(externe_kundennummer)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_kunde_externe_kundennummer", table_name="kunde")
    op.create_unique_constraint("uq_kunde_externe_kundennummer", "kunde", ["externe_kundennummer"])

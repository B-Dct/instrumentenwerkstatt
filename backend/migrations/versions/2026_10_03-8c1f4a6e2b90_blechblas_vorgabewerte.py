"""Vorgabewerte für Blechblasinstrumente, Reparaturarten Reinigung/Überholung, Stundensatz

Daten statt Schema: 15 Instrumentenklassen (14 neue + die vorhandene Trompete), 2 Reparaturarten,
38 Vorgabewerte (Trompete und Flügelhorn/Kornett mit mehreren Ausführungen) und die
Werkstatt-Einstellung "stundensatz". Quelle und Herleitung stehen in
app/grunddaten/blechblas_2026_10.py (Preisliste Reisser Musik, Stand Oktober 2026;
45 €/Std. als erste Orientierung, nicht verbindlich). Legt nur Fehlendes an.

Revision ID: 8c1f4a6e2b90
Revises: 6d2a9f3b7c15
Create Date: 2026-10-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

from app.grunddaten import blechblas_2026_10


# revision identifiers, used by Alembic.
revision: str = '8c1f4a6e2b90'
down_revision: Union[str, Sequence[str], None] = '6d2a9f3b7c15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Daten anlegen (mehrfach ausführbar, überschreibt nichts)."""
    blechblas_2026_10.anlegen(op.get_bind())


def downgrade() -> None:
    """Bewusst leer: Stammdaten werden nie gelöscht (sie können inzwischen in Aufträgen verwendet
    oder von Hand angepasst worden sein). Nicht Gewünschtes in der Verwaltung archivieren."""

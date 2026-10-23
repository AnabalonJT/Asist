"""add activity strength fields

Revision ID: 20260616_100000
Revises: 20260615_100000
Create Date: 2026-06-16 10:00:00.000000

Note: ``_migrate_columns()`` in ``database.py`` also adds these columns at
startup as a runtime safety net (ALTER TABLE on the existing ``activities``
table), since ``Base.metadata.create_all`` does NOT alter existing tables.
This migration keeps the Alembic history and environments reproducible (the
versioned source of truth for clean deploys).

Adds detailed strength-training fields to ``activities`` (Phase 2, strength
logging):
  * ``exercise_name`` -> optional exercise label (e.g. "Press Banca",
    "Sentadillas"). NULL for non-strength / legacy activities.
  * ``sets_data`` -> optional JSON string with one entry per set,
    ``[{"reps": 10, "weight_kg": 50}, ...]``. NULL for non-strength / legacy
    activities.

Both columns are nullable with no default, so existing activities remain valid
(backward compatible) and ``calories`` is left unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260616_100000'
down_revision: Union[str, None] = '20260615_100000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable so existing activities stay valid (backward compatible).
    op.add_column('activities', sa.Column('exercise_name', sa.String(length=100), nullable=True))
    op.add_column('activities', sa.Column('sets_data', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('activities', 'sets_data')
    op.drop_column('activities', 'exercise_name')

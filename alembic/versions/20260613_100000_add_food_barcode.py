"""add food barcode

Revision ID: 20260613_100000
Revises: 20260612_100000
Create Date: 2026-06-13 10:00:00.000000

Note: ``_migrate_columns`` in ``init_db()`` also adds the ``foods.barcode``
column (and its unique index) at runtime as a safety net for databases that
were created before this feature; this migration keeps the Alembic history and
environments reproducible (the versioned source of truth for clean deploys).

Adds the optional ``barcode`` column (EAN/UPC) to the ``foods`` catalog with a
unique index so a scanned food can be recognized again next time.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260613_100000'
down_revision: Union[str, None] = '20260612_100000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('foods', sa.Column('barcode', sa.String(length=14), nullable=True))
    op.create_index(op.f('ix_foods_barcode'), 'foods', ['barcode'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_foods_barcode'), table_name='foods')
    op.drop_column('foods', 'barcode')

"""add diet phase plans

Revision ID: 20260614_100000
Revises: 20260613_100000
Create Date: 2026-06-14 10:00:00.000000

Note: ``Base.metadata.create_all`` in ``init_db()`` also creates this table on
startup as a runtime safety net; because this is a NEW table (not an added
column), ``_migrate_columns`` (which only covers ALTER TABLE on existing
tables) does not apply here. This migration keeps the Alembic history and
environments reproducible (the versioned source of truth for clean deploys).

Creates the ``diet_phase_plans`` table for the Goal_Wizard: a progressive A->B
diet split into ordered phases (JSON list in a Text column), with at most one
active plan per user. Indexes on ``user_id`` and ``active`` support the usual
"active plan for this user" lookup.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260614_100000'
down_revision: Union[str, None] = '20260613_100000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create diet_phase_plans table (1:N with users, at most one active)
    op.create_table('diet_phase_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('start_weight_kg', sa.Float(), nullable=False),
        sa.Column('target_weight_kg', sa.Float(), nullable=False),
        sa.Column('goal_reached', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('phases', sa.Text(), nullable=False, server_default="'[]'"),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_diet_phase_plans_user_id'), 'diet_phase_plans', ['user_id'], unique=False)
    op.create_index(op.f('ix_diet_phase_plans_active'), 'diet_phase_plans', ['active'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_diet_phase_plans_active'), table_name='diet_phase_plans')
    op.drop_index(op.f('ix_diet_phase_plans_user_id'), table_name='diet_phase_plans')
    op.drop_table('diet_phase_plans')

"""add goals and challenges tables

Revision ID: 20260617_100000
Revises: 20260616_100000
Create Date: 2026-06-17 10:00:00.000000

Note: ``Base.metadata.create_all`` in ``init_db()`` also creates the
``challenges`` / ``goals`` tables on startup as a runtime safety net, and
``_migrate_columns()`` backfills the Phase-2 goal columns (``ends_at``,
``challenge_id``, ``closed_notified``) on pre-existing ``goals`` tables via
ALTER TABLE. This migration keeps the Alembic history and environments
reproducible (the versioned source of truth for clean deploys) — until now the
``goals`` and ``challenges`` tables existed only through ``create_all`` and had
no Alembic revision at all.

Adds the Habit Goals system (Phase 2, habit goals):
  * ``challenges`` -> groups multiple goals under one shared deadline
    (e.g. "75 días de disciplina"). Created first because ``goals`` references
    it.
  * ``goals`` -> a per-user habit/activity frequency target. ``target_count`` +
    ``period`` together express the spec's "target_frequency (times per
    period)" (e.g. "correr 3 veces por semana" -> target_count=3,
    period="weekly"; "meditar todos los días" -> period="daily"). A goal may be
    standalone (``challenge_id`` NULL) or belong to a challenge.

Both tables use server defaults matching the SQLAlchemy model defaults so rows
inserted through either ``create_all`` or Alembic behave identically.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260617_100000'
down_revision: Union[str, None] = '20260616_100000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create challenges first — goals.challenge_id references it.
    op.create_table(
        'challenges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('ends_at', sa.String(length=20), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('closed_notified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_challenges_user_id'), 'challenges', ['user_id'], unique=False)

    # Create goals. ``target_count`` + ``period`` express "target_frequency".
    op.create_table(
        'goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('challenge_id', sa.Integer(), nullable=True),
        sa.Column('activity_type', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=False),
        sa.Column('target_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('period', sa.String(length=20), nullable=False, server_default='weekly'),
        sa.Column('ends_at', sa.String(length=20), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('closed_notified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_goals_user_id'), 'goals', ['user_id'], unique=False)
    op.create_index(op.f('ix_goals_challenge_id'), 'goals', ['challenge_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_goals_challenge_id'), table_name='goals')
    op.drop_index(op.f('ix_goals_user_id'), table_name='goals')
    op.drop_table('goals')

    op.drop_index(op.f('ix_challenges_user_id'), table_name='challenges')
    op.drop_table('challenges')

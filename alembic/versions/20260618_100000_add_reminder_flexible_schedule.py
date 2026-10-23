"""add reminder flexible-schedule fields

Revision ID: 20260618_100000
Revises: 20260617_100000
Create Date: 2026-06-18 10:00:00.000000

Note: ``Base.metadata.create_all`` in ``init_db()`` also creates the
``reminders`` table on startup, and ``_migrate_columns()`` backfills these
Phase-2 columns (``schedule_days``, ``schedule_date``, ``challenge_id``) on a
pre-existing ``reminders`` table via ALTER TABLE as a runtime safety net, since
``create_all`` does NOT alter existing tables. This migration keeps the Alembic
history and environments reproducible (the versioned source of truth for clean
deploys) — the ``reminders`` table was created in the initial schema
(20260609_201421) but these flexible-schedule columns had no Alembic revision.

Schema reconciliation (Phase 2, advanced reminder scheduling):
The spec task 25.1 lists ``schedule_type`` and ``schedule_interval`` fields,
but the design and the whole implementation (scheduler, LLM service, reminder
routes) encode BOTH in the existing ``frequency`` column — "biweekly" is a
frequency value, and specific-day/one-time scheduling is expressed through
``frequency`` + ``schedule_days`` / ``schedule_date``. We therefore do NOT add
redundant ``schedule_type``/``schedule_interval`` columns (that would fragment
the schema and break the scheduler). This migration only adds the genuinely new
nullable columns:
  * ``schedule_days`` -> CSV of weekday numbers for ``frequency='specific_days'``
    (e.g. "0,2" = lunes y miércoles; "5,6" = fin de semana). 0=Mon .. 6=Sun.
  * ``schedule_date`` -> "YYYY-MM-DD" target for one-time (``frequency='once'``)
    reminders (e.g. "2026-07-06").
  * ``challenge_id`` -> optional link to a ``challenges`` row.

All three columns are nullable with no default, so existing reminders
(daily/weekdays/weekends) remain valid (backward compatible).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260618_100000'
down_revision: Union[str, None] = '20260617_100000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable so existing reminders stay valid (backward compatible).
    op.add_column('reminders', sa.Column('schedule_days', sa.String(length=50), nullable=True))
    op.add_column('reminders', sa.Column('schedule_date', sa.String(length=20), nullable=True))
    op.add_column('reminders', sa.Column('challenge_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_reminders_challenge_id'), 'reminders', ['challenge_id'], unique=False)
    op.create_foreign_key(
        'fk_reminders_challenge_id_challenges',
        'reminders', 'challenges',
        ['challenge_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_reminders_challenge_id_challenges', 'reminders', type_='foreignkey')
    op.drop_index(op.f('ix_reminders_challenge_id'), table_name='reminders')
    op.drop_column('reminders', 'challenge_id')
    op.drop_column('reminders', 'schedule_date')
    op.drop_column('reminders', 'schedule_days')

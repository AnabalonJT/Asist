"""add meal planner tables

Revision ID: 20260612_100000
Revises: 20260611_100000
Create Date: 2026-06-12 10:00:00.000000

Note: ``Base.metadata.create_all`` in ``init_db()`` also creates these tables on
startup as a runtime safety net; this migration keeps the Alembic history and
environments reproducible (the versioned source of truth for clean deploys).

Creates the five Meal_Planner tables: foods (global catalog), user_food_inventory
(1:N with dedup per (user, food)), dietary_profiles (1:1 with users),
nutrition_targets (1:1 with users) and meal_plans (1:N, at most one active per user).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260612_100000'
down_revision: Union[str, None] = '20260611_100000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create foods table (global catalog, shared across users)
    op.create_table('foods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('kcal_per_100g', sa.Float(), nullable=False),
        sa.Column('protein_g_per_100g', sa.Float(), nullable=False),
        sa.Column('fat_g_per_100g', sa.Float(), nullable=False),
        sa.Column('carbs_g_per_100g', sa.Float(), nullable=False),
        sa.Column('fiber_g_per_100g', sa.Float(), nullable=True),
        sa.Column('is_meat', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_animal', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('has_gluten', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_foods_name'), 'foods', ['name'], unique=True)

    # Create user_food_inventory table (1:N with dedup per (user, food))
    op.create_table('user_food_inventory',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('food_id', sa.Integer(), nullable=False),
        sa.Column('quantity_grams', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['food_id'], ['foods.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'food_id', name='uq_user_food')
    )
    op.create_index(op.f('ix_user_food_inventory_user_id'), 'user_food_inventory', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_food_inventory_food_id'), 'user_food_inventory', ['food_id'], unique=False)

    # Create dietary_profiles table (1:1 with users)
    op.create_table('dietary_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('vegetarian', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('vegan', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('gluten_free', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('allergens', sa.String(length=500), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dietary_profiles_user_id'), 'dietary_profiles', ['user_id'], unique=True)

    # Create nutrition_targets table (1:1 with users)
    op.create_table('nutrition_targets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kcal', sa.Float(), nullable=False),
        sa.Column('protein_g', sa.Float(), nullable=False),
        sa.Column('fat_g', sa.Float(), nullable=False),
        sa.Column('carbs_g', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_nutrition_targets_user_id'), 'nutrition_targets', ['user_id'], unique=True)

    # Create meal_plans table (1:N with users, at most one active)
    op.create_table('meal_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('structure', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_meal_plans_user_id'), 'meal_plans', ['user_id'], unique=False)
    op.create_index(op.f('ix_meal_plans_active'), 'meal_plans', ['active'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_meal_plans_active'), table_name='meal_plans')
    op.drop_index(op.f('ix_meal_plans_user_id'), table_name='meal_plans')
    op.drop_table('meal_plans')

    op.drop_index(op.f('ix_nutrition_targets_user_id'), table_name='nutrition_targets')
    op.drop_table('nutrition_targets')

    op.drop_index(op.f('ix_dietary_profiles_user_id'), table_name='dietary_profiles')
    op.drop_table('dietary_profiles')

    op.drop_index(op.f('ix_user_food_inventory_food_id'), table_name='user_food_inventory')
    op.drop_index(op.f('ix_user_food_inventory_user_id'), table_name='user_food_inventory')
    op.drop_table('user_food_inventory')

    op.drop_index(op.f('ix_foods_name'), table_name='foods')
    op.drop_table('foods')

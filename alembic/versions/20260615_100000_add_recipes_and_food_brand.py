"""add recipes and food brand

Revision ID: 20260615_100000
Revises: 20260614_100000
Create Date: 2026-06-15 10:00:00.000000

Note: ``Base.metadata.create_all`` in ``init_db()`` also creates the new
``recipes`` / ``recipe_ingredients`` tables on startup as a runtime safety net;
however ``create_all`` does NOT alter existing tables, so the changes to
``foods`` (new ``brand`` column) and ``user_food_inventory`` (nullable
``food_id``, new ``recipe_id`` column plus its unique/check constraints) rely on
this migration (or on ``_migrate_columns``). This migration keeps the Alembic
history and environments reproducible (the versioned source of truth for clean
deploys).

Adds the Recipe feature (Req 4, 5) and an optional ``brand`` on catalog foods
(Req 1):
  * ``foods.brand`` -> optional brand string.
  * ``recipes`` -> private, user-owned recipes (unique name per user).
  * ``recipe_ingredients`` -> a Food plus grams within a recipe; deleted with
    the recipe (ondelete=CASCADE).
  * ``user_food_inventory`` now holds EITHER a food OR a recipe: ``food_id``
    becomes nullable, a nullable ``recipe_id`` FK is added, dedup per
    (user, recipe) is enforced and a XOR check guarantees exactly one of
    ``food_id`` / ``recipe_id`` is set.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260615_100000'
down_revision: Union[str, None] = '20260614_100000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Optional brand on catalog foods (Req 1)
    op.add_column('foods', sa.Column('brand', sa.String(length=100), nullable=True))

    # 2. recipes table (private, user-owned; unique name per user) (Req 4).
    #    Created BEFORE recipe_ingredients and the inventory recipe_id FK, which
    #    both reference it.
    op.create_table('recipes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_user_recipe_name')
    )
    op.create_index(op.f('ix_recipes_user_id'), 'recipes', ['user_id'], unique=False)

    # 3. recipe_ingredients table (a Food plus grams within a recipe) (Req 4).
    #    recipe_id uses ondelete=CASCADE so ingredients are removed with the recipe.
    op.create_table('recipe_ingredients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('food_id', sa.Integer(), nullable=False),
        sa.Column('grams', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['food_id'], ['foods.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recipe_ingredients_recipe_id'), 'recipe_ingredients', ['recipe_id'], unique=False)
    op.create_index(op.f('ix_recipe_ingredients_food_id'), 'recipe_ingredients', ['food_id'], unique=False)

    # 4. An inventory row may now hold a recipe instead of a food: food_id nullable.
    op.alter_column('user_food_inventory', 'food_id',
        existing_type=sa.Integer(),
        nullable=True)

    # 5. New nullable recipe_id FK (Req 5).
    op.add_column('user_food_inventory', sa.Column('recipe_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_user_food_inventory_recipe_id'), 'user_food_inventory', ['recipe_id'], unique=False)
    op.create_foreign_key('fk_user_food_inventory_recipe_id_recipes',
        'user_food_inventory', 'recipes', ['recipe_id'], ['id'])

    # 6. Dedup per (user, recipe) and XOR between food_id / recipe_id (Req 5.1).
    op.create_unique_constraint('uq_user_recipe', 'user_food_inventory', ['user_id', 'recipe_id'])
    op.create_check_constraint('ck_food_xor_recipe', 'user_food_inventory',
        '(food_id IS NOT NULL) <> (recipe_id IS NOT NULL)')


def downgrade() -> None:
    # Reverse of (6): drop the check + unique constraints on user_food_inventory.
    op.drop_constraint('ck_food_xor_recipe', 'user_food_inventory', type_='check')
    op.drop_constraint('uq_user_recipe', 'user_food_inventory', type_='unique')

    # Reverse of (5): drop the recipe_id FK, index and column.
    op.drop_constraint('fk_user_food_inventory_recipe_id_recipes', 'user_food_inventory', type_='foreignkey')
    op.drop_index(op.f('ix_user_food_inventory_recipe_id'), table_name='user_food_inventory')
    op.drop_column('user_food_inventory', 'recipe_id')

    # Reverse of (4): restore food_id NOT NULL.
    op.alter_column('user_food_inventory', 'food_id',
        existing_type=sa.Integer(),
        nullable=False)

    # Reverse of (3) then (2): drop recipe_ingredients BEFORE recipes (FK order).
    op.drop_index(op.f('ix_recipe_ingredients_food_id'), table_name='recipe_ingredients')
    op.drop_index(op.f('ix_recipe_ingredients_recipe_id'), table_name='recipe_ingredients')
    op.drop_table('recipe_ingredients')

    op.drop_index(op.f('ix_recipes_user_id'), table_name='recipes')
    op.drop_table('recipes')

    # Reverse of (1): drop the brand column.
    op.drop_column('foods', 'brand')

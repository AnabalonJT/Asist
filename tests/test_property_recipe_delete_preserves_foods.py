"""Property tests for recipe deletion (food-add-redesign).

This targets the async ``delete_recipe`` in ``app.services.recipe_service``.
Like ``test_property_goal_wizard_persist.py`` it needs a live async SQLAlchemy
session, so it spins up a throwaway in-memory SQLite database per example and
drives the async calls with ``asyncio.run`` from a synchronous Hypothesis test
(Hypothesis does not drive ``async def`` tests itself). This keeps Hypothesis
and the project's async SQLAlchemy stack compatible without a running Postgres.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (recipes/recipe_ingredients FK to foods/users).
import app.models  # noqa: F401
from app.models.user import User
from app.models.food import Food
from app.models.recipe import Recipe
from app.models.recipe_ingredient import RecipeIngredient
from app.services import recipe_service
from app.services.meal_service import ForbiddenError, ValidationError


# A single ingredient: a catalog Food reference (by position index) and grams
# within the valid 1..100000 range. Keeping grams modest avoids float noise.
_grams = st.floats(min_value=1.0, max_value=100000.0,
                   allow_nan=False, allow_infinity=False)


@st.composite
def _recipe_spec(draw):
    """Draw how many distinct catalog foods exist and which subset (with grams)
    a recipe uses. Returns ``(food_count, ingredients)`` where ``ingredients`` is
    a list of ``(food_index, grams)`` referencing foods by position (1..100
    ingredients per recipe, Req 4.1)."""
    food_count = draw(st.integers(min_value=1, max_value=6))
    ingredient_count = draw(st.integers(min_value=1, max_value=min(food_count, 5)))
    # Pick a distinct subset of food indices so each recipe ingredient points at
    # a real catalog food; duplicates are not needed to exercise the property.
    indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=food_count - 1),
            min_size=ingredient_count,
            max_size=ingredient_count,
            unique=True,
        )
    )
    ingredients = [(idx, round(draw(_grams), 2)) for idx in indices]
    return food_count, ingredients


async def _seed_foods(db: AsyncSession, count: int) -> list[int]:
    """Insert ``count`` distinct catalog foods and return their ids in order."""
    foods = [
        Food(
            name=f"Alimento {i}",
            kcal_per_100g=100.0 + i,
            protein_g_per_100g=5.0,
            fat_g_per_100g=2.0,
            carbs_g_per_100g=10.0,
            fiber_g_per_100g=1.0,
        )
        for i in range(count)
    ]
    db.add_all(foods)
    await db.flush()
    return [food.id for food in foods]


async def _count_rows(db: AsyncSession, model) -> int:
    rows = (await db.execute(select(model))).scalars().all()
    return len(rows)


async def _run_scenario(food_count: int, ingredients: list[tuple[int, float]]) -> None:
    """Seed two users + a shared catalog, create one recipe for the owner, then
    verify the three facets of Property 9 / Req 4.6, 8.4, 5.3:

      1. Deleting the OWNED recipe removes it and its RecipeIngredient rows
         (cascade) while every referenced catalog Food survives.
      2. Deleting a non-existent recipe id raises Spanish ValidationError and
         leaves all counts unchanged.
      3. Deleting a recipe owned by ANOTHER user raises ForbiddenError and does
         NOT delete it (privacy).
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            owner = User(email="owner@example.com", password_hash="x")
            other = User(email="other@example.com", password_hash="x")
            db.add_all([owner, other])
            await db.flush()

            food_ids = await _seed_foods(db, food_count)

            # Build the ingredient payload referencing real catalog foods.
            payload = [
                {"food_id": food_ids[idx], "grams": grams}
                for idx, grams in ingredients
            ]
            referenced_food_ids = {food_ids[idx] for idx, _ in ingredients}

            recipe = await recipe_service.create_recipe(
                db, owner.id, "Mi receta", payload
            )
            recipe_id = recipe.id
            ingredient_count = len(payload)

            # Sanity: the recipe + its ingredients exist, catalog is intact.
            assert await _count_rows(db, Recipe) == 1
            assert await _count_rows(db, RecipeIngredient) == ingredient_count
            assert await _count_rows(db, Food) == food_count

            # ── Facet 2: deleting a non-existent recipe is rejected, no changes.
            missing_id = recipe_id + 10_000
            with pytest.raises(ValidationError):
                await recipe_service.delete_recipe(db, owner.id, missing_id)
            assert await _count_rows(db, Recipe) == 1
            assert await _count_rows(db, RecipeIngredient) == ingredient_count
            assert await _count_rows(db, Food) == food_count

            # ── Facet 3: another user cannot delete this recipe (privacy).
            with pytest.raises(ForbiddenError):
                await recipe_service.delete_recipe(db, other.id, recipe_id)
            # The recipe and its ingredients still exist untouched.
            assert await db.get(Recipe, recipe_id) is not None
            assert await _count_rows(db, Recipe) == 1
            assert await _count_rows(db, RecipeIngredient) == ingredient_count
            assert await _count_rows(db, Food) == food_count

            # ── Facet 1: owner deletes → recipe + ingredients gone, foods survive.
            await recipe_service.delete_recipe(db, owner.id, recipe_id)
            await db.flush()

            assert await db.get(Recipe, recipe_id) is None
            assert await _count_rows(db, Recipe) == 0
            # Cascade removed every RecipeIngredient row.
            assert await _count_rows(db, RecipeIngredient) == 0
            # Every referenced catalog Food still exists (deletion preserves Food).
            assert await _count_rows(db, Food) == food_count
            surviving_food_ids = {
                fid
                for fid in (
                    (await db.execute(select(Food.id))).scalars().all()
                )
            }
            assert referenced_food_ids <= surviving_food_ids
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(spec=_recipe_spec())
def test_delete_recipe_preserves_referenced_foods(spec):
    """Feature: food-add-redesign, Property 9: Eliminar una Recipe es un viaje de
    ida y vuelta que preserva los Food.

    Validates: Requirements 4.6

    For every owned recipe, deleting it removes the recipe and its
    RecipeIngredient rows (cascade) while every referenced catalog Food survives;
    deleting a non-existent recipe raises a Spanish ValidationError and changes
    nothing; deleting another user's recipe raises ForbiddenError and does not
    delete it (Req 4.6, 8.4, 5.3 privacy).
    """
    food_count, ingredients = spec
    asyncio.run(_run_scenario(food_count, ingredients))

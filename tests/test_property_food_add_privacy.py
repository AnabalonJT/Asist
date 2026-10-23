"""Property test for the Food_Add_Redesign privacy invariant (food-add-redesign).

This targets the async services that read a user's PRIVATE data: the unified
incremental search (``app.services.search_service.unified_search``) and the
recipe CRUD (``list_recipes`` / ``get_recipe`` / ``delete_recipe`` in
``app.services.recipe_service``). The catalog of ``Food`` rows is GLOBAL and
shared across users, so a catalog hit may legitimately appear for anyone; the
privacy scope is specifically the user's own inventory entries and recipes.

Like ``test_property_goal_wizard_persist.py``, these functions need a live async
SQLAlchemy session, so each example spins up a throwaway in-memory SQLite
database and drives the async calls with ``asyncio.run`` from inside a
synchronous Hypothesis test. ``food_lookup_service.search_by_name`` is
monkeypatched to return ``[]`` so the Open Food Facts fallback contributes
nothing and the assertions concern only local, privately-scoped data.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio

import pytest
from hypothesis import given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (foods, recipes, recipe_ingredients,
# user_food_inventory, users).
import app.models  # noqa: F401
from app.models.food import Food
from app.models.recipe import Recipe
from app.models.recipe_ingredient import RecipeIngredient
from app.models.user import User
from app.models.user_food_inventory import UserFoodInventory
from app.services import food_lookup_service, recipe_service
from app.services.meal_service import ForbiddenError
from app.services.search_service import unified_search


# A short, LIKE-safe search token: letters only so it never contains SQL LIKE
# wildcards and always matches via the shared substring embedded in every name.
_token = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz",
    min_size=1,
    max_size=8,
)


@st.composite
def _scenario(draw):
    """Two distinct users A and B, each owning a private food (held only in
    their own inventory) and a private recipe, over a shared global catalog.

    Every name embeds a common ``term`` so a single ``unified_search(term)``
    matches the catalog food plus BOTH users' private food and recipe names;
    privacy is what must keep B's private rows out of A's results. ``suffix``
    makes names collide-free so ``create``/unique constraints never trip.
    """
    term = draw(_token)
    a_suffix = draw(_token)
    b_suffix = draw(_token)
    return {
        "term": term,
        # Distinct private-food names (both contain term) for A and B.
        "a_food": f"{term}-privfood-a-{a_suffix}",
        "b_food": f"{term}-privfood-b-{b_suffix}",
        # Distinct recipe names (both contain term) for A and B.
        "a_recipe": f"{term}-recipe-a-{a_suffix}",
        "b_recipe": f"{term}-recipe-b-{b_suffix}",
        # Catalog food name (contains term): global, shared, may appear for both.
        "shared_food": f"{term}-shared-catalog",
    }


def _make_food(name: str) -> Food:
    """A valid catalog Food with in-range per-100 g nutrition."""
    return Food(
        name=name[:100],
        kcal_per_100g=120.0,
        protein_g_per_100g=5.0,
        fat_g_per_100g=3.0,
        carbs_g_per_100g=15.0,
        fiber_g_per_100g=2.0,
    )


async def _run_scenario(data: dict) -> None:
    """Seed two users with private inventory + recipes over a shared catalog,
    then assert A never sees or operates on B's private inventory/recipes.

    The OFF fallback is neutralized by the module-level monkeypatch applied in
    the test body, so the only results are local, privately-scoped rows."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user_a = User(email="a@example.com", password_hash="x")
            user_b = User(email="b@example.com", password_hash="x")
            db.add_all([user_a, user_b])
            await db.flush()

            # Shared global catalog food + each user's PRIVATE-only food. Every
            # food lives in the catalog table (that is the only place foods
            # exist), but the private foods are placed ONLY in their owner's
            # inventory, so they must only surface as an "inventory" result for
            # that owner.
            shared = _make_food(data["shared_food"])
            a_food = _make_food(data["a_food"])
            b_food = _make_food(data["b_food"])
            db.add_all([shared, a_food, b_food])
            await db.flush()

            # Inventory: A holds a_food, B holds b_food (food-only entries, so
            # recipe_id stays None and the XOR check passes).
            db.add_all(
                [
                    UserFoodInventory(
                        user_id=user_a.id, food_id=a_food.id, quantity_grams=100.0
                    ),
                    UserFoodInventory(
                        user_id=user_b.id, food_id=b_food.id, quantity_grams=100.0
                    ),
                ]
            )

            # Private recipes: A's recipe uses a_food, B's uses b_food.
            recipe_a = Recipe(user_id=user_a.id, name=data["a_recipe"])
            recipe_a.ingredients = [RecipeIngredient(food_id=a_food.id, grams=50.0)]
            recipe_b = Recipe(user_id=user_b.id, name=data["b_recipe"])
            recipe_b.ingredients = [RecipeIngredient(food_id=b_food.id, grams=50.0)]
            db.add_all([recipe_a, recipe_b])
            await db.flush()

            # ── unified_search run by A ──────────────────────────────────────
            results = await unified_search(db, user_a.id, data["term"])

            # No result may reference B's private recipe name.
            recipe_hits = [r for r in results if r["kind"] == "recipe"]
            assert all(r["name"] != data["b_recipe"] for r in recipe_hits), (
                "A's search leaked B's private recipe"
            )
            # A's own recipe is reachable (sanity: the term really matches).
            assert any(r["name"] == data["a_recipe"] for r in recipe_hits)

            # No inventory result may reference B's inventory-only food.
            inventory_hits = [r for r in results if r["kind"] == "inventory"]
            assert all(r["name"] != data["b_food"] for r in inventory_hits), (
                "A's search leaked B's private inventory food"
            )
            # A's own inventory food is reachable.
            assert any(r["name"] == data["a_food"] for r in inventory_hits)

            # The shared catalog food is global: it may appear (as kind catalog)
            # — privacy says nothing against it. We only assert it is NOT
            # misclassified as B's private data (already covered above).

            # ── recipe CRUD scoped to A ──────────────────────────────────────
            # list_recipes for A returns only A's recipes.
            a_recipes = await recipe_service.list_recipes(db, user_a.id)
            a_recipe_names = {r.name for r in a_recipes}
            assert data["a_recipe"] in a_recipe_names
            assert data["b_recipe"] not in a_recipe_names

            # A cannot read B's recipe (ForbiddenError, not a silent success).
            with pytest.raises(ForbiddenError):
                await recipe_service.get_recipe(db, user_a.id, recipe_b.id)

            # A cannot delete B's recipe; it must stay intact afterwards.
            with pytest.raises(ForbiddenError):
                await recipe_service.delete_recipe(db, user_a.id, recipe_b.id)

            still_there = (
                await db.execute(select(Recipe).where(Recipe.id == recipe_b.id))
            ).scalar_one_or_none()
            assert still_there is not None, (
                "A's forbidden delete removed B's recipe"
            )
    finally:
        await engine.dispose()


async def _no_off(term):
    """Replacement for ``food_lookup_service.search_by_name``: the Open Food
    Facts fallback contributes no products, so only local rows are asserted."""
    return []


@settings(max_examples=100, deadline=None)
@given(data=_scenario())
def test_inventory_and_recipes_are_scoped_to_owner(data):
    """Feature: food-add-redesign, Property 8: El inventario y las recetas se
    limitan a su dueño.

    Validates: Requirements 2.7, 5.4, 8.4

    For two distinct users A and B with their own inventory and recipes over a
    shared catalog, ``unified_search`` run by A never returns an ``inventory`` or
    ``recipe`` result belonging to B, and the recipe CRUD (list/get/delete) run
    by A never exposes or affects B's recipes (ForbiddenError on get/delete).

    ``food_lookup_service.search_by_name`` is patched for the whole test so the
    OFF fallback never contributes (patched once, not per Hypothesis example, to
    avoid function-scoped fixture reuse under ``@given``).
    """
    original = food_lookup_service.search_by_name
    food_lookup_service.search_by_name = _no_off
    try:
        asyncio.run(_run_scenario(data))
    finally:
        food_lookup_service.search_by_name = original

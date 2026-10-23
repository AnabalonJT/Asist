"""Property test for the Recipe create→read round-trip (food-add-redesign).

This targets the async CRUD in ``app.services.recipe_service`` — namely
``create_recipe`` plus ``list_recipes``/``get_recipe``. Like
``test_property_goal_wizard_persist.py`` (and unlike the pure-logic
``test_property_*`` modules), this needs a live async SQLAlchemy session, so it
spins up a throwaway in-memory SQLite database per example and drives the async
calls with ``asyncio.run`` from inside a synchronous Hypothesis test (Hypothesis
does not drive ``async def`` tests itself). This keeps Hypothesis compatible with
the project's async SQLAlchemy stack without requiring a running PostgreSQL.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio

from hypothesis import given, settings, strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (recipes/recipe_ingredients FK to users/foods).
import app.models  # noqa: F401
from app.models.user import User
from app.models.food import Food
from app.services import recipe_service
from app.services.meal_service import INVENTORY_GRAMS_RANGE

# Recipe ingredient grams live in the same band as the inventory (Req 4.3).
_GRAMS_MIN, _GRAMS_MAX = INVENTORY_GRAMS_RANGE


# A catalog Food's per-100 g nutrition, within the project's validation bands so
# the seeded rows resemble real catalog entries. Nutrition values do not affect
# the round-trip of (name, ingredients) but are needed to build valid Food rows.
_kcal = st.floats(min_value=0.0, max_value=900.0,
                  allow_nan=False, allow_infinity=False)
_macro = st.floats(min_value=0.0, max_value=100.0,
                   allow_nan=False, allow_infinity=False)
_fiber = st.one_of(st.none(), _macro)

# Grams for an ingredient, kept inside INVENTORY_GRAMS_RANGE (1..100000).
_grams = st.floats(min_value=_GRAMS_MIN, max_value=_GRAMS_MAX,
                   allow_nan=False, allow_infinity=False)

# A recipe name of 1..100 characters. Avoid control chars that ``_normalize_name``
# might collapse to empty (which create_recipe rejects as a blank name).
_recipe_name = st.text(
    alphabet=st.characters(min_codepoint=0x41, max_codepoint=0x7A),
    min_size=1, max_size=100,
).filter(lambda s: s.strip() != "")


@st.composite
def _scenario(draw):
    """Draw a catalog of distinct Foods plus one valid recipe over them.

    Returns ``(foods, name, ingredients)`` where ``ingredients`` is a list of
    ``{"food_id_index", "grams"}`` referencing a seeded Food by its position in
    ``foods`` (the real DB id is only known after seeding). 1..100 ingredients;
    the same Food may appear more than once, which ``create_recipe`` allows."""
    catalog_size = draw(st.integers(min_value=1, max_value=8))
    # Distinct Food nutrition rows; names are generated at seed time so they stay
    # unique (Food.name is unique). Only nutrition is drawn here.
    foods = [
        {
            "kcal_per_100g": draw(_kcal),
            "protein_g_per_100g": draw(_macro),
            "fat_g_per_100g": draw(_macro),
            "carbs_g_per_100g": draw(_macro),
            "fiber_g_per_100g": draw(_fiber),
        }
        for _ in range(catalog_size)
    ]
    count = draw(st.integers(min_value=1, max_value=100))
    ingredients = [
        {
            "food_id_index": draw(st.integers(min_value=0, max_value=catalog_size - 1)),
            "grams": round(draw(_grams), 3),
        }
        for _ in range(count)
    ]
    name = draw(_recipe_name)
    return foods, name, ingredients


async def _run_scenario(foods: list[dict], name: str, ingredients: list[dict]) -> None:
    """Create a fresh in-memory DB, seed a user and the catalog Foods, create the
    recipe via ``create_recipe`` and assert it reads back identically via
    ``list_recipes`` and ``get_recipe``."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user = User(email="chef@example.com", password_hash="x")
            db.add(user)
            await db.flush()

            # Seed the catalog Foods with unique names; capture their real ids.
            food_ids: list[int] = []
            for position, food in enumerate(foods):
                row = Food(
                    name=f"Alimento {position}",
                    kcal_per_100g=food["kcal_per_100g"],
                    protein_g_per_100g=food["protein_g_per_100g"],
                    fat_g_per_100g=food["fat_g_per_100g"],
                    carbs_g_per_100g=food["carbs_g_per_100g"],
                    fiber_g_per_100g=food["fiber_g_per_100g"],
                )
                db.add(row)
                await db.flush()
                food_ids.append(row.id)

            # Resolve ingredient indices to real Food ids and build the input the
            # service consumes (dicts carrying food_id + grams).
            recipe_input = [
                {"food_id": food_ids[ing["food_id_index"]], "grams": ing["grams"]}
                for ing in ingredients
            ]
            # The expected ingredient multiset, in the order they were submitted —
            # the service preserves ingredient order (stable round-trip).
            expected_pairs = [
                (food_ids[ing["food_id_index"]], float(ing["grams"]))
                for ing in ingredients
            ]

            created = await recipe_service.create_recipe(
                db, user.id, name, recipe_input
            )
            await db.flush()

            # ── Round-trip via list_recipes (Req 4.5) ───────────────────────
            listed = await recipe_service.list_recipes(db, user.id)
            assert len(listed) == 1, (
                f"Expected exactly one recipe listed, found {len(listed)}"
            )
            fetched = listed[0]

            # Same recipe id and owner (private to the user).
            assert fetched.id == created.id
            assert fetched.user_id == user.id

            # Same name (create_recipe strips surrounding whitespace).
            assert fetched.name == name.strip()

            # Same ingredients: (food_id, grams) in the same stable order.
            actual_pairs = [
                (ing.food_id, float(ing.grams)) for ing in fetched.ingredients
            ]
            assert actual_pairs == expected_pairs, (
                f"Ingredients did not round-trip: {actual_pairs} != {expected_pairs}"
            )

            # Recipe_Nutrition is present (derivable from the eager-loaded foods).
            nutrition = recipe_service.compute_recipe_nutrition(
                [
                    {
                        "grams": ing.grams,
                        "kcal_per_100g": ing.food.kcal_per_100g,
                        "protein_g_per_100g": ing.food.protein_g_per_100g,
                        "fat_g_per_100g": ing.food.fat_g_per_100g,
                        "carbs_g_per_100g": ing.food.carbs_g_per_100g,
                        "fiber_g_per_100g": ing.food.fiber_g_per_100g,
                    }
                    for ing in fetched.ingredients
                ]
            )
            assert nutrition is not None
            for key in ("kcal", "protein", "fat", "carbs"):
                assert key in nutrition and nutrition[key] is not None

            # ── Round-trip via get_recipe (same identity + ingredients) ─────
            got = await recipe_service.get_recipe(db, user.id, created.id)
            assert got.id == created.id
            assert got.name == name.strip()
            got_pairs = [
                (ing.food_id, float(ing.grams)) for ing in got.ingredients
            ]
            assert got_pairs == expected_pairs
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(scenario=_scenario())
def test_recipe_create_read_round_trip(scenario):
    """Feature: food-add-redesign, Property 4: Alta y lectura de una Recipe son
    un viaje de ida y vuelta.

    Validates: Requirements 4.1, 4.5

    For every valid Recipe (name 1..100 chars and 1..100 ingredients referencing
    existing Foods with grams in 1..100000), creating it and then reading it back
    (via list_recipes / get_recipe) returns the same name, the same ordered
    (food_id, grams) ingredients, an owner-scoped recipe, and a present
    Recipe_Nutrition.
    """
    foods, name, ingredients = scenario
    asyncio.run(_run_scenario(foods, name, ingredients))

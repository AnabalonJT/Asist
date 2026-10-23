"""Property test for rejecting invalid recipe creation (food-add-redesign).

Feature: food-add-redesign, Property 6: Toda Recipe inválida se rechaza y no se
registra.

Validates: Requirements 4.3, 4.4

This targets the async ``create_recipe`` in ``app.services.recipe_service``.
Like ``test_property_goal_wizard_persist.py``, it needs a live async
SQLAlchemy session, so it spins up a throwaway in-memory SQLite database per
example and drives the async call with ``asyncio.run`` from inside a synchronous
Hypothesis test (Hypothesis does not drive ``async def`` tests itself). This
keeps Hypothesis and the project's async SQLAlchemy stack compatible without a
running PostgreSQL instance.

The property: for every invalid recipe input the service raises
``ValidationError`` (Spanish message, from ``meal_service``) and NOTHING is
persisted — the ``recipes`` and ``recipe_ingredients`` tables stay unchanged
relative to the seeded baseline (here: empty).

Invalid cases, mirroring ``create_recipe``'s validation order:
  - name length outside FOOD_NAME_LEN (1..100): empty or > 100 chars;
  - ingredients not a list (a dict/str/int);
  - ingredient count outside RECIPE_INGREDIENTS_RANGE (1..100): empty or > 100;
  - an ingredient whose grams are outside INVENTORY_GRAMS_RANGE (1..100000) or
    non-numeric;
  - an ingredient referencing a food_id absent from the catalog;
  - a duplicate (normalized) recipe name for the same user.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio

from hypothesis import given, settings, strategies as st
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (recipes/recipe_ingredients FK -> foods/users).
import app.models  # noqa: F401
from app.models.food import Food
from app.models.recipe import Recipe
from app.models.recipe_ingredient import RecipeIngredient
from app.models.user import User
from app.services import recipe_service
from app.services.meal_service import (
    FOOD_NAME_LEN,
    INVENTORY_GRAMS_RANGE,
    ValidationError,
)
from app.services.recipe_service import RECIPE_INGREDIENTS_RANGE


_GRAMS_MIN, _GRAMS_MAX = INVENTORY_GRAMS_RANGE  # 1..100000
_NAME_MIN, _NAME_MAX = FOOD_NAME_LEN            # 1..100
_ING_MIN, _ING_MAX = RECIPE_INGREDIENTS_RANGE  # 1..100

# Seeded catalog: three foods with ids that the valid-ingredient generator uses.
_SEED_FOOD_IDS = (1, 2, 3)

# A valid name (used when the invalidity lives in the ingredients) and a valid
# ingredient (used when the invalidity lives in the name/ingredient-count).
_valid_name = st.text(min_size=_NAME_MIN, max_size=_NAME_MAX).filter(lambda s: len(s.strip()) >= 1)
_valid_grams = st.floats(min_value=_GRAMS_MIN, max_value=_GRAMS_MAX,
                         allow_nan=False, allow_infinity=False)


@st.composite
def _valid_ingredient(draw):
    """An ingredient pointing at a seeded food with in-range grams."""
    return {"food_id": draw(st.sampled_from(_SEED_FOOD_IDS)), "grams": draw(_valid_grams)}


# ── Generators for each flavor of invalid input ──────────────────────────────

@st.composite
def _bad_name_case(draw):
    """Valid ingredients, but a name outside FOOD_NAME_LEN (empty or > 100)."""
    bad_name = draw(st.one_of(
        st.just(""),                                   # too short
        st.text(min_size=_NAME_MAX + 1, max_size=_NAME_MAX + 50),  # too long
    ))
    ingredients = draw(st.lists(_valid_ingredient(), min_size=1, max_size=4))
    return bad_name, ingredients


@st.composite
def _not_a_list_case(draw):
    """A valid name but ingredients that are not a list/tuple."""
    name = draw(_valid_name)
    not_list = draw(st.one_of(
        st.dictionaries(st.text(max_size=3), st.integers(), max_size=2),
        st.text(max_size=5),
        st.integers(),
        st.none(),
    ))
    return name, not_list


@st.composite
def _bad_count_case(draw):
    """A valid name but an ingredient count outside RECIPE_INGREDIENTS_RANGE."""
    name = draw(_valid_name)
    if draw(st.booleans()):
        ingredients = []  # empty -> below the minimum (1)
    else:
        n = draw(st.integers(min_value=_ING_MAX + 1, max_value=_ING_MAX + 10))
        ingredients = [{"food_id": 1, "grams": 100.0} for _ in range(n)]
    return name, ingredients


@st.composite
def _bad_grams_case(draw):
    """A valid name and foods, but one ingredient's grams are out of range or
    non-numeric."""
    name = draw(_valid_name)
    ingredients = draw(st.lists(_valid_ingredient(), min_size=1, max_size=3))
    bad_grams = draw(st.one_of(
        st.floats(max_value=_GRAMS_MIN - 0.01, allow_nan=False, allow_infinity=False),  # too low / negative
        st.floats(min_value=_GRAMS_MAX + 0.01, max_value=_GRAMS_MAX * 2,
                  allow_nan=False, allow_infinity=False),                                # too high
        st.just(0.0),                                                                    # zero
        st.text(max_size=4),                                                             # non-numeric
        st.none(),                                                                       # missing value
    ))
    position = draw(st.integers(min_value=0, max_value=len(ingredients) - 1))
    ingredients[position] = {"food_id": 1, "grams": bad_grams}
    return name, ingredients


@st.composite
def _missing_food_case(draw):
    """A valid name and grams, but one ingredient references an absent food_id."""
    name = draw(_valid_name)
    ingredients = draw(st.lists(_valid_ingredient(), min_size=0, max_size=3))
    missing_id = draw(st.integers(min_value=max(_SEED_FOOD_IDS) + 1,
                                  max_value=max(_SEED_FOOD_IDS) + 1000))
    ingredients.append({"food_id": missing_id, "grams": draw(_valid_grams)})
    return name, ingredients


# Marker: this case needs the recipe to be seeded BEFORE calling create_recipe
# so that a normalized-name duplicate is rejected.
@st.composite
def _duplicate_name_case(draw):
    """A name that collides (case/accent-insensitively) with a pre-seeded recipe."""
    base = draw(st.sampled_from(["Ensalada", "Sopa", "Guiso", "Pure"]))
    # Vary case so the collision is on the normalized form, not an exact match.
    variant = draw(st.sampled_from([base, base.lower(), base.upper()]))
    ingredients = draw(st.lists(_valid_ingredient(), min_size=1, max_size=3))
    return base, variant, ingredients


async def _seed(db: AsyncSession) -> int:
    """Create a user and the seeded catalog foods; return the user id."""
    user = User(email="tester@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    for fid in _SEED_FOOD_IDS:
        db.add(Food(
            id=fid, name=f"Food {fid}",
            kcal_per_100g=100.0, protein_g_per_100g=5.0,
            fat_g_per_100g=2.0, carbs_g_per_100g=10.0, fiber_g_per_100g=1.0,
        ))
    await db.flush()
    return user.id


async def _counts(db: AsyncSession) -> tuple[int, int]:
    """Return (recipe_count, recipe_ingredient_count) across the whole DB."""
    recipes = (await db.execute(select(func.count()).select_from(Recipe))).scalar_one()
    ings = (await db.execute(select(func.count()).select_from(RecipeIngredient))).scalar_one()
    return recipes, ings


async def _assert_rejected(name, ingredients, *, seed_duplicate=None):
    """Fresh in-memory DB: seed, optionally pre-create a recipe (for the duplicate
    case), snapshot the baseline, call ``create_recipe`` and assert it raises
    ``ValidationError`` in Spanish while leaving recipes/ingredients unchanged."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user_id = await _seed(db)

            if seed_duplicate is not None:
                await recipe_service.create_recipe(
                    db, user_id, seed_duplicate,
                    [{"food_id": _SEED_FOOD_IDS[0], "grams": 100.0}],
                )
                await db.flush()

            baseline = await _counts(db)

            raised = False
            try:
                await recipe_service.create_recipe(db, user_id, name, ingredients)
            except ValidationError as exc:
                raised = True
                # Message is present and in Spanish (non-empty str).
                assert isinstance(str(exc), str) and str(exc).strip()
            await db.flush()

            assert raised, (
                f"create_recipe accepted an invalid input: "
                f"name={name!r}, ingredients={ingredients!r}"
            )

            # Nothing persisted: counts unchanged relative to the baseline.
            after = await _counts(db)
            assert after == baseline, (
                f"Invalid create_recipe mutated the DB: {baseline} -> {after}"
            )
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(case=st.one_of(
    _bad_name_case(),
    _not_a_list_case(),
    _bad_count_case(),
    _bad_grams_case(),
    _missing_food_case(),
))
def test_invalid_recipe_is_rejected_and_not_persisted(case):
    """Feature: food-add-redesign, Property 6: Toda Recipe inválida se rechaza y
    no se registra.

    Validates: Requirements 4.3, 4.4

    For every invalid recipe input (bad name length, non-list ingredients, bad
    ingredient count, out-of-range/non-numeric grams, or a missing catalog
    food), ``create_recipe`` raises ``ValidationError`` and persists neither the
    Recipe nor any RecipeIngredient.
    """
    name, ingredients = case
    asyncio.run(_assert_rejected(name, ingredients))


@settings(max_examples=100, deadline=None)
@given(case=_duplicate_name_case())
def test_duplicate_recipe_name_is_rejected_and_not_persisted(case):
    """Feature: food-add-redesign, Property 6: Toda Recipe inválida se rechaza y
    no se registra.

    Validates: Requirements 4.3, 4.4

    A second recipe whose normalized name collides with an existing recipe of the
    same user is rejected with ``ValidationError`` and leaves the recipes and
    recipe_ingredients tables unchanged (one recipe, one ingredient remain).
    """
    seeded_name, duplicate_name, ingredients = case
    asyncio.run(_assert_rejected(duplicate_name, ingredients, seed_duplicate=seeded_name))

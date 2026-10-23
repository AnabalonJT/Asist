"""Property tests for ``add_recipe_to_inventory`` (food-add-redesign).

This targets the async function ``add_recipe_to_inventory`` in
``app.services.recipe_service``. Like ``test_property_goal_wizard_persist.py``,
it needs a live async SQLAlchemy session, so it spins up a throwaway in-memory
SQLite database per example and drives the async calls with ``asyncio.run`` from
inside a synchronous Hypothesis test (Hypothesis does not drive ``async def``
tests itself). This keeps Hypothesis and the project's async SQLAlchemy stack
compatible without requiring a running PostgreSQL instance.

Covers Property 7 (dedup + grams validation) plus the ownership guard of Req 5.3:
  (a) grams outside INVENTORY_GRAMS_RANGE (1..100000) or non-numeric → Spanish
      ``ValidationError`` and nothing persisted (Req 5.2/5.4);
  (b) adding the SAME recipe multiple times is DEDUPLICATED by
      (user_id, recipe_id): at most one inventory row, its ``quantity_grams``
      equals the latest valid grams (Req 5.1/5.2);
  (c) adding a recipe not owned by the user → ``ForbiddenError`` (owned by
      another user) / not-found → ``ValidationError``, nothing persisted (Req 5.3).

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio

from hypothesis import given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (recipes/recipe_ingredients/foods/
# user_food_inventory FKs all point at each other and at users).
import app.models  # noqa: F401
from app.models.food import Food
from app.models.user import User
from app.models.user_food_inventory import UserFoodInventory
from app.services import recipe_service
from app.services.meal_service import (
    INVENTORY_GRAMS_RANGE,
    ForbiddenError,
    ValidationError,
)

_GRAMS_MIN, _GRAMS_MAX = INVENTORY_GRAMS_RANGE  # (1.0, 100000.0)

# Valid grams: strictly inside the inclusive 1..100000 band.
_valid_grams = st.floats(
    min_value=_GRAMS_MIN, max_value=_GRAMS_MAX,
    allow_nan=False, allow_infinity=False,
)

# Invalid grams: finite numbers below 1, finite numbers above 100000, and
# non-numeric values the validator must reject. NOTE: IEEE ``nan`` is excluded
# on purpose. Req 5.2 constrains numeric *quantities* to the 1..100000 range,
# and ``add_recipe_to_inventory`` rejects via ``grams < 1 or grams > 100000``;
# ``nan`` satisfies neither comparison, so it is not a "quantity outside the
# range" the spec/implementation contemplate. ``inf`` IS covered because
# ``inf > 100000`` is True (and thus rejected). Treating ``nan`` as an invalid
# quantity would require an explicit spec/implementation decision (a NaN guard),
# so it is kept out of this property's input space rather than silently asserted.
_invalid_grams = st.one_of(
    st.floats(min_value=-1000.0, max_value=_GRAMS_MIN - 0.001,
              allow_nan=False, allow_infinity=False),
    st.floats(min_value=_GRAMS_MAX + 0.001, max_value=_GRAMS_MAX * 2,
              allow_nan=False, allow_infinity=False),
    st.just(0.0),
    st.none(),
    st.text(max_size=8),
    st.booleans(),
    st.just(float("inf")),
)


async def _seed(db: AsyncSession, email: str) -> int:
    """Create a user and return its id."""
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user.id


async def _seed_recipe(db: AsyncSession, user_id: int, name: str) -> int:
    """Create a catalog Food and a one-ingredient recipe via ``create_recipe``;
    return the recipe id."""
    food = Food(
        name=f"ingrediente-{name}",
        kcal_per_100g=100.0,
        protein_g_per_100g=10.0,
        fat_g_per_100g=5.0,
        carbs_g_per_100g=20.0,
        fiber_g_per_100g=2.0,
    )
    db.add(food)
    await db.flush()
    recipe = await recipe_service.create_recipe(
        db, user_id, name, [{"food_id": food.id, "grams": 150.0}]
    )
    return recipe.id


async def _inventory_rows(db: AsyncSession, user_id, recipe_id):
    """Return all inventory rows for (user_id, recipe_id)."""
    result = await db.execute(
        select(UserFoodInventory).where(
            UserFoodInventory.user_id == user_id,
            UserFoodInventory.recipe_id == recipe_id,
        )
    )
    return list(result.scalars().all())


def _make_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


# ── Property 7a + dedup: valid grams sequence deduplicates to the latest ──────


async def _run_dedup(grams_sequence: list[float]) -> None:
    engine, factory = _make_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            user_id = await _seed(db, "owner@example.com")
            recipe_id = await _seed_recipe(db, user_id, "Ensalada")

            for grams in grams_sequence:
                entry = await recipe_service.add_recipe_to_inventory(
                    db, user_id, recipe_id, grams
                )
                await db.flush()
                assert entry.recipe_id == recipe_id
                assert entry.food_id is None  # XOR constraint: only recipe_id set

                rows = await _inventory_rows(db, user_id, recipe_id)
                # Exactly one row for this recipe, holding the latest quantity.
                assert len(rows) == 1
                assert rows[0].quantity_grams == float(grams)
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(grams_sequence=st.lists(_valid_grams, min_size=1, max_size=6))
def test_adding_recipe_deduplicates_to_latest_grams(grams_sequence):
    """Feature: food-add-redesign, Property 7: Agregar una Recipe al inventario
    deduplica y valida los gramos.

    Validates: Requirements 5.2, 5.3

    For any sequence of valid-grams additions of the same owned recipe, the
    inventory holds exactly one row for that recipe and its ``quantity_grams``
    equals the latest requested amount (Req 5.1/5.2).
    """
    asyncio.run(_run_dedup(grams_sequence))


# ── Property 7b: invalid grams rejected, inventory unchanged ──────────────────


async def _run_invalid_grams(pre_grams: float, bad_grams) -> None:
    engine, factory = _make_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            user_id = await _seed(db, "owner@example.com")
            recipe_id = await _seed_recipe(db, user_id, "Ensalada")

            # Establish a known-good baseline row.
            await recipe_service.add_recipe_to_inventory(
                db, user_id, recipe_id, pre_grams
            )
            await db.flush()
            before = await _inventory_rows(db, user_id, recipe_id)
            assert len(before) == 1
            baseline = before[0].quantity_grams

            # An out-of-range / non-numeric grams must be rejected in Spanish and
            # leave the inventory untouched.
            try:
                await recipe_service.add_recipe_to_inventory(
                    db, user_id, recipe_id, bad_grams
                )
                raised = False
            except ValidationError as exc:
                raised = True
                assert str(exc).strip(), "ValidationError message must not be empty"
            await db.flush()

            assert raised, f"Expected ValidationError for grams={bad_grams!r}"
            after = await _inventory_rows(db, user_id, recipe_id)
            assert len(after) == 1
            assert after[0].quantity_grams == baseline  # unchanged
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(pre_grams=_valid_grams, bad_grams=_invalid_grams)
def test_adding_recipe_with_invalid_grams_is_rejected(pre_grams, bad_grams):
    """Feature: food-add-redesign, Property 7: Agregar una Recipe al inventario
    deduplica y valida los gramos.

    Validates: Requirements 5.2, 5.3

    For any grams outside 1..100000 (or non-numeric), the addition is rejected
    with a Spanish ``ValidationError`` and the inventory keeps its prior state
    (Req 5.2/5.4).
    """
    asyncio.run(_run_invalid_grams(pre_grams, bad_grams))


# ── Property 7c: ownership guard — foreign / missing recipe rejected ──────────


async def _run_ownership(grams: float, missing_offset: int) -> None:
    engine, factory = _make_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            owner_id = await _seed(db, "owner@example.com")
            other_id = await _seed(db, "other@example.com")
            recipe_id = await _seed_recipe(db, owner_id, "Ensalada")

            # (c1) Another user adding the owner's recipe → ForbiddenError,
            #      nothing persisted for the other user.
            try:
                await recipe_service.add_recipe_to_inventory(
                    db, other_id, recipe_id, grams
                )
                raised_forbidden = False
            except ForbiddenError as exc:
                raised_forbidden = True
                assert str(exc).strip()
            await db.flush()
            assert raised_forbidden, "Expected ForbiddenError for a foreign recipe"
            assert await _inventory_rows(db, other_id, recipe_id) == []

            # (c2) Adding a recipe that does not exist → ValidationError (not
            #      found), nothing persisted.
            missing_id = recipe_id + 1 + missing_offset
            try:
                await recipe_service.add_recipe_to_inventory(
                    db, owner_id, missing_id, grams
                )
                raised_missing = False
            except ValidationError as exc:
                raised_missing = True
                assert str(exc).strip()
            await db.flush()
            assert raised_missing, "Expected ValidationError for a missing recipe"
            assert await _inventory_rows(db, owner_id, missing_id) == []
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(grams=_valid_grams, missing_offset=st.integers(min_value=0, max_value=1000))
def test_adding_foreign_or_missing_recipe_is_rejected(grams, missing_offset):
    """Feature: food-add-redesign, Property 7: Agregar una Recipe al inventario
    deduplica y valida los gramos.

    Validates: Requirements 5.2, 5.3

    A recipe owned by another user is rejected with ``ForbiddenError`` and a
    missing recipe with ``ValidationError`` (both Spanish), without persisting
    any inventory row (Req 5.3).
    """
    asyncio.run(_run_ownership(grams, missing_offset))

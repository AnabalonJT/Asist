"""Property test for rejecting invalid food/search inputs (food-add-redesign).

Feature: food-add-redesign, Property 1: Toda entrada inválida se rechaza y
preserva el estado.

Validates: Requirements 1.4, 2.5, 3.4

This covers the three dimensions of Property 1 with Hypothesis:

  * Req 1.4 — a ``brand`` longer than ``BRAND_MAX_LEN`` (100) rejects the alta of
    a Food (both the admin catalog flow ``create_food`` and the inventory flow
    ``add_inventory``).
  * Req 3.4 — a nutrition value per 100 g outside its ``FOOD_*`` range, or a name
    outside ``FOOD_NAME_LEN`` (1..100), rejects the alta (same two flows).
  * Req 2.5 — a search term of length 0 or greater than 100 rejects the
    ``unified_search``.

In every case the service raises ``ValidationError`` (Spanish message, from
``meal_service``) and NOTHING is persisted — the ``foods`` and
``user_food_inventory`` tables stay unchanged relative to the seeded baseline.

Like ``test_property_recipe_invalid.py`` it needs a live async SQLAlchemy
session, so it spins up a throwaway in-memory SQLite database per example and
drives the async call with ``asyncio.run`` from inside a synchronous Hypothesis
test (Hypothesis does not drive ``async def`` tests itself). This keeps
Hypothesis and the project's async SQLAlchemy stack compatible without a running
PostgreSQL instance.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from unittest.mock import AsyncMock

from hypothesis import given, settings, strategies as st
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (foods / user_food_inventory FK -> users).
import app.models  # noqa: F401
from app.models.food import Food
from app.models.user import User
from app.models.user_food_inventory import UserFoodInventory
from app.services import meal_service, search_service
from app.services.meal_service import (
    BRAND_MAX_LEN,
    FOOD_KCAL_RANGE,
    FOOD_MACRO_RANGE,
    FOOD_NAME_LEN,
    ValidationError,
)
from app.services.search_service import SEARCH_TERM_LEN


_NAME_MIN, _NAME_MAX = FOOD_NAME_LEN          # 1..100
_KCAL_MIN, _KCAL_MAX = FOOD_KCAL_RANGE        # 0..900
_MACRO_MIN, _MACRO_MAX = FOOD_MACRO_RANGE     # 0..100
_TERM_MIN, _TERM_MAX = SEARCH_TERM_LEN        # 1..100

# A seeded catalog food whose name a valid search term can match, so the search
# baseline is non-trivial (there IS something to preserve / not surface).
_SEED_FOOD_NAME = "Pollo"

# ── Generators for in-range nutrition values (used when the invalidity lives
#    in another field such as the brand) ───────────────────────────────────────
_valid_name = st.text(min_size=_NAME_MIN, max_size=_NAME_MAX).filter(
    lambda s: _NAME_MIN <= len(s) <= _NAME_MAX
)
_valid_kcal = st.floats(min_value=_KCAL_MIN, max_value=_KCAL_MAX,
                        allow_nan=False, allow_infinity=False)
_valid_macro = st.floats(min_value=_MACRO_MIN, max_value=_MACRO_MAX,
                         allow_nan=False, allow_infinity=False)


# ── Dimension A: brand longer than BRAND_MAX_LEN (Req 1.4) ───────────────────

@st.composite
def _bad_brand_fields(draw):
    """Valid name + in-range nutrition, but a brand longer than 100 chars."""
    over = draw(st.integers(min_value=1, max_value=50))
    brand = draw(st.text(min_size=BRAND_MAX_LEN + over,
                         max_size=BRAND_MAX_LEN + over)).ljust(BRAND_MAX_LEN + over, "x")
    return {
        "name": draw(_valid_name),
        "brand": brand,
        "kcal": draw(_valid_kcal),
        "protein": draw(_valid_macro),
        "fat": draw(_valid_macro),
        "carbs": draw(_valid_macro),
        "fiber": draw(st.none() | _valid_macro),
    }


# ── Dimension B: a nutrition value out of range, or a bad name (Req 3.4) ─────

@st.composite
def _bad_nutrition_fields(draw):
    """In-range brand (or none), but exactly one nutrition field (or the name) is
    unambiguously outside its valid range, together with the flow that actually
    validates that corruption.

    Returns ``(fields, via_inventory)``. The corrupted value is drawn with a
    CLEAR margin (below MIN-1 or above MAX+1) so float representation can never
    round it back into range and the service must reject it.

    The two alta flows differ in ONE respect that matters here: ``add_inventory``
    takes the food's name as a separate ``food_name`` argument and, when the
    ``new_food_fields`` name is empty/whitespace, substitutes that argument (a
    valid name) before validating. So an EMPTY / too-short name is only rejected
    by ``create_food`` (where the name in ``fields`` is the sole source). This is
    a deliberate flow difference, not a missing validation: ``add_inventory``
    still validates every nutrition value and a non-empty (too-long) name. We
    therefore pair the empty-name corruption with the ``create_food`` flow only,
    while every other corruption is rejected by BOTH flows (so the flow is free).
    """
    fields = {
        "name": draw(_valid_name),
        "brand": draw(st.none() | st.text(min_size=1, max_size=BRAND_MAX_LEN)),
        "kcal": draw(_valid_kcal),
        "protein": draw(_valid_macro),
        "fat": draw(_valid_macro),
        "carbs": draw(_valid_macro),
        "fiber": draw(_valid_macro),  # start in-range; the fiber case overrides it
    }

    # Clear-margin out-of-range generators (at least 1 unit past the boundary).
    _too_low_kcal = st.floats(min_value=-_KCAL_MAX, max_value=_KCAL_MIN - 1.0,
                              allow_nan=False, allow_infinity=False)
    _too_high_kcal = st.floats(min_value=_KCAL_MAX + 1.0, max_value=_KCAL_MAX * 3,
                               allow_nan=False, allow_infinity=False)
    _too_low_macro = st.floats(min_value=-_MACRO_MAX, max_value=_MACRO_MIN - 1.0,
                               allow_nan=False, allow_infinity=False)
    _too_high_macro = st.floats(min_value=_MACRO_MAX + 1.0, max_value=_MACRO_MAX * 10,
                                allow_nan=False, allow_infinity=False)

    # Default: either flow validates the corruption, so leave it free.
    via_inventory = draw(st.booleans())

    # Pick exactly which field to corrupt so the input is guaranteed invalid.
    dimension = draw(st.sampled_from(
        ["name_empty", "name_long", "kcal", "protein", "fat", "carbs", "fiber"]
    ))
    if dimension == "name_empty":
        # Empty / too-short name: only create_food rejects it (add_inventory
        # substitutes the valid food_name argument). Pin to the create_food flow.
        fields["name"] = ""
        via_inventory = False
    elif dimension == "name_long":
        # A non-empty name longer than 100 chars is rejected by BOTH flows: it is
        # not empty, so add_inventory keeps and validates it. Letters only so its
        # length is unambiguous.
        over = draw(st.integers(min_value=1, max_value=50))
        fields["name"] = "a" * (_NAME_MAX + over)
    elif dimension == "kcal":
        fields["kcal"] = draw(st.one_of(_too_low_kcal, _too_high_kcal))
    elif dimension == "fiber":
        # fiber is optional (None is valid), so force an out-of-range NUMBER.
        fields["fiber"] = draw(st.one_of(_too_low_macro, _too_high_macro))
    else:
        fields[dimension] = draw(st.one_of(_too_low_macro, _too_high_macro))
    return fields, via_inventory


# ── Dimension C: a search term out of range (Req 2.5) ────────────────────────

# Every value is guaranteed invalid AFTER ``str.strip()`` (which ``unified_search``
# applies before measuring the length): either it strips to length 0 (empty or
# all-whitespace), or it is strictly longer than 100 ASCII letters so stripping
# cannot bring it back into the 1..100 range. Mirrors
# ``tests/test_property_search_subset.py::test_search_rejects_out_of_range_term``.
_bad_term = st.one_of(
    st.just(""),                                                   # strips to 0
    st.text(alphabet=" \t\n\r", min_size=1, max_size=10),          # all-whitespace → 0
    st.integers(min_value=_TERM_MAX + 1, max_value=160).map(       # > 100 letters
        lambda n: "a" * n
    ),
)


# ── DB harness ───────────────────────────────────────────────────────────────

async def _seed(db: AsyncSession) -> int:
    """Create a user and one seeded catalog food; return the user id."""
    user = User(email="tester@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    db.add(Food(
        name=_SEED_FOOD_NAME,
        kcal_per_100g=165.0, protein_g_per_100g=31.0,
        fat_g_per_100g=3.6, carbs_g_per_100g=0.0, fiber_g_per_100g=0.0,
    ))
    await db.flush()
    return user.id


async def _counts(db: AsyncSession) -> tuple[int, int]:
    """Return (food_count, inventory_count) across the whole DB."""
    foods = (await db.execute(select(func.count()).select_from(Food))).scalar_one()
    inv = (await db.execute(
        select(func.count()).select_from(UserFoodInventory)
    )).scalar_one()
    return foods, inv


async def _run(operation):
    """Fresh in-memory DB: seed, snapshot the baseline (foods/inventory), run the
    async ``operation(db, user_id)`` and assert it raises ``ValidationError`` in
    Spanish while leaving the foods and user_food_inventory tables unchanged."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            user_id = await _seed(db)
            baseline = await _counts(db)

            raised = False
            try:
                await operation(db, user_id)
            except ValidationError as exc:
                raised = True
                # Message is present and a non-empty string (Spanish).
                assert isinstance(str(exc), str) and str(exc).strip()
            # A rollback may have been issued inside the service; re-seed is not
            # needed because we only compare counts, and the seed persists unless
            # rolled back. Flush to surface any pending (unexpected) mutation.
            try:
                await db.flush()
            except Exception:
                pass

            assert raised, "Expected ValidationError but the operation succeeded"

            after = await _counts(db)
            assert after == baseline, (
                f"Invalid operation mutated the DB: {baseline} -> {after}"
            )
    finally:
        await engine.dispose()


# ── Property 1: brand too long is rejected (Req 1.4) ─────────────────────────

@settings(max_examples=100, deadline=None)
@given(fields=_bad_brand_fields(), via_inventory=st.booleans())
def test_invalid_brand_is_rejected_and_state_preserved(fields, via_inventory):
    """Feature: food-add-redesign, Property 1: Toda entrada inválida se rechaza y
    preserva el estado.

    Validates: Requirements 1.4

    A Food alta carrying a brand longer than 100 characters is rejected with a
    Spanish ``ValidationError`` and leaves the Food_Catalog and the
    User_Food_Inventory unchanged — whether it goes through the admin catalog
    flow (``create_food``) or the inventory flow (``add_inventory``).
    """
    async def op(db, user_id):
        if via_inventory:
            await meal_service.add_inventory(
                db, user_id, fields["name"], 100.0, new_food_fields=fields
            )
        else:
            await meal_service.create_food(
                db, fields, is_meat=False, is_animal=False, has_gluten=False
            )

    asyncio.run(_run(op))


# ── Property 1: out-of-range nutrition / bad name is rejected (Req 3.4) ──────

@settings(max_examples=100, deadline=None)
@given(case=_bad_nutrition_fields())
def test_invalid_nutrition_is_rejected_and_state_preserved(case):
    """Feature: food-add-redesign, Property 1: Toda entrada inválida se rechaza y
    preserva el estado.

    Validates: Requirements 3.4

    A Food alta with a nutrition value per 100 g outside its FOOD_* range, or a
    name outside 1..100 characters, is rejected with a Spanish ``ValidationError``
    and leaves the Food_Catalog and the User_Food_Inventory unchanged — in both
    the admin catalog flow (``create_food``) and the inventory flow
    (``add_inventory``). The generator pairs each corruption with a flow that
    actually validates it (see ``_bad_nutrition_fields``).
    """
    fields, via_inventory = case

    async def op(db, user_id):
        if via_inventory:
            await meal_service.add_inventory(
                db, user_id, fields["name"] or "sin-nombre", 100.0,
                new_food_fields=fields,
            )
        else:
            await meal_service.create_food(
                db, fields, is_meat=False, is_animal=False, has_gluten=False
            )

    asyncio.run(_run(op))


# ── Property 1: out-of-range search term is rejected (Req 2.5) ───────────────

@settings(max_examples=100, deadline=None)
@given(term=_bad_term)
def test_invalid_search_term_is_rejected_and_state_preserved(term):
    """Feature: food-add-redesign, Property 1: Toda entrada inválida se rechaza y
    preserva el estado.

    Validates: Requirements 2.5

    An Incremental_Search whose term strips to length 0 or exceeds 100 characters
    is rejected with a Spanish ``ValidationError`` and performs no mutation to the
    Food_Catalog or the User_Food_Inventory.

    ``food_lookup_service.search_by_name`` is patched for the whole test (like
    ``test_property_food_add_privacy.py``) so a VALID term never reaches the real
    Open Food Facts network — the term is always out of range here, so the OFF
    fallback is unreachable, but the patch guarantees NO network under any input.
    """
    async def op(db, user_id):
        await search_service.unified_search(db, user_id, term)

    original = search_service.food_lookup_service.search_by_name
    search_service.food_lookup_service.search_by_name = AsyncMock(return_value=[])
    try:
        asyncio.run(_run(op))
    finally:
        search_service.food_lookup_service.search_by_name = original

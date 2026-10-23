"""Property test for the Search_Result serialization invariant (food-add-redesign).

This targets the ``Search_Result`` dicts produced by ``unified_search`` in
``app.services.search_service`` (built by ``_food_result`` / ``_recipe_result``
for the local origins and by the inline OFF branch), and the Pydantic
``SearchResultOut`` schema that the ``GET /search`` endpoint serializes them
through (defined in ``app.routes.meals``).

Like ``test_property_search_subset.py`` and ``test_property_goal_wizard_persist.py``
(and unlike the pure-logic ``test_property_*`` modules), it needs a live async
SQLAlchemy session, so it spins up a throwaway in-memory SQLite database per
example and drives the async calls with ``asyncio.run`` from inside a synchronous
Hypothesis test (Hypothesis does not drive ``async def`` tests itself). This keeps
Hypothesis compatible with the project's async SQLAlchemy stack without requiring
a running PostgreSQL.

Both the local origins (catalog / inventory / recipe) and the OFF origin are
exercised: the seeded term always matches the seeded catalog/inventory/recipe
rows, and a separate run with an empty local catalog monkeypatches
``food_lookup_service.search_by_name`` to return a varied OFF payload so the
``off`` branch contributes results too.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings, strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (foods/recipes/inventory FK to users/foods).
import app.models  # noqa: F401
from app.models.user import User
from app.models.food import Food
from app.models.recipe import Recipe
from app.models.recipe_ingredient import RecipeIngredient
from app.models.user_food_inventory import UserFoodInventory
from app.routes.meals import SearchResultOut
from app.services import search_service

# The exact key set every Search_Result dict must carry — no missing, no extra
# fields (Req 2.3: "sin perder ni inventar campos"). Mirrors SearchResultOut.
_EXPECTED_KEYS = {
    "kind", "id", "name", "brand", "kcal", "protein",
    "fat", "carbs", "fiber", "barcode", "image_url",
}

# All origins unified_search may emit. Local origins never expose an image_url.
_LOCAL_KINDS = {"catalog", "inventory", "recipe"}
_ALL_KINDS = _LOCAL_KINDS | {"off"}


# Nutrition values within the project's validation bands, so seeded Foods
# resemble real catalog entries.
_kcal = st.floats(min_value=0.0, max_value=900.0,
                  allow_nan=False, allow_infinity=False)
_macro = st.floats(min_value=0.0, max_value=100.0,
                   allow_nan=False, allow_infinity=False)
_fiber = st.one_of(st.none(), _macro)
# Brand is optional (<=100 chars); exercise both the present and None cases.
_brand = st.one_of(st.none(), st.text(min_size=1, max_size=20))


@st.composite
def _food_row(draw):
    """Draw the nutrition + optional brand for one catalog Food."""
    return {
        "brand": draw(_brand),
        "kcal_per_100g": draw(_kcal),
        "protein_g_per_100g": draw(_macro),
        "fat_g_per_100g": draw(_macro),
        "carbs_g_per_100g": draw(_macro),
        "fiber_g_per_100g": draw(_fiber),
    }


@st.composite
def _scenario(draw):
    """Draw a scenario where the seeded rows all match a fixed search term.

    All local rows embed the term ``"match"`` in their name so a single search
    surfaces catalog, inventory and recipe results together, guaranteeing every
    local origin is covered by at least one example. Returns the catalog
    nutrition rows plus which of them the target user keeps in inventory and how
    many recipes they own.
    """
    catalog_size = draw(st.integers(min_value=1, max_value=6))
    catalog = [draw(_food_row()) for _ in range(catalog_size)]
    # Subset of catalog indices the user has in inventory (as food_id entries).
    inv_mine = draw(
        st.lists(st.integers(min_value=0, max_value=catalog_size - 1),
                 min_size=0, max_size=catalog_size, unique=True)
    )
    recipe_count = draw(st.integers(min_value=0, max_value=3))
    return {
        "catalog": catalog,
        "inv_mine": inv_mine,
        "recipe_count": recipe_count,
    }


# A varied OFF payload (as returned by food_lookup_service.search_by_name after
# mapping): mixes present/missing brand, image_url and nutrition, and a None
# barcode, so the ``off`` branch of unified_search is exercised with realistic
# gaps. Keys match what the OFF branch reads (name/brand/kcal/.../image_url).
_OFF_PAYLOAD = [
    {
        "name": "match galletas OFF",
        "brand": "MarcaX",
        "kcal": 450.0,
        "protein": 7.0,
        "fat": 20.0,
        "carbs": 60.0,
        "fiber": 3.0,
        "barcode": "7501234567890",
        "image_url": "https://images.example/off1.jpg",
    },
    {
        "name": "match bebida OFF",
        "brand": None,
        "kcal": None,
        "protein": None,
        "fat": None,
        "carbs": None,
        "fiber": None,
        "barcode": None,
        "image_url": None,
    },
    {
        "name": "match snack OFF",
        "brand": "OtraMarca",
        "kcal": 200.0,
        "protein": 2.5,
        "fat": 10.0,
        "carbs": 25.0,
        "fiber": None,
        "barcode": "0012345678905",
        "image_url": "https://images.example/off3.jpg",
    },
]


def _assert_result_shape(result: dict) -> None:
    """Assert one Search_Result dict satisfies Property 2 and serializes cleanly.

    Checks the exact key set, the kind domain, the local-kind image_url rule, and
    that the dict validates against the SearchResultOut Pydantic model used by the
    GET /search endpoint without error.
    """
    # 1. Exactly the SearchResultOut keys — no missing, no invented fields.
    assert set(result.keys()) == _EXPECTED_KEYS, (
        f"Unexpected key set: {set(result.keys()) ^ _EXPECTED_KEYS}"
    )
    # 2. kind is one of the allowed origins.
    assert result["kind"] in _ALL_KINDS, f"Unexpected kind {result['kind']!r}"
    # 3. A result always carries a name (required by the schema).
    assert result["name"] is not None
    # 4. Local origins never expose an image_url (it is always None).
    if result["kind"] in _LOCAL_KINDS:
        assert result["image_url"] is None, (
            f"Local {result['kind']} result leaked image_url {result['image_url']!r}"
        )
    # 5. The dict validates against the endpoint's Pydantic model unchanged, and
    #    round-trips to a payload carrying the same present fields (no loss, no
    #    invention). This is the serialization the GET /search endpoint performs.
    model = SearchResultOut(**result)
    dumped = model.model_dump()
    assert set(dumped.keys()) == _EXPECTED_KEYS
    for key in _EXPECTED_KEYS:
        assert dumped[key] == result[key], (
            f"Serialization changed field {key!r}: {result[key]!r} -> {dumped[key]!r}"
        )


async def _run_local(scenario: dict) -> None:
    """Seed catalog/inventory/recipes that all match the term and assert every
    returned Search_Result conforms to the serialization shape. The OFF fallback
    is patched to return nothing (it never runs when locals exist, but we patch
    defensively to keep the run offline)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            me = User(email="me@example.com", password_hash="x")
            db.add(me)
            await db.flush()

            # Seed catalog Foods; every name embeds the term so all of them match.
            catalog = scenario["catalog"]
            food_ids: list[int] = []
            for position, row in enumerate(catalog):
                food = Food(
                    name=f"match food {position}",
                    brand=row["brand"],
                    kcal_per_100g=row["kcal_per_100g"],
                    protein_g_per_100g=row["protein_g_per_100g"],
                    fat_g_per_100g=row["fat_g_per_100g"],
                    carbs_g_per_100g=row["carbs_g_per_100g"],
                    fiber_g_per_100g=row["fiber_g_per_100g"],
                )
                db.add(food)
                await db.flush()
                food_ids.append(food.id)

            # Inventory rows (food_id entries) for the user.
            for idx in scenario["inv_mine"]:
                db.add(UserFoodInventory(
                    user_id=me.id, food_id=food_ids[idx], quantity_grams=100.0
                ))

            # Recipes owned by the user, each with one matching-name and one
            # ingredient backed by the first catalog food.
            for i in range(scenario["recipe_count"]):
                recipe = Recipe(user_id=me.id, name=f"match recipe {i}")
                recipe.ingredients.append(
                    RecipeIngredient(food_id=food_ids[0], grams=150.0)
                )
                db.add(recipe)
            await db.flush()

            with patch.object(
                search_service.food_lookup_service,
                "search_by_name",
                new=AsyncMock(return_value=[]),
            ):
                results = await search_service.unified_search(db, me.id, "match")

            # The seeded catalog guarantees at least one local result.
            assert results, "Expected at least one local Search_Result"
            got_kinds = set()
            for result in results:
                _assert_result_shape(result)
                assert result["kind"] in _LOCAL_KINDS
                got_kinds.add(result["kind"])
            # Catalog always matches; inventory/recipe appear when seeded.
            assert "catalog" in got_kinds
            if scenario["inv_mine"]:
                assert "inventory" in got_kinds
            if scenario["recipe_count"]:
                assert "recipe" in got_kinds
    finally:
        await engine.dispose()


async def _run_off() -> None:
    """With an EMPTY local catalog, monkeypatch the OFF lookup to return a varied
    payload and assert every ``off`` Search_Result conforms to the serialization
    shape (and validates against SearchResultOut)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            me = User(email="me@example.com", password_hash="x")
            db.add(me)
            await db.flush()

            # No local rows → unified_search falls back to the OFF source.
            with patch.object(
                search_service.food_lookup_service,
                "search_by_name",
                new=AsyncMock(return_value=[dict(p) for p in _OFF_PAYLOAD]),
            ):
                results = await search_service.unified_search(db, me.id, "match")

            assert len(results) == len(_OFF_PAYLOAD), (
                "OFF fallback should surface one result per payload product"
            )
            for result in results:
                assert result["kind"] == "off"
                # OFF results have no local id.
                assert result["id"] is None
                _assert_result_shape(result)
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(scenario=_scenario())
def test_local_search_result_serialization(scenario):
    """Feature: food-add-redesign, Property 2: La serialización de un
    Search_Result conserva los campos presentes.

    Validates: Requirements 1.5, 2.3

    For any catalog/inventory/recipe produced by ``unified_search``, each
    Search_Result dict carries exactly the SearchResultOut field set
    {kind, id, name, brand, kcal, protein, fat, carbs, fiber, barcode,
    image_url}; its ``kind`` is a local origin (catalog/inventory/recipe);
    ``image_url`` is None for every local result; and the dict validates against
    the ``SearchResultOut`` model used by GET /search, round-tripping without
    losing or inventing any field.
    """
    asyncio.run(_run_local(scenario))


def test_off_search_result_serialization():
    """Feature: food-add-redesign, Property 2: La serialización de un
    Search_Result conserva los campos presentes.

    Validates: Requirements 1.5, 2.3

    When there are no local results, the OFF fallback results produced by
    ``unified_search`` also carry exactly the SearchResultOut field set, have
    ``kind == "off"`` with a None id, and validate against ``SearchResultOut``
    (with brand/image_url/nutrition preserved or None as the payload dictates).
    """
    asyncio.run(_run_off())

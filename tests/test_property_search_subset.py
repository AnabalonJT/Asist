"""Property test for the unified_search "search subset" invariant (food-add-redesign).

This targets the async ``unified_search`` in ``app.services.search_service``.
Like ``test_property_goal_wizard_persist.py`` and ``test_property_recipe_round_trip.py``
(and unlike the pure-logic ``test_property_*`` modules), it needs a live async
SQLAlchemy session, so it spins up a throwaway in-memory SQLite database per
example and drives the async calls with ``asyncio.run`` from inside a synchronous
Hypothesis test (Hypothesis does not drive ``async def`` tests itself). This keeps
Hypothesis compatible with the project's async SQLAlchemy stack without requiring
a running PostgreSQL.

The Open Food Facts fallback is out of scope here: ``food_lookup_service.
search_by_name`` is patched to return ``[]`` so no network happens and the ``off``
branch never contributes. The property is strictly about LOCAL results.

User-facing text is Spanish; identifiers and comments are English.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
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
from app.services import search_service
from app.services.meal_service import ValidationError

# The local Search_Result origins the property allows (Req 2.1). The OFF origin
# is excluded on purpose: it is patched out so it never contributes a result.
_LOCAL_KINDS = {"catalog", "inventory", "recipe"}


# Nutrition values within the project's validation bands, so seeded Foods
# resemble real catalog entries. They do not affect matching but are required to
# build valid rows.
_kcal = st.floats(min_value=0.0, max_value=900.0,
                  allow_nan=False, allow_infinity=False)
_macro = st.floats(min_value=0.0, max_value=100.0,
                   allow_nan=False, allow_infinity=False)
_fiber = st.one_of(st.none(), _macro)

# Name fragments are ASCII letters/digits/space only. This keeps the service's
# SQL ``ilike`` substring match (case-insensitive, accent-sensitive) in agreement
# with the independently-computed expected set, which uses Python's
# case-insensitive ``in``. Accented terms are covered by other tests; mixing them
# here would conflate two different matching semantics.
_fragment_alphabet = st.characters(
    whitelist_categories=(),
    whitelist_characters="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ",
)
_fragment = st.text(alphabet=_fragment_alphabet, min_size=1, max_size=12).filter(
    lambda s: s.strip() != ""
)


@st.composite
def _food_row(draw):
    """Draw the nutrition for one catalog Food (name assigned at seed time)."""
    return {
        "kcal_per_100g": draw(_kcal),
        "protein_g_per_100g": draw(_macro),
        "fat_g_per_100g": draw(_macro),
        "carbs_g_per_100g": draw(_macro),
        "fiber_g_per_100g": draw(_fiber),
    }


@st.composite
def _scenario(draw):
    """Draw a whole search scenario.

    Returns a dict describing:
      - ``catalog``: nutrition for N global Foods (names generated at seed time).
      - ``inv_mine`` / ``inv_other``: indices into ``catalog`` that the target user
        and a second user have in their inventory (as food_id entries).
      - ``recipes_mine`` / ``recipes_other``: recipe names for each user (each
        backed by one catalog Food as its single ingredient).
      - ``term``: the search term to query with.

    Names carry an embedded, controllable fragment so that some rows match the
    term and some don't, exercising the subset property on a non-trivial mix.
    """
    catalog_size = draw(st.integers(min_value=1, max_value=8))
    catalog = [draw(_food_row()) for _ in range(catalog_size)]

    # Fragments embedded into the generated names. Reusing a small pool across
    # names (and sometimes as the term) makes real matches likely.
    term = draw(_fragment).strip()
    fragment_pool = draw(
        st.lists(_fragment, min_size=1, max_size=4)
    )
    fragment_pool = [f.strip() for f in fragment_pool if f.strip()] or [term]

    # For each catalog food, pick a fragment to embed in its (seed-time) name.
    catalog_fragments = [
        draw(st.sampled_from(fragment_pool + [term])) for _ in range(catalog_size)
    ]

    def _subset(upper):
        return draw(
            st.lists(st.integers(min_value=0, max_value=upper - 1),
                     min_size=0, max_size=upper, unique=True)
        )

    inv_mine = _subset(catalog_size)
    inv_other = _subset(catalog_size)

    # Recipe names for each user, each embedding a chosen fragment and backed by a
    # catalog food as its single ingredient.
    def _recipes():
        count = draw(st.integers(min_value=0, max_value=4))
        return [
            {
                "fragment": draw(st.sampled_from(fragment_pool + [term])),
                "food_index": draw(st.integers(min_value=0, max_value=catalog_size - 1)),
            }
            for _ in range(count)
        ]

    recipes_mine = _recipes()
    recipes_other = _recipes()

    return {
        "catalog": catalog,
        "catalog_fragments": catalog_fragments,
        "inv_mine": inv_mine,
        "inv_other": inv_other,
        "recipes_mine": recipes_mine,
        "recipes_other": recipes_other,
        "term": term,
    }


async def _run_scenario(scenario: dict) -> None:
    """Seed two users (mine + other) with catalog/inventory/recipes, run
    ``unified_search`` for the target user, and assert the subset property."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                         expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            me = User(email="me@example.com", password_hash="x")
            other = User(email="other@example.com", password_hash="x")
            db.add_all([me, other])
            await db.flush()

            # Seed catalog Foods with unique names that embed their fragment.
            catalog = scenario["catalog"]
            fragments = scenario["catalog_fragments"]
            food_ids: list[int] = []
            food_names: list[str] = []
            for position, row in enumerate(catalog):
                # Position keeps Food.name globally unique; the fragment makes it
                # match (or not) the term under a case-insensitive substring test.
                name = f"Food {fragments[position]} {position}"
                food = Food(
                    name=name,
                    kcal_per_100g=row["kcal_per_100g"],
                    protein_g_per_100g=row["protein_g_per_100g"],
                    fat_g_per_100g=row["fat_g_per_100g"],
                    carbs_g_per_100g=row["carbs_g_per_100g"],
                    fiber_g_per_100g=row["fiber_g_per_100g"],
                )
                db.add(food)
                await db.flush()
                food_ids.append(food.id)
                food_names.append(name)

            # Inventory rows (food_id entries) for each user.
            def _seed_inventory(user_id, indices):
                for idx in indices:
                    db.add(UserFoodInventory(
                        user_id=user_id, food_id=food_ids[idx], quantity_grams=100.0
                    ))

            _seed_inventory(me.id, scenario["inv_mine"])
            _seed_inventory(other.id, scenario["inv_other"])
            await db.flush()

            # Recipe rows for each user. Names are made unique per user with an
            # index suffix (uq_user_recipe_name). Each has one ingredient.
            def _seed_recipes(user_id, specs, tag):
                names = []
                for i, spec in enumerate(specs):
                    rname = f"Recipe {spec['fragment']} {tag}{i}"
                    recipe = Recipe(user_id=user_id, name=rname)
                    recipe.ingredients.append(
                        RecipeIngredient(
                            food_id=food_ids[spec["food_index"]], grams=100.0
                        )
                    )
                    db.add(recipe)
                    names.append(rname)
                return names

            mine_recipe_names = _seed_recipes(me.id, scenario["recipes_mine"], "m")
            other_recipe_names = _seed_recipes(other.id, scenario["recipes_other"], "o")
            await db.flush()

            term = scenario["term"]
            needle = term.lower()

            # Independently compute the EXPECTED local matching sets (case-
            # insensitive substring, exactly what the service's ``ilike %term%``
            # does), scoped to the target user for inventory and recipes.
            def _matches(name: str) -> bool:
                return needle in name.lower()

            expected_catalog = {
                food_names[i] for i in range(len(food_names)) if _matches(food_names[i])
            }
            expected_inventory = {
                food_names[i] for i in scenario["inv_mine"] if _matches(food_names[i])
            }
            expected_recipes = {n for n in mine_recipe_names if _matches(n)}

            # Names that belong ONLY to the other user — they must never surface.
            other_inventory_names = {
                food_names[i] for i in scenario["inv_other"]
            }
            other_recipe_name_set = set(other_recipe_names)

            # Run the search with the OFF fallback patched to contribute nothing,
            # so every result is strictly local.
            with patch.object(
                search_service.food_lookup_service,
                "search_by_name",
                new=AsyncMock(return_value=[]),
            ):
                results = await search_service.unified_search(db, me.id, term)

            got_catalog = set()
            got_inventory = set()
            got_recipe = set()
            for r in results:
                # 1. kind is one of the allowed LOCAL origins (OFF is patched out).
                assert r["kind"] in _LOCAL_KINDS, (
                    f"Unexpected kind {r['kind']!r}; OFF/unknown origin leaked"
                )
                # 2. The result name matches the term (case-insensitive substring).
                assert r["name"] is not None and _matches(r["name"]), (
                    f"Result {r['name']!r} does not contain term {term!r}"
                )
                if r["kind"] == "catalog":
                    got_catalog.add(r["name"])
                elif r["kind"] == "inventory":
                    got_inventory.add(r["name"])
                    # 3a. An inventory hit must be one of MY inventory's foods and
                    #     never reference the other user's private inventory.
                    assert r["name"] not in (
                        other_inventory_names - expected_inventory
                    ), f"Inventory result {r['name']!r} belongs to another user"
                else:  # recipe
                    got_recipe.add(r["name"])
                    # 3b. A recipe hit must never reference the other user's recipe.
                    assert r["name"] not in other_recipe_name_set, (
                        f"Recipe result {r['name']!r} belongs to another user"
                    )

            # 4. Each origin's returned set is a SUBSET of the independently
            #    computed expected matching set (scoped to the target user).
            assert got_catalog <= expected_catalog, (
                f"catalog results not a subset: extra={got_catalog - expected_catalog}"
            )
            assert got_inventory <= expected_inventory, (
                f"inventory results not a subset: extra={got_inventory - expected_inventory}"
            )
            assert got_recipe <= expected_recipes, (
                f"recipe results not a subset: extra={got_recipe - expected_recipes}"
            )

            # 5. A term that matches NOTHING locally yields NO local results. We
            #    use a sentinel guaranteed absent from every seeded name.
            sentinel = "zzqq_no_match_sentinel_9999"
            with patch.object(
                search_service.food_lookup_service,
                "search_by_name",
                new=AsyncMock(return_value=[]),
            ):
                empty = await search_service.unified_search(db, me.id, sentinel)
            local_empty = [r for r in empty if r["kind"] in _LOCAL_KINDS]
            assert local_empty == [], (
                f"Non-matching term produced local results: {local_empty}"
            )
    finally:
        await engine.dispose()


@settings(max_examples=100, deadline=None)
@given(scenario=_scenario())
def test_search_returns_only_matching_local_results(scenario):
    """Feature: food-add-redesign, Property 3: La búsqueda incremental solo
    devuelve resultados locales que coinciden y de orígenes permitidos.

    Validates: Requirements 2.1

    For any generated catalog, user inventory and recipe set, and any term of
    1..100 characters, every LOCAL Search_Result returned by ``unified_search``
    has a name matching the term (case-insensitive substring) and a ``kind`` in
    {catalog, inventory, recipe}; the returned set per origin is a subset of the
    independently-computed matching set, scoped to the querying user (no other
    user's inventory/recipes leak); and a term matching nothing locally yields no
    local results.
    """
    asyncio.run(_run_scenario(scenario))


@settings(max_examples=100, deadline=None)
@given(
    term=st.one_of(
        st.just(""),
        st.just("   "),
        st.text(min_size=101, max_size=200),
    )
)
def test_search_rejects_out_of_range_term(term):
    """Feature: food-add-redesign, Property 3: La búsqueda incremental solo
    devuelve resultados locales que coinciden y de orígenes permitidos.

    Validates: Requirements 2.1

    A term whose stripped length is outside 1..100 characters is rejected with a
    Spanish ValidationError before any search runs (Req 2.5 boundary of the
    property's "término de 1 a 100 caracteres" precondition).
    """
    async def _check():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, class_=AsyncSession,
                                             expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with session_factory() as db:
                with pytest.raises(ValidationError):
                    await search_service.unified_search(db, 1, term)
        finally:
            await engine.dispose()

    asyncio.run(_check())

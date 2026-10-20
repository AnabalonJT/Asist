"""Unified incremental search service (Food_Add_Redesign).

This module hosts ``unified_search`` (Req 2): a single entry point that, given a
search term, returns a flat list of ``Search_Result`` dicts drawn from several
origins: the LOCAL origins — the global ``Food`` catalog, the user's own
inventory, and the user's own recipes — plus a best-effort Open Food Facts
fallback (``kind="off"``) that runs ONLY when there are no local results.

A ``Search_Result`` is a plain dict matching the design's ``SearchResultOut``:
``kind, id, name, brand, kcal, protein, fat, carbs, fiber, barcode, image_url``.
Nutrition values are per 100 g; ``image_url`` is always ``None`` for local
results. Inventory and recipe searches are scoped to ``user_id`` so a user never
sees another user's private records (Req 2.7, 8.1).

User-facing text (messages) is in Spanish; identifiers and comments are in
English by project convention.

Requirements: 2.1, 2.3, 2.5, 2.7, 8.1.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.food import Food
from app.models.recipe import Recipe
from app.models.recipe_ingredient import RecipeIngredient
from app.models.user_food_inventory import UserFoodInventory
from app.services import food_lookup_service, recipe_service
from app.services.meal_service import ValidationError

# Maximum rows returned per local origin. Keeps incremental (keystroke-driven)
# search responsive and bounds the payload size.
SEARCH_LIMIT = 20

# The allowed term length (characters, after stripping). Matches the catalog
# food name range (1..100) so a search term can always name an existing food.
SEARCH_TERM_LEN = (1, 100)


def _food_result(kind: str, food: Food) -> dict:
    """Map a ``Food`` row to a ``Search_Result`` dict for the given ``kind``.

    Used for both the ``catalog`` and ``inventory`` origins: an inventory hit is
    rendered from the ``Food`` it references, carrying the same per-100 g macros,
    brand and barcode. ``image_url`` is ``None`` for every local result."""
    return {
        "kind": kind,
        "id": food.id,
        "name": food.name,
        "brand": food.brand,
        "kcal": food.kcal_per_100g,
        "protein": food.protein_g_per_100g,
        "fat": food.fat_g_per_100g,
        "carbs": food.carbs_g_per_100g,
        "fiber": food.fiber_g_per_100g,
        "barcode": food.barcode,
        "image_url": None,
    }


def _recipe_result(recipe: Recipe) -> dict:
    """Map a ``Recipe`` (with ingredients+foods eager-loaded) to a
    ``Search_Result`` dict of ``kind="recipe"``.

    The recipe's per-100 g nutrition is derived from its ingredients via
    ``recipe_service.compute_recipe_nutrition`` (Req 4.2). A recipe has no brand
    or barcode, and ``image_url`` is ``None``."""
    nutrition = recipe_service.compute_recipe_nutrition(
        [
            {
                "grams": ingredient.grams,
                "kcal_per_100g": ingredient.food.kcal_per_100g,
                "protein_g_per_100g": ingredient.food.protein_g_per_100g,
                "fat_g_per_100g": ingredient.food.fat_g_per_100g,
                "carbs_g_per_100g": ingredient.food.carbs_g_per_100g,
                "fiber_g_per_100g": ingredient.food.fiber_g_per_100g,
            }
            for ingredient in recipe.ingredients
        ]
    )
    return {
        "kind": "recipe",
        "id": recipe.id,
        "name": recipe.name,
        "brand": None,
        "kcal": nutrition["kcal"],
        "protein": nutrition["protein"],
        "fat": nutrition["fat"],
        "carbs": nutrition["carbs"],
        "fiber": nutrition["fiber"],
        "barcode": None,
        "image_url": None,
    }


async def unified_search(db: AsyncSession, user_id, q) -> list[dict]:
    """Return ``Search_Result`` dicts (Req 2). Validates term length (1..100);
    searches catalog (ilike), the user's inventory, and the user's recipes;
    when there are no local results, falls back to ``food_lookup_service.
    search_by_name`` (best-effort). Scoped to ``user_id`` (Req 2.7, 8.1).

    Steps:
      1. Strip ``q`` and validate its length is within ``SEARCH_TERM_LEN``
         (1..100) → ``ValidationError`` (Spanish) (Req 2.5).
      2. Catalog (``kind="catalog"``): foods whose name matches the term
         (case-insensitive ``ilike``).
      3. Inventory (``kind="inventory"``): this user's ``UserFoodInventory`` rows
         that reference a ``Food`` whose name matches the term. Recipe-only
         inventory entries are surfaced via the recipe search instead (Req 2.7).
      4. Recipes (``kind="recipe"``): this user's ``Recipe`` rows whose name
         matches the term, with nutrition derived from their ingredients.
    Returns the concatenated local results. The OFF fallback (task 6.2) extends
    this list when it is empty.
    """
    # 1. Validate the search term (strip, then length within range).
    term = q.strip() if isinstance(q, str) else ""
    min_len, max_len = SEARCH_TERM_LEN
    if len(term) < min_len or len(term) > max_len:
        raise ValidationError(
            "El término de búsqueda debe tener entre 1 y 100 caracteres."
        )

    # SQL LIKE wildcards around the raw term: case-insensitive substring match.
    pattern = f"%{term}%"
    results: list[dict] = []

    # 2. Catalog: global foods whose name matches the term.
    catalog_rows = await db.execute(
        select(Food).where(Food.name.ilike(pattern)).order_by(Food.name).limit(SEARCH_LIMIT)
    )
    for food in catalog_rows.scalars().all():
        results.append(_food_result("catalog", food))

    # 3. Inventory: this user's inventory rows referencing a matching Food. Join
    #    to Food (only food_id entries; recipe entries surface via step 4) and
    #    scope to user_id for privacy (Req 2.7, 8.1).
    inventory_rows = await db.execute(
        select(Food)
        .join(UserFoodInventory, UserFoodInventory.food_id == Food.id)
        .where(
            UserFoodInventory.user_id == user_id,
            Food.name.ilike(pattern),
        )
        .order_by(Food.name)
        .limit(SEARCH_LIMIT)
    )
    for food in inventory_rows.scalars().all():
        results.append(_food_result("inventory", food))

    # 4. Recipes: this user's recipes whose name matches, nutrition derived from
    #    the ingredients (eager-loaded to avoid lazy I/O). Scoped to user_id.
    recipe_rows = await db.execute(
        select(Recipe)
        .where(Recipe.user_id == user_id, Recipe.name.ilike(pattern))
        .order_by(Recipe.name)
        .limit(SEARCH_LIMIT)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.food))
    )
    for recipe in recipe_rows.scalars().all():
        results.append(_recipe_result(recipe))

    # 5. OFF fallback (Req 2.2, 2.6): only when there are NO local results, query
    #    Open Food Facts by name. `search_by_name` is best-effort and never
    #    raises — on any failure (timeout, HTTP/JSON error, no products) it
    #    returns []. We still never let an external error propagate here.
    if len(results) == 0:
        external = await food_lookup_service.search_by_name(term)
        for product in external:
            results.append(
                {
                    "kind": "off",
                    "id": None,  # OFF results have no local id
                    "name": product.get("name"),
                    "brand": product.get("brand"),
                    "kcal": product.get("kcal"),
                    "protein": product.get("protein"),
                    "fat": product.get("fat"),
                    "carbs": product.get("carbs"),
                    "fiber": product.get("fiber"),
                    "barcode": product.get("barcode"),
                    "image_url": product.get("image_url"),
                }
            )

    return results

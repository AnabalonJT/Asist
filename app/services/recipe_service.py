"""Recipe service layer (Food_Add_Redesign).

This module hosts the recipe business logic. Task 2.1 defines ONLY the pure
aggregate-nutrition function ``compute_recipe_nutrition``; the async CRUD and
inventory operations (``create_recipe``, ``list_recipes``, ``delete_recipe``,
``add_recipe_to_inventory``) are added by later tasks (3.1/4.1) and will reuse
``meal_service`` (``validate_food_fields``, ``add_inventory``, ``_normalize_name``,
``INVENTORY_GRAMS_RANGE``).

The recipe's nutrition is derived from its ingredients as a grams-weighted
average of each ingredient's per-100 g values, renormalized to 100 g (Req 4.2).

User-facing text (messages) is in Spanish; identifiers and comments are in
English by project convention.

Requirements: 4.2.
"""

# ── Pure functions: aggregate recipe nutrition (Task 2.1) ────────────────────

# The per-100 g nutrition keys contributed by each ingredient. ``fiber`` is
# handled separately because it is optional (may be None).
_MACRO_KEYS = ("kcal", "protein", "fat", "carbs")

# Maps each returned dict key to the ingredient's per-100 g source key.
_SOURCE_KEYS = {
    "kcal": "kcal_per_100g",
    "protein": "protein_g_per_100g",
    "fat": "fat_g_per_100g",
    "carbs": "carbs_g_per_100g",
    "fiber": "fiber_g_per_100g",
}


def _is_number(value) -> bool:
    """True if value is a real number (int/float) and not a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def compute_recipe_nutrition(ingredients: list[dict]) -> dict:
    """PURE. ingredients: [{grams, kcal_per_100g, protein_g_per_100g,
    fat_g_per_100g, carbs_g_per_100g, fiber_g_per_100g|None}]. Returns per-100g
    nutrition = (sum over i of value_i/100 * grams_i) / total_grams * 100.
    fiber is None only if every ingredient's fiber is None (Req 4.2).

    The ``value_i/100 * grams_i`` form is the absolute amount of that nutrient
    contributed by ingredient ``i`` (its per-100 g value scaled by its mass);
    summing those and renormalizing by ``total_grams / 100`` yields the recipe's
    per-100 g value — a grams-weighted average, invariant to uniform scaling of
    every ingredient's mass.

    Returned keys: ``kcal, protein, fat, carbs, fiber`` (matching
    ``RecipeNutritionOut``). ``fiber`` is ``None`` only when EVERY ingredient has
    ``fiber_g_per_100g`` None; when at least one ingredient reports fiber, the
    others (None) are treated as 0.

    When ``total_grams`` is 0 (no ingredients or all-zero grams), returns zeros
    for the macros and ``None`` for fiber, so the function never divides by zero.
    """
    ingredients = ingredients or []

    total_grams = 0.0
    # Absolute per-nutrient totals (grams of nutrient) across all ingredients.
    weighted_sums = {key: 0.0 for key in _MACRO_KEYS}
    fiber_sum = 0.0
    any_fiber = False  # True once at least one ingredient reports a fiber value.

    for ingredient in ingredients:
        if not isinstance(ingredient, dict):
            continue
        grams = ingredient.get("grams")
        if not _is_number(grams) or grams <= 0:
            # Non-positive or non-numeric mass contributes nothing (and must not
            # inflate total_grams). Skip it.
            continue
        grams = float(grams)
        total_grams += grams

        for key in _MACRO_KEYS:
            value = ingredient.get(_SOURCE_KEYS[key])
            if _is_number(value):
                # value per 100 g → absolute nutrient = value/100 * grams
                weighted_sums[key] += value / 100.0 * grams

        fiber_value = ingredient.get(_SOURCE_KEYS["fiber"])
        if _is_number(fiber_value):
            any_fiber = True
            fiber_sum += fiber_value / 100.0 * grams

    if total_grams <= 0:
        # No usable mass: avoid division by zero. Macros are zero; fiber follows
        # the "None only if every ingredient's fiber is None" rule.
        return {
            "kcal": 0.0,
            "protein": 0.0,
            "fat": 0.0,
            "carbs": 0.0,
            "fiber": 0.0 if any_fiber else None,
        }

    # Renormalize each absolute nutrient total back to a per-100 g value.
    factor = 100.0 / total_grams
    result = {key: weighted_sums[key] * factor for key in _MACRO_KEYS}
    result["fiber"] = (fiber_sum * factor) if any_fiber else None
    return result


# ── I/O functions: recipe CRUD (Task 3.1) ────────────────────────────────────
# These async functions follow the project convention: "validate before mutate"
# (every check runs BEFORE any INSERT/DELETE so a failure leaves the DB intact),
# then mutate + ``db.flush()`` and let the ``get_db`` dependency issue the final
# commit. They reuse ``meal_service``'s internal exceptions, name normalization
# and shared validation ranges so error handling stays consistent across the
# feature. User-facing messages are in Spanish; identifiers/comments in English.

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.food import Food
from app.models.recipe import Recipe
from app.models.recipe_ingredient import RecipeIngredient
from app.models.user_food_inventory import UserFoodInventory
from app.services.meal_service import (
    ForbiddenError,
    INVENTORY_GRAMS_RANGE,
    FOOD_NAME_LEN,
    ValidationError,
    _normalize_name,
)

# A recipe must have between 1 and 100 ingredients (Req 4.1). Reusing
# INVENTORY_GRAMS_RANGE (1..100000) for each ingredient's grams matches Req 4.3.
RECIPE_INGREDIENTS_RANGE = (1, 100)


def _ingredient_fields(ingredient):
    """Extract ``(food_id, grams)`` from an ingredient (a dict or an object).

    Accepts mapping access (dict) or attribute access (e.g. a Pydantic model).
    Missing keys yield ``None`` so the caller can validate them uniformly."""
    if isinstance(ingredient, dict):
        return ingredient.get("food_id"), ingredient.get("grams")
    return getattr(ingredient, "food_id", None), getattr(ingredient, "grams", None)


async def _find_recipe_by_name(db: AsyncSession, user_id, name):
    """Return the user's ``Recipe`` whose normalized name matches ``name``, or
    ``None``. Matches case/accent-insensitively (via ``_normalize_name``) so
    "Ensalada" and "ensalada" collide, enforcing uniqueness per user beyond the
    DB's exact ``uq_user_recipe_name`` constraint. Scans only this user's recipes."""
    target = _normalize_name(name)
    if not target:
        return None
    result = await db.execute(select(Recipe).where(Recipe.user_id == user_id))
    for recipe in result.scalars().all():
        if _normalize_name(recipe.name) == target:
            return recipe
    return None


async def _load_recipe(db: AsyncSession, recipe_id) -> Recipe | None:
    """Load a ``Recipe`` by id with its ingredients and their foods eager-loaded
    (``selectinload``), so nutrition can be computed without lazy I/O. Returns
    ``None`` when the recipe does not exist."""
    result = await db.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.food))
    )
    return result.scalar_one_or_none()


async def create_recipe(db: AsyncSession, user_id, name, ingredients) -> Recipe:
    """Create and persist a private ``Recipe`` for ``user_id`` (Req 4.1, 4.3, 4.4).

    ``ingredients`` is a list of items carrying ``food_id`` and ``grams`` (each a
    dict or an object). Every check runs BEFORE any INSERT so a failure leaves
    the DB unchanged:
      1. ``name`` length within ``FOOD_NAME_LEN`` (1..100) → ``ValidationError``.
      2. ``ingredients`` is a list of ``RECIPE_INGREDIENTS_RANGE`` (1..100) items
         → ``ValidationError`` when empty or too many.
      3. Each ingredient's ``grams`` within ``INVENTORY_GRAMS_RANGE`` (1..100000)
         → ``ValidationError`` (Req 4.3).
      4. Every referenced ``food_id`` must exist in the catalog → ``ValidationError``
         naming the missing id (Req 4.4), loaded via a single ``IN`` query.
      5. ``name`` is unique per user (normalized) → ``ValidationError``.
    On success, insert the ``Recipe`` and its ``RecipeIngredient`` rows, flush so
    ids populate, and return the recipe with ingredients+foods eager-loaded.
    """
    # 1. Name length (Req 4.1).
    name_len = len(name) if isinstance(name, str) else -1
    min_len, max_len = FOOD_NAME_LEN
    if name_len < min_len or name_len > max_len:
        raise ValidationError(
            f"El nombre de la receta debe tener entre {min_len} y {max_len} caracteres."
        )

    # 2. Ingredient count (Req 4.1).
    if not isinstance(ingredients, (list, tuple)):
        raise ValidationError(
            "Los ingredientes deben enviarse como una lista."
        )
    min_count, max_count = RECIPE_INGREDIENTS_RANGE
    if len(ingredients) < min_count or len(ingredients) > max_count:
        raise ValidationError(
            f"La receta debe tener entre {min_count} y {max_count} ingredientes "
            f"(recibidos {len(ingredients)})."
        )

    # 3. Each ingredient: a valid food_id and grams within range (Req 4.3).
    grams_min, grams_max = INVENTORY_GRAMS_RANGE
    parsed: list[tuple[int, float]] = []  # (food_id, grams)
    for position, ingredient in enumerate(ingredients, start=1):
        food_id, grams = _ingredient_fields(ingredient)

        if not _is_number(food_id) or isinstance(food_id, bool):
            raise ValidationError(
                f"El ingrediente {position} debe indicar un alimento válido."
            )
        if not _is_number(grams) or grams < grams_min or grams > grams_max:
            raise ValidationError(
                f"Los gramos del ingrediente {position} deben estar entre "
                f"{grams_min:g} y {grams_max:g}."
            )
        parsed.append((int(food_id), float(grams)))

    # 4. Every referenced food must exist (Req 4.4). Single IN query.
    food_ids = {food_id for food_id, _ in parsed}
    result = await db.execute(select(Food).where(Food.id.in_(food_ids)))
    foods_by_id = {food.id: food for food in result.scalars().all()}
    missing = sorted(food_ids - set(foods_by_id))
    if missing:
        raise ValidationError(
            f"El ingrediente con alimento id {missing[0]} no existe en el catálogo."
        )

    # 5. Unique name per user (normalized) — preserve the DB on duplicate.
    existing = await _find_recipe_by_name(db, user_id, name)
    if existing is not None:
        raise ValidationError(
            f"Ya tienes una receta con el nombre '{name}'."
        )

    # Compute nutrition from the loaded foods (derived; not persisted on the
    # model). The endpoint/schema layer recomputes this for serialization.
    compute_recipe_nutrition(
        [
            {
                "grams": grams,
                "kcal_per_100g": foods_by_id[food_id].kcal_per_100g,
                "protein_g_per_100g": foods_by_id[food_id].protein_g_per_100g,
                "fat_g_per_100g": foods_by_id[food_id].fat_g_per_100g,
                "carbs_g_per_100g": foods_by_id[food_id].carbs_g_per_100g,
                "fiber_g_per_100g": foods_by_id[food_id].fiber_g_per_100g,
            }
            for food_id, grams in parsed
        ]
    )

    # All checks passed → mutate.
    recipe = Recipe(user_id=user_id, name=name.strip() if isinstance(name, str) else name)
    recipe.ingredients = [
        RecipeIngredient(food_id=food_id, grams=grams) for food_id, grams in parsed
    ]
    db.add(recipe)
    await db.flush()  # populate recipe.id and ingredient ids

    # Return the recipe with ingredients+foods eager-loaded for serialization.
    return await _load_recipe(db, recipe.id)


async def list_recipes(db: AsyncSession, user_id) -> list[Recipe]:
    """Return the user's recipes ordered by name, owner-restricted (Req 4.5, 8.1).

    Ingredients and their foods are eager-loaded (``selectinload``) so the caller
    can derive each recipe's nutrition without further I/O. Read-only."""
    result = await db.execute(
        select(Recipe)
        .where(Recipe.user_id == user_id)
        .order_by(Recipe.name)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.food))
    )
    return list(result.scalars().all())


async def get_recipe(db: AsyncSession, user_id, recipe_id) -> Recipe:
    """Return a single owned ``Recipe`` with ingredients+foods eager-loaded.

    Not found → ``ValidationError`` (Spanish). Found but owned by another user →
    ``ForbiddenError`` (Req 5.3 privacy: do not confirm the recipe's existence to
    a non-owner). Read-only."""
    recipe = await _load_recipe(db, recipe_id)
    if recipe is None:
        raise ValidationError(
            f"No se encontró la receta con id {recipe_id}."
        )
    if recipe.user_id != user_id:
        raise ForbiddenError(
            "No tienes permiso para acceder a esta receta."
        )
    return recipe


async def delete_recipe(db: AsyncSession, user_id, recipe_id) -> None:
    """Delete an owned ``Recipe`` and its ingredients (Req 4.6, 8.4).

    Not found → ``ValidationError`` (Spanish). Owned by another user →
    ``ForbiddenError`` without confirming the recipe exists. On success, deleting
    the recipe cascades to its ``RecipeIngredient`` rows (relationship
    ``cascade="all, delete-orphan"``) while leaving the referenced ``Food`` rows
    in the catalog untouched. Flushes and lets ``get_db`` commit."""
    recipe = await _load_recipe(db, recipe_id)
    if recipe is None:
        raise ValidationError(
            f"No se encontró la receta con id {recipe_id}."
        )
    if recipe.user_id != user_id:
        raise ForbiddenError(
            "No tienes permiso para eliminar esta receta."
        )

    await db.delete(recipe)  # cascade removes RecipeIngredient rows
    await db.flush()


# ── I/O functions: recipe → inventory (Task 4.1) ─────────────────────────────


async def add_recipe_to_inventory(
    db: AsyncSession, user_id, recipe_id, grams
) -> UserFoodInventory:
    """Add (or update) a recipe in the user's inventory (Req 5.1-5.4).

    Follows the "validate before mutate" convention: every check runs BEFORE any
    INSERT/UPDATE so a failure leaves the inventory untouched. User-facing
    messages are in Spanish; identifiers/comments in English.

    Steps:
      1. Validate ``grams`` is a number within ``INVENTORY_GRAMS_RANGE``
         (1..100000); otherwise raise ``ValidationError`` (Spanish) (Req 5.2, 5.4).
      2. Verify the recipe exists AND is owned by ``user_id`` via
         ``get_recipe`` (raises ``ValidationError`` if not found, ``ForbiddenError``
         if owned by another user) (Req 5.3).
      3. Upsert the inventory row deduplicated by ``(user_id, recipe_id)``: update
         the existing row's ``quantity_grams`` or insert a new one with
         ``food_id`` left ``None`` so the XOR check constraint passes (Req 5.1, 5.2).
    Returns the persisted ``UserFoodInventory`` row.
    """
    # 1. Validate grams first (must be present and within range for a recipe).
    grams_min, grams_max = INVENTORY_GRAMS_RANGE
    if (
        not _is_number(grams)
        or isinstance(grams, bool)
        or grams < grams_min
        or grams > grams_max
    ):
        raise ValidationError(
            f"La cantidad en gramos debe estar entre {grams_min:g} y "
            f"{grams_max:g}."
        )

    # 2. Verify the recipe exists and is owned by this user (Req 5.3). Raises
    #    ValidationError (not found) or ForbiddenError (owned by another user)
    #    before any mutation.
    await get_recipe(db, user_id, recipe_id)

    # 3. Upsert the inventory row, deduplicated by (user_id, recipe_id).
    result = await db.execute(
        select(UserFoodInventory).where(
            UserFoodInventory.user_id == user_id,
            UserFoodInventory.recipe_id == recipe_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        # food_id left None so the ck_food_xor_recipe constraint is satisfied.
        entry = UserFoodInventory(
            user_id=user_id,
            recipe_id=recipe_id,
            quantity_grams=float(grams),
        )
        db.add(entry)
    else:
        # Deduplicated: keep the single row and store the latest quantity.
        entry.quantity_grams = float(grams)

    await db.flush()
    return entry

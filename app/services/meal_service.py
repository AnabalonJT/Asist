"""Meal_Planner service layer.

This module hosts the constants, internal exceptions, and (in later tasks) the
pure and I/O business logic for the meal planner. Task 5.1 defines ONLY the
constants and the internal exception hierarchy; functions are added by
subsequent tasks (5.2, 5.4, 5.7, 5.10, 6.x, 7.x, 9.x).

User-facing text (messages, disclaimer) is in Spanish; identifiers and comments
are in English by project convention.

Requirements: 4.5, 6.7, 12.6.
"""

import math
import unicodedata

# ── Constants ────────────────────────────────────────────────────────────────

CALORIE_TOLERANCE = 0.10          # ±10 % per day (Req 6.7, Calorie_Tolerance)
KCAL_PER_G = {"protein": 4.0, "carb": 4.0, "fat": 9.0}  # (Req 4.5)
MACRO_KCAL_TOLERANCE = 10.0       # ±10 kcal on macro split sum (Req 4.5)

# Minimum protein per kg of current body weight, by goal (Req 4.2/4.3/4.4)
PROTEIN_PER_KG = {
    "gain_muscle": 1.8,
    "lose_weight": 1.6,
    "weight_target_deficit": 1.6,
    "maintain": 1.4,
}

VALID_MEAL_TYPES = {"desayuno", "almuerzo", "cena", "snack"}
PLAN_DAYS = 7

# Validation ranges
FOOD_NAME_LEN = (1, 100)
FOOD_KCAL_RANGE = (0.0, 900.0)
FOOD_MACRO_RANGE = (0.0, 100.0)          # protein/fat/carbs/fiber per 100 g
INVENTORY_GRAMS_RANGE = (1.0, 100000.0)  # (Req 2.1, 6.4)
ALLERGEN_LEN = (1, 50)                   # (Req 3.1)
MANUAL_KCAL_RANGE = (800.0, 6000.0)      # (Req 5.1)
MANUAL_PROTEIN_RANGE = (0.0, 500.0)
MANUAL_FAT_RANGE = (0.0, 500.0)
MANUAL_CARBS_RANGE = (0.0, 1000.0)

DIET_FLAGS = {"vegetarian", "vegan", "gluten_free"}

MEAL_DISCLAIMER = (
    "Esta información es orientativa y no constituye consejo nutricional ni médico. "
    "Eres responsable de verificar los ingredientes y alérgenos de cada alimento."
)


# ── Internal exceptions ──────────────────────────────────────────────────────
# These are internal service exceptions; the router translates them to
# HTTPException with Spanish `detail` (see design.md Error Handling).


class MealServiceError(Exception):
    """Base class for all Meal_Planner service errors."""


class ValidationError(MealServiceError):
    """A field (food/target/allergen) is out of range or otherwise invalid.

    The message is in Spanish and identifies the invalid field(s) and range.
    """


class GoalRequiredError(MealServiceError):
    """Nutrition targets (manual or derived from a fitness profile) are required
    before the requested operation can proceed (Req 4.6, 5.5, 6.9, 8.5)."""


class LLMError(MealServiceError):
    """The LLM plan generation failed (timeout, error, or unparseable content).

    Carries a `kind` attribute ("timeout" | "error" | "parse") so the router can
    map it to the appropriate HTTP status and Spanish message (Req 9.1–9.3).
    """

    def __init__(self, message, kind=None):
        super().__init__(message)
        self.kind = kind


class ToleranceError(MealServiceError):
    """The generated plan is outside the calorie tolerance on at least one day;
    the previous active plan is left untouched (Req 6.8)."""


class DietaryError(MealServiceError):
    """The generated plan violates a dietary restriction or allergen; the
    previous active plan is left untouched (Req 7.1–7.4)."""


class ShoppingRequiresPlanError(MealServiceError):
    """A shopping list was requested but no active plan exists (Req 13.4)."""


class ForbiddenError(MealServiceError):
    """Attempt to access another user's records without permission (Req 12.3, 12.4)."""


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_name(value) -> str:
    """Normalize a food/allergen name for matching: lowercase, strip surrounding
    whitespace, and remove diacritics (accents). Non-string input is coerced to
    an empty string. Used for allergen substring matching and food lookups."""
    if not isinstance(value, str):
        return ""
    text = value.strip().lower()
    # Decompose accents and drop combining marks (á -> a, ñ -> n).
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# ── Pure functions: field validation (Task 5.2) ─────────────────────────────


def validate_food_fields(name, kcal, protein, fat, carbs, fiber) -> None:
    """Validate the fields of a catalog food (nutrition per 100 g).

    Raise ``ValidationError`` (Spanish message identifying the invalid field) if:
      - ``name`` length is not within ``FOOD_NAME_LEN`` (1..100),
      - ``kcal`` is not within ``FOOD_KCAL_RANGE`` (0..900),
      - ``protein``/``fat``/``carbs`` are not within ``FOOD_MACRO_RANGE`` (0..100),
      - ``fiber`` is not within ``FOOD_MACRO_RANGE`` (0..100) — but ``fiber`` MAY be
        ``None`` (optional), in which case its check is skipped.

    Returns ``None`` when every field is valid (Req 1.3, 1.4, 1.5, 2.3, 2.4).
    """
    # Name: must be a string whose length is within the allowed range.
    name_len = len(name) if isinstance(name, str) else -1
    min_len, max_len = FOOD_NAME_LEN
    if name_len < min_len or name_len > max_len:
        raise ValidationError(
            f"El nombre del alimento debe tener entre {min_len} y {max_len} caracteres."
        )

    kcal_min, kcal_max = FOOD_KCAL_RANGE
    if not _is_number(kcal) or kcal < kcal_min or kcal > kcal_max:
        raise ValidationError(
            f"Las calorías (kcal) deben estar entre {kcal_min:g} y {kcal_max:g} por 100 g."
        )

    macro_min, macro_max = FOOD_MACRO_RANGE
    for value, label in (
        (protein, "Las proteínas"),
        (fat, "Las grasas"),
        (carbs, "Los carbohidratos"),
    ):
        if not _is_number(value) or value < macro_min or value > macro_max:
            raise ValidationError(
                f"{label} deben estar entre {macro_min:g} y {macro_max:g} g por 100 g."
            )

    # Fiber is optional: skip when None, otherwise validate against the macro range.
    if fiber is not None:
        if not _is_number(fiber) or fiber < macro_min or fiber > macro_max:
            raise ValidationError(
                f"La fibra debe estar entre {macro_min:g} y {macro_max:g} g por 100 g."
            )


def validate_manual_targets(kcal, protein_g, fat_g, carbs_g) -> None:
    """Validate manually entered nutrition targets. All-or-nothing.

    Raise ``ValidationError`` (Spanish) listing EVERY out-of-range field together
    with its valid range if any value is outside the ``MANUAL_*`` ranges. Returns
    ``None`` when all four values are valid (Req 5.1, 5.2).
    """
    errors: list[str] = []

    checks = (
        (kcal, MANUAL_KCAL_RANGE, "calorías (kcal)"),
        (protein_g, MANUAL_PROTEIN_RANGE, "proteínas (g)"),
        (fat_g, MANUAL_FAT_RANGE, "grasas (g)"),
        (carbs_g, MANUAL_CARBS_RANGE, "carbohidratos (g)"),
    )
    for value, (low, high), label in checks:
        if not _is_number(value) or value < low or value > high:
            errors.append(f"{label} deben estar entre {low:g} y {high:g}")

    if errors:
        raise ValidationError(
            "Metas nutricionales inválidas: " + "; ".join(errors) + "."
        )


def _is_number(value) -> bool:
    """True if value is a real number (int/float) and not a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ── Pure functions: nutrition derivation (Task 5.4) ──────────────────────────


def estimate_maintenance_kcal(view: dict) -> float:
    """Estimate maintenance TDEE from a FitnessProfile meal_planner_view using the
    Mifflin-St Jeor equation for BMR plus a light-activity factor.

        BMR = 10*weight_kg + 6.25*height_cm - 5*age + s
            s = +5 (male), -161 (female), -78 (other/unknown)
        maintenance = round(BMR * 1.375)   # light-activity multiplier

    Pure function. Requires ``weight_kg``, ``height_cm``, ``age`` and ``sex`` in
    the view. Raises ``ValidationError`` (Spanish) if any required body datum is
    missing or not numeric (handled upstream as Req 4.6).
    """
    weight_kg = view.get("weight_kg")
    height_cm = view.get("height_cm")
    age = view.get("age")
    sex = view.get("sex")

    missing = []
    if not _is_number(weight_kg):
        missing.append("peso")
    if not _is_number(height_cm):
        missing.append("altura")
    if not _is_number(age):
        missing.append("edad")
    if missing:
        raise ValidationError(
            "Faltan datos corporales para estimar el mantenimiento: "
            + ", ".join(missing)
            + "."
        )

    sex_normalized = _normalize_name(sex)
    if sex_normalized in ("male", "hombre", "m", "masculino"):
        s = 5.0
    elif sex_normalized in ("female", "mujer", "f", "femenino"):
        s = -161.0
    else:
        # other / unknown → average of the two sex constants (-78)
        s = -78.0

    bmr = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age + s
    return float(round(bmr * 1.375))


def derive_nutrition_targets(view: dict, target_rate: dict | None) -> dict:
    """PURE. Build derived daily targets from a fitness view and an optional
    target rate, returning ``{kcal, protein_g, fat_g, carbs_g, source:'derived'}``.

    kcal is set by goal (maintenance +/- a daily delta); protein is grams-per-kg
    of current body weight by goal; the remaining kcal is split 40% fat / 60%
    carbs using 9/4 kcal per gram.

    Post-condition (Req 4.5): ``|protein_g*4 + carbs_g*4 + fat_g*9 - kcal| <=
    MACRO_KCAL_TOLERANCE``. Rounding can break the naive split, so ``carbs_g`` is
    adjusted afterward so the macro-kcal sum lands within tolerance of the target
    kcal. The returned ``kcal`` is the target kcal, not the macro sum.
    Does not touch the DB.
    """
    maintenance = estimate_maintenance_kcal(view)
    goal = view.get("goal_type")
    weight = view.get("current_weight_kg")
    if not _is_number(weight):
        raise ValidationError(
            "Falta el peso actual para derivar las metas nutricionales."
        )

    direction = target_rate.get("direction") if target_rate else None

    # Default daily kcal delta by goal when no target_rate is supplied.
    if target_rate and _is_number(target_rate.get("daily_kcal_delta")):
        delta = float(target_rate["daily_kcal_delta"])
    else:
        delta = 400.0  # sensible default for gain/lose when absent

    if goal == "gain_muscle":
        kcal = maintenance + delta
        ppk = 1.8
    elif goal == "maintain":
        kcal = maintenance
        ppk = 1.4
    elif goal == "lose_weight" or (
        goal == "weight_target" and direction == "déficit"
    ):
        kcal = maintenance - delta
        ppk = 1.6
    elif goal == "weight_target" and direction == "superávit":
        kcal = maintenance + delta
        ppk = 1.8
    else:
        # endurance / performance / other / unknown
        kcal = maintenance
        ppk = 1.6

    kcal = float(kcal)
    protein_g = round(ppk * weight, 1)
    protein_kcal = protein_g * KCAL_PER_G["protein"]
    remaining = max(kcal - protein_kcal, 0.0)

    fat_g = round((remaining * 0.40) / KCAL_PER_G["fat"], 1)
    carbs_g = round((remaining * 0.60) / KCAL_PER_G["carb"], 1)

    # Enforce the macro-kcal post-condition: adjust carbs so the macro sum lands
    # within MACRO_KCAL_TOLERANCE of the target kcal despite rounding drift.
    macro_kcal = (
        protein_g * KCAL_PER_G["protein"]
        + carbs_g * KCAL_PER_G["carb"]
        + fat_g * KCAL_PER_G["fat"]
    )
    diff = kcal - macro_kcal
    if abs(diff) > MACRO_KCAL_TOLERANCE:
        # carbs contribute 4 kcal/g; nudge carbs_g to close the gap.
        carbs_g = round(carbs_g + diff / KCAL_PER_G["carb"], 1)
        if carbs_g < 0:
            carbs_g = 0.0

    return {
        "kcal": kcal,
        "protein_g": protein_g,
        "fat_g": fat_g,
        "carbs_g": carbs_g,
        "source": "derived",
    }


# ── Pure functions: plan tolerance & structure (Task 5.7) ────────────────────


def check_calorie_tolerance(day_totals: dict, target_kcal: float) -> bool:
    """PURE. Return ``True`` iff the day's kcal is within ``CALORIE_TOLERANCE`` of
    the target, i.e. ``|day_kcal - target_kcal| <= CALORIE_TOLERANCE *
    target_kcal`` (Req 6.7). A plan passes iff all 7 days pass (Req 6.8).
    """
    day_kcal = day_totals.get("kcal") if isinstance(day_totals, dict) else None
    if not _is_number(day_kcal) or not _is_number(target_kcal):
        return False
    return abs(day_kcal - target_kcal) <= CALORIE_TOLERANCE * target_kcal


def validate_plan_structure(structure) -> None:
    """PURE. Validate the weekly meal-plan structure (Req 6.3, 6.4, 6.5).

    Accepts either a list of day dicts or a dict with a ``"days"`` key (the LLM
    returns the latter). Raises ``ValidationError`` (Spanish) on any violation:
      - not exactly ``PLAN_DAYS`` (7) days,
      - a day with no meal, or a meal whose ``type`` is not in ``VALID_MEAL_TYPES``,
      - a meal with no item, or an item whose ``grams`` is not within
        ``INVENTORY_GRAMS_RANGE`` (1..100000),
      - a day missing its ``totals`` (a dict containing ``kcal``).

    Returns ``None`` when the structure is valid.
    """
    # Normalize: accept {"days": [...]} or a bare list.
    if isinstance(structure, dict):
        days = structure.get("days")
    else:
        days = structure

    if not isinstance(days, list):
        raise ValidationError("El plan debe contener una lista de días.")

    if len(days) != PLAN_DAYS:
        raise ValidationError(
            f"El plan debe tener exactamente {PLAN_DAYS} días (recibidos {len(days)})."
        )

    grams_min, grams_max = INVENTORY_GRAMS_RANGE

    for index, day in enumerate(days, start=1):
        if not isinstance(day, dict):
            raise ValidationError(f"El día {index} tiene un formato inválido.")

        meals = day.get("meals")
        if not isinstance(meals, list) or len(meals) < 1:
            raise ValidationError(
                f"El día {index} debe incluir al menos una comida."
            )

        for meal in meals:
            if not isinstance(meal, dict):
                raise ValidationError(
                    f"El día {index} contiene una comida con formato inválido."
                )
            meal_type = meal.get("type")
            if meal_type not in VALID_MEAL_TYPES:
                raise ValidationError(
                    f"El día {index} contiene una comida con tipo inválido: "
                    f"{meal_type!r}. Tipos válidos: "
                    f"{', '.join(sorted(VALID_MEAL_TYPES))}."
                )

            items = meal.get("items")
            if not isinstance(items, list) or len(items) < 1:
                raise ValidationError(
                    f"La comida '{meal_type}' del día {index} debe incluir al menos un alimento."
                )

            for item in items:
                if not isinstance(item, dict):
                    raise ValidationError(
                        f"La comida '{meal_type}' del día {index} contiene un ítem inválido."
                    )
                grams = item.get("grams")
                if not _is_number(grams) or grams < grams_min or grams > grams_max:
                    raise ValidationError(
                        f"Los gramos de un alimento en el día {index} deben estar "
                        f"entre {grams_min:g} y {grams_max:g}."
                    )

        totals = day.get("totals")
        if not isinstance(totals, dict) or "kcal" not in totals:
            raise ValidationError(
                f"El día {index} debe incluir los totales diarios (kcal)."
            )


# ── Pure functions: dietary compliance & shopping list (Task 5.10) ───────────


def check_dietary_compliance(
    structure: list[dict], dietary: dict, foods: dict
) -> str | None:
    """PURE. Scan every item across all days/meals and return a Spanish error
    STRING on the FIRST dietary violation, or ``None`` when compliant (Req 7).

    ``foods`` maps a normalized food_name → dict ``{is_meat, is_animal,
    has_gluten, name}``. Rules:
      - vegetarian active + item food ``is_meat``   → error (Req 7.1)
      - vegan active + item food ``is_animal``      → error (Req 7.2)
      - gluten_free active + item food ``has_gluten`` → error (Req 7.3)
      - any declared allergen (``dietary['allergens']``) is a normalized substring
        of the item's food name → error (Req 7.4)

    Names are normalized (lowercase, accent-stripped) for matching. Unknown foods
    (not in ``foods``) only trigger the allergen-by-name check; missing flags
    default to ``False``.
    """
    dietary = dietary or {}
    vegetarian = bool(dietary.get("vegetarian"))
    vegan = bool(dietary.get("vegan"))
    gluten_free = bool(dietary.get("gluten_free"))
    raw_allergens = dietary.get("allergens") or []
    allergens = [
        _normalize_name(a) for a in raw_allergens if _normalize_name(a)
    ]

    # Normalize structure to a list of days.
    if isinstance(structure, dict):
        days = structure.get("days") or []
    else:
        days = structure or []

    for day in days:
        if not isinstance(day, dict):
            continue
        for meal in day.get("meals") or []:
            if not isinstance(meal, dict):
                continue
            for item in meal.get("items") or []:
                if not isinstance(item, dict):
                    continue
                raw_food_name = item.get("food_name", "")
                key = _normalize_name(raw_food_name)
                food = foods.get(key) if isinstance(foods, dict) else None

                if food:
                    if vegetarian and food.get("is_meat"):
                        return (
                            f"El plan incluye '{raw_food_name}', que es carne o "
                            f"pescado y no es apto para una dieta vegetariana."
                        )
                    if vegan and food.get("is_animal"):
                        return (
                            f"El plan incluye '{raw_food_name}', de origen animal, "
                            f"no apto para una dieta vegana."
                        )
                    if gluten_free and food.get("has_gluten"):
                        return (
                            f"El plan incluye '{raw_food_name}', que contiene "
                            f"gluten y no es apto para una dieta sin gluten."
                        )

                # Allergen check applies to all foods (known or unknown) by name.
                for allergen in allergens:
                    if allergen and allergen in key:
                        return (
                            f"El plan incluye '{raw_food_name}', que coincide con "
                            f"el alérgeno declarado '{allergen}'."
                        )

    return None


def compute_shopping_list(
    plan_structure: list[dict], inventory: dict
) -> list[dict]:
    """PURE (Req 13). Sum the required grams per food_name across the plan, then
    for each food compute the shortfall against the inventory:

        available = inventory.get(name, 0.0)   # missing/None quantity → 0
        missing   = required - available
        if missing > 0: include {food_name, grams: max(ceil(missing), 1)}
        else:           exclude

    Returns the list of missing items (possibly empty). Uses ``math.ceil``.
    """
    inventory = inventory or {}

    # Normalize structure to a list of days.
    if isinstance(plan_structure, dict):
        days = plan_structure.get("days") or []
    else:
        days = plan_structure or []

    # Sum required grams per food_name, preserving the first-seen display name.
    required: dict[str, float] = {}
    display_name: dict[str, str] = {}
    for day in days:
        if not isinstance(day, dict):
            continue
        for meal in day.get("meals") or []:
            if not isinstance(meal, dict):
                continue
            for item in meal.get("items") or []:
                if not isinstance(item, dict):
                    continue
                raw_name = item.get("food_name", "")
                key = _normalize_name(raw_name)
                if not key:
                    continue
                grams = item.get("grams")
                if not _is_number(grams):
                    continue
                required[key] = required.get(key, 0.0) + float(grams)
                display_name.setdefault(key, raw_name)

    # Build inventory lookup by normalized name (missing/None → 0).
    inv_available: dict[str, float] = {}
    for name, qty in inventory.items():
        key = _normalize_name(name)
        if not key:
            continue
        amount = float(qty) if _is_number(qty) else 0.0
        inv_available[key] = inv_available.get(key, 0.0) + amount

    result: list[dict] = []
    for key, needed in required.items():
        available = inv_available.get(key, 0.0)
        missing = needed - available
        if missing > 0:
            result.append(
                {
                    "food_name": display_name.get(key, key),
                    "grams": max(math.ceil(missing), 1),
                }
            )
    return result

# ── I/O functions: food catalog CRUD (Task 6.1) ──────────────────────────────
# Admin authorization is enforced at the router; these functions assume the
# caller is permitted. They follow the project convention: mutate + ``db.flush()``
# and let the ``get_db`` dependency issue the final commit (see fitness_service).
# "Validate before mutate": every check runs BEFORE any INSERT/UPDATE/DELETE so a
# failure leaves the catalog unchanged.

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.food import Food
from app.models.dietary_profile import DietaryProfile


def _food_fields(fields):
    """Extract the six nutrition fields from ``fields`` (a dict or an object).

    Returns the tuple ``(name, kcal, protein, fat, carbs, fiber)``. ``fiber`` may
    be ``None`` (optional). Accepts either mapping access (dict) or attribute
    access (e.g. a Pydantic model)."""
    def _get(key):
        if isinstance(fields, dict):
            return fields.get(key)
        return getattr(fields, key, None)

    return (
        _get("name"),
        _get("kcal"),
        _get("protein"),
        _get("fat"),
        _get("carbs"),
        _get("fiber"),
    )


async def _find_food_by_name(db: AsyncSession, name):
    """Return the ``Food`` whose normalized name matches ``name``, or ``None``.

    Matches case/accent-insensitively (via ``_normalize_name``) so "Pollo" and
    "pollo" collide, enforcing a stronger uniqueness than the DB's exact-unique
    index. Loads the whole catalog (small, global) and compares in Python."""
    target = _normalize_name(name)
    if not target:
        return None
    result = await db.execute(select(Food))
    for food in result.scalars().all():
        if _normalize_name(food.name) == target:
            return food
    return None


async def list_foods(db: AsyncSession) -> list[Food]:
    """Return every catalog food ordered by name (Req 1.7). Read-only."""
    result = await db.execute(select(Food).order_by(Food.name))
    return list(result.scalars().all())


async def create_food(
    db: AsyncSession, fields, is_meat, is_animal, has_gluten
) -> Food:
    """Create and persist a catalog ``Food`` (admin-only; Req 1.3, 1.5).

    ``fields`` carries ``name, kcal, protein, fat, carbs, fiber``. Steps, all
    BEFORE any mutation so the catalog is preserved on failure:
      1. ``validate_food_fields`` → ``ValidationError`` (Spanish) if invalid.
      2. Enforce the invariant ``is_meat ⇒ is_animal`` (meat is always animal).
      3. Reject a duplicate name (normalized match) → ``ValidationError`` (Spanish),
         nothing inserted.
    On success, insert the food and return it."""
    name, kcal, protein, fat, carbs, fiber = _food_fields(fields)

    # 1. Validate the nutrition fields first (raises on invalid, no mutation).
    validate_food_fields(name, kcal, protein, fat, carbs, fiber)

    # 2. Invariant: meat/fish is always of animal origin.
    is_meat = bool(is_meat)
    is_animal = bool(is_animal) or is_meat
    has_gluten = bool(has_gluten)

    # 3. Unique name (normalized) — preserve the catalog on duplicate.
    existing = await _find_food_by_name(db, name)
    if existing is not None:
        raise ValidationError(
            f"Ya existe un alimento con el nombre '{name}'."
        )

    food = Food(
        name=name.strip() if isinstance(name, str) else name,
        kcal_per_100g=float(kcal),
        protein_g_per_100g=float(protein),
        fat_g_per_100g=float(fat),
        carbs_g_per_100g=float(carbs),
        fiber_g_per_100g=(float(fiber) if fiber is not None else None),
        is_meat=is_meat,
        is_animal=is_animal,
        has_gluten=has_gluten,
    )
    db.add(food)
    await db.flush()
    return food


async def update_food(
    db: AsyncSession, food_id, fields, is_meat, is_animal, has_gluten
) -> Food:
    """Update an existing catalog ``Food`` in place (admin-only; Req 1.3, 1.5).

    Loads by ``food_id`` (not found → ``ValidationError`` Spanish). Validates the
    new values, enforces ``is_meat ⇒ is_animal``, and keeps the name unique: if the
    new name collides with a DIFFERENT food, raise ``ValidationError`` (Spanish)
    and preserve the catalog (no field is mutated before every check passes)."""
    name, kcal, protein, fat, carbs, fiber = _food_fields(fields)

    food = await db.get(Food, food_id)
    if food is None:
        raise ValidationError(
            f"No se encontró el alimento con id {food_id}."
        )

    # 1. Validate the new values first.
    validate_food_fields(name, kcal, protein, fat, carbs, fiber)

    # 2. Invariant.
    is_meat = bool(is_meat)
    is_animal = bool(is_animal) or is_meat
    has_gluten = bool(has_gluten)

    # 3. Unique name — a collision with ANOTHER food is rejected (preserve).
    existing = await _find_food_by_name(db, name)
    if existing is not None and existing.id != food.id:
        raise ValidationError(
            f"Ya existe otro alimento con el nombre '{name}'."
        )

    # All checks passed → mutate.
    food.name = name.strip() if isinstance(name, str) else name
    food.kcal_per_100g = float(kcal)
    food.protein_g_per_100g = float(protein)
    food.fat_g_per_100g = float(fat)
    food.carbs_g_per_100g = float(carbs)
    food.fiber_g_per_100g = float(fiber) if fiber is not None else None
    food.is_meat = is_meat
    food.is_animal = is_animal
    food.has_gluten = has_gluten
    await db.flush()
    return food


async def delete_food(db: AsyncSession, food_id) -> None:
    """Delete a catalog ``Food`` by id (admin-only; Req 1).

    Not found → ``ValidationError`` (Spanish). If inventory rows reference the
    food, the FK prevents deletion; that ``IntegrityError`` is surfaced as a
    ``ValidationError`` with a Spanish message and the catalog is preserved."""
    food = await db.get(Food, food_id)
    if food is None:
        raise ValidationError(
            f"No se encontró el alimento con id {food_id}."
        )

    await db.delete(food)
    try:
        await db.flush()
    except IntegrityError:
        # Referenced by inventory (or another FK) — cannot delete. Roll back the
        # pending delete so the catalog stays intact, then report in Spanish.
        await db.rollback()
        raise ValidationError(
            f"No se puede eliminar el alimento '{food.name}' porque está en uso "
            f"en el inventario de uno o más usuarios."
        )


# ── I/O functions: dietary profile (Task 6.4) ─────────────────────────────────
# Full-replace semantics with "validate before mutate": allergens are validated
# and deduplicated BEFORE the profile is created or updated, so an invalid input
# leaves any previous profile untouched (Req 3.3).


def _validate_and_dedup_allergens(allergens) -> list[str]:
    """Validate and deduplicate a list of allergen strings (Req 3.2).

    Each allergen must be a string whose (trimmed) length is within
    ``ALLERGEN_LEN`` (1..50); otherwise raise ``ValidationError`` (Spanish).
    Deduplication is case/accent-insensitive (via ``_normalize_name``) while the
    trimmed ORIGINAL spelling of the first occurrence is preserved. Returns the
    deduplicated list. Runs entirely before any mutation (preserves prior state)."""
    if allergens is None:
        return []
    if not isinstance(allergens, (list, tuple)):
        raise ValidationError(
            "Los alérgenos deben enviarse como una lista de textos."
        )

    low, high = ALLERGEN_LEN
    result: list[str] = []
    seen: set[str] = set()
    for raw in allergens:
        if not isinstance(raw, str):
            raise ValidationError(
                "Cada alérgeno debe ser un texto."
            )
        trimmed = raw.strip()
        if len(trimmed) < low or len(trimmed) > high:
            raise ValidationError(
                f"Cada alérgeno debe tener entre {low} y {high} caracteres: "
                f"'{raw}' no es válido."
            )
        key = _normalize_name(trimmed)
        if key in seen:
            continue
        seen.add(key)
        result.append(trimmed)
    return result


async def get_dietary(db: AsyncSession, user_id) -> dict:
    """Return the user's dietary profile as a dict (Req 3.6).

    When no profile exists, return the "no restrictions" default:
    ``{"vegetarian": False, "vegan": False, "gluten_free": False, "allergens": []}``.
    When present, return the flags plus ``allergens`` via ``allergen_list()``."""
    result = await db.execute(
        select(DietaryProfile).where(DietaryProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        return {
            "vegetarian": False,
            "vegan": False,
            "gluten_free": False,
            "allergens": [],
        }
    return {
        "vegetarian": bool(profile.vegetarian),
        "vegan": bool(profile.vegan),
        "gluten_free": bool(profile.gluten_free),
        "allergens": profile.allergen_list(),
    }


async def set_dietary(
    db: AsyncSession, user_id, vegetarian, vegan, gluten_free, allergens
) -> DietaryProfile:
    """Upsert the user's dietary profile with full-replace semantics (Req 3.1-3.4).

    Validates and deduplicates ``allergens`` FIRST; on any invalid allergen raise
    ``ValidationError`` (Spanish) without mutating the previous profile (Req 3.3).
    Then fully REPLACE the prior flags and allergens (Req 3.4): update the existing
    profile if present, otherwise create one. Allergens are stored as a JSON string
    (``json.dumps(..., ensure_ascii=False)``). Returns the persisted profile."""
    import json

    # 1. Validate + dedup before touching any state (preserves previous profile).
    cleaned = _validate_and_dedup_allergens(allergens)
    allergens_json = json.dumps(cleaned, ensure_ascii=False)

    vegetarian = bool(vegetarian)
    vegan = bool(vegan)
    gluten_free = bool(gluten_free)

    # 2. Upsert: full replace of flags + allergens.
    result = await db.execute(
        select(DietaryProfile).where(DietaryProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = DietaryProfile(
            user_id=user_id,
            vegetarian=vegetarian,
            vegan=vegan,
            gluten_free=gluten_free,
            allergens=allergens_json,
        )
        db.add(profile)
    else:
        profile.vegetarian = vegetarian
        profile.vegan = vegan
        profile.gluten_free = gluten_free
        profile.allergens = allergens_json

    await db.flush()
    return profile


# ── I/O functions: user inventory (Task 6.2) ─────────────────────────────────
# "Validate before mutate": grams and (for unknown foods) nutrition fields are
# validated BEFORE any INSERT/UPDATE, so a failure leaves the inventory and the
# catalog untouched. Mutations use ``db.add(...)`` + ``await db.flush()`` and let
# the ``get_db`` dependency issue the final commit (same as the Food/dietary
# functions above).

from app.models.user_food_inventory import UserFoodInventory
from app.models.nutrition_targets import NutritionTargets
from app.services import fitness_link


async def add_inventory(
    db: AsyncSession, user_id, food_name, quantity_grams, new_food_fields=None
) -> UserFoodInventory:
    """Add (or update) a food in the user's inventory (Req 2.1-2.4).

    Steps, all validated BEFORE any mutation so a failure preserves the inventory
    and the catalog:
      1. If ``quantity_grams`` is not ``None``, it must be a number within
         ``INVENTORY_GRAMS_RANGE`` (1..100000); otherwise raise ``ValidationError``
         (Spanish). ``None`` is allowed (the model column is nullable).
      2. Look up the ``Food`` by name (normalized). If it exists, use it.
      3. If it does NOT exist, ``new_food_fields`` is required (a dict with
         ``name/kcal/protein/fat/carbs/fiber`` and optionally
         ``is_meat/is_animal/has_gluten``). Missing → ``ValidationError`` (Spanish)
         telling the user the food is unknown and needs nutrition data. Otherwise
         validate the fields, enforce ``is_meat ⇒ is_animal``, and create the Food.
      4. Upsert the inventory row deduplicated by ``(user_id, food_id)``: update the
         existing row's ``quantity_grams`` or insert a new one (Req 2.1, 2.2).
    Returns the persisted ``UserFoodInventory`` row.
    """
    # 1. Validate grams first (None is allowed; the column is nullable).
    if quantity_grams is not None:
        grams_min, grams_max = INVENTORY_GRAMS_RANGE
        if (
            not _is_number(quantity_grams)
            or quantity_grams < grams_min
            or quantity_grams > grams_max
        ):
            raise ValidationError(
                f"La cantidad en gramos debe estar entre {grams_min:g} y "
                f"{grams_max:g}."
            )

    # 2. Resolve the food from the catalog (normalized match).
    food = await _find_food_by_name(db, food_name)

    # 3. Unknown food → require and validate nutrition data, then create it.
    if food is None:
        if new_food_fields is None:
            raise ValidationError(
                f"El alimento '{food_name}' no está en el catálogo. Debes "
                f"proporcionar sus datos nutricionales (calorías y macros por "
                f"100 g) para agregarlo."
            )

        name, kcal, protein, fat, carbs, fiber = _food_fields(new_food_fields)
        # Prefer the explicit food_name when the fields omit a name.
        if not (isinstance(name, str) and name.strip()):
            name = food_name

        # Validate before mutating (raises on invalid, preserving state).
        validate_food_fields(name, kcal, protein, fat, carbs, fiber)

        def _flag(key):
            if isinstance(new_food_fields, dict):
                return new_food_fields.get(key)
            return getattr(new_food_fields, key, None)

        is_meat = bool(_flag("is_meat"))
        is_animal = bool(_flag("is_animal")) or is_meat  # invariant: meat ⇒ animal
        has_gluten = bool(_flag("has_gluten"))

        food = Food(
            name=name.strip() if isinstance(name, str) else name,
            kcal_per_100g=float(kcal),
            protein_g_per_100g=float(protein),
            fat_g_per_100g=float(fat),
            carbs_g_per_100g=float(carbs),
            fiber_g_per_100g=(float(fiber) if fiber is not None else None),
            is_meat=is_meat,
            is_animal=is_animal,
            has_gluten=has_gluten,
        )
        db.add(food)
        # Flush so the new food gets an id for the inventory FK below.
        await db.flush()

    # 4. Upsert the inventory row, deduplicated by (user_id, food_id).
    result = await db.execute(
        select(UserFoodInventory).where(
            UserFoodInventory.user_id == user_id,
            UserFoodInventory.food_id == food.id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        entry = UserFoodInventory(
            user_id=user_id,
            food_id=food.id,
            quantity_grams=(
                float(quantity_grams) if quantity_grams is not None else None
            ),
        )
        db.add(entry)
    else:
        # Deduplicated: keep the single row and store the latest quantity.
        entry.quantity_grams = (
            float(quantity_grams) if quantity_grams is not None else None
        )

    await db.flush()
    return entry


async def remove_inventory(db: AsyncSession, user_id, food_id) -> None:
    """Remove a food from the user's inventory (Req 2.5).

    Deletes the inventory row for ``(user_id, food_id)`` if present. The catalog
    ``Food`` entry is KEPT (only the user's inventory link is removed). When no such
    row exists this is an idempotent no-op."""
    result = await db.execute(
        select(UserFoodInventory).where(
            UserFoodInventory.user_id == user_id,
            UserFoodInventory.food_id == food_id,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return  # No-op: nothing to remove (Food catalog stays intact).

    await db.delete(entry)
    await db.flush()


async def get_inventory(db: AsyncSession, user_id) -> list[dict]:
    """Return the user's inventory as a list of dicts (Req 2.6).

    Each item is ``{"food_id": int, "food_name": str, "grams": float | None}`` where
    ``grams`` is the stored ``quantity_grams`` (which may be ``None``). Joins the
    ``Food`` catalog to resolve the display name. Read-only."""
    result = await db.execute(
        select(UserFoodInventory, Food)
        .join(Food, UserFoodInventory.food_id == Food.id)
        .where(UserFoodInventory.user_id == user_id)
        .order_by(Food.name)
    )
    items: list[dict] = []
    for entry, food in result.all():
        items.append(
            {
                "food_id": entry.food_id,
                "food_name": food.name,
                "grams": entry.quantity_grams,
            }
        )
    return items


# ── I/O functions: nutrition targets (Task 7.1) ──────────────────────────────
# Manual targets are validated before mutating (preserving any previous targets);
# derived targets are RECOMPUTED on each call from the current fitness view (Req
# 8.3). Both upsert the single 1:1 ``NutritionTargets`` row, fully replacing any
# prior targets regardless of source. Mutations use ``db.flush()`` and defer commit
# to ``get_db``.


async def get_targets(db: AsyncSession, user_id) -> NutritionTargets | None:
    """Return the user's ``NutritionTargets`` row, or ``None`` if unset (Req 5.4).
    Read-only."""
    result = await db.execute(
        select(NutritionTargets).where(NutritionTargets.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _upsert_targets(
    db: AsyncSession, user_id, kcal, protein_g, fat_g, carbs_g, source
) -> NutritionTargets:
    """Internal: create or fully replace the user's 1:1 ``NutritionTargets`` row
    with the given values and ``source``. Assumes the values are already valid.
    Callers run all validation BEFORE invoking this, so the previous targets are
    preserved on any validation failure."""
    result = await db.execute(
        select(NutritionTargets).where(NutritionTargets.user_id == user_id)
    )
    targets = result.scalar_one_or_none()
    if targets is None:
        targets = NutritionTargets(
            user_id=user_id,
            kcal=float(kcal),
            protein_g=float(protein_g),
            fat_g=float(fat_g),
            carbs_g=float(carbs_g),
            source=source,
        )
        db.add(targets)
    else:
        # Full replace of any prior targets (derived or manual).
        targets.kcal = float(kcal)
        targets.protein_g = float(protein_g)
        targets.fat_g = float(fat_g)
        targets.carbs_g = float(carbs_g)
        targets.source = source

    await db.flush()
    return targets


async def set_manual_targets(
    db: AsyncSession, user_id, kcal, protein_g, fat_g, carbs_g
) -> NutritionTargets:
    """Store manually entered nutrition targets (Req 5.1, 5.3).

    ``validate_manual_targets`` runs FIRST; on any out-of-range value it raises
    ``ValidationError`` (Spanish) without mutating, so any previous targets are
    preserved. On success, upsert with ``source='manual'``, REPLACING any prior
    targets (derived or manual). Returns the persisted row."""
    # Validate before mutate (raises on invalid, preserving previous targets).
    validate_manual_targets(kcal, protein_g, fat_g, carbs_g)
    return await _upsert_targets(
        db, user_id, kcal, protein_g, fat_g, carbs_g, source="manual"
    )


async def derive_targets(db: AsyncSession, user_id) -> NutritionTargets:
    """Derive nutrition targets from the user's fitness profile (Req 4.1, 8.3, 8.5).

    Reads the fitness view via ``fitness_link.get_fitness_view``. When no view is
    available (fitness-coach absent or no profile) raise ``GoalRequiredError``
    (Spanish) guiding the user to complete their fitness profile or enter manual
    targets (Req 4.6, 8.5). Otherwise compute the target rate and the pure
    ``derive_nutrition_targets``; if the body data is insufficient, surface the same
    ``GoalRequiredError`` guidance. Upsert with ``source='derived'``, RECOMPUTING on
    each call (Req 8.3) and replacing any prior targets. Returns the persisted row."""
    view = await fitness_link.get_fitness_view(db, user_id)
    if view is None:
        raise GoalRequiredError(
            "No se encontró tu perfil de fitness para derivar las metas "
            "nutricionales. Completa tu perfil en el Fitness Coach o ingresa "
            "metas manuales."
        )

    target_rate = fitness_link.compute_target_rate_for_view(view)

    try:
        derived = derive_nutrition_targets(view, target_rate)
    except ValidationError as exc:
        # Body data missing/insufficient → guide the user (complete profile / manual).
        raise GoalRequiredError(
            "Faltan datos corporales para derivar tus metas nutricionales "
            f"({exc}). Completa tu perfil en el Fitness Coach o ingresa metas "
            "manuales."
        )

    return await _upsert_targets(
        db,
        user_id,
        derived["kcal"],
        derived["protein_g"],
        derived["fat_g"],
        derived["carbs_g"],
        source="derived",
    )

# ── I/O functions: plan generation (Task 9.1) ────────────────────────────────
# "Validate before mutate": the LLM call, structure validation, calorie
# tolerance, and dietary compliance ALL run BEFORE any INSERT/UPDATE. Because the
# only DB writes in generate_meal_plan happen at the very end (on success), any
# failure leaves the previous active plan, inventory, dietary profile and targets
# untouched (Req 9.4). Mutations use ``db.flush()`` and defer commit to ``get_db``.

import json

from app.models.meal_plan import MealPlan


def _target_kcal(targets) -> float | None:
    """Read the target kcal from either a ``NutritionTargets`` ORM object (has
    ``.kcal``) or a plain dict (``targets['kcal']``). Returns ``None`` when the
    value is absent/non-numeric."""
    if targets is None:
        return None
    if isinstance(targets, dict):
        value = targets.get("kcal")
    else:
        value = getattr(targets, "kcal", None)
    return float(value) if _is_number(value) else None


def _targets_macros(targets):
    """Read (protein_g, fat_g, carbs_g) from a ``NutritionTargets`` ORM object or
    a dict. Each value may be ``None`` when absent."""
    def _get(key):
        if isinstance(targets, dict):
            return targets.get(key)
        return getattr(targets, key, None)

    return _get("protein_g"), _get("fat_g"), _get("carbs_g")


def build_meal_prompt(inventory, targets, dietary) -> str:
    """PURE. Build the Spanish USER prompt for the meal-plan LLM call (Req 6.1, 6.6).

    Composes a plain Spanish string (never ``str.format`` — the system prompt holds
    literal JSON braces and lives in ``llm_service``) describing:
      - the user's inventory (each food ``name`` + grams, or "sin cantidad
        especificada" when grams is ``None``), instructing the model to PRIORITIZE
        these foods,
      - the daily targets (``kcal`` + ``protein_g``/``fat_g``/``carbs_g``),
      - the active dietary restrictions (which of vegetarian/vegan/gluten_free are
        on) and the declared allergen list.

    ``targets`` may be a ``NutritionTargets`` ORM object or a dict; ``inventory`` is
    the ``list[dict]`` from ``get_inventory``; ``dietary`` is the dict from
    ``get_dietary``. Returns the composed prompt string.
    """
    lines: list[str] = []
    lines.append(
        "Genera un plan de comidas semanal (7 días) para el usuario, "
        "priorizando los alimentos que ya tiene disponibles en su inventario."
    )

    # ── Inventory ──
    lines.append("")
    lines.append("Inventario disponible (prioriza estos alimentos):")
    inventory = inventory or []
    if not inventory:
        lines.append("- (sin alimentos en el inventario)")
    else:
        for item in inventory:
            if isinstance(item, dict):
                name = item.get("food_name") or item.get("name") or "alimento"
                grams = item.get("grams")
            else:
                name = getattr(item, "food_name", None) or "alimento"
                grams = getattr(item, "grams", None)
            if _is_number(grams):
                lines.append(f"- {name}: {float(grams):g} g")
            else:
                lines.append(f"- {name}: sin cantidad especificada")

    # ── Targets ──
    target_kcal = _target_kcal(targets)
    protein_g, fat_g, carbs_g = _targets_macros(targets)
    lines.append("")
    lines.append("Metas nutricionales diarias (aproxima cada día, ±10 %):")
    lines.append(
        f"- Calorías: {target_kcal:g} kcal"
        if target_kcal is not None
        else "- Calorías: no especificadas"
    )
    lines.append(
        f"- Proteínas: {float(protein_g):g} g"
        if _is_number(protein_g)
        else "- Proteínas: no especificadas"
    )
    lines.append(
        f"- Grasas: {float(fat_g):g} g"
        if _is_number(fat_g)
        else "- Grasas: no especificadas"
    )
    lines.append(
        f"- Carbohidratos: {float(carbs_g):g} g"
        if _is_number(carbs_g)
        else "- Carbohidratos: no especificados"
    )

    # ── Dietary restrictions ──
    dietary = dietary or {}
    active_flags: list[str] = []
    if dietary.get("vegetarian"):
        active_flags.append("vegetariana (sin carne ni pescado)")
    if dietary.get("vegan"):
        active_flags.append("vegana (sin ningún producto de origen animal)")
    if dietary.get("gluten_free"):
        active_flags.append("sin gluten")

    allergens = [a for a in (dietary.get("allergens") or []) if isinstance(a, str) and a.strip()]

    lines.append("")
    lines.append("Restricciones dietéticas (respétalas estrictamente):")
    if active_flags:
        lines.append("- Dieta: " + ", ".join(active_flags))
    else:
        lines.append("- Dieta: sin restricciones especiales")
    if allergens:
        lines.append("- Alérgenos a EVITAR: " + ", ".join(allergens))
    else:
        lines.append("- Alérgenos a evitar: ninguno declarado")

    lines.append("")
    lines.append(
        "Recuerda: prioriza el inventario, respeta las metas y las restricciones, "
        "y calcula los totales diarios de kcal y macros. Nombres de alimentos en "
        "español."
    )

    return "\n".join(lines)


async def generate_meal_plan(db: AsyncSession, user_id, overrides: dict | None = None) -> MealPlan:
    """Generate, validate and persist a weekly meal plan for the user (Req 6, 7, 9).

    Flow (all validation BEFORE any DB write, so failure preserves prior state —
    Req 9.4):
      1. Resolve targets: ``get_targets``; if absent, try ``derive_targets`` (which
         reads the fitness view — the Telegram ``goal_type`` override, if any, is
         already honored by ``derive_targets`` via the fitness profile). If deriving
         also fails (no fitness view) → ``GoalRequiredError`` (Spanish) (Req 6.9, 5.5).
      2. ``get_inventory``; empty → ``ValidationError`` (Spanish) asking the user to
         add foods first (Req 6.10).
      3. ``get_dietary`` (absent → no restrictions, Req 3.6).
      4. Build the prompt and call the LLM (120 s timeout — the free model is slow).
         ``None`` → ``LLMError`` (Spanish, ``kind='error'``, offer retry) (Req 9.1-9.3).
      5. ``validate_plan_structure``; a ``ValidationError`` becomes an
         ``LLMError(kind='parse')`` (Spanish, offer regenerate).
      6. Per day: ``check_calorie_tolerance`` vs the target kcal; any day out of
         ±10 % → ``ToleranceError`` (Spanish, naming the day, offer regenerate)
         (Req 6.7, 6.8).
      7. ``check_dietary_compliance`` vs the ``Food`` flags + allergens; non-``None``
         → ``DietaryError`` (already Spanish) (Req 7).
      8. On success only: deactivate the user's previous active plan(s) and insert a
         new active ``MealPlan`` whose ``structure`` is the JSON-encoded day list so
         ``structure_list()`` yields the 7-day list (Req 6.2, 6.11). Returns it.
    """
    # 1. Resolve targets (manual first, then derive from the fitness view).
    targets = await get_targets(db, user_id)
    if targets is None:
        try:
            targets = await derive_targets(db, user_id)
        except GoalRequiredError:
            # No manual targets and no fitness view to derive from → guide the user.
            raise GoalRequiredError(
                "Necesitas metas nutricionales para generar un plan de comidas. "
                "Ingresa metas manuales o completa tu perfil en el Fitness Coach "
                "para derivarlas automáticamente."
            )

    # 2. Inventory must not be empty.
    inventory = await get_inventory(db, user_id)
    if not inventory:
        raise ValidationError(
            "Tu inventario está vacío. Agrega primero los alimentos que tienes "
            "disponibles para poder generar un plan de comidas."
        )

    # 3. Dietary profile (absent → no restrictions).
    dietary = await get_dietary(db, user_id)

    # 4. Build the prompt and call the LLM (120 s — the free model is slow).
    # Lazy import to avoid a circular import at module load; aliased so it
    # does not shadow this function.
    from app.services.llm_service import generate_meal_plan as llm_generate_meal_plan

    prompt = build_meal_prompt(inventory, targets, dietary)
    parsed = await llm_generate_meal_plan(prompt, timeout_seconds=120.0)
    if parsed is None:
        raise LLMError(
            "No pude generar el plan de comidas en este momento (el servicio no "
            "respondió o falló). Vuelve a intentarlo en unos minutos.",
            kind="error",
        )

    # 5. Validate the structure; a parse/shape error is an LLM parse failure.
    try:
        validate_plan_structure(parsed)
    except ValidationError as exc:
        raise LLMError(
            "El plan generado no tiene un formato válido "
            f"({exc}). Intenta regenerarlo.",
            kind="parse",
        )

    # Normalize to the list of day dicts.
    days = parsed["days"] if isinstance(parsed, dict) else parsed

    # 6. Calorie tolerance per day (±10 % of the target kcal).
    target_kcal = _target_kcal(targets)
    if target_kcal is None:
        raise GoalRequiredError(
            "No se pudo determinar tu objetivo calórico diario. Ingresa metas "
            "manuales o completa tu perfil en el Fitness Coach."
        )
    for index, day in enumerate(days, start=1):
        day_label = day.get("day") if isinstance(day, dict) else None
        day_name = day_label if isinstance(day_label, str) and day_label.strip() else f"día {index}"
        totals = day.get("totals") if isinstance(day, dict) else None
        if not check_calorie_tolerance(totals or {}, target_kcal):
            raise ToleranceError(
                f"El plan generado se sale del margen de calorías permitido (±10 %) "
                f"en {day_name}. Intenta regenerarlo."
            )

    # 7. Dietary compliance vs the Food catalog flags + declared allergens.
    foods_by_name: dict[str, dict] = {}
    all_foods = await list_foods(db)
    for food in all_foods:
        foods_by_name[_normalize_name(food.name)] = {
            "is_meat": bool(food.is_meat),
            "is_animal": bool(food.is_animal),
            "has_gluten": bool(food.has_gluten),
            "name": food.name,
        }
    err = check_dietary_compliance(days, dietary, foods_by_name)
    if err is not None:
        raise DietaryError(err)

    # 8. All validation passed → persist. Deactivate any previous active plan(s),
    #    then insert the new active plan. This is the FIRST and ONLY mutation.
    result = await db.execute(
        select(MealPlan).where(
            MealPlan.user_id == user_id,
            MealPlan.active == True,  # noqa: E712 (SQL boolean comparison)
        )
    )
    for previous in result.scalars().all():
        previous.active = False

    plan = MealPlan(
        user_id=user_id,
        structure=json.dumps(days, ensure_ascii=False),
        active=True,
    )
    db.add(plan)
    await db.flush()
    return plan


# ── I/O functions: active plan & shopping list (Task 9.2) ─────────────────────


async def get_active_plan(db: AsyncSession, user_id) -> MealPlan | None:
    """Return the user's active ``MealPlan`` (``active == True``), or ``None`` when
    there is none (Req 6.12, 6.13). If more than one is somehow active, return the
    most recent (``created_at`` descending). Read-only."""
    result = await db.execute(
        select(MealPlan)
        .where(
            MealPlan.user_id == user_id,
            MealPlan.active == True,  # noqa: E712 (SQL boolean comparison)
        )
        .order_by(MealPlan.created_at.desc())
    )
    return result.scalars().first()


async def get_shopping_list(db: AsyncSession, user_id) -> list[dict]:
    """Compute the shopping list from the active plan and the inventory (Req 13.1, 13.4).

    Loads the active ``MealPlan``; when there is none raise ``ShoppingRequiresPlanError``
    (Spanish) telling the user to generate a plan first (Req 13.4). Builds the
    inventory map ``name -> grams`` (missing/``None`` quantity → ``0.0``) and delegates
    to the pure ``compute_shopping_list``. Returns the list of missing items."""
    plan = await get_active_plan(db, user_id)
    if plan is None:
        raise ShoppingRequiresPlanError(
            "No tienes un plan de comidas activo. Genera un plan primero para "
            "obtener tu lista de compras."
        )

    inventory = await get_inventory(db, user_id)
    inventory_map: dict[str, float] = {}
    for item in inventory:
        name = item.get("food_name")
        if not name:
            continue
        grams = item.get("grams")
        inventory_map[name] = float(grams) if _is_number(grams) else 0.0

    return compute_shopping_list(plan.structure_list(), inventory_map)

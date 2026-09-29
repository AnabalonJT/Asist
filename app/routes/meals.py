"""Meal Planner API routes (prefix /api/meals set in main.py).

All endpoints require an Authenticated_User via ``get_current_user`` and scope
every query to ``current_user.id`` (Req 12.1-12.4). Writing the global ``Food``
catalog (create/update/delete) additionally requires an admin via
``get_current_admin`` (Req 1.6, 12.5). Internal service exceptions are translated
to ``HTTPException`` with Spanish ``detail`` messages, following the Error Handling
table of the design. Plan and targets responses always include the Spanish meal
disclaimer (Req 4.7, 12.6).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_user, get_current_admin
from app.models.food import Food
from app.models.user import User
from app.services import meal_service
from app.services.meal_service import (
    MEAL_DISCLAIMER,
    DietaryError,
    GoalRequiredError,
    LLMError,
    ShoppingRequiresPlanError,
    ToleranceError,
    ValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────
class FoodIn(BaseModel):
    name: str
    kcal: float
    protein: float
    fat: float
    carbs: float
    fiber: float | None = None
    is_meat: bool = False
    is_animal: bool = False
    has_gluten: bool = False


class FoodOut(BaseModel):
    id: int
    name: str
    kcal: float
    protein: float
    fat: float
    carbs: float
    fiber: float | None
    is_meat: bool
    is_animal: bool
    has_gluten: bool

    @classmethod
    def from_model(cls, f: Food) -> "FoodOut":
        return cls(
            id=f.id,
            name=f.name,
            kcal=f.kcal_per_100g,
            protein=f.protein_g_per_100g,
            fat=f.fat_g_per_100g,
            carbs=f.carbs_g_per_100g,
            fiber=f.fiber_g_per_100g,
            is_meat=f.is_meat,
            is_animal=f.is_animal,
            has_gluten=f.has_gluten,
        )


class InventoryIn(BaseModel):
    food_name: str
    quantity_grams: float | None = None
    # Optional nutrition data used to create an unknown food on the fly (Req 2.3).
    new_food: FoodIn | None = None


class InventoryOut(BaseModel):
    food_id: int
    food_name: str
    grams: float | None


class DietaryIn(BaseModel):
    vegetarian: bool = False
    vegan: bool = False
    gluten_free: bool = False
    allergens: list[str] = []


class DietaryOut(BaseModel):
    vegetarian: bool
    vegan: bool
    gluten_free: bool
    allergens: list[str]


class TargetsIn(BaseModel):
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float


class TargetsOut(BaseModel):
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    source: str
    disclaimer: str


class MealPlanOut(BaseModel):
    id: int
    structure: list
    disclaimer: str


class ShoppingItemOut(BaseModel):
    food_name: str
    grams: int


# ── Food catalog (Req 1) ─────────────────────────────────────────────────────
@router.get("/foods", response_model=list[FoodOut])
async def list_foods(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    foods = await meal_service.list_foods(db)
    return [FoodOut.from_model(f) for f in foods]


@router.post("/foods", response_model=FoodOut)
async def create_food(
    body: FoodIn,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    fields = {
        "name": body.name,
        "kcal": body.kcal,
        "protein": body.protein,
        "fat": body.fat,
        "carbs": body.carbs,
        "fiber": body.fiber,
    }
    try:
        food = await meal_service.create_food(
            db,
            fields=fields,
            is_meat=body.is_meat,
            is_animal=body.is_animal,
            has_gluten=body.has_gluten,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return FoodOut.from_model(food)


@router.put("/foods/{food_id}", response_model=FoodOut)
async def update_food(
    food_id: int,
    body: FoodIn,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    fields = {
        "name": body.name,
        "kcal": body.kcal,
        "protein": body.protein,
        "fat": body.fat,
        "carbs": body.carbs,
        "fiber": body.fiber,
    }
    try:
        food = await meal_service.update_food(
            db,
            food_id,
            fields=fields,
            is_meat=body.is_meat,
            is_animal=body.is_animal,
            has_gluten=body.has_gluten,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return FoodOut.from_model(food)


@router.delete("/foods/{food_id}")
async def delete_food(
    food_id: int,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await meal_service.delete_food(db, food_id)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"message": "Alimento eliminado del catálogo."}


# ── Inventory (Req 2) ────────────────────────────────────────────────────────
@router.get("/inventory", response_model=list[InventoryOut])
async def get_inventory(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await meal_service.get_inventory(db, current_user.id)
    return [
        InventoryOut(
            food_id=item["food_id"],
            food_name=item["food_name"],
            grams=item["grams"],
        )
        for item in items
    ]


@router.post("/inventory", response_model=InventoryOut)
async def add_inventory(
    body: InventoryIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        entry = await meal_service.add_inventory(
            db,
            current_user.id,
            body.food_name,
            body.quantity_grams,
            new_food_fields=(body.new_food.model_dump() if body.new_food else None),
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Resolve the food name for the response (the entry only stores the FK).
    food = await db.get(Food, entry.food_id)
    return InventoryOut(
        food_id=entry.food_id,
        food_name=food.name if food else body.food_name,
        grams=entry.quantity_grams,
    )


@router.delete("/inventory/{food_id}")
async def remove_inventory(
    food_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await meal_service.remove_inventory(db, current_user.id, food_id)
    return {"message": "Alimento eliminado de tu inventario."}


# ── Dietary profile (Req 3) ──────────────────────────────────────────────────
@router.get("/dietary", response_model=DietaryOut)
async def get_dietary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await meal_service.get_dietary(db, current_user.id)
    return DietaryOut(**data)


@router.put("/dietary", response_model=DietaryOut)
async def set_dietary(
    body: DietaryIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await meal_service.set_dietary(
            db,
            current_user.id,
            vegetarian=body.vegetarian,
            vegan=body.vegan,
            gluten_free=body.gluten_free,
            allergens=body.allergens,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    data = await meal_service.get_dietary(db, current_user.id)
    return DietaryOut(**data)


# ── Nutrition targets (Req 4, 5) ─────────────────────────────────────────────
@router.get("/targets")
async def get_targets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    targets = await meal_service.get_targets(db, current_user.id)
    if targets is None:
        return {
            "message": "No tienes metas nutricionales definidas todavía.",
            "disclaimer": MEAL_DISCLAIMER,
        }
    return TargetsOut(
        kcal=targets.kcal,
        protein_g=targets.protein_g,
        fat_g=targets.fat_g,
        carbs_g=targets.carbs_g,
        source=targets.source,
        disclaimer=MEAL_DISCLAIMER,
    )


@router.put("/targets", response_model=TargetsOut)
async def set_targets(
    body: TargetsIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        targets = await meal_service.set_manual_targets(
            db,
            current_user.id,
            kcal=body.kcal,
            protein_g=body.protein_g,
            fat_g=body.fat_g,
            carbs_g=body.carbs_g,
        )
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return TargetsOut(
        kcal=targets.kcal,
        protein_g=targets.protein_g,
        fat_g=targets.fat_g,
        carbs_g=targets.carbs_g,
        source=targets.source,
        disclaimer=MEAL_DISCLAIMER,
    )


@router.post("/targets/derive", response_model=TargetsOut)
async def derive_targets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        targets = await meal_service.derive_targets(db, current_user.id)
    except GoalRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return TargetsOut(
        kcal=targets.kcal,
        protein_g=targets.protein_g,
        fat_g=targets.fat_g,
        carbs_g=targets.carbs_g,
        source=targets.source,
        disclaimer=MEAL_DISCLAIMER,
    )


# ── Plan generation & active plan (Req 6, 7, 9) ──────────────────────────────
@router.post("/plan/generate", response_model=MealPlanOut)
async def generate_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await meal_service.generate_meal_plan(db, current_user.id)
    except GoalRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ToleranceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except DietaryError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LLMError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception:
        # Defense in depth: never surface a raw 500. Any unexpected failure during
        # plan generation becomes a friendly retryable error in Spanish. Placed
        # AFTER the specific handlers so business errors keep their proper status.
        logger.exception(
            "Unexpected error generating meal plan for user_id=%s", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No pudimos generar tu plan de comidas en este momento. "
            "Intenta de nuevo.",
        )

    return MealPlanOut(
        id=plan.id,
        structure=plan.structure_list(),
        disclaimer=MEAL_DISCLAIMER,
    )


@router.get("/plan")
async def get_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await meal_service.get_active_plan(db, current_user.id)
    if plan is None:
        return {"message": "No tienes un plan activo. Puedes generar uno."}
    return MealPlanOut(
        id=plan.id,
        structure=plan.structure_list(),
        disclaimer=MEAL_DISCLAIMER,
    )


# ── Shopping list (Req 13) ───────────────────────────────────────────────────
@router.get("/shopping-list", response_model=list[ShoppingItemOut])
async def get_shopping_list(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await meal_service.get_shopping_list(db, current_user.id)
    except ShoppingRequiresPlanError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return [
        ShoppingItemOut(food_name=item["food_name"], grams=item["grams"])
        for item in items
    ]

"""Example-based tests for barcode propagation through the meal_service alta flow
(food-barcode, task 5.2).

These exercise the already-implemented change that adds ``barcode`` to the alta
path: ``create_food`` and ``add_inventory`` persist the optional ``barcode`` onto
the created ``Food`` row (normalized), keep it ``None`` when absent, and enforce
its uniqueness (duplicate → Spanish ``ValidationError`` with the catalog
preserved). Range validation at the alta is also checked (out-of-range → Spanish
``ValidationError``).

Like the other async DB tests in this suite, each test spins up a throwaway
in-memory SQLite database (``Base.metadata.create_all``) so nothing touches a
real PostgreSQL instance or the network.

User-facing text is Spanish; identifiers and comments are English.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
# Importing the models package registers every table on Base.metadata so
# create_all builds the full schema (the inventory FK points at foods/users).
import app.models  # noqa: F401
from app.models.food import Food
from app.models.user import User
from app.models.user_food_inventory import UserFoodInventory
from app.services import meal_service
from app.services.meal_service import ValidationError


async def _make_session() -> tuple[AsyncSession, object]:
    """Create a fresh in-memory SQLite schema and return a live session + engine.

    The engine must be kept alive for the lifetime of the session (SQLite's
    ``:memory:`` DB vanishes when the connection pool is disposed), so callers
    dispose it in a ``finally``.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return session_factory(), engine


async def _make_user(db: AsyncSession, email: str = "u@test.com") -> User:
    user = User(email=email, password_hash="x")
    db.add(user)
    await db.flush()
    return user


# ── create_food: barcode persistence ─────────────────────────────────────────


async def test_create_food_with_barcode_persists_it():
    """create_food stores the barcode on the catalog Food when one is supplied."""
    db, engine = await _make_session()
    try:
        fields = {
            "name": "Yogur de prueba",
            "kcal": 60.0,
            "protein": 5.0,
            "fat": 3.0,
            "carbs": 4.0,
            "fiber": None,
            "barcode": "7501234567890",
        }
        food = await meal_service.create_food(
            db, fields, is_meat=False, is_animal=True, has_gluten=False
        )
        await db.commit()

        # Re-read from the DB to confirm the value was actually persisted.
        reread = (
            await db.execute(select(Food).where(Food.id == food.id))
        ).scalar_one()
        assert reread.barcode == "7501234567890"
    finally:
        await db.close()
        await engine.dispose()


async def test_create_food_without_barcode_leaves_it_none():
    """create_food leaves barcode None when the field is absent (backward compat)."""
    db, engine = await _make_session()
    try:
        fields = {
            "name": "Arroz de prueba",
            "kcal": 350.0,
            "protein": 7.0,
            "fat": 1.0,
            "carbs": 78.0,
            "fiber": 1.5,
        }  # no "barcode" key at all
        food = await meal_service.create_food(
            db, fields, is_meat=False, is_animal=False, has_gluten=False
        )
        await db.commit()

        reread = (
            await db.execute(select(Food).where(Food.id == food.id))
        ).scalar_one()
        assert reread.barcode is None
    finally:
        await db.close()
        await engine.dispose()


async def test_create_food_blank_barcode_normalizes_to_none():
    """A whitespace-only barcode is normalized to None (treated as no barcode)."""
    db, engine = await _make_session()
    try:
        fields = {
            "name": "Avena de prueba",
            "kcal": 380.0,
            "protein": 13.0,
            "fat": 7.0,
            "carbs": 60.0,
            "fiber": 10.0,
            "barcode": "   ",
        }
        food = await meal_service.create_food(
            db, fields, is_meat=False, is_animal=False, has_gluten=False
        )
        await db.commit()

        reread = (
            await db.execute(select(Food).where(Food.id == food.id))
        ).scalar_one()
        assert reread.barcode is None
    finally:
        await db.close()
        await engine.dispose()


# ── add_inventory: barcode carried through the reuse path ─────────────────────


async def test_add_inventory_new_food_persists_barcode():
    """add_inventory creates the Food with its barcode AND an inventory row when
    the name is new (the 'confirmar → agregar' reuse path, Req 5.2)."""
    db, engine = await _make_session()
    try:
        user = await _make_user(db)
        new_food = {
            "name": "Barrita proteica",
            "kcal": 400.0,
            "protein": 30.0,
            "fat": 12.0,
            "carbs": 40.0,
            "fiber": 5.0,
            "barcode": "0123456789012",
        }
        entry = await meal_service.add_inventory(
            db,
            user_id=user.id,
            food_name="Barrita proteica",
            quantity_grams=50.0,
            new_food_fields=new_food,
        )
        await db.commit()

        # The created Food carries the barcode.
        food = (
            await db.execute(
                select(Food).where(Food.name == "Barrita proteica")
            )
        ).scalar_one()
        assert food.barcode == "0123456789012"

        # And the inventory row points at it.
        reread_entry = (
            await db.execute(
                select(UserFoodInventory).where(
                    UserFoodInventory.id == entry.id
                )
            )
        ).scalar_one()
        assert reread_entry.food_id == food.id
        assert reread_entry.user_id == user.id
        assert reread_entry.quantity_grams == 50.0
    finally:
        await db.close()
        await engine.dispose()


async def test_add_inventory_existing_name_no_duplicate_food():
    """When the name already exists, add_inventory reuses the existing Food (no
    duplicate catalog row); the existing food's barcode is untouched (Req 5.3)."""
    db, engine = await _make_session()
    try:
        user = await _make_user(db)
        # Seed an existing catalog food (with its own barcode).
        existing = await meal_service.create_food(
            db,
            {
                "name": "Leche entera",
                "kcal": 64.0,
                "protein": 3.2,
                "fat": 3.6,
                "carbs": 4.8,
                "fiber": None,
                "barcode": "1111111111111",
            },
            is_meat=False,
            is_animal=True,
            has_gluten=False,
        )
        await db.flush()

        # Add to inventory by the SAME name (case/accent-insensitive match).
        entry = await meal_service.add_inventory(
            db,
            user_id=user.id,
            food_name="leche entera",
            quantity_grams=200.0,
            new_food_fields={
                "name": "leche entera",
                "kcal": 64.0,
                "protein": 3.2,
                "fat": 3.6,
                "carbs": 4.8,
                "barcode": "9999999999999",  # would be ignored: food already exists
            },
        )
        await db.commit()

        foods = (
            await db.execute(select(Food).where(Food.name == "Leche entera"))
        ).scalars().all()
        assert len(foods) == 1  # no duplicate catalog entry
        # Existing food keeps its original barcode (not overwritten).
        assert foods[0].barcode == "1111111111111"
        assert entry.food_id == existing.id
    finally:
        await db.close()
        await engine.dispose()


async def test_add_inventory_duplicate_barcode_rejected_and_catalog_preserved():
    """A second food with an already-used barcode is rejected with a Spanish
    ValidationError, and the catalog is preserved (Req 1.4, rollback)."""
    db, engine = await _make_session()
    try:
        user = await _make_user(db)
        await meal_service.create_food(
            db,
            {
                "name": "Galleta A",
                "kcal": 450.0,
                "protein": 6.0,
                "fat": 20.0,
                "carbs": 60.0,
                "barcode": "2222222222222",
            },
            is_meat=False,
            is_animal=False,
            has_gluten=True,
        )
        await db.commit()

        with pytest.raises(ValidationError) as excinfo:
            await meal_service.add_inventory(
                db,
                user_id=user.id,
                food_name="Galleta B",
                quantity_grams=30.0,
                new_food_fields={
                    "name": "Galleta B",
                    "kcal": 460.0,
                    "protein": 5.0,
                    "fat": 21.0,
                    "carbs": 61.0,
                    "barcode": "2222222222222",  # duplicate
                },
            )
        assert "código de barras" in str(excinfo.value).lower()

        # Catalog preserved: only "Galleta A" exists; "Galleta B" was not created.
        names = (
            await db.execute(select(Food.name).order_by(Food.name))
        ).scalars().all()
        assert names == ["Galleta A"]
    finally:
        await db.close()
        await engine.dispose()


async def test_add_inventory_out_of_range_values_rejected():
    """Out-of-range nutrition values at the alta raise a Spanish ValidationError
    and nothing is persisted (Req 5.4)."""
    db, engine = await _make_session()
    try:
        user = await _make_user(db)
        with pytest.raises(ValidationError):
            await meal_service.add_inventory(
                db,
                user_id=user.id,
                food_name="Alimento inválido",
                quantity_grams=10.0,
                new_food_fields={
                    "name": "Alimento inválido",
                    "kcal": 5000.0,  # out of FOOD_KCAL_RANGE (0..900)
                    "protein": 10.0,
                    "fat": 10.0,
                    "carbs": 10.0,
                    "barcode": "3333333333333",
                },
            )
        await db.rollback()

        # No food and no inventory row were persisted.
        foods = (await db.execute(select(Food))).scalars().all()
        assert foods == []
        entries = (await db.execute(select(UserFoodInventory))).scalars().all()
        assert entries == []
    finally:
        await db.close()
        await engine.dispose()

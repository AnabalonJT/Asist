"""
Seed script for the Food catalog with a base set of common foods.

This script populates the ``foods`` table with common foods, their nutrition per
100 g, and dietary flags (``is_meat``, ``is_animal``, ``has_gluten``).

Data invariant: every food with ``is_meat=True`` also has ``is_animal=True``
(meat/fish is of animal origin). The reverse does not hold (egg/dairy are animal
but not meat).

Idempotent: ``seed_if_empty`` only inserts the base set when the catalog is empty
(``SELECT count(*) FROM foods == 0``); it does nothing when at least one food exists.

Usage:
    python scripts/seed_foods.py
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.models.food import Food


# Base catalog: values per 100 g. Flags enforce the invariant is_meat => is_animal.
# (name, kcal, protein_g, fat_g, carbs_g, fiber_g|None, is_meat, is_animal, has_gluten)
BASE_FOODS = [
    ("Pollo",           165.0, 31.0,  3.6,  0.0,  0.0,  True,  True,  False),
    ("Arroz",           130.0,  2.7,  0.3, 28.0,  0.4,  False, False, False),
    ("Huevo",           155.0, 13.0, 11.0,  1.1,  0.0,  False, True,  False),
    ("Avena",           389.0, 16.9,  6.9, 66.3, 10.6,  False, False, True),
    ("Lenteja",         116.0,  9.0,  0.4, 20.0,  7.9,  False, False, False),
    ("Salmón",          208.0, 20.0, 13.0,  0.0,  0.0,  True,  True,  False),
    ("Leche",            42.0,  3.4,  1.0,  5.0,  0.0,  False, True,  False),
    ("Pan",             265.0,  9.0,  3.2, 49.0,  2.7,  False, False, True),
    ("Plátano",          89.0,  1.1,  0.3, 23.0,  2.6,  False, False, False),
    ("Manzana",          52.0,  0.3,  0.2, 14.0,  2.4,  False, False, False),
    ("Atún",            132.0, 28.0,  1.3,  0.0,  0.0,  True,  True,  False),
    ("Palta",           160.0,  2.0, 15.0,  9.0,  6.7,  False, False, False),
    ("Almendras",       579.0, 21.0, 50.0, 22.0, 12.5,  False, False, False),
    ("Yogur",            59.0, 10.0,  0.4,  3.6,  0.0,  False, True,  False),
    ("Pasta",           371.0, 13.0,  1.5, 75.0,  3.2,  False, False, True),
    ("Brócoli",          34.0,  2.8,  0.4,  7.0,  2.6,  False, False, False),
    ("Papa",             77.0,  2.0,  0.1, 17.0,  2.2,  False, False, False),
    ("Queso",           402.0, 25.0, 33.0,  1.3,  0.0,  False, True,  False),
    ("Aceite de oliva", 884.0,  0.0,100.0,  0.0,  0.0,  False, False, False),
    ("Frijoles",       127.0,  8.7,  0.5, 22.8,  6.4,  False, False, False),
]


def _build_food(row: tuple) -> Food:
    name, kcal, protein, fat, carbs, fiber, is_meat, is_animal, has_gluten = row
    # Enforce invariant: meat/fish is always of animal origin.
    if is_meat:
        is_animal = True
    return Food(
        name=name,
        kcal_per_100g=kcal,
        protein_g_per_100g=protein,
        fat_g_per_100g=fat,
        carbs_g_per_100g=carbs,
        fiber_g_per_100g=fiber,
        is_meat=is_meat,
        is_animal=is_animal,
        has_gluten=has_gluten,
    )


async def seed_if_empty(session: AsyncSession) -> int:
    """Insert the base food set only when the catalog is empty.

    Returns the number of foods inserted (0 if the catalog already had entries).
    Idempotent by design (Req 1.1, 1.2): does nothing when count(foods) >= 1.
    The caller is responsible for committing the session.
    """
    count = await session.scalar(select(func.count()).select_from(Food))
    if count and count > 0:
        return 0

    for row in BASE_FOODS:
        session.add(_build_food(row))
    return len(BASE_FOODS)


async def main() -> None:
    """Main entry point for the seed script (manual execution)."""
    print("🌱 Seeding food catalog...\n")
    async with AsyncSessionLocal() as session:
        try:
            inserted = await seed_if_empty(session)
            await session.commit()
            if inserted:
                print(f"✅ Inserted {inserted} foods into the catalog.")
            else:
                print("⏭️  Catalog already populated; nothing to seed.")
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error seeding food catalog: {e}")
            raise
        finally:
            await session.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

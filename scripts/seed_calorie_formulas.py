"""
Seed script for CalorieFormula table with default activity types and MET values.

This script populates the calorie_formulas table with common activity types,
their MET (Metabolic Equivalent of Task) values, and distance factors where applicable.

Usage:
    python scripts/seed_calorie_formulas.py
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.models.calorie_formula import CalorieFormula


async def seed_calorie_formulas() -> None:
    """
    Seed the database with default calorie formulas.
    
    Default formulas include:
    - running: MET 9.8, 60 cal/km
    - walking: MET 3.5, 40 cal/km
    - cycling: MET 7.5, 35 cal/km
    - gym: MET 5.0, no distance factor
    - swimming: MET 8.0, no distance factor
    - yoga: MET 3.0, no distance factor
    """
    default_formulas = [
        {
            "activity_type": "running",
            "met_value": 9.8,
            "distance_factor": 60.0,
        },
        {
            "activity_type": "walking",
            "met_value": 3.5,
            "distance_factor": 40.0,
        },
        {
            "activity_type": "cycling",
            "met_value": 7.5,
            "distance_factor": 35.0,
        },
        {
            "activity_type": "gym",
            "met_value": 5.0,
            "distance_factor": None,
        },
        {
            "activity_type": "swimming",
            "met_value": 8.0,
            "distance_factor": None,
        },
        {
            "activity_type": "yoga",
            "met_value": 3.0,
            "distance_factor": None,
        },
    ]
    
    async with AsyncSessionLocal() as session:
        try:
            # Check existing formulas to avoid duplicates
            result = await session.execute(select(CalorieFormula))
            existing_formulas = result.scalars().all()
            existing_types = {formula.activity_type for formula in existing_formulas}
            
            added_count = 0
            skipped_count = 0
            
            for formula_data in default_formulas:
                activity_type = formula_data["activity_type"]
                
                if activity_type in existing_types:
                    print(f"⏭️  Skipping '{activity_type}' - already exists")
                    skipped_count += 1
                    continue
                
                # Create new formula
                formula = CalorieFormula(**formula_data)
                session.add(formula)
                
                distance_info = (
                    f", {formula_data['distance_factor']} cal/km"
                    if formula_data['distance_factor']
                    else ""
                )
                print(
                    f"✅ Added '{activity_type}': "
                    f"MET {formula_data['met_value']}{distance_info}"
                )
                added_count += 1
            
            # Commit all changes
            await session.commit()
            
            print(f"\n🎉 Seeding complete!")
            print(f"   Added: {added_count} formulas")
            print(f"   Skipped: {skipped_count} formulas (already exist)")
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error seeding database: {e}")
            raise
        finally:
            await session.close()


async def main() -> None:
    """Main entry point for the seed script."""
    print("🌱 Seeding calorie formulas...\n")
    
    try:
        await seed_calorie_formulas()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        # Close database connections
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

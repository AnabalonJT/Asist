"""Remove duplicate weight entries for a user, keeping one per date (highest id)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, delete
from app.database import AsyncSessionLocal, engine
from app.models.user import User
from app.models.weight_entry import WeightEntry

EMAIL = "jtanabalon@gmail.com"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if user is None:
            print("NO_USER")
            return
        rows = (await db.execute(
            select(WeightEntry).where(WeightEntry.user_id == user.id)
            .order_by(WeightEntry.entry_date.asc(), WeightEntry.id.asc())
        )).scalars().all()

        seen: dict[str, int] = {}  # date -> id to keep (highest id)
        for r in rows:
            seen[r.entry_date] = r.id  # asc id order -> ends with highest id per date

        keep_ids = set(seen.values())
        to_delete = [r.id for r in rows if r.id not in keep_ids]
        print(f"user_id={user.id} total={len(rows)} keep={len(keep_ids)} delete={len(to_delete)}")

        if to_delete:
            await db.execute(delete(WeightEntry).where(WeightEntry.id.in_(to_delete)))
            await db.commit()
            print("DELETED", len(to_delete), "duplicate weight entries")
        else:
            print("No duplicates to delete")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

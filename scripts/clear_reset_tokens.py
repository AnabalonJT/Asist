"""Clear password reset tokens for a user by email (resets the rate-limit counter).

Usage: python scripts/clear_reset_tokens.py --email user@example.com
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, delete
from app.database import AsyncSessionLocal, engine
from app.models.user import User
from app.models.password_reset_token import PasswordResetToken


async def main(email: str) -> int:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(f"[ERROR] No existe un usuario con email: {email}")
            return 1
        count = (await db.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )).scalars().all()
        n = len(count)
        await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
        await db.commit()
        print(f"[OK] Borrados {n} tokens de recuperacion del usuario id={user.id} ({email}). Rate limit reiniciado.")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    args = p.parse_args()
    raise SystemExit(asyncio.run(main(args.email)))

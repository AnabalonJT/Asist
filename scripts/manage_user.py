"""
Admin user management script for HabitTrack.

Runs against the configured DATABASE_URL (same env the app uses), so it works
locally, on Fly.io (via `fly ssh console`), or Railway.

Capabilities:
  - Promote/demote a user to admin (--make-admin / --remove-admin)
  - Reset a user's password (--reset-password), or generate a random one
  - Show a user's current state (default action if no flags given)

Usage examples:
    # On Fly.io:
    #   fly ssh console -a <your-app>
    #   cd /app  (or wherever the app lives)
    # then:

    # Promote to admin AND set a new password
    python scripts/manage_user.py --email jtanabalon@gmail.com --make-admin --reset-password "NuevaClave123"

    # Just promote to admin
    python scripts/manage_user.py --email jtanabalon@gmail.com --make-admin

    # Reset password to a random strong value (printed once)
    python scripts/manage_user.py --email jtanabalon@gmail.com --reset-password

    # Inspect a user
    python scripts/manage_user.py --email jtanabalon@gmail.com
"""
import argparse
import asyncio
import secrets
import string
import sys
from pathlib import Path

# Allow running from anywhere: add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.database import AsyncSessionLocal, engine
from app.models.user import User
from app.services.auth_service import auth_service


def _generate_password(length: int = 16) -> str:
    """Generate a URL-safe, human-copyable strong password."""
    alphabet = string.ascii_letters + string.digits
    # Ensure at least one lower, upper, and digit
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw)
                and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw


async def manage_user(
    email: str,
    make_admin: bool,
    remove_admin: bool,
    reset_password: bool,
    new_password: str | None,
) -> int:
    """Apply the requested changes to the user. Returns a process exit code."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            print(f"[ERROR] No existe un usuario con email: {email}")
            return 1

        print(f"Usuario encontrado: id={user.id} email={user.email}")
        print(f"  Estado actual -> is_admin={user.is_admin}, "
              f"telegram_linked={user.telegram_chat_id is not None}")

        changed = False
        generated_password: str | None = None

        # ── Admin flag ──
        if make_admin and remove_admin:
            print("[ERROR] No puedes usar --make-admin y --remove-admin a la vez.")
            return 2
        if make_admin and not user.is_admin:
            user.is_admin = True
            changed = True
            print("  -> Promovido a ADMIN.")
        elif make_admin and user.is_admin:
            print("  -> Ya era admin (sin cambios).")
        if remove_admin and user.is_admin:
            user.is_admin = False
            changed = True
            print("  -> Admin removido.")
        elif remove_admin and not user.is_admin:
            print("  -> No era admin (sin cambios).")

        # ── Password reset ──
        if reset_password:
            pw = new_password or _generate_password()
            if len(pw) < 6:
                print("[ERROR] La contraseña debe tener al menos 6 caracteres.")
                return 3
            user.password_hash = auth_service.hash_password(pw)
            changed = True
            if new_password is None:
                generated_password = pw
            print("  -> Contraseña restablecida.")

        if changed:
            await session.commit()
            print("\n[OK] Cambios guardados.")
            if generated_password is not None:
                print("\n==================================================")
                print("  CONTRASEÑA GENERADA (guárdala, no se vuelve a mostrar):")
                print(f"  {generated_password}")
                print("==================================================")
        else:
            print("\n[INFO] Sin cambios que aplicar.")

        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gestiona usuarios de HabitTrack (admin / password).")
    parser.add_argument("--email", required=True, help="Email del usuario objetivo.")
    parser.add_argument("--make-admin", action="store_true", help="Promueve el usuario a administrador.")
    parser.add_argument("--remove-admin", action="store_true", help="Quita el rol de administrador.")
    parser.add_argument(
        "--reset-password",
        nargs="?",
        const="",  # present with no value -> generate random
        default=None,  # absent -> no reset
        metavar="NUEVA_CLAVE",
        help="Restablece la contraseña. Da un valor para fijarla, u omítelo para generar una aleatoria.",
    )
    return parser.parse_args(argv)


async def _main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    reset_requested = args.reset_password is not None
    explicit_password = args.reset_password if (reset_requested and args.reset_password != "") else None

    try:
        return await manage_user(
            email=args.email,
            make_admin=args.make_admin,
            remove_admin=args.remove_admin,
            reset_password=reset_requested,
            new_password=explicit_password,
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))

"""Authentication service: registration, login, JWT, and Telegram linking tokens."""
import uuid
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.models.linking_token import LinkingToken

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised for authentication/authorization failures."""
    pass


class AuthService:

    # ── Password helpers ──────────────────────────────────────────────────────

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(password.encode(), password_hash.encode())

    # ── JWT ───────────────────────────────────────────────────────────────────

    @staticmethod
    def create_token(user_id: int, is_admin: bool = False) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
        payload = {
            "sub": str(user_id),
            "is_admin": is_admin,
            "exp": expire,
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def decode_token(token: str) -> dict:
        """Decode and validate a JWT. Raises AuthError on failure."""
        try:
            return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except jwt.ExpiredSignatureError:
            raise AuthError("Token expired")
        except jwt.InvalidTokenError as e:
            raise AuthError(f"Invalid token: {e}")

    # ── Register / Login ──────────────────────────────────────────────────────

    async def register(self, db: AsyncSession, email: str, password: str) -> tuple[User, str]:
        """Create a new user. Returns (user, jwt_token). Raises AuthError on duplicate email."""
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise AuthError("Email already registered")

        user = User(
            email=email,
            password_hash=self.hash_password(password),
        )
        db.add(user)
        await db.flush()  # get user.id without committing

        token = self.create_token(user.id, user.is_admin)
        logger.info("Registered new user id=%s email=%s", user.id, email)
        return user, token

    async def login(self, db: AsyncSession, email: str, password: str) -> tuple[User, str]:
        """Validate credentials. Returns (user, jwt_token). Raises AuthError on failure."""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not self.verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password")

        token = self.create_token(user.id, user.is_admin)
        logger.info("Login user id=%s", user.id)
        return user, token

    # ── Linking tokens ────────────────────────────────────────────────────────

    async def create_linking_token(self, db: AsyncSession, user_id: int) -> LinkingToken:
        """Generate a fresh 24-hour linking token for a user."""
        raw = uuid.uuid4().hex  # 32-char hex, URL-safe
        now = datetime.utcnow()
        link = LinkingToken(
            user_id=user_id,
            token=raw,
            expires_at=now + timedelta(hours=24),
        )
        db.add(link)
        await db.flush()
        logger.info("Created linking token for user_id=%s", user_id)
        return link

    async def validate_linking_token(self, db: AsyncSession, token: str) -> User:
        """
        Validate a linking token and return the associated User.
        Marks token as used. Raises AuthError if invalid/expired/used.
        """
        result = await db.execute(
            select(LinkingToken).where(LinkingToken.token == token)
        )
        link = result.scalar_one_or_none()

        if not link:
            raise AuthError("Linking token not found")
        if link.used:
            raise AuthError("Linking token already used")
        if link.expires_at < datetime.utcnow():
            raise AuthError("Linking token expired")

        link.used = True

        user_result = await db.execute(select(User).where(User.id == link.user_id))
        user = user_result.scalar_one()
        return user


auth_service = AuthService()

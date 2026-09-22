"""Authentication service: registration, login, JWT, and Telegram linking tokens."""
import uuid
import secrets
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import httpx
import jwt
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.models.linking_token import LinkingToken
from app.models.password_reset_token import PasswordResetToken

logger = logging.getLogger(__name__)


# ── Password recovery constants ────────────────────────────────────────────────
RESET_CODE_EXPIRY_MINUTES = 15
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128
RESET_RATE_LIMIT_WINDOW_MINUTES = 15
RESET_MAX_REQUESTS_PER_WINDOW = 3

# Constant bcrypt hash used for anti-timing dummy verification when a user (or a
# candidate token) does not exist. Verifying against this keeps the timing profile
# of the "user missing" path close to the "user exists" path (Req 4.3).
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"dummy-anti-timing", bcrypt.gensalt(rounds=12)).decode()


def build_recovery_message(code: str) -> str:
    """Build the Spanish recovery message containing the code and its validity in minutes.

    Pure function so it can be property-tested independently of the network call (Req 6.1).
    """
    return (
        f"🔐 Tu código de recuperación es: {code}\n"
        f"Válido por {RESET_CODE_EXPIRY_MINUTES} minutos. "
        f"Si no solicitaste este código, ignóralo."
    )


async def send_recovery_code(chat_id: int, code: str) -> None:
    """Send the recovery code to the user's Telegram chat, in Spanish.

    Mirrors the ``_send`` helper in ``app/routes/telegram.py`` (httpx POST to the Bot
    API ``sendMessage``). On failure, logs a warning and swallows the error so the
    caller's response is unaffected (Req 6.2).
    """
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    text = build_recovery_message(code)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={"chat_id": chat_id, "text": text})
    except Exception as e:
        logger.warning("Failed to send recovery code to %s: %s", chat_id, e)


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

    # ── Password recovery ─────────────────────────────────────────────────────

    async def create_password_reset_token(self, db: AsyncSession, user: User) -> str:
        """
        Invalidate the user's prior non-used, non-expired reset tokens (mark used=True),
        generate a fresh 6-digit numeric code, persist a PasswordResetToken with
        expires_at = utcnow() + RESET_CODE_EXPIRY_MINUTES, and return the PLAINTEXT code
        (needed once, to send via Telegram; only the bcrypt hash is stored).
        """
        now = datetime.utcnow()

        # Invalidate prior non-used, non-expired tokens before inserting the new one (Req 2.1).
        result = await db.execute(
            select(PasswordResetToken).where(
                and_(
                    PasswordResetToken.user_id == user.id,
                    PasswordResetToken.used == False,  # noqa: E712
                    PasswordResetToken.expires_at >= now,
                )
            )
        )
        for prior in result.scalars().all():
            prior.used = True

        # Cryptographically secure 6-digit code, leading zeros preserved (Req 1.1).
        code = f"{secrets.randbelow(1_000_000):06d}"

        token = PasswordResetToken(
            user_id=user.id,
            code_hash=self.hash_password(code),
            used=False,
            expires_at=now + timedelta(minutes=RESET_CODE_EXPIRY_MINUTES),
        )
        db.add(token)
        await db.flush()
        logger.info("Created password reset token for user_id=%s", user.id)
        return code

    async def validate_and_consume_reset(
        self, db: AsyncSession, email: str, code: str, new_password: str
    ) -> None:
        """
        Reset a password using a recovery code. Raises AuthError with a category so the
        route can map to the correct status code and generic message.

        Deterministic rejection precedence (Req 3.4) — stop at the first that applies:
          (1) code does not match any of the user's tokens  -> AuthError("invalid")
          (2) matched token is used                          -> AuthError("invalid")
          (3) matched token is expired                       -> AuthError("invalid")
          (4) new_password length outside [6, 128]           -> AuthError("length")

        On success: update user.password_hash = hash_password(new_password) and set
        the matched token used = True.
        """
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            # Anti-timing: perform a dummy verify so the timing profile matches the
            # "user exists" path (Req 4.2, 4.3), then reject generically.
            self.verify_password(code, _DUMMY_PASSWORD_HASH)
            raise AuthError("invalid")

        # Candidate tokens ordered by recency (Req 2.2): created_at DESC, id DESC.
        result = await db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id)
            .order_by(
                PasswordResetToken.created_at.desc(),
                PasswordResetToken.id.desc(),
            )
        )
        tokens = result.scalars().all()

        if not tokens:
            # No candidate tokens: still spend a dummy verify (anti-timing) then reject.
            self.verify_password(code, _DUMMY_PASSWORD_HASH)
            raise AuthError("invalid")

        matched = next(
            (t for t in tokens if self.verify_password(code, t.code_hash)), None
        )

        # Deterministic rejection precedence — stop at the first that applies.
        if matched is None:                                   # (1) no match
            raise AuthError("invalid")
        if matched.used:                                      # (2) used
            raise AuthError("invalid")
        if matched.expires_at < datetime.utcnow():            # (3) expired
            raise AuthError("invalid")
        if not (MIN_PASSWORD_LENGTH <= len(new_password) <= MAX_PASSWORD_LENGTH):
            # (4) length — do NOT consume the token nor change the password (Req 3.8).
            raise AuthError("length")

        user.password_hash = self.hash_password(new_password)
        matched.used = True
        await db.flush()
        logger.info("Password reset completed for user_id=%s", user.id)

    async def is_rate_limited(self, db: AsyncSession, user: User | None) -> bool:
        """
        True if the user already has >= RESET_MAX_REQUESTS_PER_WINDOW reset tokens
        created within the last RESET_RATE_LIMIT_WINDOW_MINUTES. Returns False when
        user is None (nonexistent email) (Req 5.1, 5.2, 5.3).
        """
        if user is None:
            return False

        from sqlalchemy import func as sa_func

        window_start = datetime.utcnow() - timedelta(
            minutes=RESET_RATE_LIMIT_WINDOW_MINUTES
        )
        result = await db.execute(
            select(sa_func.count())
            .select_from(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.created_at >= window_start,
            )
        )
        count = result.scalar() or 0
        return count >= RESET_MAX_REQUESTS_PER_WINDOW


auth_service = AuthService()

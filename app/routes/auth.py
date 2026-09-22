"""Auth routes: register, login, me, and Telegram linking token."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.middleware import get_current_user
from app.models.user import User
from app.services.auth_service import AuthError, auth_service

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    timezone: str | None = None  # Auto-detected from browser


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    is_admin: bool
    telegram_linked: bool

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            is_admin=user.is_admin,
            telegram_linked=user.telegram_chat_id is not None,
        )


class LinkingTokenResponse(BaseModel):
    token: str
    bot_url: str
    expires_at: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class GenericResponse(BaseModel):
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, token = await auth_service.register(db, body.email, body.password)
        # Save timezone if provided by browser
        if body.timezone:
            from sqlalchemy import update as sql_update
            from app.models.user import User
            await db.execute(sql_update(User).where(User.id == user.id).values(timezone=body.timezone))
        return TokenResponse(access_token=token)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        _, token = await auth_service.login(db, body.email, body.password)
        return TokenResponse(access_token=token)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse.from_user(current_user)


@router.post("/linking-token", response_model=LinkingTokenResponse)
async def create_linking_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a Telegram linking token for the authenticated user."""
    from app.config import settings
    import logging

    logger = logging.getLogger(__name__)

    try:
        link = await auth_service.create_linking_token(db, current_user.id)

        from app.services.telegram_bot import get_bot_username
        bot_username = get_bot_username()
        bot_url = f"https://t.me/{bot_username}?start={link.token}"

        return LinkingTokenResponse(
            token=link.token,
            bot_url=bot_url,
            expires_at=link.expires_at.isoformat(),
        )
    except Exception as e:
        logger.exception("Error creating linking token for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create linking token: {type(e).__name__}: {str(e)}"
        )


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.put("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password for authenticated user."""
    if not auth_service.verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña actual incorrecta")

    if len(body.new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mínimo 6 caracteres")

    from sqlalchemy import update as sql_update
    new_hash = auth_service.hash_password(body.new_password)
    await db.execute(sql_update(User).where(User.id == current_user.id).values(password_hash=new_hash))
    return {"ok": True, "message": "Contraseña actualizada"}


# ── Password recovery endpoints ────────────────────────────────────────────────

@router.post("/forgot-password", response_model=GenericResponse)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Request a password recovery code delivered via Telegram.

    Always returns the identical generic 200 response, regardless of whether the
    email belongs to a linked user, an unlinked user, or no user, to avoid account
    enumeration (Req 1.3, 4.1). Invalid email format yields 422 automatically via
    EmailStr (Req 1.7).
    """
    from sqlalchemy import select

    # Resolve user by email (may be None).
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Rate limit check — no token generated, no Telegram sent when limited (Req 5.1, 5.2).
    if await auth_service.is_rate_limited(db, user):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas solicitudes. Intenta de nuevo más tarde.",
        )

    # Only generate a token and send Telegram for a Linked_User (Req 1.1).
    # For nonexistent or unlinked emails, do nothing (Req 1.4, 1.5, 6.3).
    if user is not None and user.telegram_chat_id is not None:
        code = await auth_service.create_password_reset_token(db, user)
        # send_recovery_code swallows its own errors, so the endpoint still returns
        # the identical generic 200 with the token persisted (Req 1.6, 6.2).
        await auth_service.send_recovery_code(user.telegram_chat_id, code)

    # ALWAYS return the identical generic response with 200 (Req 1.3, 4.1).
    return GenericResponse(
        message="Si la cuenta existe y tiene Telegram vinculado, recibirás un código."
    )


@router.post("/reset-password", response_model=GenericResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset a password using a recovery code.

    Returns an identical generic 400 for all enumeration-sensitive rejection reasons
    (no user, no match, used, expired) and a distinct 400 for out-of-range length
    (Req 3.5, 3.6, 3.7, 3.8, 4.2).
    """
    try:
        await auth_service.validate_and_consume_reset(
            db, body.email, body.code, body.new_password
        )
        return GenericResponse(message="Contraseña actualizada correctamente.")
    except AuthError as e:
        if str(e) == "length":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La contraseña debe tener entre 6 y 128 caracteres.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido o expirado.",
        )

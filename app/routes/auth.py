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

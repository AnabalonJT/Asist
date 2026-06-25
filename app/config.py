"""Application configuration using pydantic-settings."""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/habittrack"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # Telegram Bot
    # El código usa settings.bot_token — acepta ambas variables del .env
    telegram_bot_token: str = "test_token"
    telegram_token: str = ""                      # alias: TELEGRAM_TOKEN en .env
    telegram_bot_username: str = "HabitBot"
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = ""
    telegram_bot_mode: str = "webhook"            # "webhook" | "polling"
    telegram_allowed_ids: str = ""                # CSV de chat_ids permitidos (vacío = todos)
    telegram_max_requests_per_hour: int = 20

    # OpenRouter LLM
    openrouter_api_key: str = "test_key"
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # JWT Authentication
    jwt_secret_key: str = "test_secret_key_change_in_production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days

    # Application
    environment: str = "development"
    debug: bool = True
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Admin
    admin_email: str = "admin@habittrack.local"
    admin_password: str = "changeme"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def bot_token(self) -> str:
        """Token real del bot. Prefiere TELEGRAM_TOKEN si TELEGRAM_BOT_TOKEN es el default."""
        if self.telegram_bot_token not in ("test_token", ""):
            return self.telegram_bot_token
        return self.telegram_token or self.telegram_bot_token


settings = Settings()
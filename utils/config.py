"""
Centralised app configuration loaded from the .env file.

Uses Pydantic v2 BaseSettings — all fields are type-validated at startup.
Import the singleton `settings` object everywhere instead of reading os.environ directly.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All environment variables required by ArthSaathi."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Gemini
    gemini_api_key: str = Field(..., description="Google Gemini API key")

    # Supabase
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_key: str = Field(..., description="Supabase anon/service key")

    # WhatsApp Business API (Meta Cloud)
    whatsapp_token: str = Field(..., description="Meta permanent access token")
    whatsapp_phone_number_id: str = Field(..., description="WhatsApp phone number ID")
    whatsapp_verify_token: str = Field(
        ..., description="Webhook verification token (self-chosen secret)"
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # PostgreSQL / Supabase async connection
    database_url: str = Field(
        ...,
        description="Async PostgreSQL URL — must start with postgresql+asyncpg://",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (loaded once, cached forever)."""
    return Settings()


# Module-level singleton — import this everywhere
settings: Settings = get_settings()

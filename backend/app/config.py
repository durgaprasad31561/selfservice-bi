"""Application settings, read from the project-root .env file (pydantic-settings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All runtime configuration. Values come from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    admin_database_url: str = Field(..., description="bi_admin: app tables + maintenance")
    reader_database_url: str = Field(..., description="bi_reader: ALL user queries (read-only)")

    # LLM
    llm_provider: Literal["gemini", "openai"] = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_fallback_models: str = ""
    gemini_thinking_level: str = "low"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_fallback_models: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = Field(2, ge=0, le=5)
    llm_cache_ttl_seconds: int = 3600

    # Auth
    jwt_secret: str = Field(..., min_length=16)
    jwt_expire_minutes: int = 480
    demo_admin_email: str = "admin@demo.com"
    demo_admin_password: str = ""
    demo_analyst_email: str = "analyst@demo.com"
    demo_analyst_password: str = ""
    demo_viewer_email: str = "viewer@demo.com"
    demo_viewer_password: str = ""

    # Query safety
    query_timeout_ms: int = Field(5000, gt=0)
    max_rows: int = Field(1000, gt=0)
    query_rate_limit: str = "30/minute"

    # Web
    cors_origins: str = "http://localhost:5173"

    @property
    def llm_models(self) -> list[str]:
        """Primary model followed by fallbacks for the configured provider."""
        if self.llm_provider == "gemini":
            primary, fallbacks = self.gemini_model, self.gemini_fallback_models
        else:
            primary, fallbacks = self.openai_model, self.openai_fallback_models
        names = [primary.strip()] + [m.strip() for m in fallbacks.split(",")]
        return list(dict.fromkeys(n for n in names if n))

    @property
    def llm_api_key(self) -> str:
        return self.gemini_api_key if self.llm_provider == "gemini" else self.openai_api_key

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()  # type: ignore[call-arg]

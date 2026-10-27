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
    llm_provider: Literal["gemini", "openai", "grok", "groq"] = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_fallback_models: str = ""
    gemini_thinking_level: str = "low"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_fallback_models: str = ""
    # xAI Grok (OpenAI-compatible API)
    xai_api_key: str = ""
    xai_model: str = ""
    xai_fallback_models: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    # Groq (groq.com, OpenAI-compatible API)
    groq_api_key: str = ""
    groq_model: str = ""
    groq_fallback_models: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
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
        primary, fallbacks = {
            "gemini": (self.gemini_model, self.gemini_fallback_models),
            "openai": (self.openai_model, self.openai_fallback_models),
            "grok": (self.xai_model, self.xai_fallback_models),
            "groq": (self.groq_model, self.groq_fallback_models),
        }[self.llm_provider]
        names = [primary.strip()] + [m.strip() for m in fallbacks.split(",")]
        return list(dict.fromkeys(n for n in names if n))

    @property
    def llm_api_key(self) -> str:
        return {
            "gemini": self.gemini_api_key,
            "openai": self.openai_api_key,
            "grok": self.xai_api_key,
            "groq": self.groq_api_key,
        }[self.llm_provider]

    @property
    def llm_env_names(self) -> tuple[str, str]:
        """(.env key variable, .env model variable) for the configured provider."""
        prefix = {"gemini": "GEMINI", "openai": "OPENAI", "grok": "XAI", "groq": "GROQ"}[
            self.llm_provider
        ]
        return f"{prefix}_API_KEY", f"{prefix}_MODEL"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()  # type: ignore[call-arg]

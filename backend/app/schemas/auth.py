"""Auth request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    email: str = Field(..., pattern=EMAIL_PATTERN, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field("", max_length=120)
    role: Literal["admin", "analyst", "viewer"] = "viewer"

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def _role_value(cls, v: object) -> str:
        return getattr(v, "value", v)  # type: ignore[return-value]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut

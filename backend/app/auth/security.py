"""Password hashing (bcrypt) and JWT creation/verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

ALGORITHM = "HS256"
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenError(ValueError):
    """The token is missing, invalid or expired."""


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(password, password_hash)
    except ValueError:
        return False


def create_access_token(user_id: int, role: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.jwt_expire_minutes
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise TokenError("Invalid or expired token.") from exc
    if "sub" not in payload:
        raise TokenError("Invalid token.")
    return payload

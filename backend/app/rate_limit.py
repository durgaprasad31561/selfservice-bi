"""Rate limiting (slowapi) keyed by the authenticated user, falling back to the client IP."""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth.security import TokenError, decode_token


def user_or_ip(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            return f"user:{decode_token(auth[7:].strip())['sub']}"
        except TokenError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=user_or_ip)

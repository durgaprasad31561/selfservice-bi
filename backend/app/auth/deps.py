"""FastAPI dependencies: current user and role requirements."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.security import TokenError, decode_token
from app.db import get_app_session
from app.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated. Please log in.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_app_session)
) -> User:
    if not token:
        raise _UNAUTHORIZED
    try:
        payload = decode_token(token)
    except TokenError as exc:
        raise _UNAUTHORIZED from exc
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return user


def require_roles(*roles: Role) -> Callable[[User], User]:
    """Dependency factory: allow only the given roles."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action requires one of the roles: "
                + ", ".join(r.value for r in roles)
                + ".",
            )
        return user

    return checker


can_edit_dashboards = require_roles(Role.admin, Role.analyst)
admin_only = require_roles(Role.admin)

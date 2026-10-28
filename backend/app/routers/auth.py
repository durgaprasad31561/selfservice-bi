"""Authentication: register, login (JSON and OAuth2 form), current user, user list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import admin_only, get_current_user, oauth2_scheme
from app.auth.security import (
    TokenError,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.db import get_app_session
from app.models import Role, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut, UserUpdate

router = APIRouter(prefix="/api/auth", tags=["auth"])

_BAD_LOGIN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password."
)


def _token_for(user: User) -> TokenResponse:
    minutes = get_settings().jwt_expire_minutes
    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        expires_in=minutes * 60,
        user=UserOut.model_validate(user),
    )


def _authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise _BAD_LOGIN
    return user


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account (viewer by default; other roles need an admin)",
)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_app_session),
    token: str | None = Depends(oauth2_scheme),
) -> User:
    if body.role != "viewer":
        requester = None
        if token:
            try:
                requester = db.get(User, int(decode_token(token)["sub"]))
            except TokenError:
                requester = None
        if requester is None or requester.role != Role.admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an admin can create analyst or admin accounts.",
            )
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    user = User(
        email=body.email,
        full_name=body.full_name.strip(),
        password_hash=hash_password(body.password),
        role=Role(body.role),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse, summary="Log in with email and password")
def login(body: LoginRequest, db: Session = Depends(get_app_session)) -> TokenResponse:
    return _token_for(_authenticate(db, body.email, body.password))


@router.post(
    "/token",
    response_model=TokenResponse,
    include_in_schema=True,
    summary="OAuth2 form login (used by the Authorize button in /docs)",
)
def token(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_app_session)
) -> TokenResponse:
    return _token_for(_authenticate(db, form.username, form.password))


@router.get("/me", response_model=UserOut, summary="The logged-in user")
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/users", response_model=list[UserOut], summary="All users (admin only)")
def list_users(_: User = Depends(admin_only), db: Session = Depends(get_app_session)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    summary="Change a user's role, name or active status (admin only)",
)
def update_user(
    user_id: int,
    body: UserUpdate,
    admin: User = Depends(admin_only),
    db: Session = Depends(get_app_session),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    new_role = Role(body.role) if body.role is not None else user.role
    new_active = body.is_active if body.is_active is not None else user.is_active
    if user.id == admin.id and (new_role != Role.admin or not new_active):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You cannot remove your own admin role or deactivate yourself.",
        )
    user.role, user.is_active = new_role, new_active
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    db.commit()
    db.refresh(user)
    return user

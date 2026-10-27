"""Users and roles."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Role(enum.StrEnum):
    """admin: manage users, see everything; analyst: ask + build dashboards; viewer: ask + view."""

    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", schema="app"), default=Role.viewer
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    dashboards = relationship("Dashboard", back_populates="owner", cascade="all, delete-orphan")

"""Dashboards and pinned widgets.

A widget stores the question and how to re-run it (the semantic plan, or for custom
queries the validated SQL) — never the result — so data is fresh on every load.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Dashboard(TimestampMixin, Base):
    __tablename__ = "dashboards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("app.users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")

    owner = relationship("User", back_populates="dashboards")
    widgets = relationship(
        "Widget",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        order_by="Widget.position",
    )


class Widget(TimestampMixin, Base):
    __tablename__ = "widgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(
        ForeignKey("app.dashboards.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20), default="semantic")  # semantic | custom_sql
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    custom_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    chart_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    dashboard = relationship("Dashboard", back_populates="widgets")

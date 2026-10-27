"""Every question a user asked, with its outcome."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class QueryHistory(Base):
    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app.users.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), index=True)
    answer_text: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    execution_ms: Mapped[int] = mapped_column(Integer, default=0)
    llm_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

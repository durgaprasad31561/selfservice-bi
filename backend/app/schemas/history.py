"""Query history model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class HistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    question: str
    status: str
    answer_text: str
    reason: str | None
    sql: str | None
    confidence: str | None
    mode: str | None
    plan: dict[str, Any] | None
    warnings: list[str] | None
    row_count: int
    execution_ms: int
    llm_model: str | None
    created_at: datetime
    user_email: str | None = None  # filled for admins viewing all users


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    total: int
    limit: int
    offset: int

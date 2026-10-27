"""Dashboard and widget models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.query import QueryResponse


class DashboardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=1000)


class DashboardUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=1000)


class WidgetCreate(BaseModel):
    """Pin a result: store the question and how to re-run it (not the data)."""

    title: str = Field(..., min_length=1, max_length=200)
    question: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["semantic", "custom_sql"] = "semantic"
    plan: dict[str, Any] | None = None
    custom_sql: str | None = Field(None, max_length=10_000)
    chart_type: Literal["kpi", "line", "bar", "pie", "table"] | None = None

    @model_validator(mode="after")
    def _has_source(self) -> WidgetCreate:
        if self.mode == "semantic" and not self.plan:
            raise ValueError("a semantic widget needs the plan from the query response")
        if self.mode == "custom_sql" and not self.custom_sql:
            raise ValueError("a custom_sql widget needs the SQL from the query response")
        return self


class WidgetUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    chart_type: Literal["kpi", "line", "bar", "pie", "table"] | None = None
    position: int | None = Field(None, ge=0)


class WidgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dashboard_id: int
    title: str
    question: str
    mode: str
    chart_type: str | None
    position: int
    created_at: datetime
    result: QueryResponse | None = None  # filled when the widget is re-run


class DashboardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    owner_id: int
    created_at: datetime
    updated_at: datetime
    widget_count: int = 0
    can_edit: bool = False


class DashboardDetail(DashboardOut):
    widgets: list[WidgetOut] = []

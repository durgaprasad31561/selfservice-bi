"""The semantic query plan: what the LLM planner returns and the compiler consumes.

A plan names business measures and dimensions only — never tables or SQL.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Operator = Literal["=", "!=", "in", "not_in", ">", ">=", "<", "<=", "between"]
Grain = Literal["day", "week", "month", "quarter", "year"]
Scalar = str | int | float


class PlanFilter(BaseModel):
    """A filter on a dimension (WHERE) or on a measure in the plan (applied to results)."""

    dimension: str = Field(description="Dimension name, or a measure name to filter results")
    operator: Operator = "="
    value: Scalar | list[Scalar]

    def values(self) -> list[Scalar]:
        """The value(s) as a list."""
        return list(self.value) if isinstance(self.value, list) else [self.value]


class TimeRange(BaseModel):
    """Inclusive date range on the order date."""

    start: date
    end: date
    label: str | None = Field(default=None, description="How the user said it, e.g. '2018'")

    @model_validator(mode="after")
    def _ordered(self) -> TimeRange:
        if self.end < self.start:
            raise ValueError("time_range end is before start")
        return self


class OrderBy(BaseModel):
    """Sort by a measure or dimension in the plan."""

    field: str
    direction: Literal["asc", "desc"] = "desc"


class QueryPlan(BaseModel):
    """Structured interpretation of a business question."""

    can_answer: bool = True
    reason: str | None = None
    measures: list[str] = []
    dimensions: list[str] = []
    filters: list[PlanFilter] = []
    time_range: TimeRange | None = None
    time_grain: Grain | None = None
    order_by: list[OrderBy] = []
    limit: int | None = Field(default=None, ge=1)
    clarification_needed: str | None = None
    clarification_options: list[str] = []
    assumptions: list[str] = []

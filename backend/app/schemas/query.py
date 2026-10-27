"""Request/response models for POST /api/query."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["answered", "answered_with_warning", "refused", "clarify", "error"]
Confidence = Literal["high", "medium", "low"]
ChartType = Literal["kpi", "line", "bar", "pie", "table"]

INSUFFICIENT_DATA = "I don't have sufficient data to answer that question."


class QueryRequest(BaseModel):
    question: str = Field(..., max_length=2000, description="Business question in plain English")


class ColumnInfo(BaseModel):
    name: str
    label: str
    role: Literal["dimension", "measure", "column"]
    format: str | None = None  # currency | integer | decimal | percent | days | rating
    dimension_type: str | None = None  # time | categorical
    grain: str | None = None


class ChartSpec(BaseModel):
    type: ChartType
    title: str
    x: str | None = None  # dimension column for the category / time axis
    y: list[str] = []  # measure columns
    series: str | None = None  # second dimension split into series
    reason: str = ""


class Explanation(BaseModel):
    mode: Literal["semantic", "custom_sql", "none"] = "none"
    definitions: list[dict[str, str]] = []  # business definitions of the measures used
    business_rules: list[str] = []  # default filters applied (e.g. excludes canceled)
    filters: list[str] = []  # user filters, human readable
    time_range: str | None = None
    sources: list[str] = []
    notes: list[str] = []


class PipelineStep(BaseModel):
    name: str  # understanding | generating_sql | validating | running | checking_results
    status: Literal["ok", "warning", "failed", "skipped"]
    ms: int = 0
    detail: str | None = None


class Clarification(BaseModel):
    question: str
    options: list[str]


class QueryResponse(BaseModel):
    """Standard response for every question, whatever the outcome."""

    status: Status
    question: str
    answer_text: str
    reason: str | None = None  # why it was refused / what went wrong
    suggestions: list[str] = []
    clarification: Clarification | None = None
    sql: str | None = None
    data: list[dict[str, Any]] = []
    columns: list[ColumnInfo] = []
    chart: ChartSpec | None = None
    explanation: Explanation = Explanation()
    warnings: list[str] = []
    assumptions: list[str] = []
    confidence: Confidence = "low"
    plan: dict[str, Any] | None = None
    steps: list[PipelineStep] = []
    row_count: int = 0
    truncated: bool = False
    execution_ms: int = 0
    llm_model: str | None = None

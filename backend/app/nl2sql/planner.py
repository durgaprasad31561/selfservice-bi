"""Mode A: business question -> semantic query plan (structured LLM output).

Flow: prompt (catalog + rules + few-shot) -> structured output -> name/date
validation -> one automatic repair attempt if invalid -> deterministic override of
relative dates -> cached PlanResult.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from app.nl2sql.dates import RelativeRange, find_relative_range, single_explicit_period
from app.nl2sql.llm import LLMClient, LLMError, get_llm_client
from app.nl2sql.prompts import (
    PROMPT_VERSION,
    planner_system_prompt,
    planner_user_prompt,
    repair_prompt,
)
from app.schemas.plan import QueryPlan, TimeRange
from app.semantic.catalog import SemanticCatalog, normalize

log = logging.getLogger(__name__)


# ------------------------------------------------------------ LLM-facing schema
# Kept deliberately simple (strings and lists) so every provider's structured-output
# mode accepts it; it is converted into the strict QueryPlan afterwards.


class LLMFilter(BaseModel):
    dimension: str = Field(description="Dimension name, or a measure name to filter results")
    operator: Literal["=", "!=", "in", "not_in", ">", ">=", "<", "<=", "between"] = "="
    values: list[str] = Field(description="Value(s) exactly as the user wrote them")


class LLMOrder(BaseModel):
    field: str = Field(description="A measure or dimension name from the plan")
    direction: Literal["asc", "desc"] = "desc"


class LLMPlan(BaseModel):
    """Semantic query plan for one business question."""

    can_answer: bool = Field(True, description="False if the data cannot answer the question")
    reason: str | None = Field(None, description="Why it cannot be answered")
    needs_custom_sql: bool = Field(
        False, description="Answerable but not expressible with the measures/dimensions"
    )
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[LLMFilter] = Field(default_factory=list)
    time_start: str | None = Field(None, description="Inclusive start date YYYY-MM-DD")
    time_end: str | None = Field(None, description="Inclusive end date YYYY-MM-DD")
    time_label: str | None = Field(None, description="The period as the user said it")
    time_grain: Literal["day", "week", "month", "quarter", "year"] | None = None
    order_by: list[LLMOrder] = Field(default_factory=list)
    limit: int | None = None
    clarification_needed: str | None = None
    clarification_options: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class PlannerError(LLMError):
    """The model did not produce a usable plan even after repair."""


@dataclass
class PlanResult:
    """Planner output plus provenance for logging and the UI."""

    plan: QueryPlan
    needs_custom_sql: bool
    model: str | None
    latency_ms: int
    cached: bool = False
    repaired: bool = False
    relative_range: RelativeRange | None = None
    raw_output: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- conversion


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value.strip()[:10])


def _scalar(value: str) -> str | int | float:
    """Keep user text as text; numeric strings become numbers."""
    text = value.strip()
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def check_plan(llm_plan: LLMPlan, catalog: SemanticCatalog) -> list[str]:
    """Problems that make the LLM plan unusable (unknown names, bad dates)."""
    model = catalog.model
    errors: list[str] = []
    if not llm_plan.can_answer or llm_plan.clarification_needed:
        return errors
    if not llm_plan.measures and not llm_plan.needs_custom_sql:
        errors.append("No measure was given; choose at least one measure name.")
    for m in llm_plan.measures:
        if not model.has_measure(m):
            errors.append(
                f"Unknown measure '{m}'. Valid: {', '.join(x.name for x in model.measures)}."
            )
    for d in llm_plan.dimensions:
        if not model.has_dimension(d):
            errors.append(
                f"Unknown dimension '{d}'. Valid: {', '.join(x.name for x in model.dimensions)}."
            )
    for f in llm_plan.filters:
        if not (model.has_dimension(f.dimension) or model.has_measure(f.dimension)):
            errors.append(f"Unknown filter field '{f.dimension}'.")
        if not f.values:
            errors.append(f"Filter on '{f.dimension}' has no values.")
    names = set(llm_plan.measures) | set(llm_plan.dimensions)
    if llm_plan.time_grain:
        names.add(model.default_time_dimension)
    for o in llm_plan.order_by:
        if o.field not in names:
            errors.append(
                f"order_by field '{o.field}' must be one of the plan's measures/dimensions."
            )
    try:
        start, end = _parse_date(llm_plan.time_start), _parse_date(llm_plan.time_end)
        if (start is None) != (end is None):
            errors.append("Give both time_start and time_end, or neither.")
        elif start and end and end < start:
            errors.append("time_end is before time_start.")
    except ValueError:
        errors.append("time_start/time_end must be dates in YYYY-MM-DD format.")
    if llm_plan.limit is not None and llm_plan.limit < 1:
        errors.append("limit must be a positive integer.")
    return errors


def to_query_plan(llm_plan: LLMPlan) -> QueryPlan:
    """Convert a validated LLMPlan into the strict QueryPlan."""
    time_range = None
    start, end = _parse_date(llm_plan.time_start), _parse_date(llm_plan.time_end)
    if start and end:
        time_range = TimeRange(start=start, end=end, label=llm_plan.time_label)
    filters = []
    for f in llm_plan.filters:
        values = [_scalar(v) for v in f.values]
        value = (
            values if (f.operator in ("in", "not_in", "between") or len(values) > 1) else values[0]
        )
        filters.append({"dimension": f.dimension, "operator": f.operator, "value": value})
    return QueryPlan(
        can_answer=llm_plan.can_answer,
        reason=llm_plan.reason,
        measures=list(dict.fromkeys(llm_plan.measures)),
        dimensions=list(dict.fromkeys(llm_plan.dimensions)),
        filters=filters,
        time_range=time_range,
        time_grain=llm_plan.time_grain,
        order_by=[o.model_dump() for o in llm_plan.order_by],
        limit=llm_plan.limit,
        clarification_needed=llm_plan.clarification_needed,
        clarification_options=llm_plan.clarification_options,
        assumptions=llm_plan.assumptions,
    )


def apply_relative_dates(
    plan: QueryPlan, question: str, today: date
) -> tuple[QueryPlan, RelativeRange | None]:
    """Force relative phrases ('last month') to resolve against today, deterministically."""
    rel = find_relative_range(question, today)
    if rel is None:
        return plan, None
    note = (
        f"'{rel.phrase}' was interpreted relative to today ({today.isoformat()}): "
        f"{rel.start.isoformat()} to {rel.end.isoformat()}."
    )
    updated = plan.model_copy(
        update={
            "time_range": TimeRange(start=rel.start, end=rel.end, label=rel.phrase),
            "assumptions": [*plan.assumptions, note],
        }
    )
    return updated, rel


def apply_explicit_period(plan: QueryPlan, question: str) -> QueryPlan:
    """Make sure a single period written in the question ("in 2018") is in the plan.

    The model sometimes drops or misreads the period; the question text is the
    authority. Plans with several periods (comparisons) are left to the model.
    """
    period = single_explicit_period(question)
    if period is None or not plan.can_answer or plan.clarification_needed:
        return plan
    tr = plan.time_range
    if tr is not None and tr.start == period.start and tr.end == period.end:
        return plan
    if tr is not None and period.start <= tr.start and tr.end <= period.end:
        return plan  # the model narrowed it further (e.g. "first half of 2018")
    note = (
        f"Applied the period '{period.phrase}' from the question "
        f"({period.start.isoformat()} to {period.end.isoformat()})."
    )
    return plan.model_copy(
        update={
            "time_range": TimeRange(start=period.start, end=period.end, label=period.phrase),
            "assumptions": [*plan.assumptions, note],
        }
    )


# --------------------------------------------------------------------- cache


class TTLCache:
    """Small thread-safe LRU cache with expiry."""

    def __init__(self, ttl_seconds: int, max_items: int = 512) -> None:
        self.ttl = ttl_seconds
        self.max_items = max_items
        self._data: OrderedDict[str, tuple[float, PlanResult]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> PlanResult | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            stored, value = item
            if time.monotonic() - stored > self.ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def put(self, key: str, value: PlanResult) -> None:
        if self.ttl <= 0:
            return
        with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# ------------------------------------------------------------------- planner


class Planner:
    """Turns questions into semantic plans using the configured LLM."""

    def __init__(
        self,
        catalog: SemanticCatalog,
        llm: LLMClient | None = None,
        today: Callable[[], date] = date.today,
        cache: TTLCache | None = None,
    ) -> None:
        self.catalog = catalog
        self._llm = llm
        self.today = today
        if cache is None:
            from app.config import get_settings

            cache = TTLCache(get_settings().llm_cache_ttl_seconds)
        self.cache = cache

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    def _cache_key(self, question: str, today: date) -> str:
        models = ",".join(self.llm.models)
        return f"{PROMPT_VERSION}|{self.llm.provider}|{models}|{today}|{normalize(question)}"

    def plan(self, question: str) -> PlanResult:
        """Plan a question; raises LLMError/PlannerError on failure."""
        today = self.today()
        key = self._cache_key(question, today)
        cached = self.cache.get(key)
        if cached is not None:
            return replace(cached, cached=True)

        messages: list[BaseMessage] = [
            SystemMessage(planner_system_prompt(self.catalog, today)),
            HumanMessage(planner_user_prompt(question)),
        ]
        result = self.llm.structured(messages, LLMPlan, purpose="plan")
        total_latency = result.latency_ms
        llm_plan, errors = self._validate(result.parsed, result.parsing_error, result.raw_text)
        repaired = False
        if errors:
            log.info("plan invalid, repairing: %s", errors)
            messages += [AIMessage(result.raw_text or "{}"), HumanMessage(repair_prompt(errors))]
            result = self.llm.structured(messages, LLMPlan, purpose="plan_repair")
            total_latency += result.latency_ms
            repaired = True
            llm_plan, errors = self._validate(result.parsed, result.parsing_error, result.raw_text)
            if errors:
                raise PlannerError(
                    "I could not interpret this question reliably. Try rephrasing it with a "
                    "measure (e.g. total sales, orders) and a period or location."
                )
        assert llm_plan is not None
        plan = to_query_plan(llm_plan)
        plan, rel = apply_relative_dates(plan, question, today)
        if rel is None:
            plan = apply_explicit_period(plan, question)
        out = PlanResult(
            plan=plan,
            needs_custom_sql=llm_plan.needs_custom_sql and plan.can_answer,
            model=result.model,
            latency_ms=total_latency,
            repaired=repaired,
            relative_range=rel,
            raw_output=result.raw_text,
        )
        self.cache.put(key, out)
        return out

    def _validate(
        self, parsed: BaseModel | None, parsing_error: str | None, raw: str
    ) -> tuple[LLMPlan | None, list[str]]:
        if parsed is None:
            try:
                parsed = LLMPlan.model_validate_json(raw)
            except ValidationError as exc:
                return None, [f"Output did not match the PLAN format: {parsing_error or exc}"[:600]]
        if not isinstance(parsed, LLMPlan):
            try:
                parsed = LLMPlan.model_validate(parsed.model_dump())
            except ValidationError as exc:
                return None, [f"Output did not match the PLAN format: {exc}"[:600]]
        return parsed, check_plan(parsed, self.catalog)

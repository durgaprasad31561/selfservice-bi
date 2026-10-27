"""The question-answering pipeline with layered correctness safeguards.

    question
      -> 1 question guard (empty / injection / off-topic)      [no LLM]
      -> 2 concept check (profit, inventory, India ...)        [no LLM]
      -> 3 semantic planner (LLM -> plan) / clarification
      -> 4 time coverage check (outside -> refuse, partial -> warn)
      -> 5 filter value check (values must exist in the data)
      -> 6 measure/dimension compatibility (compiler)
      -> 7 SQL validation + read-only execution
      -> 8 result checks (empty, NULL, impossible values, small samples)
      -> chart selection, answer sentence, explanation, confidence

Every refusal answers with the standard sentence plus a specific reason.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.db import get_reader_engine
from app.nl2sql.llm import LLMError
from app.nl2sql.planner import Planner, PlannerError, PlanResult
from app.nl2sql.sql_generator import GeneratedSQL, SQLGenerator
from app.safety.data_checks import FilterResolution, check_time_coverage, resolve_filters
from app.safety.question_guard import check_question
from app.safety.result_checks import (
    check_generic_result,
    check_sample_sizes,
    check_semantic_result,
)
from app.safety.sql_validator import SQLValidator
from app.schemas.plan import QueryPlan
from app.schemas.query import (
    INSUFFICIENT_DATA,
    Clarification,
    ColumnInfo,
    Explanation,
    PipelineStep,
    QueryResponse,
)
from app.semantic.catalog import SemanticCatalog
from app.semantic.compiler import CompiledQuery, CompileError, compile_plan
from app.services.chart_selector import select_chart, select_chart_generic
from app.services.explainer import generic_answer, semantic_answer
from app.services.formatting import format_value, to_json_value
from app.services.query_executor import QueryExecutionError, QueryExecutor
from app.services.sql_runner import SafeSQLRunner, SQLRun, UnsafeSQLError

log = logging.getLogger(__name__)

SAMPLE_CHECK_TYPES = {"average", "ratio"}


@dataclass
class _Trace:
    """Collects pipeline steps, warnings and assumptions while a question runs."""

    question: str
    started: float = field(default_factory=time.perf_counter)
    steps: list[PipelineStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    downgrades: list[str] = field(default_factory=list)  # reasons confidence was lowered
    plan: QueryPlan | None = None
    model: str | None = None
    _t: float = field(default_factory=time.perf_counter)

    def step(self, name: str, status: str = "ok", detail: str | None = None) -> None:
        now = time.perf_counter()
        self.steps.append(
            PipelineStep(
                name=name,
                status=status,  # type: ignore[arg-type]
                ms=int((now - self._t) * 1000),
                detail=detail,
            )
        )
        self._t = now

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)


class QueryService:
    """Answers business questions safely; one instance per process."""

    def __init__(
        self,
        catalog: SemanticCatalog,
        planner: Planner,
        generator: SQLGenerator,
        runner: SafeSQLRunner,
        max_rows: int,
    ) -> None:
        self.catalog = catalog
        self.model = catalog.model
        self.planner = planner
        self.generator = generator
        self.runner = runner
        self.max_rows = max_rows

    # ================================================================ public

    def answer(self, question: str) -> QueryResponse:
        """Run the full pipeline; never raises for user-caused problems."""
        question = (question or "").strip()
        trace = _Trace(question)
        try:
            return self._answer(trace)
        except LLMError as exc:
            trace.step("understanding", "failed", str(exc))
            return self._error(trace, str(exc), ["Try again in a minute."])
        except QueryExecutionError as exc:
            trace.step("running", "failed", exc.code)
            return self._error(trace, exc.message)
        except Exception:  # noqa: BLE001 - last-resort guard: never leak internals
            log.exception("unexpected error answering %r", question)
            return self._error(trace, "Something went wrong while answering this question.")

    # ============================================================== pipeline

    def _answer(self, t: _Trace) -> QueryResponse:
        # 1-2 pre-LLM checks
        guard = check_question(t.question, self.catalog)
        if not guard.ok:
            t.step("understanding", "failed", guard.code)
            return self._refuse(t, guard.reason or "", guard.suggestions)

        # 3 planning
        try:
            result = self.planner.plan(t.question)
        except PlannerError as exc:
            t.step("understanding", "failed", "uninterpretable")
            return self._refuse(t, str(exc), self._example_questions())
        plan = result.plan
        t.plan, t.model = plan, result.model
        t.assumptions += plan.assumptions
        if result.repaired:
            t.downgrades.append("the AI plan needed a repair")
        t.step(
            "understanding", detail=f"model={result.model}{' (cached)' if result.cached else ''}"
        )

        if not plan.can_answer:
            return self._refuse(
                t, plan.reason or "The data cannot answer this question.", self._example_questions()
            )
        if plan.clarification_needed:
            return self._clarify(t, plan)
        if result.needs_custom_sql:
            return self._custom_sql(t, result)
        return self._semantic(t, plan)

    # ---------------------------------------------------------------- Mode A

    def _semantic(self, t: _Trace, plan: QueryPlan) -> QueryResponse:
        # 4 time coverage
        coverage = check_time_coverage(plan.time_range, self.catalog.coverage, plan.time_grain)
        if coverage.status == "outside":
            t.step("generating_sql", "skipped")
            return self._refuse(t, coverage.message or "", self._time_suggestions(plan))
        if coverage.status == "partial" and coverage.message:
            t.warnings.append(coverage.message)
            t.downgrades.append("the period is only partly covered")

        # 5 filter values
        resolution = resolve_filters(plan, self.catalog)
        if resolution.unresolved:
            t.step("generating_sql", "skipped")
            return self._refuse_values(t, resolution)
        if resolution.notes:
            t.assumptions += resolution.notes
            if any(n.startswith("Matched") for n in resolution.notes):
                t.downgrades.append("a value was matched approximately")
        plan = resolution.plan

        # 6 compatibility + compilation
        try:
            compiled = compile_plan(plan, self.model, self.max_rows)
        except CompileError as exc:
            t.step("generating_sql", "failed", exc.code)
            return self._refuse(t, exc.message, [exc.suggestion] if exc.suggestion else [])
        t.step("generating_sql", detail="compiled from the semantic layer")

        # 7 validation + execution
        try:
            run = self.runner.run_compiled(compiled)
        except UnsafeSQLError as exc:
            t.step("validating", "failed")
            log.error("compiled SQL rejected by validator: %s", exc.validation.message)
            return self._refuse(t, "A safe query could not be produced for this question.")
        t.step("validating", detail=", ".join(run.validation.tables))
        t.step("running", detail=f"{run.result.row_count} rows in {run.result.execution_ms} ms")

        # 8 result checks
        check = check_semantic_result(
            run.result.rows, compiled.columns, self.model, run.result.truncated, self.max_rows
        )
        if not check.ok:
            t.step("checking_results", "failed", check.code)
            return self._refuse(
                t, check.reason or "", self._broaden_suggestions(plan), sql=run.display_sql
            )
        t.warnings += check.warnings
        small = self._sample_warnings(plan, compiled, run)
        if small:
            t.warnings += small
            t.downgrades.append("small sample")
        t.step("checking_results", "warning" if t.warnings else "ok")
        return self._semantic_response(t, plan, compiled, run, resolution)

    def _sample_warnings(self, plan: QueryPlan, compiled: CompiledQuery, run: SQLRun) -> list[str]:
        """For averages/rates, count the orders behind each value."""
        if not any(self.model.measure(m).type in SAMPLE_CHECK_TYPES for m in compiled.measures):
            return []
        support_plan = QueryPlan(
            measures=["order_count"],
            dimensions=compiled.dimensions,
            filters=[f for f in plan.filters if self.model.has_dimension(f.dimension)],
            time_range=plan.time_range,
            time_grain=plan.time_grain,
        )
        try:
            support = self.runner.run_compiled(
                compile_plan(support_plan, self.model, self.max_rows)
            )
        except (CompileError, UnsafeSQLError, QueryExecutionError) as exc:
            log.info("sample-size check skipped: %s", exc)
            return []
        counts = {tuple(r[:-1]): int(r[-1] or 0) for r in support.result.rows}
        return check_sample_sizes(run.result.rows, compiled.columns, counts)

    def _semantic_response(
        self,
        t: _Trace,
        plan: QueryPlan,
        compiled: CompiledQuery,
        run: SQLRun,
        resolution: FilterResolution,
    ) -> QueryResponse:
        columns = [
            ColumnInfo(
                name=c.name,
                label=c.label,
                role=c.role,
                format=c.format,  # type: ignore[arg-type]
                dimension_type=c.dimension_type,
                grain=c.grain,
            )
            for c in compiled.columns
        ]
        data = [
            {c.name: to_json_value(v) for c, v in zip(columns, row, strict=True)}
            for row in run.result.rows
        ]
        additive = {m: self.model.measure(m).type in ("sum", "count") for m in compiled.measures}
        chart = select_chart(t.question, columns, data, additive)
        filters_text = self._filters_text(resolution.plan)
        period = self._period_text(plan)
        descending = not any(o.direction == "asc" for o in plan.order_by)
        answer = semantic_answer(columns, data, filters_text, period, descending)
        explanation = Explanation(
            mode="semantic",
            definitions=compiled.definitions,
            business_rules=compiled.business_rules,
            filters=filters_text or compiled.filters_applied,
            time_range=compiled.time_range_text,
            sources=compiled.sources,
            notes=(
                [f"Default ordering: {'descending' if descending else 'ascending'}."]
                if compiled.dimensions
                else []
            ),
        )
        return self._final(t, answer, run, columns, data, chart, explanation)

    # ---------------------------------------------------------------- Mode B

    def _custom_sql(self, t: _Trace, result: PlanResult) -> QueryResponse:
        t.downgrades.append("a custom query was needed (not built from the semantic layer)")
        try:
            outcome = self.runner.run_generated(t.question, self.generator)
        except UnsafeSQLError as exc:
            t.step("generating_sql")
            t.step("validating", "failed", exc.validation.message)
            return self._refuse(
                t,
                "A safe query could not be produced for this question.",
                ["Try rephrasing it using the measures and dimensions in the Data Catalog."],
                sql=exc.sql,
            )
        if isinstance(outcome, GeneratedSQL):
            t.step("generating_sql", "failed", "declined")
            return self._refuse(t, outcome.reason or "The data cannot answer this question.")
        run = outcome
        if run.repaired:
            t.downgrades.append("the custom query needed a correction")
        t.assumptions += run.generated.assumptions if run.generated else []
        t.step("generating_sql", detail="custom SQL (fallback)")
        t.step("validating", detail=", ".join(run.validation.tables))
        t.step("running", detail=f"{run.result.row_count} rows in {run.result.execution_ms} ms")
        check = check_generic_result(
            run.result.rows, run.result.columns, run.result.truncated, self.max_rows
        )
        if not check.ok:
            t.step("checking_results", "failed", check.code)
            return self._refuse(t, check.reason or "", sql=run.display_sql)
        t.warnings += check.warnings + run.notes
        t.step("checking_results", "warning" if t.warnings else "ok")
        columns = [
            ColumnInfo(name=c, label=c.replace("_", " ").title(), role="column")
            for c in run.result.columns
        ]
        data = [
            {c: to_json_value(v) for c, v in zip(run.result.columns, row, strict=True)}
            for row in run.result.rows
        ]
        explanation = Explanation(
            mode="custom_sql",
            sources=run.validation.tables,
            notes=[
                "This question needed a custom query that is not built from the semantic "
                "layer definitions; it was checked by the SQL validator before running.",
                *(
                    [run.generated.explanation]
                    if run.generated and run.generated.explanation
                    else []
                ),
            ],
        )
        return self._final(
            t,
            generic_answer(columns, data),
            run,
            columns,
            data,
            select_chart_generic(columns, data),
            explanation,
        )

    # ============================================================= responses

    def _confidence(self, t: _Trace) -> str:
        if (
            "small sample" in t.downgrades
            or len(t.downgrades) >= 3
            or any("correction" in d for d in t.downgrades)
        ):
            return "low"
        if t.downgrades or t.assumptions:
            return "medium"
        return "high"

    def _final(
        self,
        t: _Trace,
        answer: str,
        run: SQLRun,
        columns: list[ColumnInfo],
        data: list[dict[str, Any]],
        chart: Any,
        explanation: Explanation,
    ) -> QueryResponse:
        warnings = list(dict.fromkeys(t.warnings))
        return QueryResponse(
            status="answered_with_warning" if warnings else "answered",
            question=t.question,
            answer_text=answer,
            sql=run.display_sql,
            data=data,
            columns=columns,
            chart=chart,
            explanation=explanation,
            warnings=warnings,
            assumptions=list(dict.fromkeys(t.assumptions)),
            confidence=self._confidence(t),  # type: ignore[arg-type]
            plan=t.plan.model_dump(mode="json") if t.plan else None,
            steps=t.steps,
            row_count=run.result.row_count,
            truncated=run.result.truncated,
            execution_ms=t.elapsed_ms,
            llm_model=t.model,
        )

    def _refuse(
        self, t: _Trace, reason: str, suggestions: list[str] | None = None, sql: str | None = None
    ) -> QueryResponse:
        return QueryResponse(
            status="refused",
            question=t.question,
            answer_text=INSUFFICIENT_DATA,
            reason=reason,
            suggestions=[s for s in (suggestions or []) if s],
            sql=sql,
            assumptions=list(dict.fromkeys(t.assumptions)),
            warnings=list(dict.fromkeys(t.warnings)),
            confidence="high",  # confident that it cannot be answered
            plan=t.plan.model_dump(mode="json") if t.plan else None,
            steps=t.steps,
            execution_ms=t.elapsed_ms,
            llm_model=t.model,
        )

    def _clarify(self, t: _Trace, plan: QueryPlan) -> QueryResponse:
        options = plan.clarification_options[:3] or self._example_questions()[:2]
        return QueryResponse(
            status="clarify",
            question=t.question,
            answer_text=plan.clarification_needed or "Could you clarify the question?",
            clarification=Clarification(question=plan.clarification_needed or "", options=options),
            confidence="medium",
            plan=plan.model_dump(mode="json"),
            steps=t.steps,
            execution_ms=t.elapsed_ms,
            llm_model=t.model,
        )

    def _error(
        self, t: _Trace, message: str, suggestions: list[str] | None = None
    ) -> QueryResponse:
        return QueryResponse(
            status="error",
            question=t.question,
            answer_text=message,
            reason=message,
            suggestions=suggestions or [],
            steps=t.steps,
            execution_ms=t.elapsed_ms,
            llm_model=t.model,
        )

    def _refuse_values(self, t: _Trace, resolution: FilterResolution) -> QueryResponse:
        reasons, suggestions = [], []
        for u in resolution.unresolved:
            reasons.append(f"'{u.value}' is not a {u.dimension_label} in the data.")
            if u.suggestions:
                suggestions.append(f"Did you mean: {', '.join(u.suggestions)}?")
            if u.dimension in ("customer_city", "seller_city", "customer_state", "seller_state"):
                states = self.catalog.values("customer_state")
                cities = self.catalog.values("customer_city")
                suggestions.append(
                    f"The data covers customers in {len(states)} Brazilian states (e.g. São "
                    f"Paulo, Rio de Janeiro, Minas Gerais) and {len(cities):,} cities."
                )
            elif self.catalog.values(u.dimension) and len(self.catalog.values(u.dimension)) <= 15:
                values = ", ".join(v.display for v in self.catalog.values(u.dimension))
                suggestions.append(f"Valid {u.dimension_label} values: {values}.")
        return self._refuse(t, " ".join(reasons), list(dict.fromkeys(suggestions)))

    # =============================================================== helpers

    def _filters_text(self, plan: QueryPlan) -> list[str]:
        texts = []
        for f in plan.filters:
            if self.model.has_measure(f.dimension):
                m = self.model.measure(f.dimension)
                values = " and ".join(format_value(v, m.format) for v in f.values())
                texts.append(f"{m.label} {f.operator} {values}")
                continue
            dim = self.model.dimension(f.dimension)
            shown = []
            for v in f.values():
                match = self.catalog.resolve_value(f.dimension, v)
                shown.append(match.display if match.matched else str(v))
            joined = " or ".join(shown)
            prefix = {"!=": "not ", "not_in": "not "}.get(f.operator, "")
            texts.append(f"{dim.label} {prefix}{joined}")
        return texts

    @staticmethod
    def _period_text(plan: QueryPlan) -> str | None:
        tr = plan.time_range
        if tr is None:
            return None
        if tr.label and any(ch.isdigit() for ch in tr.label):
            return f"in {tr.label}"
        return f"from {tr.start:%d %b %Y} to {tr.end:%d %b %Y}"

    def _time_suggestions(self, plan: QueryPlan) -> list[str]:
        cov = self.catalog.coverage
        if cov is None:
            return []
        measure = self.model.measure(plan.measures[0]).label if plan.measures else "Total Sales"
        return [
            f"Ask about a period between {cov.min_date:%b %Y} and {cov.max_date:%b %Y} "
            f"(complete months: Oct 2016 to Aug 2018).",
            f"For example: '{measure} in August 2018' or 'Monthly {measure.lower()} in 2017'.",
        ]

    @staticmethod
    def _broaden_suggestions(plan: QueryPlan) -> list[str]:
        out = []
        if plan.filters:
            out.append("Try removing or changing a filter.")
        if plan.time_range:
            out.append("Try a longer period.")
        return out

    def _example_questions(self) -> list[str]:
        return [
            "Total sales in 2017",
            "Top 5 product categories by product sales",
            "Monthly orders in 2018",
            "Average rating by payment type",
        ]


@lru_cache(maxsize=1)
def get_query_service() -> QueryService:
    """Process-wide service built from settings and the loaded catalog."""
    from app.semantic.state import get_catalog

    settings = get_settings()
    catalog = get_catalog()
    validator = SQLValidator(catalog.model, settings.max_rows)
    executor = QueryExecutor(get_reader_engine(), settings.query_timeout_ms, settings.max_rows)
    return QueryService(
        catalog=catalog,
        planner=Planner(catalog),
        generator=SQLGenerator(catalog, settings.max_rows),
        runner=SafeSQLRunner(validator, executor),
        max_rows=settings.max_rows,
    )

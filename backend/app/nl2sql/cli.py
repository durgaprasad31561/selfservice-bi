"""Developer CLI: show how a question is planned, compiled, validated and executed.

    .venv\\Scripts\\python.exe -m app.nl2sql.cli "Show total sales in São Paulo in 2018"

Both modes run through SafeSQLRunner, i.e. the SQL validator and the read-only
executor. Nothing reaches the database without passing validation.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.db import get_reader_engine
from app.nl2sql.llm import LLMError
from app.nl2sql.planner import Planner
from app.nl2sql.sql_generator import GeneratedSQL, SQLGenerator
from app.safety.data_checks import check_time_coverage, resolve_filters
from app.safety.sql_validator import SQLValidator
from app.semantic.compiler import CompileError, compile_plan
from app.semantic.state import load_catalog
from app.services.query_executor import QueryExecutionError, QueryExecutor
from app.services.sql_runner import SafeSQLRunner, SQLRun, UnsafeSQLError


def _print_run(run: SQLRun) -> None:
    print("\nSQL:\n" + run.display_sql)
    print(
        f"\nVALIDATION: ok, tables={run.validation.tables}, limit={run.validation.limit}"
        + (" (enforced)" if run.validation.limit_enforced else "")
    )
    res = run.result
    print(f"RESULT ({res.row_count} rows, {res.execution_ms} ms): columns={res.columns}")
    for row in res.rows[:15]:
        print("  ", tuple(row))


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, compile and run a business question.")
    parser.add_argument("question")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    catalog = load_catalog()
    runner = SafeSQLRunner(
        SQLValidator(catalog.model, settings.max_rows),
        QueryExecutor(get_reader_engine(), settings.query_timeout_ms, settings.max_rows),
    )
    try:
        result = Planner(catalog).plan(args.question)
    except LLMError as exc:
        print(f"LLM error: {exc}")
        return 2
    plan = result.plan
    print(f"model={result.model} latency={result.latency_ms}ms repaired={result.repaired}")
    print(
        "PLAN:",
        json.dumps(
            plan.model_dump(mode="json", exclude_defaults=True), indent=2, ensure_ascii=False
        ),
    )

    if not plan.can_answer:
        print("\nREFUSED:", plan.reason)
        return 0
    if plan.clarification_needed:
        print("\nCLARIFY:", plan.clarification_needed, plan.clarification_options)
        return 0
    try:
        if result.needs_custom_sql:
            print("\nMODE B (generated SQL)")
            outcome = runner.run_generated(args.question, SQLGenerator(catalog, settings.max_rows))
            if isinstance(outcome, GeneratedSQL):
                print("REFUSED (sql):", outcome.reason)
            else:
                _print_run(outcome)
            return 0

        coverage = check_time_coverage(plan.time_range, catalog.coverage, plan.time_grain)
        if coverage.status == "outside":
            print("\nREFUSED (time):", coverage.message)
            return 0
        if coverage.message:
            print("\nWARNING (time):", coverage.message)
        resolution = resolve_filters(plan, catalog)
        if resolution.unresolved:
            for u in resolution.unresolved:
                print(
                    f"\nREFUSED (value): '{u.value}' is not a known {u.dimension_label}. "
                    f"Suggestions: {u.suggestions}"
                )
            return 0
        for note in resolution.notes:
            print("NOTE:", note)
        compiled = compile_plan(resolution.plan, catalog.model, settings.max_rows)
        _print_run(runner.run_compiled(compiled))
    except CompileError as exc:
        print(f"\nREFUSED (semantic): {exc.message} {exc.suggestion or ''}")
    except UnsafeSQLError as exc:
        print(f"\nBLOCKED (unsafe SQL, not executed): {exc.validation.message}\n{exc.sql}")
    except (QueryExecutionError, LLMError) as exc:
        print(f"\nERROR: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

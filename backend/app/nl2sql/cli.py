"""Developer CLI: show how a question is planned and compiled.

    .venv\\Scripts\\python.exe -m app.nl2sql.cli "Show total sales in São Paulo in 2018"

Mode A plans are compiled deterministically and executed on the read-only
connection. Mode B (fallback) SQL is printed but NOT executed here: LLM-written SQL
only runs through the full pipeline after it passes the SQL validator.
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text

from app.config import get_settings
from app.db import get_reader_engine
from app.nl2sql.llm import LLMError
from app.nl2sql.planner import Planner
from app.nl2sql.sql_generator import SQLGenerator
from app.safety.data_checks import check_time_coverage, resolve_filters
from app.semantic.compiler import CompileError, compile_plan
from app.semantic.state import load_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan and compile a business question.")
    parser.add_argument("question")
    parser.add_argument("--no-run", action="store_true", help="do not execute the SQL")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    catalog = load_catalog()
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
    if result.needs_custom_sql:
        gen = SQLGenerator(catalog, settings.max_rows).generate(args.question)
        print(f"\nMODE B SQL ({gen.latency_ms}ms) — not executed until validated:")
        print(gen.sql or f"(none) {gen.reason}")
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
    try:
        compiled = compile_plan(resolution.plan, catalog.model, settings.max_rows)
    except CompileError as exc:
        print(f"\nREFUSED (semantic): {exc.message} {exc.suggestion or ''}")
        return 0
    print("\nSQL:\n" + compiled.display_sql)
    if not args.no_run:
        with get_reader_engine().connect() as conn:
            rows = conn.execute(text(compiled.sql), compiled.params).all()
        print(f"\nRESULT ({len(rows)} rows):")
        for row in rows[:15]:
            print("  ", tuple(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

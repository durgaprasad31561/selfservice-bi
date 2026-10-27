"""Developer CLI: run a question through the full answering pipeline.

    .venv\\Scripts\\python.exe -m app.nl2sql.cli "Show total sales in São Paulo in 2018"
    .venv\\Scripts\\python.exe -m app.nl2sql.cli --json "Top 5 categories by revenue"

Uses exactly the same QueryService as POST /api/query (all safeguards included).
"""

from __future__ import annotations

import argparse
import json
import sys

from app.services.query_service import get_query_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Answer a business question.")
    parser.add_argument("question")
    parser.add_argument("--json", action="store_true", help="print the full JSON response")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    resp = get_query_service().answer(args.question)
    if args.json:
        print(json.dumps(resp.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 0
    print(
        f"[{resp.status} | confidence {resp.confidence} | {resp.execution_ms} ms | "
        f"model {resp.llm_model}]"
    )
    print(resp.answer_text)
    if resp.reason and resp.status != "answered":
        print("Reason:", resp.reason)
    for s in resp.suggestions:
        print("Suggestion:", s)
    if resp.clarification:
        for o in resp.clarification.options:
            print("Option:", o)
    for w in resp.warnings:
        print("Warning:", w)
    for a in resp.assumptions:
        print("Assumption:", a)
    if resp.sql:
        print("\nSQL:\n" + resp.sql)
    if resp.data:
        print(f"\nChart: {resp.chart.type if resp.chart else '-'}; first rows:")
        for row in resp.data[:8]:
            print("  ", row)
    print("\nSteps:", " -> ".join(f"{s.name}({s.status})" for s in resp.steps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

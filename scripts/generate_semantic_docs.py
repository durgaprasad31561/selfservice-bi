"""Generate docs/semantic_layer.md from backend/app/semantic/model.yaml.

    backend\\.venv\\Scripts\\python.exe scripts\\generate_semantic_docs.py

Tables (measures, dimensions, sources, joins, filters, unsupported concepts) are produced
from the YAML so the documentation never drifts from the model; the explanatory text is
kept here.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.semantic.loader import load_model  # noqa: E402

INTRO = """# Semantic layer

The semantic layer (`backend/app/semantic/model.yaml`) is the **only place where business
definitions live**. The LLM never writes business logic: it picks measures, dimensions and
filters by name, and the compiler (`backend/app/semantic/compiler.py`) turns that plan into
SQL deterministically from this file. Changing a definition here changes every answer,
dashboard widget and the data catalog page at once.

The file is validated at startup (`backend/app/semantic/loader.py`): every source, column,
filter, join and synonym is cross-checked (column references are parsed with sqlglot), and
the backend refuses to start if anything is inconsistent.

## Why measures are computed at their own grain

An order can have **several items and several payments**. Joining `order_items` to
`payments` row by row multiplies the rows: an order with 3 items and 2 payments becomes 6
rows, so summing payments triples revenue and summing prices doubles item sales.

The model avoids this in three layers:

1. **Analytics tables at one grain each** (`database/02_analytics_views.sql`):
   `fact_orders` (one row per order, payments and items pre-aggregated separately),
   `fact_order_items` (one row per item) and `fact_payments` (one row per payment).
   The loader asserts `SUM(fact_payments.payment_value) = SUM(fact_orders.order_revenue)`
   and `SUM(fact_order_items.price) = SUM(fact_orders.items_amount)`.
2. **Each measure is aggregated on its own source.** When a question mixes measures from
   different sources (e.g. Total Sales and Items Sold by state), the compiler aggregates
   each source separately in its own CTE and joins the *results* on the dimension values,
   never the fact rows.
3. **The SQL validator blocks fan-out** in custom (Mode B) SQL: joining more than two fact
   tables, or summing order-level columns after joining items to orders, is rejected.

A measure that cannot be split by a dimension is **refused, not approximated**. Example:
Total Sales is the sum of an order's payments, and an order can contain products from
several categories, so "Total Sales by Product Category" is refused and Product Sales
(item prices) is suggested instead.

## How a measure is resolved

Each measure lists one SQL aggregate per source, in order of preference. The compiler uses
the first source that supports every requested dimension and filter:

- *Order Count* by state uses `fact_orders` (`COUNT(*)`); by product category it uses
  `fact_order_items` (`COUNT(DISTINCT order_id)`: orders containing that category).
- *Average Rating* by payment type uses `fact_orders`; by product category it uses
  `fact_order_items` (average over items sold, as the definition says).

## Default business rules

Named filters are applied automatically wherever a measure declares them and are shown in
every answer's "How this was calculated" panel:
"""

OUTRO = """
## Data coverage

Allowed values for every dimension and the monthly coverage table
(`analytics.meta_data_coverage`) are loaded from the database at startup. A month is
`none` with no orders, `partial` with fewer than 5% of the median monthly order volume, and
`full` otherwise. With the Olist data this marks Sep 2016, Dec 2016, Sep 2018 and Oct 2018
as partial and Nov 2016 as empty; questions touching them get a warning (or a refusal when
nothing matches), and charts draw those months dashed.

## Changing the model

1. Edit `backend/app/semantic/model.yaml`.
2. Restart the backend (the model is validated on startup).
3. Run `scripts\\test.ps1` (every measure x dimension combination is executed on PostgreSQL).
4. Regenerate this page: `backend\\.venv\\Scripts\\python.exe scripts\\generate_semantic_docs.py`.
"""


def esc(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def main() -> None:
    m = load_model()
    out = [INTRO]
    out += ["| Filter | Meaning | SQL |", "|---|---|---|"]
    for name, f in m.filters.items():
        out.append(f"| `{name}` | {esc(f.description)} | `{esc(f.sql)}` |")

    out += [
        "",
        f"## Measures ({len(m.measures)})",
        "",
        "| Measure | Definition | Format | Computed on | Default filters | Synonyms |",
        "|---|---|---|---|---|---|",
    ]
    for x in m.measures:
        sources = "<br>".join(f"`{s}`: `{esc(e)}`" for s, e in x.sources.items())
        filters = sorted({f for s in x.sources for f in x.filters_for(s)})
        out.append(
            f"| **{x.label}** (`{x.name}`) | {esc(x.description)} | {x.format} | {sources} | "
            f"{', '.join(f'`{f}`' for f in filters) or '-'} | {esc(', '.join(x.synonyms[:8]))} |"
        )

    dims = [d.name for d in m.dimensions]
    out += [
        "",
        "### Which measure can be split by which dimension",
        "",
        "| Measure | " + " | ".join(m.dimension(d).label for d in dims) + " |",
        "|---|" + "---|" * len(dims),
    ]
    for x in m.measures:
        valid = set(m.valid_dimensions(x.name))
        out.append(
            f"| {x.label} | " + " | ".join("yes" if d in valid else "-" for d in dims) + " |"
        )
    out += [
        "",
        "A measure valid for two dimensions separately is not always valid for both "
        "at once (e.g. Product Sales by category uses items, by payment type uses orders); "
        "the compiler checks the exact combination and refuses it if no single source "
        "supports it.",
    ]

    out += [
        "",
        f"## Dimensions ({len(m.dimensions)})",
        "",
        "| Dimension | Description | Available on | Value matching | Synonyms |",
        "|---|---|---|---|---|",
    ]
    for d in m.dimensions:
        grains = f" Grains: {', '.join(d.grains)} (default {d.default_grain})." if d.grains else ""
        matching = d.matching if d.type != "time" else "dates"
        out.append(
            f"| **{d.label}** (`{d.name}`) | {esc(d.description)}{grains} | "
            f"{', '.join(f'`{s}`' for s in d.columns)} | {matching} | "
            f"{esc(', '.join(d.synonyms[:8]))} |"
        )
    out += [
        "",
        "Value matching: **state** accepts the code or full name (SP, São Paulo, "
        "Sao Paulo); **fuzzy** is accent- and case-insensitive with typo tolerance "
        "('Sao Paolo' -> 'Sao Paulo'); **exact** requires the exact value. A value that "
        "does not exist in the data is refused with suggestions.",
    ]

    out += ["", "## Sources", "", "| Source | Table | Grain | Description |", "|---|---|---|---|"]
    for name, s in m.sources.items():
        out.append(f"| `{name}` | `{s.table}` | {esc(s.grain)} | {esc(s.description)} |")

    out += [
        "",
        "## Allowed joins",
        "",
        "Only these joins may appear in custom SQL; the validator rejects any other.",
        "",
        "| From | To | Type |",
        "|---|---|---|",
    ]
    for r in m.relationships:
        out.append(f"| `{r.from_}` | `{r.to}` | {r.type} |")

    out += [
        "",
        "## Concepts the data cannot answer",
        "",
        "Questions mentioning these are refused before any LLM call, with the reason below.",
        "",
        "| Concept | Example keywords | Reason | Suggestion |",
        "|---|---|---|---|",
    ]
    for u in m.unsupported_concepts:
        out.append(
            f"| {u.name.replace('_', ' ')} | {esc(', '.join(u.keywords[:6]))} | "
            f"{esc(u.reason)} | {esc(u.suggestion or '-')} |"
        )
    out.append(OUTRO)
    path = ROOT / "docs" / "semantic_layer.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()

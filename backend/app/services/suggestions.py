"""Example questions generated from the semantic layer (names, valid dimensions, coverage)."""

from __future__ import annotations

from app.semantic.catalog import SemanticCatalog

#: Preferred dimension to pair with a measure, in order.
_PAIRING = [
    "product_category",
    "customer_state",
    "payment_type",
    "seller_state",
    "delivery_status",
    "rating",
]


def _plural(label: str) -> str:
    if label.endswith("y") and not label.endswith(("ay", "ey", "oy")):
        return label[:-1] + "ies"
    return label if label.endswith("s") else label + "s"


def build_suggestions(catalog: SemanticCatalog, limit: int = 16) -> list[dict[str, str]]:
    """Totals, trends, rankings and comparisons built from measure/dimension metadata."""
    model = catalog.model
    cov = catalog.coverage
    full_years = sorted({m.month_start.year for m in cov.full_months}) if cov else [2017]
    year = 2017 if 2017 in full_years else (full_years[-1] if full_years else 2017)
    recent_year = full_years[-1] if full_years else 2018
    out: list[dict[str, str]] = []

    def add(question: str, category: str) -> None:
        if all(q["question"] != question for q in out):
            out.append({"question": question, "category": category})

    for name in ("total_sales", "order_count", "customer_count"):
        if model.has_measure(name):
            add(f"{model.measure(name).label} in {year}", "Totals")
    if model.has_measure("total_sales"):
        add(f"Monthly total sales in {recent_year}", "Trends")
        add(f"Show total sales in São Paulo in {recent_year}", "Totals")
    if model.has_measure("order_count"):
        add(f"Weekly orders in Q1 {recent_year}", "Trends")

    for m in model.measures:
        valid = model.valid_dimensions(m.name)
        dim = next((d for d in _PAIRING if d in valid), None)
        if dim is None:
            continue
        dim_label = model.dimension(dim).label.lower()
        if m.type in ("sum", "count", "count_distinct"):
            add(f"Top 5 {_plural(dim_label)} by {m.label.lower()}", "Rankings")
        else:
            add(f"{m.label} by {dim_label}", "Comparisons")
        if len(out) >= limit - 4:
            break

    add("Average rating for health and beauty", "Filters")
    add("Late delivery rate in Rio de Janeiro state", "Filters")
    add("What is our profit?", "Safeguards (refused)")
    add("Show last month's sales", "Safeguards (refused)")
    return out[:limit]

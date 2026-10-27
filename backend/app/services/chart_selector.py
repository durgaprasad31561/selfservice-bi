"""Pick a visual for a result.

Rules:
* single value                       -> KPI card
* time dimension                     -> line chart (one line per measure, or per series
                                        value when split by one more dimension, <= 6)
* one categorical dimension, <= 15   -> bar chart
* share-of-total question, <= 6 rows -> pie/donut (additive, non-negative measure only)
* otherwise                          -> sortable table
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.schemas.query import ChartSpec, ColumnInfo

MAX_BAR_CATEGORIES = 15
MAX_PIE_SLICES = 6
MAX_LINE_SERIES = 6
MAX_LINE_MEASURES = 3
SHARE_WORDS = re.compile(
    r"\b(share|mix|proportion|percentage of|percent of|% of|breakdown|composition|split)\b"
)
ADDITIVE_FORMATS = {"currency", "integer"}


def _title(columns: list[ColumnInfo]) -> str:
    measures = [c.label for c in columns if c.role == "measure"]
    dims = [c.label for c in columns if c.role == "dimension"]
    title = " and ".join(measures) if measures else "Result"
    return f"{title} by {' and '.join(dims)}" if dims else title


def select_chart(
    question: str,
    columns: list[ColumnInfo],
    rows: list[dict[str, Any]],
    additive: dict[str, bool] | None = None,
) -> ChartSpec:
    """Choose the chart for a semantic result (column roles known)."""
    measures = [c for c in columns if c.role == "measure"]
    dims = [c for c in columns if c.role == "dimension"]
    time = [d for d in dims if d.dimension_type == "time"]
    cats = [d for d in dims if d.dimension_type != "time"]
    title = _title(columns)
    y = [m.name for m in measures]

    if not dims and len(rows) == 1:
        return ChartSpec(type="kpi", title=title, y=y, reason="single value")
    if time and len(dims) == 1 and len(measures) <= MAX_LINE_MEASURES and len(rows) > 1:
        return ChartSpec(type="line", title=title, x=time[0].name, y=y, reason="trend over time")
    if time and len(dims) == 2 and len(measures) == 1:
        series_values = {r.get(cats[0].name) for r in rows}
        if 1 < len(series_values) <= MAX_LINE_SERIES:
            return ChartSpec(
                type="line",
                title=title,
                x=time[0].name,
                y=y,
                series=cats[0].name,
                reason="trend per group",
            )
    if len(cats) == 1 and not time:
        share = bool(SHARE_WORDS.search(question.lower()))
        m = measures[0] if len(measures) == 1 else None
        if (
            share
            and m is not None
            and 1 < len(rows) <= MAX_PIE_SLICES
            and (additive or {}).get(m.name, False)
            and all((r.get(m.name) or 0) >= 0 for r in rows)
        ):
            return ChartSpec(type="pie", title=title, x=cats[0].name, y=y, reason="share of total")
        if 1 < len(rows) <= MAX_BAR_CATEGORIES:
            return ChartSpec(type="bar", title=title, x=cats[0].name, y=y, reason="comparison")
        if len(rows) == 1:
            return ChartSpec(type="kpi", title=title, x=cats[0].name, y=y, reason="single group")
    return ChartSpec(
        type="table",
        title=title,
        x=dims[0].name if dims else None,
        y=y,
        reason="many rows or several dimensions",
    )


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _is_date(v: Any) -> bool:
    if isinstance(v, date):
        return True
    return isinstance(v, str) and bool(re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", v))


def select_chart_generic(columns: list[ColumnInfo], rows: list[dict[str, Any]]) -> ChartSpec:
    """Choose a chart for custom SQL results by inspecting the values."""
    names = [c.name for c in columns]
    if not rows:
        return ChartSpec(type="table", title="Result", reason="no rows")
    numeric = [
        n
        for n in names
        if all(_is_number(r.get(n)) or r.get(n) is None for r in rows)
        and any(_is_number(r.get(n)) for r in rows)
    ]
    labels = [n for n in names if n not in numeric]
    if len(rows) == 1 and len(numeric) >= 1 and not labels:
        return ChartSpec(type="kpi", title="Result", y=numeric, reason="single value")
    if len(labels) == 1 and numeric:
        x = labels[0]
        if all(_is_date(r.get(x)) for r in rows) and len(rows) > 1:
            return ChartSpec(type="line", title="Result", x=x, y=numeric[:3], reason="trend")
        if 1 < len(rows) <= MAX_BAR_CATEGORIES:
            return ChartSpec(type="bar", title="Result", x=x, y=numeric[:1], reason="comparison")
    return ChartSpec(type="table", title="Result", reason="general result")

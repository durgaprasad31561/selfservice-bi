"""Plain-English answer sentences, built only from query results (no LLM numbers)."""

from __future__ import annotations

from typing import Any

from app.schemas.query import ColumnInfo
from app.services.formatting import format_period, format_value


def _value_text(row: dict[str, Any], col: ColumnInfo) -> str:
    return format_value(row.get(col.name), col.format)


def _dim_text(row: dict[str, Any], col: ColumnInfo) -> str:
    value = row.get(col.name)
    if col.dimension_type == "time":
        return format_period(value, col.grain)
    if col.name == "rating" and value is not None:
        return f"{value} star{'s' if value != 1 else ''}"
    return "(none)" if value is None else str(value)


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def context_text(filters: list[str], period: str | None) -> str:
    """'for Customer City Sao Paulo in 2018' style context."""
    parts = []
    if filters:
        parts.append("for " + _join(filters))
    if period:
        parts.append(period)
    return " ".join(parts)


def semantic_answer(
    columns: list[ColumnInfo],
    rows: list[dict[str, Any]],
    filters: list[str],
    period: str | None,
    descending: bool = True,
    incomplete_periods: set[str] | None = None,
) -> str:
    """Answer sentence for a semantic-layer result."""
    measures = [c for c in columns if c.role == "measure"]
    dims = [c for c in columns if c.role == "dimension"]
    ctx = context_text(filters, period)
    ctx = f" {ctx}" if ctx else ""
    if not rows or not measures:
        return "No data matches this question."

    if not dims:
        row = rows[0]
        first = f"{measures[0].label}{ctx} was {_value_text(row, measures[0])}"
        rest = [f"{m.label} was {_value_text(row, m)}" for m in measures[1:]]
        return _join([first, *rest]) + "."

    main = measures[0]
    time = next((d for d in dims if d.dimension_type == "time"), None)
    if time and len(dims) == 1:
        valued = [r for r in rows if r.get(main.name) is not None]
        if not valued:
            return f"{main.label} has no values{ctx}."
        # incomplete months (little or no data) must not be reported as real lows/highs
        complete = [
            r
            for r in valued
            if not (
                incomplete_periods
                and time.grain in ("month", "week", "day")
                and str(r.get(time.name))[:7] in incomplete_periods
            )
        ]
        note = " (excluding incomplete months)" if complete and len(complete) < len(valued) else ""
        valued = complete or valued
        hi = max(valued, key=lambda r: r[main.name])
        lo = min(valued, key=lambda r: r[main.name])
        first, last = _dim_text(rows[0], time), _dim_text(rows[-1], time)
        grain = time.grain or "period"
        return (
            f"{main.label} by {grain}{ctx} from {first} to {last}: highest in "
            f"{_dim_text(hi, time)} ({_value_text(hi, main)}), lowest in "
            f"{_dim_text(lo, time)} ({_value_text(lo, main)}){note}."
        )
    if time:
        other = next(d for d in dims if d is not time)
        groups = {r.get(other.name) for r in rows}
        return (
            f"{main.label} by {time.grain or 'period'} for {len(groups)} "
            f"{other.label.lower()} values{ctx}."
        )

    dim = dims[0]
    if len(rows) == 1:
        return f"{main.label} for {_dim_text(rows[0], dim)}{ctx} was {_value_text(rows[0], main)}."
    word = "highest" if descending else "lowest"
    top = rows[0]
    follow = [f"{_dim_text(r, dim)} ({_value_text(r, main)})" for r in rows[1:3]]
    tail = f", followed by {_join(follow)}" if follow else ""
    scope = f" among {len(rows)} {dim.label.lower()} values" if len(dims) == 1 else ""
    return (
        f"{_dim_text(top, dim)} had the {word} {main.label} ({_value_text(top, main)})"
        f"{tail}{scope}{ctx}."
    )


def generic_answer(columns: list[ColumnInfo], rows: list[dict[str, Any]]) -> str:
    """Answer sentence for a custom-SQL result."""
    if not rows:
        return "No data matches this question."
    if len(rows) == 1 and len(columns) <= 3:
        parts = [f"{c.label} = {format_value(rows[0].get(c.name), None)}" for c in columns]
        return "Result: " + _join(parts) + "."
    first = rows[0]
    lead = ", ".join(f"{c.label} {format_value(first.get(c.name), None)}" for c in columns[:3])
    return f"The query returned {len(rows)} rows. First row: {lead}."

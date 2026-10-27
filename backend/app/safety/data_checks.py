"""Data availability checks run after planning and before SQL is executed.

* :func:`resolve_filters` — every filter value must exist in the allowed values
  (accent-insensitive, state code/name, typo-tolerant); values are rewritten to the
  canonical keys the compiler expects.
* :func:`check_time_coverage` — compares the requested period with
  ``analytics.meta_data_coverage``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.schemas.plan import QueryPlan, TimeRange
from app.semantic.catalog import DataCoverage, SemanticCatalog


@dataclass
class UnresolvedValue:
    """A filter value that does not exist in the data."""

    dimension: str
    dimension_label: str
    value: str
    suggestions: list[str] = field(default_factory=list)


@dataclass
class FilterResolution:
    plan: QueryPlan
    unresolved: list[UnresolvedValue]
    notes: list[str]  # e.g. "Matched 'Sao Paolo' to 'Sao Paulo'"


def resolve_filters(plan: QueryPlan, catalog: SemanticCatalog) -> FilterResolution:
    """Map user-typed filter values to canonical keys; collect values that do not exist."""
    model = catalog.model
    new_filters = []
    unresolved: list[UnresolvedValue] = []
    notes: list[str] = []
    for f in plan.filters:
        if not model.has_dimension(f.dimension):
            new_filters.append(f)  # measure filters are numeric thresholds
            continue
        dim = model.dimension(f.dimension)
        if dim.type == "time":
            new_filters.append(f)
            continue
        keys: list[str | int] = []
        for raw in f.values():
            match = catalog.resolve_value(f.dimension, raw)
            if not match.matched:
                unresolved.append(
                    UnresolvedValue(f.dimension, dim.label, str(raw), match.suggestions)
                )
                continue
            keys.append(match.key)  # type: ignore[arg-type]
            if match.method == "fuzzy":
                notes.append(f"Matched '{raw}' to {dim.label} '{match.display}'.")
            elif match.method == "alias" and str(raw).strip().upper() != str(match.key):
                notes.append(f"'{raw}' interpreted as {dim.label} '{match.display}'.")
        if keys:
            value = (
                keys if (len(keys) > 1 or f.operator in ("in", "not_in", "between")) else keys[0]
            )
            new_filters.append(f.model_copy(update={"value": value}))
    return FilterResolution(plan.model_copy(update={"filters": new_filters}), unresolved, notes)


@dataclass
class TimeCoverage:
    """Result of comparing a requested period with the available data."""

    status: str  # ok | partial | outside
    message: str | None = None
    incomplete_months: list[str] = field(default_factory=list)
    covered_range: TimeRange | None = None


def _months(start: date, end: date) -> list[date]:
    months, d = [], start.replace(day=1)
    while d <= end:
        months.append(d)
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def _fmt(d: date) -> str:
    return f"{d:%d %b %Y}"


def check_time_coverage(
    time_range: TimeRange | None, coverage: DataCoverage, time_grain: str | None = None
) -> TimeCoverage:
    """Classify the requested period as fully covered, partially covered or outside the data.

    Without an explicit period the whole dataset is used; a time series over it still
    gets a warning because the first and last months are incomplete.
    """
    data_start, data_end = coverage.min_date, coverage.max_date
    if time_range is None:
        if time_grain:
            bad = [
                m
                for m in coverage.months
                if m.status != "full" and data_start.replace(day=1) <= m.month_start <= data_end
            ]
            if bad:
                names = [f"{m.month_start:%b %Y}" for m in bad]
                return TimeCoverage(
                    "partial",
                    "Some months have little or no data, so low values there reflect missing "
                    f"data, not real drops: {', '.join(names)}.",
                    names,
                )
        return TimeCoverage("ok")

    start, end = time_range.start, time_range.end
    if end < data_start or start > data_end:
        return TimeCoverage(
            "outside",
            f"The data only covers orders from {_fmt(data_start)} to {_fmt(data_end)}; the "
            f"requested period ({_fmt(start)} to {_fmt(end)}) has no data.",
        )

    messages: list[str] = []
    if start < data_start or end > data_end:
        messages.append(
            f"The requested period extends beyond the available data ({_fmt(data_start)} to "
            f"{_fmt(data_end)}); only the overlapping part is included."
        )
    incomplete = []
    for month in _months(max(start, data_start), min(end, data_end)):
        status = coverage.status_of(month)
        if status != "full":
            count = next((m.order_count for m in coverage.months if m.month_start == month), 0)
            incomplete.append(f"{month:%b %Y} ({count} order{'' if count == 1 else 's'})")
    if incomplete:
        messages.append(
            "Data is incomplete for "
            + ", ".join(incomplete)
            + ", so these figures are not comparable with complete months."
        )
    covered = TimeRange(
        start=max(start, data_start), end=min(end, data_end), label=time_range.label
    )
    if messages:
        return TimeCoverage("partial", " ".join(messages), incomplete, covered)
    return TimeCoverage("ok", covered_range=covered)

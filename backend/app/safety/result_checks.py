"""Sanity checks on query results before they are shown.

* no rows, or a single aggregate row that is entirely NULL/0  -> "no data matches"
  (a 0 is never presented as if it were a real measurement)
* values outside the measure's bounds (negative money, rating > 5, % > 100)
  -> the answer is withheld
* NULL values in some groups -> warning
* small samples (< MIN_SAMPLE orders behind an average/ratio) -> warning
* row cap reached -> warning
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.semantic.compiler import ResultColumn
from app.semantic.loader import SemanticModel

MIN_SAMPLE = 30


@dataclass
class ResultCheck:
    ok: bool  # False = do not show the result
    code: str | None = None  # no_data | impossible_value
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def _num(v: Any) -> float | None:
    if isinstance(v, int | float | Decimal) and not isinstance(v, bool):
        return float(v)
    return None


def check_semantic_result(
    rows: list[tuple[Any, ...]],
    columns: list[ResultColumn],
    model: SemanticModel,
    truncated: bool = False,
    max_rows: int = 1000,
) -> ResultCheck:
    """Check a result produced from a semantic plan (column roles and formats known)."""
    measure_idx = [i for i, c in enumerate(columns) if c.role == "measure"]
    has_dims = any(c.role == "dimension" for c in columns)
    if not rows:
        return ResultCheck(False, "no_data", "No data matches these filters and period.")
    if not has_dims and len(rows) == 1:
        values = [rows[0][i] for i in measure_idx]
        if all(v is None or _num(v) == 0 for v in values):
            return ResultCheck(
                False, "no_data", "No data matches these filters and period (the result is empty)."
            )

    warnings: list[str] = []
    for i in measure_idx:
        col = columns[i]
        lo, hi = model.measure(col.name).bounds
        nulls = 0
        for row in rows:
            value = _num(row[i])
            if row[i] is None:
                nulls += 1
                continue
            if value is None:
                continue
            if (lo is not None and value < lo - 1e-9) or (hi is not None and value > hi + 1e-9):
                return ResultCheck(
                    False,
                    "impossible_value",
                    f"The result failed a sanity check: {col.label} = {value:g} is outside the "
                    f"possible range ({lo if lo is not None else '-inf'} to "
                    f"{hi if hi is not None else 'inf'}), so it is not shown.",
                )
        if nulls and has_dims:
            warnings.append(
                f"{col.label} has no value for {nulls} of {len(rows)} groups " "(shown as empty)."
            )
    if truncated or len(rows) >= max_rows:
        warnings.append(f"Only the first {max_rows} rows are shown.")
    return ResultCheck(True, warnings=warnings)


def check_sample_sizes(
    rows: list[tuple[Any, ...]],
    columns: list[ResultColumn],
    support: dict[tuple[Any, ...], int],
) -> list[str]:
    """Warn when an average or rate is based on fewer than MIN_SAMPLE orders."""
    dim_idx = [i for i, c in enumerate(columns) if c.role == "dimension"]
    small = []
    for row in rows:
        key = tuple(row[i] for i in dim_idx)
        count = support.get(key)
        if count is not None and count < MIN_SAMPLE:
            label = ", ".join(str(row[i]) for i in dim_idx) or "the selection"
            small.append((label, count))
    if not small:
        return []
    if not dim_idx:
        return [f"This figure is based on only {small[0][1]} orders, so it may not be reliable."]
    examples = "; ".join(f"{label} ({n})" for label, n in small[:3])
    more = f" and {len(small) - 3} more" if len(small) > 3 else ""
    return [
        f"{len(small)} group(s) are based on fewer than {MIN_SAMPLE} orders, so their "
        f"averages/rates may not be reliable: {examples}{more}."
    ]


def check_generic_result(
    rows: list[tuple[Any, ...]], columns: list[str], truncated: bool = False, max_rows: int = 1000
) -> ResultCheck:
    """Checks for custom (Mode B) SQL, where column meanings are unknown."""
    if not rows:
        return ResultCheck(False, "no_data", "No data matches this question.")
    if all(all(v is None for v in row) for row in rows):
        return ResultCheck(False, "no_data", "The query returned only empty values.")
    numeric_cols = [i for i in range(len(columns)) if any(_num(r[i]) is not None for r in rows)]
    if (
        len(rows) == 1
        and numeric_cols
        and all(_num(rows[0][i]) in (None, 0.0) for i in numeric_cols)
    ):
        return ResultCheck(False, "no_data", "No data matches this question (the result is 0).")
    warnings = []
    money_like = ("revenue", "sales", "price", "value", "amount", "freight", "count", "orders")
    for i in numeric_cols:
        if any(w in columns[i].lower() for w in money_like) and any(
            (_num(r[i]) or 0) < 0 for r in rows
        ):
            return ResultCheck(
                False,
                "impossible_value",
                f"The result failed a sanity check: negative values in {columns[i]}.",
            )
    if truncated or len(rows) >= max_rows:
        warnings.append(f"Only the first {max_rows} rows are shown.")
    return ResultCheck(True, warnings=warnings)

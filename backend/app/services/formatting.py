"""Value formatting and JSON conversion shared by the explainer and the API.

Money is Brazilian Real, formatted consistently as ``R$ 1,234.56``; large values
can be abbreviated (``R$ 16.0M``).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def to_json_value(value: Any) -> Any:
    """Make a database value JSON-serialisable without losing meaning."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def format_value(value: Any, fmt: str | None, abbreviate: bool = False) -> str:
    """Human-readable value for the answer sentence."""
    if value is None:
        return "no value"
    if not isinstance(value, int | float | Decimal):
        return str(value)
    number = float(value)
    if fmt == "currency":
        if abbreviate and abs(number) >= 1_000_000:
            return f"R$ {number / 1_000_000:,.1f}M"
        if abbreviate and abs(number) >= 10_000:
            return f"R$ {number / 1_000:,.1f}K"
        return f"R$ {number:,.2f}"
    if fmt == "integer":
        return f"{round(number):,}"
    if fmt == "percent":
        return f"{number:,.2f}%"
    if fmt == "days":
        return f"{number:,.1f} days"
    if fmt == "rating":
        return f"{number:.2f} / 5"
    if fmt == "decimal":
        return f"{number:,.2f}"
    return f"{number:,.2f}" if not number.is_integer() else f"{int(number):,}"


def format_period(value: Any, grain: str | None) -> str:
    """Label for a time-axis value at a given grain (e.g. 'Mar 2018', 'Q2 2017')."""
    if grain == "year" or isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return value
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return str(value)
    if grain == "month":
        return f"{MONTH_ABBR[value.month - 1]} {value.year}"
    if grain == "quarter":
        return f"Q{(value.month - 1) // 3 + 1} {value.year}"
    if grain == "week":
        return f"week of {value.isoformat()}"
    return value.isoformat()

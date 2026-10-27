"""Deterministic resolution of relative date phrases against the REAL current date.

"Last month", "this year", "recently" ... always mean relative to today, not to the
end of the dataset. Because the data stops in 2018, such questions fall outside the
data and the coverage safeguard refuses them with the actual data range.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

_UNITS = {
    "day": "day",
    "days": "day",
    "week": "week",
    "weeks": "week",
    "month": "month",
    "months": "month",
    "quarter": "quarter",
    "quarters": "quarter",
    "year": "year",
    "years": "year",
}
_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
}

#: An explicit 4-digit year or a named month+year means the user gave absolute dates.
_EXPLICIT = re.compile(r"\b(19|20)\d{2}\b")


@dataclass(frozen=True)
class RelativeRange:
    """A relative phrase found in a question and the dates it resolves to."""

    phrase: str
    start: date
    end: date


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def _month_end(d: date) -> date:
    return _add_months(_month_start(d), 1) - timedelta(days=1)


def _quarter_start(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def _period(unit: str, today: date, offset: int) -> tuple[date, date]:
    """Calendar period containing today shifted by ``offset`` periods (0 = current)."""
    if unit == "day":
        d = today + timedelta(days=offset)
        return d, d
    if unit == "week":
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        return monday, monday + timedelta(days=6)
    if unit == "month":
        start = _add_months(_month_start(today), offset)
        return start, _month_end(start)
    if unit == "quarter":
        start = _add_months(_quarter_start(today), 3 * offset)
        return start, _add_months(start, 3) - timedelta(days=1)
    start = date(today.year + offset, 1, 1)
    return start, date(start.year, 12, 31)


def _rolling(unit: str, n: int, today: date) -> tuple[date, date]:
    """The last n units up to today, e.g. last 30 days."""
    if unit == "day":
        return today - timedelta(days=n - 1), today
    if unit == "week":
        return today - timedelta(weeks=n) + timedelta(days=1), today
    if unit in ("month", "quarter"):
        months = n if unit == "month" else 3 * n
        start = _add_months(_month_start(today), -months + 1)
        return start, today
    return date(today.year - n + 1, 1, 1), today


def find_relative_range(question: str, today: date) -> RelativeRange | None:
    """Return the relative period mentioned in ``question``, if any."""
    q = question.lower()
    if _EXPLICIT.search(q):
        return None  # "last month of 2017", "in 2018 so far" ... are absolute

    n_pat = r"(\d+|" + "|".join(_NUMBERS) + r")"
    unit_pat = "(" + "|".join(_UNITS) + ")"

    m = re.search(rf"\b(last|past|previous|prior)\s+{n_pat}\s+{unit_pat}\b", q)
    if m:
        n = int(m.group(2)) if m.group(2).isdigit() else _NUMBERS[m.group(2)]
        start, end = _rolling(_UNITS[m.group(3)], max(n, 1), today)
        return RelativeRange(m.group(0), start, end)

    m = re.search(rf"\b(this|current|last|previous|past|prior)\s+{unit_pat}\b", q)
    if m and _UNITS[m.group(2)] != "day":
        unit = _UNITS[m.group(2)]
        offset = 0 if m.group(1) in ("this", "current") else -1
        start, end = _period(unit, today, offset)
        if offset == 0:
            end = today
        return RelativeRange(m.group(0), start, end)

    simple = [
        (r"\btoday\b", (today, today)),
        (r"\byesterday\b", (today - timedelta(days=1),) * 2),
        (r"\b(year to date|ytd|so far this year)\b", (date(today.year, 1, 1), today)),
        (r"\b(month to date|mtd)\b", (_month_start(today), today)),
        # "most recent" usually means "latest in the data", so it is not treated as relative
        (
            r"(?<!most )\b(recently|recent|lately|nowadays|these days)\b",
            (today - timedelta(days=29), today),
        ),
        (r"\bthis (season|period)\b", (_month_start(today), today)),
    ]
    for pattern, (start, end) in simple:
        m = re.search(pattern, q)
        if m:
            return RelativeRange(m.group(0), start, end)
    return None

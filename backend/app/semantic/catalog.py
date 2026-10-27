"""Runtime catalog: semantic model + allowed values + data coverage.

* Allowed values for every categorical dimension are read from the analytics
  schema at startup (through the read-only engine).
* User-typed values are resolved accent- and case-insensitively, with state
  code <-> name mapping and typo-tolerant fuzzy matching.
* Data coverage per month comes from ``analytics.meta_data_coverage``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz, process
from sqlalchemy import Engine, text
from unidecode import unidecode

from app.semantic.loader import DimensionDef, SemanticModel

#: Minimum rapidfuzz ratio to accept a typo-corrected value automatically.
ACCEPT_SCORE = 88.0
#: Minimum WRatio score to offer a value as a suggestion.
SUGGEST_SCORE = 75.0


def normalize(value: object) -> str:
    """Lowercase, strip accents, '&' -> 'and', drop punctuation, collapse spaces."""
    s = unidecode(str(value)).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass(frozen=True)
class AllowedValue:
    """One valid value of a dimension."""

    key: str | int
    display: str
    aliases: tuple[str, ...]


@dataclass
class ValueMatch:
    """Result of resolving a user-typed value against a dimension's allowed values."""

    dimension: str
    input: str
    key: str | int | None = None
    display: str | None = None
    method: str = "none"  # exact | alias | fuzzy | none
    score: float = 0.0
    suggestions: list[str] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return self.key is not None


@dataclass(frozen=True)
class MonthCoverage:
    month_start: date
    order_count: int
    status: str  # full | partial | none


@dataclass
class DataCoverage:
    """Monthly coverage of the order data."""

    min_date: date
    max_date: date
    months: list[MonthCoverage]

    def status_of(self, month_start: date) -> str:
        """Coverage status of a month; months outside the calendar are 'none'."""
        for m in self.months:
            if m.month_start == month_start:
                return m.status
        return "none"

    @property
    def full_months(self) -> list[MonthCoverage]:
        return [m for m in self.months if m.status == "full"]

    def describe(self) -> str:
        """Human description of the range, e.g. 'Sep 2016 to Oct 2018 (...)'."""
        full = self.full_months
        partial = [
            m
            for m in self.months
            if m.status != "full" and self.min_date <= m.month_start <= self.max_date.replace(day=1)
        ]
        text_ = f"{self.min_date:%d %b %Y} to {self.max_date:%d %b %Y}"
        if full:
            text_ += (
                f"; complete months {full[0].month_start:%b %Y} to {full[-1].month_start:%b %Y}"
            )
        if partial:
            text_ += "; incomplete: " + ", ".join(
                f"{m.month_start:%b %Y} ({m.order_count} order{'' if m.order_count == 1 else 's'})"
                for m in partial
            )
        return text_


class SemanticCatalog:
    """Semantic model plus runtime metadata, shared by the planner and safeguards."""

    def __init__(
        self,
        model: SemanticModel,
        allowed_values: dict[str, list[AllowedValue]],
        coverage: DataCoverage | None = None,
    ) -> None:
        self.model = model
        self.allowed_values = allowed_values
        self.coverage = coverage
        self._alias_index: dict[str, dict[str, AllowedValue]] = {
            dim: {alias: v for v in values for alias in v.aliases}
            for dim, values in allowed_values.items()
        }

    # ------------------------------------------------------------------ build

    @classmethod
    def from_database(cls, model: SemanticModel, engine: Engine) -> SemanticCatalog:
        """Load allowed values and coverage from the analytics schema."""
        allowed: dict[str, list[AllowedValue]] = {}
        with engine.connect() as conn:
            for dim in model.dimensions:
                if dim.values_from is None:
                    continue
                vf = dim.values_from
                table = model.sources[vf.source].table
                display = vf.display or vf.key
                extra = "".join(f", {a} AS a{i}" for i, a in enumerate(vf.aliases))
                rows = conn.execute(
                    text(
                        f"SELECT DISTINCT {vf.key} AS k, {display} AS d{extra} FROM {table} "
                        f"WHERE {vf.key} IS NOT NULL ORDER BY 1"
                    )
                ).all()
                allowed[dim.name] = [build_value(dim, r[0], r[1], r[2:]) for r in rows]
            cov_rows = conn.execute(
                text(
                    "SELECT month_start, order_count, coverage_status "
                    "FROM analytics.meta_data_coverage ORDER BY month_start"
                )
            ).all()
            min_ts, max_ts = conn.execute(
                text("SELECT MIN(purchase_date), MAX(purchase_date) FROM analytics.fact_orders")
            ).one()
        coverage = DataCoverage(
            min_date=min_ts,
            max_date=max_ts,
            months=[
                MonthCoverage(r.month_start, r.order_count, r.coverage_status) for r in cov_rows
            ],
        )
        return cls(model, allowed, coverage)

    # -------------------------------------------------------------- resolving

    def values(self, dimension: str) -> list[AllowedValue]:
        return self.allowed_values.get(dimension, [])

    def resolve_value(self, dimension: str, raw: object) -> ValueMatch:
        """Resolve a user-typed value to the dimension's canonical key."""
        dim = self.model.dimension(dimension)
        result = ValueMatch(dimension=dimension, input=str(raw))
        values = self.values(dimension)
        if not values:
            return result

        if dim.value_type == "integer":
            m = re.search(r"-?\d+", str(raw))
            if m:
                for v in values:
                    if v.key == int(m.group()):
                        return _hit(result, v, "exact", 100.0)
            result.suggestions = [v.display for v in values]
            return result

        norm = normalize(raw)
        index = self._alias_index.get(dimension, {})
        if norm in index:
            v = index[norm]
            method = "exact" if norm == normalize(v.key) else "alias"
            return _hit(result, v, method, 100.0)

        if dim.matching != "exact" and norm:
            choices = list(index.keys())
            best = process.extractOne(norm, choices, scorer=fuzz.ratio)
            if best and best[1] >= ACCEPT_SCORE and len(norm) >= 4:
                return _hit(result, index[best[0]], "fuzzy", float(best[1]))
            seen: list[str] = []
            for alias, _score, _ in process.extract(norm, choices, scorer=fuzz.WRatio, limit=8):
                if _score < SUGGEST_SCORE:
                    break
                display = index[alias].display
                if display not in seen:
                    seen.append(display)
            result.suggestions = seen[:3]
        return result

    def find_terms(self, text_: str) -> dict[str, list[str]]:
        """Measures and dimensions whose name, label or synonym occurs in the text."""
        norm = f" {normalize(text_)} "
        found: dict[str, list[str]] = {"measures": [], "dimensions": []}
        for m in self.model.measures:
            if any(f" {normalize(s)} " in norm for s in [m.name, m.label, *m.synonyms]):
                found["measures"].append(m.name)
        for d in self.model.dimensions:
            if any(f" {normalize(s)} " in norm for s in [d.name, d.label, *d.synonyms]):
                found["dimensions"].append(d.name)
        return found

    # --------------------------------------------------------------- metadata

    def metadata(self, include_values: bool = True) -> dict:
        """Business-friendly catalog for the UI and the LLM prompt."""
        model = self.model
        measures = [
            {
                "name": m.name,
                "label": m.label,
                "description": m.description.strip(),
                "type": m.type,
                "format": m.format,
                "synonyms": m.synonyms,
                "valid_dimensions": model.valid_dimensions(m.name),
                "default_filters": sorted(
                    {model.filters[f].description for s in m.sources for f in m.filters_for(s)}
                ),
            }
            for m in model.measures
        ]
        dimensions = []
        for d in model.dimensions:
            entry: dict = {
                "name": d.name,
                "label": d.label,
                "description": d.description.strip(),
                "type": d.type,
                "synonyms": d.synonyms,
                "grains": d.grains,
                "value_count": len(self.values(d.name)),
            }
            if include_values and d.type != "time":
                entry["values"] = [v.display for v in self.values(d.name)]
            dimensions.append(entry)
        coverage = None
        if self.coverage:
            coverage = {
                "min_date": self.coverage.min_date.isoformat(),
                "max_date": self.coverage.max_date.isoformat(),
                "description": self.coverage.describe(),
                "months": [
                    {
                        "month": m.month_start.isoformat()[:7],
                        "order_count": m.order_count,
                        "status": m.status,
                    }
                    for m in self.coverage.months
                ],
            }
        return {
            "name": model.name,
            "description": model.description.strip(),
            "currency": model.currency,
            "country": model.country,
            "measures": measures,
            "dimensions": dimensions,
            "coverage": coverage,
            "unsupported_concepts": [
                {"name": u.name, "reason": u.reason, "suggestion": u.suggestion}
                for u in model.unsupported_concepts
            ],
        }


def build_value(
    dim: DimensionDef, key: object, display: object, extra_aliases: tuple | list = ()
) -> AllowedValue:
    """Create an AllowedValue with every alias a user might type for it."""
    if dim.value_type == "integer":
        return AllowedValue(key=int(key), display=str(key), aliases=(str(key),))
    key_s = str(key).strip()
    display_s = str(display).strip() if display is not None else key_s
    if display_s == key_s and dim.columns:
        first = next(iter(dim.columns.values()))
        if first.display and first.display.upper().startswith("INITCAP"):
            display_s = key_s.title()
    aliases = {normalize(key_s), normalize(display_s)}
    aliases |= {normalize(a) for a in extra_aliases if a is not None}
    # "Bed, Bath & Table" should also match "bed bath table"
    aliases |= {re.sub(r"\s+", " ", f" {a} ".replace(" and ", " ")).strip() for a in list(aliases)}
    if dim.matching == "state":
        aliases.add(normalize(f"state of {display_s}"))
    return AllowedValue(key=key_s, display=display_s, aliases=tuple(a for a in aliases if a))


def _hit(result: ValueMatch, value: AllowedValue, method: str, score: float) -> ValueMatch:
    result.key, result.display, result.method, result.score = (
        value.key,
        value.display,
        method,
        score,
    )
    return result

"""Load and validate the semantic layer (model.yaml) into typed pydantic models.

Validation is strict and runs at startup: any unknown source, column, filter or
duplicate name raises :class:`SemanticModelError` so a broken model never serves
queries.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import sqlglot
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlglot import exp

MODEL_PATH = Path(__file__).with_name("model.yaml")

Format = Literal["currency", "integer", "decimal", "percent", "days", "rating"]
MeasureType = Literal["sum", "count", "count_distinct", "average", "ratio"]
Grain = Literal["day", "week", "month", "quarter", "year"]
Matching = Literal["state", "fuzzy", "exact"]


class SemanticModelError(ValueError):
    """Raised when model.yaml is malformed or internally inconsistent."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceDef(_Strict):
    """An analytics table that measures and dimensions can be computed on."""

    table: str
    grain: str
    description: str
    time_column: str | None = None
    columns: dict[str, str]

    @field_validator("table")
    @classmethod
    def _analytics_only(cls, v: str) -> str:
        if not v.startswith("analytics."):
            raise ValueError(f"source table '{v}' must be in the analytics schema")
        return v


class Relationship(_Strict):
    """A permitted join between two source columns."""

    from_: str = Field(alias="from")
    to: str
    type: Literal["many_to_one", "one_to_one"]

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    def endpoints(self) -> tuple[tuple[str, str], tuple[str, str]]:
        """Return ((source, column), (source, column))."""
        a, b = self.from_.split("."), self.to.split(".")
        return (a[0], a[1]), (b[0], b[1])


class NamedFilter(_Strict):
    """A reusable business filter such as 'valid orders'."""

    description: str
    sql: str


class MeasureDef(_Strict):
    """A business metric, computable on one or more sources (in preference order)."""

    name: str
    label: str
    description: str
    type: MeasureType
    format: Format
    synonyms: list[str] = []
    sources: dict[str, str]
    default_filters: list[str] = []
    default_filters_by_source: dict[str, list[str]] = {}
    bounds: tuple[float | None, float | None] = (None, None)

    def filters_for(self, source: str) -> list[str]:
        """Named default filters that apply when this measure runs on ``source``."""
        return self.default_filters_by_source.get(source, self.default_filters)


class DimensionColumn(_Strict):
    """How a dimension is expressed on one source."""

    key: str
    display: str | None = None

    @property
    def display_sql(self) -> str:
        return self.display or self.key


class ValuesFrom(_Strict):
    """Where the allowed values of a dimension are read from at startup."""

    source: str
    key: str
    display: str | None = None
    aliases: list[str] = []


class DimensionDef(_Strict):
    """A way to slice or filter measures."""

    name: str
    label: str
    description: str
    type: Literal["time", "categorical"]
    synonyms: list[str] = []
    columns: dict[str, DimensionColumn]
    grains: list[Grain] = []
    default_grain: Grain | None = None
    matching: Matching = "fuzzy"
    value_type: Literal["text", "integer"] = "text"
    exclude_null: bool = False
    values_from: ValuesFrom | None = None


class UnsupportedConcept(_Strict):
    """A concept the data cannot answer, with the reason shown to users."""

    name: str
    keywords: list[str]
    reason: str
    suggestion: str | None = None
    except_: list[str] = Field(default=[], alias="except")

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class SemanticModel(_Strict):
    """The full semantic layer."""

    version: int
    name: str
    description: str
    currency: str
    country: str
    default_time_dimension: str
    sources: dict[str, SourceDef]
    relationships: list[Relationship]
    filters: dict[str, NamedFilter]
    measures: list[MeasureDef]
    dimensions: list[DimensionDef]
    unsupported_concepts: list[UnsupportedConcept]

    # ---- lookups ---------------------------------------------------------

    def measure(self, name: str) -> MeasureDef:
        for m in self.measures:
            if m.name == name:
                return m
        raise KeyError(name)

    def dimension(self, name: str) -> DimensionDef:
        for d in self.dimensions:
            if d.name == name:
                return d
        raise KeyError(name)

    def has_measure(self, name: str) -> bool:
        return any(m.name == name for m in self.measures)

    def has_dimension(self, name: str) -> bool:
        return any(d.name == name for d in self.dimensions)

    def valid_dimensions(self, measure: str) -> list[str]:
        """Dimensions available on at least one source of the measure."""
        sources = set(self.measure(measure).sources)
        return [d.name for d in self.dimensions if sources & set(d.columns)]

    def pick_source(self, measure: str, dimensions: list[str]) -> str | None:
        """First source of ``measure`` that supports every dimension, or None."""
        for source in self.measure(measure).sources:
            if all(source in self.dimension(d).columns for d in dimensions):
                return source
        return None

    def measures_supporting(self, dimensions: list[str]) -> list[str]:
        """Names of measures that can be sliced/filtered by all ``dimensions``."""
        return [m.name for m in self.measures if self.pick_source(m.name, dimensions)]

    def allowed_join_pairs(self) -> set[frozenset[tuple[str, str]]]:
        """Set of {(source, column), (source, column)} pairs that may be joined."""
        return {frozenset(r.endpoints()) for r in self.relationships}


# ---------------------------------------------------------------------------
# Cross-reference validation
# ---------------------------------------------------------------------------


def sql_columns(expression: str) -> set[str]:
    """Column names referenced by a SQL expression (Postgres dialect)."""
    try:
        tree = sqlglot.parse_one(f"SELECT {expression}", read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise SemanticModelError(f"invalid SQL expression {expression!r}: {exc}") from exc
    return {c.name for c in tree.find_all(exp.Column)}


def _check_columns(errors: list[str], where: str, expression: str, source: SourceDef) -> None:
    try:
        missing = sql_columns(expression) - set(source.columns)
    except SemanticModelError as exc:
        errors.append(f"{where}: {exc}")
        return
    if missing:
        errors.append(f"{where}: unknown column(s) {sorted(missing)} in {source.table}")


def validate_model(model: SemanticModel) -> None:
    """Check every reference in the model; raise one error listing all problems."""
    errors: list[str] = []

    names = [m.name for m in model.measures] + [d.name for d in model.dimensions]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        errors.append(f"duplicate measure/dimension names: {sorted(duplicates)}")

    for name, src in model.sources.items():
        if src.time_column and src.time_column not in src.columns:
            errors.append(f"source {name}: time_column '{src.time_column}' not in columns")

    for rel in model.relationships:
        for source, column in rel.endpoints():
            if source not in model.sources:
                errors.append(f"relationship {rel.from_}->{rel.to}: unknown source '{source}'")
            elif column not in model.sources[source].columns:
                errors.append(f"relationship {rel.from_}->{rel.to}: unknown column '{column}'")

    for fname, flt in model.filters.items():
        try:
            sql_columns(flt.sql)
        except SemanticModelError as exc:
            errors.append(f"filter {fname}: {exc}")

    for m in model.measures:
        if not m.sources:
            errors.append(f"measure {m.name}: no sources")
        for source, expression in m.sources.items():
            if source not in model.sources:
                errors.append(f"measure {m.name}: unknown source '{source}'")
                continue
            _check_columns(
                errors, f"measure {m.name} on {source}", expression, model.sources[source]
            )
            for fname in m.filters_for(source):
                if fname not in model.filters:
                    errors.append(f"measure {m.name}: unknown filter '{fname}'")
                else:
                    _check_columns(
                        errors,
                        f"measure {m.name} filter {fname} on {source}",
                        model.filters[fname].sql,
                        model.sources[source],
                    )
        for source in m.default_filters_by_source:
            if source not in m.sources:
                errors.append(f"measure {m.name}: filters given for unused source '{source}'")
        lo, hi = m.bounds
        if lo is not None and hi is not None and lo > hi:
            errors.append(f"measure {m.name}: bounds min > max")

    for d in model.dimensions:
        if not d.columns:
            errors.append(f"dimension {d.name}: no columns")
        for source, col in d.columns.items():
            if source not in model.sources:
                errors.append(f"dimension {d.name}: unknown source '{source}'")
                continue
            _check_columns(
                errors, f"dimension {d.name} key on {source}", col.key, model.sources[source]
            )
            _check_columns(
                errors,
                f"dimension {d.name} display on {source}",
                col.display_sql,
                model.sources[source],
            )
        if d.type == "time":
            if not d.grains or d.default_grain not in d.grains:
                errors.append(
                    f"dimension {d.name}: time dimension needs grains incl. default_grain"
                )
            for source in d.columns:
                if source in model.sources and model.sources[source].time_column is None:
                    errors.append(f"dimension {d.name}: source {source} has no time_column")
        elif d.values_from is None:
            errors.append(f"dimension {d.name}: categorical dimension needs values_from")
        if d.values_from:
            vf = d.values_from
            if vf.source not in model.sources:
                errors.append(f"dimension {d.name}: values_from unknown source '{vf.source}'")
            else:
                for expr in filter(None, (vf.key, vf.display, *vf.aliases)):
                    _check_columns(
                        errors, f"dimension {d.name} values_from", expr, model.sources[vf.source]
                    )

    if not model.has_dimension(model.default_time_dimension):
        errors.append(f"default_time_dimension '{model.default_time_dimension}' is not a dimension")

    seen: dict[str, str] = {}
    for m in model.measures:
        for syn in [m.name, m.label, *m.synonyms]:
            key = syn.strip().lower()
            if key in seen and seen[key] != m.name:
                errors.append(f"synonym '{syn}' used by both {seen[key]} and {m.name}")
            seen[key] = m.name

    if errors:
        raise SemanticModelError("Invalid semantic model:\n  - " + "\n  - ".join(errors))


def load_model(path: Path = MODEL_PATH) -> SemanticModel:
    """Parse, type-check and cross-validate a semantic model file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SemanticModelError(f"cannot read semantic model {path}: {exc}") from exc
    try:
        model = SemanticModel.model_validate(raw)
    except ValidationError as exc:
        raise SemanticModelError(f"Invalid semantic model {path}:\n{exc}") from exc
    validate_model(model)
    return model


@lru_cache(maxsize=1)
def get_model() -> SemanticModel:
    """The application's semantic model (loaded once)."""
    return load_model()

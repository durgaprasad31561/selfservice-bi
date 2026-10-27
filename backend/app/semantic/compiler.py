"""Compile a semantic query plan into SQL — deterministically, from model.yaml only.

Guarantees:
* each measure is aggregated on its own source table (its own grain);
* measures from different sources/filters are aggregated separately and then
  joined on the requested dimensions, so rows are never multiplied;
* default business filters are always applied;
* every user value is a bound parameter (``:p0``, ``:p1`` ...);
* invalid measure/dimension combinations are refused, never approximated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.schemas.plan import PlanFilter, QueryPlan
from app.semantic.loader import DimensionDef, MeasureDef, SemanticModel

GRAIN_LABEL = {"day": "Day", "week": "Week", "month": "Month", "quarter": "Quarter", "year": "Year"}
OPERATOR_TEXT = {
    "=": "is",
    "!=": "is not",
    "in": "is one of",
    "not_in": "is not one of",
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
    "between": "between",
}


class CompileError(ValueError):
    """The plan cannot be compiled; ``code`` is machine-readable, message is user-facing."""

    def __init__(self, code: str, message: str, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestion = suggestion


@dataclass
class ResultColumn:
    """Metadata for one output column."""

    name: str
    label: str
    role: str  # dimension | measure
    format: str | None = None  # measure format
    dimension_type: str | None = None  # time | categorical
    grain: str | None = None


@dataclass
class CompiledQuery:
    """SQL plus everything needed to execute and explain it."""

    sql: str
    params: dict[str, object]
    columns: list[ResultColumn]
    sources: list[str]
    definitions: list[dict[str, str]]
    business_rules: list[str]
    filters_applied: list[str]
    time_range_text: str | None
    limit: int
    measures: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)

    @property
    def display_sql(self) -> str:
        """SQL with parameters inlined as literals — for showing to users only."""
        return inline_params(self.sql, self.params)


# ---------------------------------------------------------------------------


class _Params:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def bind(self, value: object) -> str:
        name = f"p{len(self.values)}"
        self.values[name] = value
        return f":{name}"


def _time_expr(column: str, grain: str) -> str:
    if grain == "day":
        return column
    if grain == "year":
        return f"EXTRACT(YEAR FROM {column})::int"
    return f"date_trunc('{grain}', {column})::date"


def _coerce(dim: DimensionDef, value: object) -> object:
    """Convert a plan value to the Python type the column expects."""
    if dim.type == "time":
        if isinstance(value, date | datetime):
            return value if isinstance(value, date) else value.date()
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError as exc:
            raise CompileError(
                "invalid_filter", f"'{value}' is not a valid date for {dim.label} (use YYYY-MM-DD)."
            ) from exc
    if dim.value_type == "integer":
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise CompileError("invalid_filter", f"'{value}' is not a valid {dim.label}.") from exc
    return str(value)


def _filter_sql(key: str, flt: PlanFilter, dim: DimensionDef, params: _Params) -> str:
    values = [_coerce(dim, v) for v in flt.values()]
    if not values:
        raise CompileError("invalid_filter", f"The filter on {dim.label} has no value.")
    op = flt.operator
    if op in ("=", "!=") and len(values) > 1:
        op = "in" if op == "=" else "not_in"
    if op in ("in", "not_in"):
        placeholders = ", ".join(params.bind(v) for v in values)
        return f"{key} {'IN' if op == 'in' else 'NOT IN'} ({placeholders})"
    if op == "between":
        if len(values) != 2:
            raise CompileError("invalid_filter", f"'between' on {dim.label} needs two values.")
        return f"{key} BETWEEN {params.bind(values[0])} AND {params.bind(values[1])}"
    if len(values) != 1:
        raise CompileError("invalid_filter", f"Operator {op} on {dim.label} takes one value.")
    sql_op = "<>" if op == "!=" else op
    return f"{key} {sql_op} {params.bind(values[0])}"


def _measure_filter_sql(name: str, flt: PlanFilter, params: _Params) -> str:
    try:
        values = [float(v) for v in flt.values()]
    except (TypeError, ValueError) as exc:
        raise CompileError("invalid_filter", f"Filters on {name} need numeric values.") from exc
    if flt.operator == "between":
        if len(values) != 2:
            raise CompileError("invalid_filter", f"'between' on {name} needs two values.")
        return f"{name} BETWEEN {params.bind(values[0])} AND {params.bind(values[1])}"
    if flt.operator in ("in", "not_in") or len(values) != 1:
        raise CompileError("invalid_filter", f"Unsupported filter on measure {name}.")
    sql_op = "<>" if flt.operator == "!=" else flt.operator
    return f"{name} {sql_op} {params.bind(values[0])}"


def _labels(model: SemanticModel, names: list[str]) -> str:
    labels = [model.dimension(n).label for n in names]
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def _incompatible(model: SemanticModel, measure: MeasureDef, required: list[str]) -> CompileError:
    unsupported = [
        d for d in required if not any(s in model.dimension(d).columns for s in measure.sources)
    ]
    if unsupported:
        message = (
            f"{measure.label} cannot be broken down or filtered by {_labels(model, unsupported)}"
        )
        reason = {
            "fact_orders": "it is measured per order",
            "fact_payments": "it is measured per payment",
            "fact_order_items": "it is measured per item",
        }.get(next(iter(measure.sources)), "")
        if reason:
            message += f", because {reason}"
        message += "."
    else:
        message = (
            f"{measure.label} cannot be combined with {_labels(model, required)} "
            "in the same question."
        )
    alternatives = [model.measure(n).label for n in model.measures_supporting(required)]
    suggestion = None
    if alternatives:
        suggestion = "Measures that support this: " + ", ".join(alternatives[:6]) + "."
    return CompileError("incompatible", message, suggestion)


# ---------------------------------------------------------------------------


def compile_plan(plan: QueryPlan, model: SemanticModel, max_rows: int = 1000) -> CompiledQuery:
    """Turn a QueryPlan into a parameterized SQL query."""
    if not plan.measures:
        raise CompileError("no_measures", "The question does not ask for any measurable value.")

    measures: list[MeasureDef] = []
    for name in dict.fromkeys(plan.measures):
        if not model.has_measure(name):
            raise CompileError("unknown_measure", f"'{name}' is not a known measure.")
        measures.append(model.measure(name))

    time_name = model.default_time_dimension
    dims = list(dict.fromkeys(plan.dimensions))
    for d in dims:
        if not model.has_dimension(d):
            raise CompileError("unknown_dimension", f"'{d}' is not a known dimension.")
    if plan.time_grain and time_name not in dims:
        dims.insert(0, time_name)
    time_dim = model.dimension(time_name)
    grain = None
    if time_name in dims:
        grain = plan.time_grain or time_dim.default_grain
        if grain not in time_dim.grains:
            raise CompileError("invalid_grain", f"Time grain '{grain}' is not supported.")

    dim_filters: list[PlanFilter] = []
    measure_filters: list[PlanFilter] = []
    for f in plan.filters:
        if model.has_dimension(f.dimension):
            dim_filters.append(f)
        elif model.has_measure(f.dimension):
            if f.dimension not in [m.name for m in measures]:
                raise CompileError(
                    "invalid_filter",
                    f"To filter on {model.measure(f.dimension).label}, it must also be requested.",
                )
            measure_filters.append(f)
        else:
            raise CompileError("unknown_dimension", f"'{f.dimension}' is not a known dimension.")

    required = list(dict.fromkeys(dims + [f.dimension for f in dim_filters]))

    # Pick a source per measure and group measures that can share one aggregate query.
    groups: dict[tuple[str, tuple[str, ...]], list[MeasureDef]] = {}
    for m in measures:
        source = model.pick_source(m.name, required)
        if source is None:
            raise _incompatible(model, m, required)
        groups.setdefault((source, tuple(m.filters_for(source))), []).append(m)

    params = _Params()
    dim_aliases = dims  # output column name == dimension name

    def dim_select(dim: DimensionDef, source: str) -> tuple[str, str]:
        col = dim.columns[source]
        expr = _time_expr(col.key, grain or "day") if dim.type == "time" else col.display_sql
        return expr, col.key

    group_sql: list[str] = []
    business_rules: list[str] = []
    for (source, filter_names), group_measures in groups.items():
        src = model.sources[source]
        selects, group_by, where = [], [], []
        for d in dims:
            dim = model.dimension(d)
            expr, key = dim_select(dim, source)
            selects.append(f"{expr} AS {d}")
            group_by.append(expr)
            if dim.exclude_null:
                where.append(f"{key} IS NOT NULL")
        for m in group_measures:
            selects.append(f"{m.sources[source].strip()} AS {m.name}")
        for fname in filter_names:
            where.append(model.filters[fname].sql)
            rule = model.filters[fname].description
            labels = ", ".join(x.label for x in group_measures)
            business_rules.append(f"{labels}: {rule}")
        for f in dim_filters:
            dim = model.dimension(f.dimension)
            where.append(_filter_sql(dim.columns[source].key, f, dim, params))
        if plan.time_range:
            where.append(
                f"{src.time_column} BETWEEN {params.bind(plan.time_range.start)} "
                f"AND {params.bind(plan.time_range.end)}"
            )
        sql = f"SELECT {', '.join(selects)}\nFROM {src.table}"
        if where:
            sql += "\nWHERE " + "\n  AND ".join(where)
        if group_by:
            sql += "\nGROUP BY " + ", ".join(group_by)
        group_sql.append(sql)

    if len(group_sql) == 1:
        body = group_sql[0]
    else:
        names = [f"g{i + 1}" for i in range(len(group_sql))]
        ctes = [f"{n} AS (\n{s}\n)" for n, s in zip(names, group_sql, strict=True)]
        measure_cols = [
            f"{n}.{m.name}" for n, (_, ms) in zip(names, groups.items(), strict=True) for m in ms
        ]
        if dim_aliases:
            dim_list = ", ".join(dim_aliases)
            keys = "\nUNION\n".join(f"SELECT {dim_list} FROM {n}" for n in names)
            ctes.append(f"dim_keys AS (\n{keys}\n)")
            joins = "\n".join(
                f"LEFT JOIN {n} ON "
                + " AND ".join(f"{n}.{d} IS NOT DISTINCT FROM dim_keys.{d}" for d in dim_aliases)
                for n in names
            )
            select = ", ".join([f"dim_keys.{d}" for d in dim_aliases] + measure_cols)
            body = f"WITH {', '.join(ctes)}\nSELECT {select}\nFROM dim_keys\n{joins}"
        else:
            body = (
                f"WITH {', '.join(ctes)}\nSELECT {', '.join(measure_cols)}\nFROM "
                + " CROSS JOIN ".join(names)
            )

    if measure_filters:
        conds = " AND ".join(_measure_filter_sql(f.dimension, f, params) for f in measure_filters)
        body = f"SELECT *\nFROM (\n{body}\n) AS result\nWHERE {conds}"

    output_names = dim_aliases + [m.name for m in measures]
    order_parts: list[str] = []
    for ob in plan.order_by:
        if ob.field not in output_names:
            raise CompileError(
                "invalid_order", f"Cannot sort by '{ob.field}': it is not in the result."
            )
        order_parts.append(f"{ob.field} {ob.direction.upper()} NULLS LAST")
    if not order_parts:
        if time_name in dims:
            order_parts.append(f"{time_name} ASC")
        elif any(model.dimension(d).value_type == "integer" for d in dims):
            order_parts.extend(f"{d} ASC" for d in dims)
        elif dims:
            order_parts.append(f"{measures[0].name} DESC NULLS LAST")
    if dims:
        # deterministic tie-break
        order_parts.extend(
            f"{d} ASC" for d in dims if not any(p.startswith(f"{d} ") for p in order_parts)
        )

    limit = min(plan.limit or max_rows, max_rows)
    sql = body
    if order_parts:
        sql += "\nORDER BY " + ", ".join(order_parts)
    sql += f"\nLIMIT {limit}"

    columns = [
        ResultColumn(
            name=d,
            label=(
                f"Order {GRAIN_LABEL[grain]}"
                if d == time_name and grain
                else model.dimension(d).label
            ),
            role="dimension",
            dimension_type=model.dimension(d).type,
            grain=grain if d == time_name else None,
        )
        for d in dims
    ] + [
        ResultColumn(name=m.name, label=m.label, role="measure", format=m.format) for m in measures
    ]

    sources_used = list(dict.fromkeys(model.sources[s].table for s, _ in groups))
    definitions = [
        {"name": m.name, "label": m.label, "definition": " ".join(m.description.split())}
        for m in measures
    ]
    filters_applied = [_describe_filter(model, f) for f in plan.filters]
    time_text = None
    if plan.time_range:
        tr = plan.time_range
        time_text = f"Order date from {tr.start.isoformat()} to {tr.end.isoformat()}"
    return CompiledQuery(
        sql=sql,
        params=params.values,
        columns=columns,
        sources=sources_used,
        definitions=definitions,
        business_rules=list(dict.fromkeys(business_rules)),
        filters_applied=filters_applied,
        time_range_text=time_text,
        limit=limit,
        measures=[m.name for m in measures],
        dimensions=dims,
    )


def _describe_filter(model: SemanticModel, f: PlanFilter) -> str:
    label = (
        model.dimension(f.dimension).label
        if model.has_dimension(f.dimension)
        else model.measure(f.dimension).label
    )
    value = ", ".join(str(v) for v in f.values())
    return f"{label} {OPERATOR_TEXT[f.operator]} {value}"


def _literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, datetime):
        return f"TIMESTAMP '{value.isoformat(sep=' ')}'"
    if isinstance(value, date):
        return f"DATE '{value.isoformat()}'"
    return "'" + str(value).replace("'", "''") + "'"


def inline_params(sql: str, params: dict[str, object]) -> str:
    """Replace :pN placeholders with SQL literals (display only, never executed)."""
    return re.sub(
        r"(?<![:\w]):(p\d+)\b",
        lambda m: _literal(params[m.group(1)]) if m.group(1) in params else m.group(0),
        sql,
    )

"""Compiler: plan -> SQL rules (offline) and execution of every combination (database)."""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlglot
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.schemas.plan import QueryPlan
from app.semantic.compiler import CompileError, compile_plan, inline_params
from app.semantic.loader import SemanticModel


def plan(**kwargs) -> QueryPlan:
    return QueryPlan(**kwargs)


def parses(sql: str) -> None:
    sqlglot.parse_one(sql, read="postgres")


# ---------------------------------------------------------------- offline rules


def test_simple_total_sales(model: SemanticModel) -> None:
    q = compile_plan(plan(measures=["total_sales"]), model)
    assert "SUM(order_revenue)" in q.sql
    assert "FROM analytics.fact_orders" in q.sql
    assert "order_status NOT IN ('canceled', 'unavailable')" in q.sql
    assert q.business_rules == ["Total Sales: Excludes canceled and unavailable orders."]
    parses(q.sql)


def test_values_are_parameterized(model: SemanticModel) -> None:
    q = compile_plan(
        plan(
            measures=["total_sales"],
            filters=[{"dimension": "customer_city", "value": "sao paulo'; DROP TABLE x;--"}],
        ),
        model,
    )
    assert "DROP" not in q.sql and ":p0" in q.sql
    assert q.params["p0"] == "sao paulo'; DROP TABLE x;--"
    assert "'sao paulo''; DROP TABLE x;--'" in q.display_sql  # quotes escaped for display


def test_time_range_and_grain(model: SemanticModel) -> None:
    q = compile_plan(
        plan(
            measures=["order_count"],
            time_grain="month",
            time_range={"start": "2018-01-01", "end": "2018-06-30"},
        ),
        model,
    )
    assert "date_trunc('month', purchase_date)::date AS order_date" in q.sql
    assert "purchase_date BETWEEN :p0 AND :p1" in q.sql
    assert "ORDER BY order_date ASC" in q.sql
    assert q.columns[0].label == "Order Month" and q.columns[0].grain == "month"


@pytest.mark.parametrize(
    "grain, fragment",
    [
        ("day", "purchase_date AS order_date"),
        ("week", "date_trunc('week', purchase_date)"),
        ("quarter", "date_trunc('quarter', purchase_date)"),
        ("year", "EXTRACT(YEAR FROM purchase_date)::int"),
    ],
)
def test_all_grains(model: SemanticModel, grain: str, fragment: str) -> None:
    q = compile_plan(
        plan(measures=["total_sales"], dimensions=["order_date"], time_grain=grain), model
    )
    assert fragment in q.sql


def test_time_dimension_defaults_to_month(model: SemanticModel) -> None:
    q = compile_plan(plan(measures=["total_sales"], dimensions=["order_date"]), model)
    assert "date_trunc('month'" in q.sql


def test_incompatible_combination_refused(model: SemanticModel) -> None:
    with pytest.raises(CompileError) as err:
        compile_plan(plan(measures=["total_sales"], dimensions=["product_category"]), model)
    assert err.value.code == "incompatible"
    assert "Product Sales" in (err.value.suggestion or "")


def test_incompatible_filter_refused(model: SemanticModel) -> None:
    with pytest.raises(CompileError, match="Product Category"):
        compile_plan(
            plan(
                measures=["average_order_value"],
                filters=[{"dimension": "product_category", "value": "Toys"}],
            ),
            model,
        )


def test_incompatible_pair_refused(model: SemanticModel) -> None:
    # product_sales supports category (items) and payment type (orders) but not both at once
    with pytest.raises(CompileError) as err:
        compile_plan(
            plan(measures=["product_sales"], dimensions=["product_category", "payment_type"]), model
        )
    assert "cannot be combined" in err.value.message


def test_source_preference(model: SemanticModel) -> None:
    q = compile_plan(
        plan(
            measures=["average_rating"],
            filters=[{"dimension": "product_category", "value": "Toys"}],
        ),
        model,
    )
    assert q.sources == ["analytics.fact_order_items"]
    q = compile_plan(plan(measures=["average_rating"], dimensions=["payment_type"]), model)
    assert q.sources == ["analytics.fact_orders"]


def test_multi_source_never_joins_facts_directly(model: SemanticModel) -> None:
    q = compile_plan(
        plan(measures=["total_sales", "items_sold"], dimensions=["customer_state"]), model
    )
    assert "WITH g1 AS" in q.sql and "dim_keys" in q.sql
    assert "JOIN analytics." not in q.sql  # facts are aggregated separately
    parses(q.sql)


def test_multi_source_without_dimensions_cross_joins_single_rows(model: SemanticModel) -> None:
    q = compile_plan(plan(measures=["total_sales", "items_sold"]), model)
    assert "CROSS JOIN" in q.sql
    parses(q.sql)


def test_same_source_shares_query(model: SemanticModel) -> None:
    q = compile_plan(plan(measures=["total_sales", "average_order_value"]), model)
    assert "WITH" not in q.sql and q.sql.count("FROM analytics.fact_orders") == 1


def test_exclude_null_dimension(model: SemanticModel) -> None:
    q = compile_plan(plan(measures=["order_count"], dimensions=["rating"]), model)
    assert "ROUND(review_score)::int IS NOT NULL" in q.sql
    assert "ORDER BY rating ASC" in q.sql


def test_limit_capped(model: SemanticModel) -> None:
    q = compile_plan(
        plan(measures=["total_sales"], dimensions=["customer_city"], limit=50_000),
        model,
        max_rows=1000,
    )
    assert q.sql.endswith("LIMIT 1000") and q.limit == 1000
    q = compile_plan(plan(measures=["total_sales"], dimensions=["customer_city"], limit=5), model)
    assert q.sql.endswith("LIMIT 5")


def test_order_by(model: SemanticModel) -> None:
    q = compile_plan(
        plan(
            measures=["product_sales"],
            dimensions=["product_category"],
            order_by=[{"field": "product_sales", "direction": "asc"}],
        ),
        model,
    )
    assert "ORDER BY product_sales ASC NULLS LAST" in q.sql
    with pytest.raises(CompileError, match="Cannot sort"):
        compile_plan(plan(measures=["total_sales"], order_by=[{"field": "price"}]), model)


def test_in_and_between_filters(model: SemanticModel) -> None:
    q = compile_plan(
        plan(
            measures=["order_count"],
            filters=[
                {"dimension": "customer_state", "operator": "in", "value": ["SP", "RJ"]},
                {"dimension": "rating", "operator": "between", "value": [4, 5]},
            ],
        ),
        model,
    )
    assert "customer_state IN (:p0, :p1)" in q.sql
    assert "ROUND(review_score)::int BETWEEN :p2 AND :p3" in q.sql
    assert q.params == {"p0": "SP", "p1": "RJ", "p2": 4, "p3": 5}


def test_measure_filter(model: SemanticModel) -> None:
    q = compile_plan(
        plan(
            measures=["product_sales"],
            dimensions=["product_category"],
            filters=[{"dimension": "product_sales", "operator": ">", "value": 500000}],
        ),
        model,
    )
    assert "AS result\nWHERE product_sales > :p0" in q.sql
    with pytest.raises(CompileError, match="must also be requested"):
        compile_plan(
            plan(
                measures=["order_count"],
                filters=[{"dimension": "product_sales", "operator": ">", "value": 1}],
            ),
            model,
        )


@pytest.mark.parametrize(
    "bad, code",
    [
        (dict(measures=[]), "no_measures"),
        (dict(measures=["profit"]), "unknown_measure"),
        (dict(measures=["total_sales"], dimensions=["planet"]), "unknown_dimension"),
        (
            dict(measures=["total_sales"], filters=[{"dimension": "planet", "value": "x"}]),
            "unknown_dimension",
        ),
        (
            dict(measures=["total_sales"], filters=[{"dimension": "rating", "value": "five"}]),
            "invalid_filter",
        ),
        (
            dict(measures=["total_sales"], filters=[{"dimension": "order_date", "value": "soon"}]),
            "invalid_filter",
        ),
        (
            dict(
                measures=["total_sales"],
                filters=[{"dimension": "rating", "operator": "between", "value": [1]}],
            ),
            "invalid_filter",
        ),
    ],
)
def test_invalid_plans(model: SemanticModel, bad: dict, code: str) -> None:
    with pytest.raises(CompileError) as err:
        compile_plan(plan(**bad), model)
    assert err.value.code == code


def test_explanation_fields(model: SemanticModel) -> None:
    q = compile_plan(
        plan(
            measures=["late_delivery_rate"],
            filters=[{"dimension": "customer_state", "value": "RJ"}],
            time_range={"start": "2018-01-01", "end": "2018-12-31", "label": "2018"},
        ),
        model,
    )
    assert q.definitions[0]["label"] == "Late Delivery Rate"
    assert q.filters_applied == ["Customer State is RJ"]
    assert q.time_range_text == "Order date from 2018-01-01 to 2018-12-31"


def test_inline_params_does_not_touch_casts() -> None:
    sql = "SELECT ROUND(x)::int FROM t WHERE a = :p0 AND b = :p10"
    assert inline_params(sql, {"p0": "it's", "p10": 3}) == (
        "SELECT ROUND(x)::int FROM t WHERE a = 'it''s' AND b = 3"
    )


# ------------------------------------------------------------ with the database


def run(engine: Engine, model: SemanticModel, **kwargs) -> list:
    q = compile_plan(plan(**kwargs), model)
    with engine.connect() as conn:
        return conn.execute(text(q.sql), q.params).all()


def all_single_combinations(model: SemanticModel) -> list[tuple[str, str | None]]:
    combos: list[tuple[str, str | None]] = []
    for m in model.measures:
        combos.append((m.name, None))
        combos.extend((m.name, d) for d in model.valid_dimensions(m.name))
    return combos


@pytest.mark.integration
def test_every_measure_dimension_combination_executes(
    model: SemanticModel, reader_engine: Engine
) -> None:
    failures = []
    combos = all_single_combinations(model)
    with reader_engine.connect() as conn:
        for measure, dim in combos:
            q = compile_plan(
                plan(measures=[measure], dimensions=[dim] if dim else [], limit=50), model
            )
            try:
                rows = conn.execute(text(q.sql), q.params).all()
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{measure} x {dim}: {exc}")
                conn.rollback()
                continue
            if not rows:
                failures.append(f"{measure} x {dim}: no rows")
            lo, hi = model.measure(measure).bounds
            for row in rows:
                value = row[-1]
                if value is None:
                    continue
                if (lo is not None and value < lo) or (hi is not None and value > hi):
                    failures.append(f"{measure} x {dim}: {value} outside {lo}..{hi}")
                    break
    assert len(combos) > 150
    assert not failures, "\n".join(failures)


@pytest.mark.integration
def test_reference_totals(model: SemanticModel, reader_engine: Engine) -> None:
    with reader_engine.connect() as conn:
        ref = conn.execute(
            text(
                "SELECT SUM(order_revenue) FROM analytics.fact_orders "
                "WHERE order_status NOT IN ('canceled','unavailable')"
            )
        ).scalar()
        ref_2017 = conn.execute(
            text("SELECT COUNT(*) FROM analytics.fact_orders WHERE purchase_year = 2017")
        ).scalar()
    assert run(reader_engine, model, measures=["total_sales"])[0][0] == ref
    # same total whether computed from orders or from payments split by type
    by_type = run(reader_engine, model, measures=["payment_amount"], dimensions=["payment_type"])
    assert sum(r[1] for r in by_type) == ref
    assert run(reader_engine, model, measures=["customer_count"])[0][0] == 96_096
    assert run(reader_engine, model, measures=["order_count"])[0][0] == 99_441
    assert (
        run(
            reader_engine,
            model,
            measures=["order_count"],
            time_range={"start": "2017-01-01", "end": "2017-12-31"},
        )[0][0]
        == ref_2017
    )
    assert run(reader_engine, model, measures=["repeat_customers"])[0][0] == 2_997


@pytest.mark.integration
def test_category_sales_add_up(model: SemanticModel, reader_engine: Engine) -> None:
    total = run(reader_engine, model, measures=["product_sales"])[0][0]
    rows = run(reader_engine, model, measures=["product_sales"], dimensions=["product_category"])
    assert sum(r[1] for r in rows) == total
    assert rows[0][0] == "Health & Beauty"


@pytest.mark.integration
def test_multi_measure_matches_single(model: SemanticModel, reader_engine: Engine) -> None:
    combined = {
        r[0]: (r[1], r[2])
        for r in run(
            reader_engine,
            model,
            measures=["total_sales", "items_sold"],
            dimensions=["customer_state"],
        )
    }
    sales = dict(run(reader_engine, model, measures=["total_sales"], dimensions=["customer_state"]))
    items = dict(run(reader_engine, model, measures=["items_sold"], dimensions=["customer_state"]))
    assert len(combined) == 27
    for state, (s, i) in combined.items():
        assert s == sales[state] and i == items[state]


@pytest.mark.integration
def test_sao_paulo_2018(model: SemanticModel, reader_engine: Engine) -> None:
    value = run(
        reader_engine,
        model,
        measures=["total_sales"],
        filters=[{"dimension": "customer_city", "value": "sao paulo"}],
        time_range={"start": "2018-01-01", "end": "2018-12-31"},
    )[0][0]
    assert value == Decimal("1270521.80")


@pytest.mark.integration
def test_reader_cannot_write(reader_engine: Engine) -> None:
    with reader_engine.connect() as conn, pytest.raises(DBAPIError):
        conn.execute(text("CREATE TABLE analytics.hack (i int)"))

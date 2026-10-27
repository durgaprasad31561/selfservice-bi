"""SQL validator: every dangerous pattern is blocked; legitimate analytics SQL passes.
Executor: read-only role, timeout, row cap (integration)."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from app.safety.sql_validator import SQLValidator
from app.schemas.plan import QueryPlan
from app.semantic.compiler import compile_plan
from app.semantic.loader import SemanticModel


@pytest.fixture(scope="module")
def validator(model: SemanticModel) -> SQLValidator:
    return SQLValidator(model, max_rows=1000)


# Each entry: (sql, fragment expected in one of the errors)
BLOCKED = {
    # statement types
    "drop": ("DROP TABLE analytics.fact_orders", "Only SELECT"),
    "delete": ("DELETE FROM analytics.fact_orders", "Only SELECT"),
    "update": ("UPDATE analytics.fact_orders SET order_revenue = 0", "Only SELECT"),
    "insert": ("INSERT INTO analytics.fact_orders (order_id) VALUES ('x')", "Only SELECT"),
    "truncate": ("TRUNCATE analytics.fact_orders", "Only SELECT"),
    "alter": ("ALTER TABLE analytics.fact_orders ADD COLUMN x int", "Only SELECT"),
    "create": ("CREATE TABLE analytics.x AS SELECT 1", "Only SELECT"),
    "grant": ("GRANT SELECT ON raw.orders TO bi_reader", "Only SELECT"),
    "copy": ("COPY analytics.fact_orders TO '/tmp/x.csv'", "Only SELECT"),
    "copy program": ("COPY (SELECT 1) TO PROGRAM 'calc.exe'", "Only SELECT"),
    "set": ("SET statement_timeout = 0", "Only SELECT"),
    "multiple": ("SELECT order_id FROM analytics.fact_orders; DROP TABLE x", "single statement"),
    "trailing stmt": ("SELECT 1 FROM analytics.fact_orders; SELECT 2", "single statement"),
    "cte delete": (
        "WITH d AS (DELETE FROM analytics.fact_orders RETURNING *) SELECT * FROM d",
        "DELETE",
    ),
    "cte update": (
        "WITH u AS (UPDATE analytics.fact_orders SET item_count = 0 RETURNING 1) "
        "SELECT * FROM u",
        "UPDATE",
    ),
    "select into": ("SELECT * INTO analytics.copy FROM analytics.fact_orders", "INTO"),
    "for update": ("SELECT * FROM analytics.fact_orders FOR UPDATE", "locking"),
    # comments hiding statements
    "line comment": ("SELECT order_id FROM analytics.fact_orders -- ; DROP TABLE x", "Comments"),
    "block comment": (
        "SELECT order_id /* ; DELETE FROM x */ FROM analytics.fact_orders",
        "Comments",
    ),
    # schemas / tables
    "raw schema": ("SELECT * FROM raw.orders", "analytics schema"),
    "app schema": ("SELECT email, password_hash FROM app.users", "analytics schema"),
    "pg_catalog": ("SELECT usename, passwd FROM pg_catalog.pg_shadow", "analytics schema"),
    "information_schema": ("SELECT * FROM information_schema.tables", "analytics schema"),
    "unknown table": ("SELECT * FROM analytics.secret_table", "not part of the semantic layer"),
    "unqualified unknown": ("SELECT * FROM pg_user", "not part of the semantic layer"),
    "cross database": ("SELECT * FROM otherdb.analytics.fact_orders", "cross-database"),
    "union to raw": (
        "SELECT order_id FROM analytics.fact_orders UNION " "SELECT order_id FROM raw.orders",
        "analytics schema",
    ),
    "subquery to raw": (
        "SELECT * FROM analytics.fact_orders WHERE order_id IN "
        "(SELECT order_id FROM raw.orders)",
        "analytics schema",
    ),
    "meta table": ("SELECT * FROM analytics.meta_data_coverage", "not part of the semantic layer"),
    # columns
    "unknown column": ("SELECT secret FROM analytics.fact_orders", "does not exist"),
    "system column": ("SELECT ctid, xmin FROM analytics.fact_orders", "does not exist"),
    "wrong table column": ("SELECT o.price FROM analytics.fact_orders o", "does not exist"),
    # functions
    "pg_sleep": ("SELECT pg_sleep(10) FROM analytics.fact_orders", "pg_sleep"),
    "pg_read_file": ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    "pg_ls_dir": ("SELECT pg_ls_dir('.')", "pg_ls_dir"),
    "dblink": ("SELECT * FROM dblink('host=x', 'select 1') AS t(a int)", "dblink"),
    "lo_import": ("SELECT lo_import('C:/secret.txt')", "lo_import"),
    "lo_export": ("SELECT lo_export(1, 'C:/x')", "lo_export"),
    "set_config": (
        "SELECT set_config('statement_timeout', '0', false) " "FROM analytics.fact_orders",
        "set_config",
    ),
    "current_setting": (
        "SELECT current_setting('data_directory') FROM analytics.fact_orders",
        "current_setting",
    ),
    "version": ("SELECT version() FROM analytics.dim_states", "not allowed"),
    "terminate": (
        "SELECT pg_terminate_backend(1) FROM analytics.dim_states",
        "pg_terminate_backend",
    ),
    "generate_series": (
        "SELECT generate_series(1, 100000000) FROM analytics.dim_states",
        "not allowed",
    ),
    "unknown function": ("SELECT my_udf(order_id) FROM analytics.fact_orders", "allowed list"),
    # joins
    "comma join": (
        "SELECT COUNT(*) FROM analytics.fact_orders, analytics.fact_order_items",
        "cartesian",
    ),
    "cross join": (
        "SELECT COUNT(*) FROM analytics.fact_orders CROSS JOIN analytics.fact_payments",
        "cartesian",
    ),
    "items x payments": (
        "SELECT SUM(p.payment_value) FROM analytics.fact_order_items i "
        "JOIN analytics.fact_payments p ON i.order_id = p.order_id",
        "not a declared relationship",
    ),
    "undeclared key": (
        "SELECT COUNT(*) FROM analytics.fact_orders o JOIN analytics.dim_states s "
        "ON o.customer_city = s.state_name",
        "not a declared relationship",
    ),
    "non-equi join": (
        "SELECT COUNT(*) FROM analytics.fact_orders o JOIN analytics.dim_states s "
        "ON o.customer_state <> s.state_code",
        "equality",
    ),
    "fan-out sum": (
        "SELECT SUM(o.order_revenue) FROM analytics.fact_order_items i "
        "JOIN analytics.fact_orders o ON i.order_id = o.order_id",
        "double count",
    ),
    "three facts": (
        "SELECT COUNT(*) FROM analytics.fact_order_items i JOIN analytics.fact_orders o "
        "ON i.order_id = o.order_id JOIN analytics.fact_payments p "
        "ON p.order_id = o.order_id",
        "more than two fact tables",
    ),
    # misc
    "no table": ("SELECT 16008872 AS revenue", "must read from the analytics tables"),
    "parameter": ("SELECT * FROM analytics.fact_orders WHERE order_id = :id", "parameters"),
    "recursive": (
        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) " "SELECT n FROM r",
        "Recursive",
    ),
    "limit expression": ("SELECT order_id FROM analytics.fact_orders LIMIT (SELECT 5)", "literal"),
    "garbage": ("SELEC * FORM x", ""),
    "empty": ("   ", "empty"),
}


@pytest.mark.parametrize("name", list(BLOCKED))
def test_dangerous_sql_blocked(validator: SQLValidator, name: str) -> None:
    sql, fragment = BLOCKED[name]
    result = validator.validate(sql)
    assert not result.ok, f"{name} was accepted"
    assert fragment.lower() in result.message.lower(), result.message


ALLOWED = {
    "simple": "SELECT SUM(order_revenue) AS s FROM analytics.fact_orders LIMIT 1",
    "unqualified table": "SELECT COUNT(*) AS n FROM fact_orders LIMIT 1",
    "declared join": (
        "SELECT s.state_name, COUNT(*) AS n FROM analytics.fact_orders o "
        "JOIN analytics.dim_states s ON s.state_code = o.customer_state "
        "GROUP BY s.state_name LIMIT 50"
    ),
    "date join": (
        "SELECT d.day_name, COUNT(o.order_id) AS n FROM analytics.fact_orders o "
        "JOIN analytics.dim_date d ON o.purchase_date = d.date_day "
        "GROUP BY d.day_name ORDER BY n DESC LIMIT 7"
    ),
    "item to order distinct": (
        "SELECT i.category_label, COUNT(DISTINCT o.order_id) AS orders "
        "FROM analytics.fact_order_items i JOIN analytics.fact_orders o "
        "ON i.order_id = o.order_id GROUP BY 1 LIMIT 10"
    ),
    "cte": (
        "WITH t AS (SELECT seller_id, SUM(price) AS sales FROM analytics.fact_order_items "
        "GROUP BY seller_id) SELECT seller_id, sales FROM t ORDER BY sales DESC LIMIT 5"
    ),
    "window": (
        "SELECT category_label, SUM(price) AS s, RANK() OVER (ORDER BY SUM(price) DESC) "
        "AS r FROM analytics.fact_order_items GROUP BY category_label LIMIT 10"
    ),
    "case/filter": (
        "SELECT 100.0 * COUNT(*) FILTER (WHERE is_late) / NULLIF(COUNT(*), 0) AS rate, "
        "SUM(CASE WHEN order_status = 'delivered' THEN 1 ELSE 0 END) AS d "
        "FROM analytics.fact_orders LIMIT 1"
    ),
    "subquery": (
        "SELECT AVG(n) AS avg_items FROM (SELECT order_id, COUNT(*) AS n "
        "FROM analytics.fact_order_items GROUP BY order_id) per_order LIMIT 1"
    ),
    "in subquery": (
        "SELECT COUNT(*) AS n FROM analytics.fact_orders WHERE customer_unique_id IN "
        "(SELECT customer_unique_id FROM analytics.dim_customers WHERE order_count > 1) "
        "LIMIT 1"
    ),
    "trailing semicolon": "SELECT COUNT(*) AS n FROM analytics.fact_orders LIMIT 1;",
    "string with keywords": (
        "SELECT COUNT(*) AS n FROM analytics.fact_orders "
        "WHERE order_status = 'drop table; --' LIMIT 1"
    ),
}


@pytest.mark.parametrize("name", list(ALLOWED))
def test_legitimate_sql_allowed(validator: SQLValidator, name: str) -> None:
    result = validator.validate(ALLOWED[name])
    assert result.ok, result.errors


def test_limit_added_when_missing(validator: SQLValidator) -> None:
    result = validator.validate(
        "SELECT customer_state, COUNT(*) AS n FROM analytics.fact_orders " "GROUP BY customer_state"
    )
    assert result.ok and result.limit_enforced and result.limit == 1000
    assert result.sql.endswith("LIMIT 1000") and "AS limited_result" in result.sql


def test_limit_capped(validator: SQLValidator) -> None:
    result = validator.validate("SELECT order_id FROM analytics.fact_orders LIMIT 50000")
    assert result.ok and result.limit_enforced and result.sql.endswith("LIMIT 1000")


def test_small_limit_kept_and_text_unchanged(validator: SQLValidator) -> None:
    sql = "SELECT ROUND(review_score)::int AS r FROM analytics.fact_orders WHERE x_y = 1 LIMIT 5"
    result = validator.validate(sql.replace("x_y", "item_count"))
    assert result.ok and not result.limit_enforced
    assert result.sql == sql.replace("x_y", "item_count")  # executed text is the original


def test_tables_reported(validator: SQLValidator) -> None:
    result = validator.validate(ALLOWED["declared join"])
    assert result.tables == ["analytics.dim_states", "analytics.fact_orders"]


def test_every_compiled_combination_passes(model: SemanticModel, validator: SQLValidator) -> None:
    """The compiler's own SQL must always satisfy the validator."""
    failures = []
    plans = []
    for m in model.measures:
        plans.append(QueryPlan(measures=[m.name]))
        plans += [
            QueryPlan(measures=[m.name], dimensions=[d]) for d in model.valid_dimensions(m.name)
        ]
    plans += [
        QueryPlan(
            measures=["total_sales", "items_sold", "customer_count"], dimensions=["customer_state"]
        ),
        QueryPlan(measures=["total_sales", "items_sold"]),
        QueryPlan(
            measures=["product_sales"],
            dimensions=["product_category"],
            filters=[{"dimension": "product_sales", "operator": ">", "value": 1000}],
        ),
        QueryPlan(
            measures=["late_delivery_rate"],
            dimensions=["order_date", "seller_state"],
            time_grain="quarter",
            time_range={"start": "2017-01-01", "end": "2017-12-31"},
        ),
        QueryPlan(
            measures=["order_count"],
            filters=[{"dimension": "customer_state", "operator": "in", "value": ["SP", "RJ"]}],
        ),
    ]
    for p in plans:
        compiled = compile_plan(p, model)
        result = validator.validate(compiled.sql, allow_parameters=True)
        if not result.ok:
            failures.append(f"{p.measures} {p.dimensions}: {result.errors}")
    assert not failures, "\n".join(failures)


# ---------------------------------------------------------------- executor


@pytest.mark.integration
def test_executor_refuses_admin_engine() -> None:
    from app.db import get_admin_engine
    from app.services.query_executor import QueryExecutor

    with pytest.raises(RuntimeError, match="privileged"):
        QueryExecutor(get_admin_engine(), 1000, 10)


@pytest.mark.integration
def test_executor_runs_and_caps_rows(reader_engine: Engine) -> None:
    from app.services.query_executor import QueryExecutor

    ex = QueryExecutor(reader_engine, 5000, 100)
    result = ex.run("SELECT order_id FROM analytics.fact_orders")
    assert result.row_count == 100 and result.truncated and result.columns == ["order_id"]
    small = ex.run(
        "SELECT customer_state, COUNT(*) AS n FROM analytics.fact_orders "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 3"
    )
    assert small.rows[0][0] == "SP" and not small.truncated


@pytest.mark.integration
@pytest.mark.parametrize(
    "sql, code",
    [
        ("SELECT pg_sleep(3)", "timeout"),
        ("SELECT * FROM raw.orders", "permission"),
        ("SELECT * FROM app.users", "permission"),
        ("CREATE TABLE analytics.hack (i int)", "read_only"),
        ("SELECT no_such_column FROM analytics.fact_orders", "db_error"),
    ],
)
def test_database_layer_blocks_even_without_validator(
    reader_engine: Engine, sql: str, code: str
) -> None:
    """Second line of defence: the role and session settings block what slips through."""
    from app.services.query_executor import QueryExecutionError, QueryExecutor

    ex = QueryExecutor(reader_engine, 1000, 10)
    with pytest.raises(QueryExecutionError) as err:
        ex.run(sql)
    assert err.value.code == code
    assert "raw" not in err.value.message and "LINE" not in err.value.message


@pytest.mark.integration
def test_runner_blocks_and_counts(model: SemanticModel, reader_engine: Engine) -> None:
    from app.services.query_executor import QueryExecutor
    from app.services.sql_runner import SafeSQLRunner, UnsafeSQLError

    runner = SafeSQLRunner(SQLValidator(model, 1000), QueryExecutor(reader_engine, 5000, 1000))
    compiled = compile_plan(QueryPlan(measures=["order_count"]), model)
    assert runner.run_compiled(compiled).result.rows[0][0] == 99_441
    compiled.sql = "SELECT * FROM raw.orders"
    with pytest.raises(UnsafeSQLError):
        runner.run_compiled(compiled)
    assert runner.blocked_count == 1


class _FakeGenerator:
    def __init__(self, *sqls: str) -> None:
        self.sqls = list(sqls)
        self.feedback: list[str | None] = []

    def generate(self, question, feedback=None, previous_sql=None):
        from app.nl2sql.sql_generator import GeneratedSQL

        self.feedback.append(feedback)
        return GeneratedSQL(True, self.sqls.pop(0), "x", None, "fake", 1)


@pytest.mark.integration
def test_mode_b_repairs_then_runs(model: SemanticModel, reader_engine: Engine) -> None:
    from app.services.query_executor import QueryExecutor
    from app.services.sql_runner import SafeSQLRunner

    runner = SafeSQLRunner(SQLValidator(model, 1000), QueryExecutor(reader_engine, 5000, 1000))
    gen = _FakeGenerator(
        "SELECT COUNT(*) FROM raw.orders", "SELECT COUNT(*) AS n FROM analytics.fact_orders"
    )
    run = runner.run_generated("how many orders", gen)  # type: ignore[arg-type]
    assert run.repaired and run.result.rows[0][0] == 99_441
    assert "analytics schema" in gen.feedback[1]


@pytest.mark.integration
def test_mode_b_never_runs_unsafe_sql(model: SemanticModel, reader_engine: Engine) -> None:
    from app.services.query_executor import QueryExecutor
    from app.services.sql_runner import SafeSQLRunner, UnsafeSQLError

    ex = QueryExecutor(reader_engine, 5000, 1000)
    executed: list[str] = []
    original = ex.run
    ex.run = lambda sql, params=None: executed.append(sql) or original(sql, params)  # type: ignore[method-assign]
    runner = SafeSQLRunner(SQLValidator(model, 1000), ex)
    gen = _FakeGenerator("SELECT pg_sleep(30)", "DELETE FROM analytics.fact_orders")
    with pytest.raises(UnsafeSQLError):
        runner.run_generated("q", gen)  # type: ignore[arg-type]
    assert executed == [] and runner.blocked_count == 2

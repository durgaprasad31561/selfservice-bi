"""NL -> plan layer: LLM client, prompts, planner, relative dates, data checks.

All tests run offline with a fake LLM. A live smoke test runs only when
RUN_LLM_TESTS=1 is set.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from langchain_core.messages import BaseMessage

from app.config import Settings
from app.nl2sql.dates import find_relative_range
from app.nl2sql.llm import (
    LLMClient,
    LLMNotConfigured,
    LLMUnavailable,
    StructuredResult,
    is_overloaded,
    is_transient,
)
from app.nl2sql.planner import LLMPlan, Planner, PlannerError, TTLCache, check_plan, to_query_plan
from app.nl2sql.prompts import FEW_SHOT_EXAMPLES, planner_system_prompt, sql_system_prompt
from app.nl2sql.sql_generator import LLMSql, SQLGenerator
from app.schemas.plan import QueryPlan, TimeRange
from app.semantic.catalog import DataCoverage, MonthCoverage, SemanticCatalog, build_value
from app.semantic.loader import SemanticModel

TODAY = date(2026, 10, 27)


def settings(**overrides) -> Settings:
    base = dict(
        admin_database_url="postgresql+psycopg://a:b@localhost/x",
        reader_database_url="postgresql+psycopg://a:b@localhost/x",
        jwt_secret="x" * 32,
        llm_provider="gemini",
        gemini_api_key="key",
        gemini_model="primary",
        gemini_fallback_models="fallback",
        llm_max_retries=1,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


# ------------------------------------------------------------------ fixtures


def _coverage() -> DataCoverage:
    months = []
    counts = {
        date(2016, 9, 1): 4,
        date(2016, 10, 1): 324,
        date(2016, 11, 1): 0,
        date(2016, 12, 1): 1,
        date(2018, 9, 1): 16,
        date(2018, 10, 1): 4,
    }
    d = date(2016, 1, 1)
    while d <= date(2018, 12, 1):
        n = counts.get(d, 5000 if date(2017, 1, 1) <= d <= date(2018, 8, 1) else 0)
        status = "none" if n == 0 else ("partial" if n < 200 else "full")
        months.append(MonthCoverage(d, n, status))
        d = date(d.year + d.month // 12, d.month % 12 + 1, 1)
    return DataCoverage(date(2016, 9, 4), date(2018, 10, 17), months)


@pytest.fixture()
def offline_catalog(model: SemanticModel) -> SemanticCatalog:
    def values(dim: str, pairs: list[tuple[object, object]]):
        d = model.dimension(dim)
        return [build_value(d, k, v) for k, v in pairs]

    return SemanticCatalog(
        model,
        {
            "customer_state": values(
                "customer_state",
                [("SP", "São Paulo"), ("RJ", "Rio de Janeiro"), ("MG", "Minas Gerais")],
            ),
            "customer_city": values(
                "customer_city",
                [("sao paulo", None), ("rio de janeiro", None), ("belo horizonte", None)],
            ),
            "product_category": values(
                "product_category", [("Health & Beauty", None), ("Toys", None)]
            ),
            "payment_type": values("payment_type", [("Credit Card", None), ("Boleto", None)]),
        },
        _coverage(),
    )


class FakeLLM:
    """Returns queued LLMPlan/LLMSql objects (or raw text) and records calls."""

    provider = "fake"
    models = ["fake-model"]

    def __init__(self, *outputs: object) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[list[BaseMessage], str]] = []

    def structured(self, messages, schema, purpose):
        self.calls.append((messages, purpose))
        out = self.outputs.pop(0)
        if isinstance(out, str):
            return StructuredResult(None, out, "bad json", "fake-model", 5, 1)
        return StructuredResult(out, out.model_dump_json(), None, "fake-model", 5, 1)


def make_planner(catalog: SemanticCatalog, *outputs: object) -> tuple[Planner, FakeLLM]:
    llm = FakeLLM(*outputs)
    return Planner(catalog, llm=llm, today=lambda: TODAY, cache=TTLCache(60)), llm  # type: ignore[arg-type]


# -------------------------------------------------------------------- prompts


def test_prompt_is_built_from_semantic_layer(offline_catalog: SemanticCatalog) -> None:
    prompt = planner_system_prompt(offline_catalog, TODAY)
    for m in offline_catalog.model.measures:
        assert m.name in prompt
    assert "TODAY: 2026-10-27" in prompt
    assert "04 Sep 2016 to 17 Oct 2018" in prompt
    assert "Health & Beauty" in prompt  # short value lists are included
    assert "profit" in prompt
    assert 10 <= len(FEW_SHOT_EXAMPLES) <= 20


def test_few_shot_examples_use_valid_names(offline_catalog: SemanticCatalog) -> None:
    for question, plan in FEW_SHOT_EXAMPLES:
        llm_plan = LLMPlan.model_validate(
            {
                k: v
                for k, v in plan.items()
                if k not in ("time_start", "time_end") or str(v)[:1].isdigit()
            }
        )
        assert check_plan(llm_plan, offline_catalog) == [], question


def test_sql_prompt_lists_only_analytics(offline_catalog: SemanticCatalog) -> None:
    prompt = sql_system_prompt(offline_catalog, 1000)
    assert "analytics.fact_orders" in prompt and "raw." not in prompt.replace("raw or app", "")
    assert "LIMIT 1000" in prompt


# -------------------------------------------------------------------- planner


def test_plan_conversion(offline_catalog: SemanticCatalog) -> None:
    out = LLMPlan(
        measures=["total_sales"],
        dimensions=["customer_state"],
        filters=[
            {"dimension": "customer_state", "operator": "in", "values": ["SP", "RJ"]},
            {"dimension": "rating", "values": ["5"]},
        ],
        time_start="2018-01-01",
        time_end="2018-12-31",
        time_label="2018",
        order_by=[{"field": "total_sales"}],
        limit=5,
    )
    planner, llm = make_planner(offline_catalog, out)
    result = planner.plan("Top 5 states by sales in 2018")
    plan = result.plan
    assert plan.measures == ["total_sales"]
    assert plan.filters[0].value == ["SP", "RJ"] and plan.filters[1].value == 5
    assert plan.time_range == TimeRange(
        start=date(2018, 1, 1), end=date(2018, 12, 31), label="2018"
    )
    assert plan.limit == 5 and not result.repaired and len(llm.calls) == 1


def test_repair_on_unknown_names(offline_catalog: SemanticCatalog) -> None:
    bad = LLMPlan(measures=["revenue"], dimensions=["state"])
    good = LLMPlan(measures=["total_sales"], dimensions=["customer_state"])
    planner, llm = make_planner(offline_catalog, bad, good)
    result = planner.plan("sales by state")
    assert result.repaired and result.plan.measures == ["total_sales"]
    assert llm.calls[1][1] == "plan_repair"
    repair_text = llm.calls[1][0][-1].content
    assert "Unknown measure 'revenue'" in repair_text


def test_repair_on_invalid_json(offline_catalog: SemanticCatalog) -> None:
    planner, _ = make_planner(offline_catalog, "not json", LLMPlan(measures=["order_count"]))
    assert planner.plan("how many orders").plan.measures == ["order_count"]


def test_gives_up_after_one_repair(offline_catalog: SemanticCatalog) -> None:
    planner, llm = make_planner(offline_catalog, LLMPlan(measures=["x"]), LLMPlan(measures=["y"]))
    with pytest.raises(PlannerError):
        planner.plan("???")
    assert len(llm.calls) == 2


def test_cache_returns_identical_question(offline_catalog: SemanticCatalog) -> None:
    planner, llm = make_planner(offline_catalog, LLMPlan(measures=["order_count"]))
    first = planner.plan("How many orders?")
    second = planner.plan("  how many ORDERS? ")
    assert not first.cached and second.cached and len(llm.calls) == 1


def test_refusal_and_clarification_pass_through(offline_catalog: SemanticCatalog) -> None:
    planner, _ = make_planner(
        offline_catalog,
        LLMPlan(can_answer=False, reason="No cost data."),
        LLMPlan(clarification_needed="Money or units?", clarification_options=["a", "b"]),
    )
    refused = planner.plan("What is our profit?").plan
    assert not refused.can_answer and refused.reason == "No cost data."
    clarify = planner.plan("Which category sells the most?").plan
    assert clarify.clarification_needed and clarify.clarification_options == ["a", "b"]


def test_custom_sql_flag(offline_catalog: SemanticCatalog) -> None:
    planner, _ = make_planner(offline_catalog, LLMPlan(needs_custom_sql=True))
    assert planner.plan("orders by weekday").needs_custom_sql


def test_relative_dates_override_llm(offline_catalog: SemanticCatalog) -> None:
    # Even if the model maps "last month" onto the data range, today's date wins.
    out = LLMPlan(measures=["total_sales"], time_start="2018-08-01", time_end="2018-08-31")
    planner, _ = make_planner(offline_catalog, out)
    result = planner.plan("Show last month's sales")
    assert result.plan.time_range.start == date(2026, 9, 1)
    assert result.plan.time_range.end == date(2026, 9, 30)
    assert result.relative_range is not None
    assert any("relative to today" in a for a in result.plan.assumptions)


@pytest.mark.parametrize(
    "plan, problem",
    [
        (LLMPlan(measures=[]), "No measure"),
        (LLMPlan(measures=["total_sales"], time_start="2018-01-01"), "both"),
        (
            LLMPlan(measures=["total_sales"], time_start="2018-13-01", time_end="2018-12-31"),
            "YYYY-MM-DD",
        ),
        (
            LLMPlan(measures=["total_sales"], time_start="2018-12-01", time_end="2018-01-01"),
            "before",
        ),
        (LLMPlan(measures=["total_sales"], order_by=[{"field": "price"}]), "order_by"),
        (
            LLMPlan(measures=["total_sales"], filters=[{"dimension": "planet", "values": ["x"]}]),
            "Unknown filter",
        ),
    ],
)
def test_check_plan_errors(offline_catalog: SemanticCatalog, plan: LLMPlan, problem: str) -> None:
    assert any(problem in e for e in check_plan(plan, offline_catalog))


def test_to_query_plan_measure_threshold() -> None:
    plan = to_query_plan(
        LLMPlan(
            measures=["product_sales"],
            dimensions=["product_category"],
            filters=[{"dimension": "product_sales", "operator": ">", "values": ["1000000"]}],
        )
    )
    assert plan.filters[0].value == 1_000_000


# ------------------------------------------------------------------ dates


@pytest.mark.parametrize(
    "question, start, end",
    [
        ("sales last month", date(2026, 9, 1), date(2026, 9, 30)),
        ("orders this year", date(2026, 1, 1), TODAY),
        ("revenue last year", date(2025, 1, 1), date(2025, 12, 31)),
        ("orders in the last 30 days", date(2026, 9, 28), TODAY),
        ("sales over the past 3 months", date(2026, 8, 1), TODAY),
        ("what sold recently", date(2026, 9, 28), TODAY),
        ("sales yesterday", date(2026, 10, 26), date(2026, 10, 26)),
        ("sales last quarter", date(2026, 7, 1), date(2026, 9, 30)),
        ("orders last week", date(2026, 10, 19), date(2026, 10, 25)),
        ("revenue year to date", date(2026, 1, 1), TODAY),
        ("sales this month", date(2026, 10, 1), TODAY),
    ],
)
def test_relative_dates(question: str, start: date, end: date) -> None:
    rel = find_relative_range(question, TODAY)
    assert rel is not None and (rel.start, rel.end) == (start, end), rel


@pytest.mark.parametrize(
    "question",
    [
        "total sales in 2018",
        "sales in the last month of 2017",
        "top 5 categories",
        "revenue in the most recent month",
        "orders by month",
    ],
)
def test_not_relative(question: str) -> None:
    assert find_relative_range(question, TODAY) is None


# ------------------------------------------------------------- data checks


def test_resolve_filters(offline_catalog: SemanticCatalog) -> None:
    from app.safety.data_checks import resolve_filters

    plan = QueryPlan(
        measures=["total_sales"],
        filters=[
            {"dimension": "customer_state", "value": "São Paulo"},
            {"dimension": "customer_city", "value": "Sao Paolo"},
            {"dimension": "payment_type", "operator": "in", "value": ["credit card", "boleto"]},
        ],
    )
    res = resolve_filters(plan, offline_catalog)
    assert not res.unresolved
    assert [f.value for f in res.plan.filters] == ["SP", "sao paulo", ["Credit Card", "Boleto"]]
    assert any("Sao Paolo" in n for n in res.notes)


def test_resolve_filters_unknown(offline_catalog: SemanticCatalog) -> None:
    from app.safety.data_checks import resolve_filters

    plan = QueryPlan(
        measures=["total_sales"], filters=[{"dimension": "customer_city", "value": "Hyderabad"}]
    )
    res = resolve_filters(plan, offline_catalog)
    assert [u.value for u in res.unresolved] == ["Hyderabad"]
    assert res.plan.filters == []


@pytest.mark.parametrize(
    "start, end, status",
    [
        (date(2026, 9, 1), date(2026, 9, 30), "outside"),
        (date(2020, 1, 1), date(2020, 12, 31), "outside"),
        (date(2015, 1, 1), date(2015, 12, 31), "outside"),
        (date(2017, 1, 1), date(2017, 12, 31), "ok"),
        (date(2018, 3, 1), date(2018, 3, 31), "ok"),
        (date(2016, 11, 1), date(2016, 11, 30), "partial"),
        (date(2018, 10, 1), date(2018, 10, 31), "partial"),
        (date(2018, 1, 1), date(2018, 12, 31), "partial"),
        (date(2018, 6, 1), date(2019, 6, 30), "partial"),
    ],
)
def test_time_coverage(start: date, end: date, status: str) -> None:
    from app.safety.data_checks import check_time_coverage

    result = check_time_coverage(TimeRange(start=start, end=end), _coverage())
    assert result.status == status, result.message
    if status == "outside":
        assert "04 Sep 2016 to 17 Oct 2018" in result.message


def test_time_series_without_range_warns() -> None:
    from app.safety.data_checks import check_time_coverage

    assert check_time_coverage(None, _coverage()).status == "ok"
    series = check_time_coverage(None, _coverage(), time_grain="month")
    assert series.status == "partial" and "Nov 2016" in series.message


# ------------------------------------------------------------- llm client


def test_missing_api_key_is_clear() -> None:
    with pytest.raises(LLMNotConfigured, match="GEMINI_API_KEY is empty"):
        LLMClient(settings(gemini_api_key=""))
    with pytest.raises(LLMNotConfigured, match="OPENAI_MODEL is empty"):
        LLMClient(settings(llm_provider="openai", openai_api_key="k", openai_model=""))


def test_models_from_settings() -> None:
    assert settings(gemini_fallback_models="a, b,primary").llm_models == ["primary", "a", "b"]


def test_error_classification() -> None:
    assert is_overloaded(RuntimeError("503 UNAVAILABLE high demand"))
    assert is_transient(RuntimeError("429 RESOURCE_EXHAUSTED")) and not is_overloaded(
        RuntimeError("429 RESOURCE_EXHAUSTED")
    )
    assert not is_transient(RuntimeError("400 INVALID_ARGUMENT api key not valid"))


class _Runnable:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    def invoke(self, _messages):
        return self.behaviour()


class _Chat:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    def with_structured_output(self, *_a, **_k):
        return _Runnable(self.behaviour)


def _client_with(monkeypatch, behaviours: dict) -> LLMClient:
    client = LLMClient(settings())
    monkeypatch.setattr(client, "_chat", lambda model: _Chat(behaviours[model]))
    monkeypatch.setattr("app.nl2sql.llm._write_log", lambda entry: None)
    monkeypatch.setattr("app.nl2sql.llm.time.sleep", lambda s: None)
    return client


def test_overloaded_primary_falls_back(monkeypatch) -> None:
    calls = {"primary": 0}

    def primary():
        calls["primary"] += 1
        raise RuntimeError("503 UNAVAILABLE high demand")

    ok = {"raw": None, "parsed": LLMPlan(measures=["order_count"]), "parsing_error": None}
    client = _client_with(monkeypatch, {"primary": primary, "fallback": lambda: ok})
    result = client.structured([], LLMPlan, "plan")
    assert result.model == "fallback" and calls["primary"] == 1
    # primary is now cooling down: the next call goes to the fallback first
    assert client._ordered_models()[0] == "fallback"


def test_all_models_down(monkeypatch) -> None:
    def down():
        raise RuntimeError("503 UNAVAILABLE")

    client = _client_with(monkeypatch, {"primary": down, "fallback": down})
    with pytest.raises(LLMUnavailable):
        client.structured([], LLMPlan, "plan")


def test_non_transient_error_not_retried(monkeypatch) -> None:
    from app.nl2sql.llm import LLMError

    calls = {"n": 0}

    def bad():
        calls["n"] += 1
        raise RuntimeError("400 API key not valid")

    client = _client_with(monkeypatch, {"primary": bad, "fallback": bad})
    with pytest.raises(LLMError, match="API key"):
        client.structured([], LLMPlan, "plan")
    assert calls["n"] == 1


# ----------------------------------------------------------- sql generator


def test_sql_generator_strips_semicolon(offline_catalog: SemanticCatalog) -> None:
    llm = FakeLLM(LLMSql(sql="SELECT 1 FROM analytics.fact_orders;  ", explanation="x"))
    gen = SQLGenerator(offline_catalog, 1000, llm=llm).generate("q")  # type: ignore[arg-type]
    assert gen.can_answer and gen.sql == "SELECT 1 FROM analytics.fact_orders"


def test_sql_generator_refusal(offline_catalog: SemanticCatalog) -> None:
    llm = FakeLLM(LLMSql(can_answer=False, reason="no such data"))
    gen = SQLGenerator(offline_catalog, 1000, llm=llm).generate("q")  # type: ignore[arg-type]
    assert not gen.can_answer and gen.sql is None and gen.reason == "no such data"


def test_sql_generator_feedback_round(offline_catalog: SemanticCatalog) -> None:
    llm = FakeLLM(LLMSql(sql="SELECT 2"))
    SQLGenerator(offline_catalog, 1000, llm=llm).generate(  # type: ignore[arg-type]
        "q", feedback="table not allowed", previous_sql="SELECT * FROM raw.orders"
    )
    messages, purpose = llm.calls[0]
    assert purpose == "sql_repair" and "table not allowed" in messages[-1].content


# ---------------------------------------------------------------- live LLM


@pytest.mark.skipif(os.environ.get("RUN_LLM_TESTS") != "1", reason="set RUN_LLM_TESTS=1")
def test_live_planner(catalog: SemanticCatalog) -> None:
    result = Planner(catalog, cache=TTLCache(0)).plan("Total sales in 2017")
    assert result.plan.measures == ["total_sales"]
    assert result.plan.time_range.start == date(2017, 1, 1)


def test_quota_exhausted_skips_model_without_retry(monkeypatch) -> None:
    from app.nl2sql.llm import quota_retry_seconds

    calls = {"primary": 0}

    def primary():
        calls["primary"] += 1
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded. Please retry in 2h0m0s.")

    ok = {"raw": None, "parsed": LLMPlan(measures=["order_count"]), "parsing_error": None}
    client = _client_with(monkeypatch, {"primary": primary, "fallback": lambda: ok})
    assert client.structured([], LLMPlan, "plan").model == "fallback"
    assert calls["primary"] == 1  # no retries against an exhausted quota
    import time as _time

    assert client._unhealthy_until["primary"] - _time.monotonic() > 3600
    assert quota_retry_seconds(RuntimeError("'retryDelay': '52776s'")) == 52776


def test_all_quotas_exhausted_message(monkeypatch) -> None:
    def exhausted():
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota")

    client = _client_with(monkeypatch, {"primary": exhausted, "fallback": exhausted})
    with pytest.raises(LLMUnavailable, match="quota"):
        client.structured([], LLMPlan, "plan")


@pytest.mark.parametrize(
    "question, start, end",
    [
        ("Top 5 sellers in 2018", date(2018, 1, 1), date(2018, 12, 31)),
        ("sales in March 2018", date(2018, 3, 1), date(2018, 3, 31)),
        ("revenue for sept 2017", date(2017, 9, 1), date(2017, 9, 30)),
        ("orders in Q2 2017", date(2017, 4, 1), date(2017, 6, 30)),
        ("orders in 2018 Q4", date(2018, 10, 1), date(2018, 12, 31)),
        ("sales in november of 2016", date(2016, 11, 1), date(2016, 11, 30)),
    ],
)
def test_single_explicit_period(question: str, start: date, end: date) -> None:
    from app.nl2sql.dates import single_explicit_period

    p = single_explicit_period(question)
    assert p is not None and (p.start, p.end) == (start, end)


@pytest.mark.parametrize("question", ["compare 2017 and 2018", "sales by month", "top sellers"])
def test_no_single_explicit_period(question: str) -> None:
    from app.nl2sql.dates import single_explicit_period

    assert single_explicit_period(question) is None


def test_missing_period_is_restored(offline_catalog: SemanticCatalog) -> None:
    planner, _ = make_planner(
        offline_catalog, LLMPlan(measures=["product_sales"], dimensions=["seller"], limit=5)
    )
    plan = planner.plan("Top 5 sellers by product sales in 2018").plan
    assert plan.time_range.start == date(2018, 1, 1) and plan.time_range.end == date(2018, 12, 31)
    assert any("Applied the period '2018'" in a for a in plan.assumptions)


def test_wrong_period_is_corrected_but_narrower_kept(offline_catalog: SemanticCatalog) -> None:
    planner, _ = make_planner(
        offline_catalog,
        LLMPlan(measures=["total_sales"], time_start="2017-01-01", time_end="2017-12-31"),
        LLMPlan(measures=["total_sales"], time_start="2018-01-01", time_end="2018-06-30"),
    )
    assert planner.plan("sales in March 2018").plan.time_range.start == date(2018, 3, 1)
    kept = planner.plan("sales in the first half of 2018").plan.time_range
    assert (kept.start, kept.end) == (date(2018, 1, 1), date(2018, 6, 30))

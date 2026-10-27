"""Semantic layer: YAML loading/validation, catalog value resolution, metadata API."""

from __future__ import annotations

import copy

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, text

from app.semantic.catalog import AllowedValue, SemanticCatalog, normalize
from app.semantic.loader import (
    MODEL_PATH,
    SemanticModel,
    SemanticModelError,
    load_model,
    validate_model,
)

REQUIRED_MEASURES = {
    "total_sales",
    "order_count",
    "average_order_value",
    "items_sold",
    "product_sales",
    "shipping_cost",
    "customer_count",
    "repeat_customers",
    "seller_count",
    "average_rating",
    "review_count",
    "average_delivery_days",
    "late_delivery_rate",
    "cancellation_rate",
    "average_installments",
    "payment_amount",
}
REQUIRED_DIMENSIONS = {
    "order_date",
    "customer_state",
    "customer_city",
    "seller_state",
    "seller_city",
    "product_category",
    "order_status",
    "payment_type",
    "rating",
    "delivery_status",
}


def raw_yaml() -> dict:
    return yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))


def validate_dict(data: dict) -> None:
    validate_model(SemanticModel.model_validate(data))


# --------------------------------------------------------------------- loading


def test_model_loads(model: SemanticModel) -> None:
    assert model.currency == "BRL"
    assert {m.name for m in model.measures} >= REQUIRED_MEASURES
    assert {d.name for d in model.dimensions} >= REQUIRED_DIMENSIONS


def test_every_entry_is_documented(model: SemanticModel) -> None:
    for m in model.measures:
        assert m.description.strip() and m.label and m.synonyms and m.sources, m.name
    for d in model.dimensions:
        assert d.description.strip() and d.label and d.synonyms and d.columns, d.name
    for u in model.unsupported_concepts:
        assert u.keywords and u.reason, u.name


def test_revenue_measures_exclude_canceled(model: SemanticModel) -> None:
    for name in ("total_sales", "average_order_value", "product_sales", "payment_amount"):
        m = model.measure(name)
        for source in m.sources:
            assert "valid_orders" in m.filters_for(source), (name, source)
    assert "canceled" in model.filters["valid_orders"].sql


def test_customer_count_uses_unique_id(model: SemanticModel) -> None:
    for expr in model.measure("customer_count").sources.values():
        assert "COUNT(DISTINCT customer_unique_id)" in expr


def test_category_only_on_item_grain(model: SemanticModel) -> None:
    assert set(model.dimension("product_category").columns) == {"fact_order_items"}
    assert model.pick_source("total_sales", ["product_category"]) is None
    assert model.pick_source("product_sales", ["product_category"]) == "fact_order_items"
    assert model.pick_source("average_rating", ["payment_type"]) == "fact_orders"


def test_unsupported_concepts_present(model: SemanticModel) -> None:
    names = {u.name for u in model.unsupported_concepts}
    assert {"profit", "cost", "inventory", "marketing", "other_country"} <= names
    other = next(u for u in model.unsupported_concepts if u.name == "other_country")
    assert "hyderabad" in other.keywords and "india" in other.keywords


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda d: d["measures"][0]["sources"].update({"fact_orders": "SUM(no_such_col)"}),
            "unknown column",
        ),
        (lambda d: d["measures"][0]["sources"].update({"nope": "COUNT(*)"}), "unknown source"),
        (lambda d: d["measures"][0].update({"default_filters": ["nope"]}), "unknown filter"),
        (
            lambda d: d["dimensions"][1]["columns"]["fact_orders"].update({"key": "bad_col"}),
            "unknown column",
        ),
        (lambda d: d["measures"][1]["synonyms"].append("revenue"), "synonym"),
        (lambda d: d["measures"].append(copy.deepcopy(d["measures"][0])), "duplicate"),
        (
            lambda d: d["relationships"].append(
                {"from": "fact_orders.x", "to": "dim_states.state_code", "type": "many_to_one"}
            ),
            "unknown column",
        ),
        (lambda d: d.update({"default_time_dimension": "nope"}), "default_time_dimension"),
    ],
)
def test_invalid_models_fail_loudly(mutate, message: str) -> None:
    data = raw_yaml()
    mutate(data)
    with pytest.raises(SemanticModelError, match=message):
        validate_dict(data)


def test_non_analytics_table_rejected() -> None:
    data = raw_yaml()
    data["sources"]["fact_orders"]["table"] = "raw.orders"
    with pytest.raises(Exception, match="analytics"):
        SemanticModel.model_validate(data)


def test_unknown_yaml_key_rejected() -> None:
    data = raw_yaml()
    data["measures"][0]["oops"] = 1
    with pytest.raises(ValidationError, match="oops"):
        SemanticModel.model_validate(data)


def test_load_model_reports_missing_file(tmp_path) -> None:
    with pytest.raises(SemanticModelError):
        load_model(tmp_path / "missing.yaml")


# ------------------------------------------------------- catalog (no database)


def test_normalize() -> None:
    assert normalize("São Paulo") == "sao paulo"
    assert normalize("  Health & Beauty ") == "health and beauty"
    assert normalize("GOIÂNIA") == "goiania"


def _offline_catalog(model: SemanticModel) -> SemanticCatalog:
    from app.semantic.catalog import build_value

    state = model.dimension("customer_state")
    city = model.dimension("customer_city")
    return SemanticCatalog(
        model,
        {
            "customer_state": [
                build_value(state, "SP", "São Paulo"),
                build_value(state, "RJ", "Rio de Janeiro"),
            ],
            "customer_city": [
                build_value(city, "sao paulo", None),
                build_value(city, "rio de janeiro", None),
            ],
            "rating": [AllowedValue(key=i, display=str(i), aliases=(str(i),)) for i in range(1, 6)],
        },
    )


@pytest.mark.parametrize(
    "typed", ["SP", "sp", "São Paulo", "sao paulo", "SAO PAULO", "State of São Paulo"]
)
def test_state_resolution_offline(model: SemanticModel, typed: str) -> None:
    assert _offline_catalog(model).resolve_value("customer_state", typed).key == "SP"


def test_city_display_is_title_case(model: SemanticModel) -> None:
    v = _offline_catalog(model).values("customer_city")[0]
    assert v.key == "sao paulo" and v.display == "Sao Paulo"


def test_rating_resolution_offline(model: SemanticModel) -> None:
    cat = _offline_catalog(model)
    assert cat.resolve_value("rating", "5 stars").key == 5
    assert not cat.resolve_value("rating", "9").matched


def test_find_terms(model: SemanticModel) -> None:
    found = _offline_catalog(model).find_terms("Show revenue by state per month")
    assert "total_sales" in found["measures"]
    assert {"customer_state", "order_date"} <= set(found["dimensions"])


# ---------------------------------------------------------- with the database


@pytest.mark.integration
def test_yaml_columns_exist_in_database(model: SemanticModel, reader_engine: Engine) -> None:
    with reader_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'analytics'"
            )
        ).all()
    actual: dict[str, set[str]] = {}
    for table, column in rows:
        actual.setdefault(table, set()).add(column)
    for name, src in model.sources.items():
        table = src.table.split(".", 1)[1]
        assert table in actual, f"{name}: table {src.table} missing"
        missing = set(src.columns) - actual[table]
        assert not missing, f"{name}: columns {missing} not in database"


@pytest.mark.integration
def test_allowed_values_loaded(catalog: SemanticCatalog) -> None:
    counts = {k: len(v) for k, v in catalog.allowed_values.items()}
    assert counts["customer_state"] == 27
    assert counts["order_status"] == 8
    assert counts["product_category"] == 74
    assert counts["customer_city"] > 4000
    assert {v.display for v in catalog.values("payment_type")} >= {
        "Credit Card",
        "Boleto",
        "Voucher",
        "Debit Card",
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    "dimension, typed, expected",
    [
        ("customer_state", "São Paulo", "SP"),
        ("customer_state", "Sao Paulo", "SP"),
        ("customer_state", "SP", "SP"),
        ("customer_state", "minas gerais", "MG"),
        ("customer_state", "Rio de Janeiro", "RJ"),
        ("customer_city", "São Paulo", "sao paulo"),
        ("customer_city", "Sao Paolo", "sao paulo"),
        ("customer_city", "Belo Horizonte", "belo horizonte"),
        ("seller_city", "curitba", "curitiba"),
        ("product_category", "health and beauty", "Health & Beauty"),
        ("product_category", "Bed Bath Table", "Bed, Bath & Table"),
        ("product_category", "computers accessories", "Computers & Accessories"),
        ("payment_type", "credit card", "Credit Card"),
        ("payment_type", "boleto", "Boleto"),
        ("order_status", "Delivered", "delivered"),
        ("customer_region", "south east", "Southeast"),
        ("rating", "5", 5),
        ("delivery_status", "late", "Late"),
    ],
)
def test_value_resolution(catalog: SemanticCatalog, dimension: str, typed: str, expected) -> None:
    match = catalog.resolve_value(dimension, typed)
    assert match.key == expected, match


@pytest.mark.integration
@pytest.mark.parametrize(
    "dimension, typed",
    [
        ("customer_city", "Hyderabad"),
        ("customer_state", "Texas"),
        ("product_category", "spaceships"),
        ("customer_city", "Mumbai"),
    ],
)
def test_unknown_values_not_matched(catalog: SemanticCatalog, dimension: str, typed: str) -> None:
    assert not catalog.resolve_value(dimension, typed).matched


@pytest.mark.integration
def test_partial_value_gets_suggestion(catalog: SemanticCatalog) -> None:
    match = catalog.resolve_value("customer_state", "Minas")
    assert not match.matched and "Minas Gerais" in match.suggestions


@pytest.mark.integration
def test_coverage(catalog: SemanticCatalog) -> None:
    from datetime import date

    cov = catalog.coverage
    assert cov is not None
    assert cov.min_date == date(2016, 9, 4) and cov.max_date == date(2018, 10, 17)
    assert cov.status_of(date(2016, 11, 1)) == "none"
    for month in (date(2016, 12, 1), date(2018, 9, 1), date(2018, 10, 1)):
        assert cov.status_of(month) == "partial"
    assert cov.status_of(date(2017, 6, 1)) == "full"
    assert cov.status_of(date(2020, 1, 1)) == "none"


@pytest.mark.integration
def test_metadata_endpoint(reader_engine: Engine) -> None:
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/api/metadata")
        assert resp.status_code == 200
        body = resp.json()
        assert body["currency"] == "BRL"
        names = {m["name"] for m in body["measures"]}
        assert names >= REQUIRED_MEASURES
        sales = next(m for m in body["measures"] if m["name"] == "total_sales")
        assert "product_category" not in sales["valid_dimensions"]
        assert any("canceled" in f for f in sales["default_filters"])
        state = next(d for d in body["dimensions"] if d["name"] == "customer_state")
        assert "São Paulo" in state["values"]
        assert body["coverage"]["min_date"] == "2016-09-04"
        slim = client.get("/api/metadata", params={"include_values": False}).json()
        assert all("values" not in d for d in slim["dimensions"])
        assert client.get("/api/health").json()["status"] == "ok"

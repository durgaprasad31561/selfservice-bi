"""HTTP API: auth and roles, query + history, dashboards/widgets, misc endpoints.

Runs against the real database with a scripted planner (no LLM calls). Every user
created here is deleted at the end (dashboards and history cascade).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import get_admin_engine
from app.main import app
from app.models import User
from app.services.query_service import get_query_service
from tests.test_safeguards import ScriptedGenerator, ScriptedPlanner

pytestmark = pytest.mark.integration

PLANS = {
    "Total sales in 2017": {
        "measures": ["total_sales"],
        "time_range": {"start": "2017-01-01", "end": "2017-12-31", "label": "2017"},
    },
    "Top 5 categories by revenue": {
        "measures": ["product_sales"],
        "dimensions": ["product_category"],
        "limit": 5,
        "order_by": [{"field": "product_sales"}],
    },
    "Orders in Atlantis": {
        "measures": ["order_count"],
        "filters": [{"dimension": "customer_city", "value": "Atlantis"}],
    },
}
CREATED_EMAILS: list[str] = []


@pytest.fixture(scope="module")
def client(catalog, reader_engine) -> Iterator[TestClient]:
    from app.config import get_settings
    from app.db import get_reader_engine
    from app.safety.sql_validator import SQLValidator
    from app.services.query_executor import QueryExecutor
    from app.services.query_service import QueryService
    from app.services.sql_runner import SafeSQLRunner

    settings = get_settings()
    service = QueryService(
        catalog,
        ScriptedPlanner(PLANS),
        ScriptedGenerator(),  # type: ignore[arg-type]
        SafeSQLRunner(
            SQLValidator(catalog.model, settings.max_rows),
            QueryExecutor(get_reader_engine(), settings.query_timeout_ms, settings.max_rows),
        ),
        settings.max_rows,
    )
    app.dependency_overrides[get_query_service] = lambda: service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    with get_admin_engine().begin() as conn:
        conn.execute(delete(User).where(User.email.in_(CREATED_EMAILS)))


def new_email(prefix: str) -> str:
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@test.local"
    CREATED_EMAILS.append(email)
    return email


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin(client: TestClient) -> dict[str, str]:
    from app.config import get_settings

    s = get_settings()
    return login(client, s.demo_admin_email, s.demo_admin_password)


def make_user(client: TestClient, admin: dict[str, str], role: str) -> dict[str, str]:
    email, password = new_email(role), "Passw0rd!x"
    r = client.post(
        "/api/auth/register",
        headers=admin,
        json={"email": email, "password": password, "role": role},
    )
    assert r.status_code == 201, r.text
    return login(client, email, password)


# ------------------------------------------------------------------ auth


def test_health_is_public(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["database"]["reader"]["ok"] and "llm" in body


def test_register_login_me(client: TestClient) -> None:
    email = new_email("viewer")
    r = client.post(
        "/api/auth/register",
        json={"email": email.upper(), "password": "Secret123!", "full_name": "Test Viewer"},
    )
    assert r.status_code == 201 and r.json()["role"] == "viewer" and r.json()["email"] == email
    assert (
        client.post(
            "/api/auth/register", json={"email": email, "password": "Secret123!"}
        ).status_code
        == 409
    )
    headers = login(client, email, "Secret123!")
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == email and "password_hash" not in me


def test_bad_credentials_and_tokens(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"email": "admin@demo.com", "password": "wrong"})
    assert r.status_code == 401 and r.json()["error"] == "http_error"
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.get("/api/auth/me", headers={"Authorization": "Bearer abc.def.ghi"}).status_code
        == 401
    )


def test_expired_token_rejected(client: TestClient) -> None:
    from app.auth.security import create_access_token

    token = create_access_token(1, "admin", expires_minutes=-1)
    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    )


def test_oauth2_form_login(client: TestClient) -> None:
    from app.config import get_settings

    s = get_settings()
    r = client.post(
        "/api/auth/token",
        data={"username": s.demo_viewer_email, "password": s.demo_viewer_password},
    )
    assert r.status_code == 200 and r.json()["user"]["role"] == "viewer"


def test_privileged_registration_needs_admin(client: TestClient, admin: dict[str, str]) -> None:
    body = {"email": new_email("analyst"), "password": "Secret123!", "role": "analyst"}
    assert client.post("/api/auth/register", json=body).status_code == 403
    viewer = make_user(client, admin, "viewer")
    assert client.post("/api/auth/register", json=body, headers=viewer).status_code == 403
    assert client.post("/api/auth/register", json=body, headers=admin).status_code == 201


def test_user_list_admin_only(client: TestClient, admin: dict[str, str]) -> None:
    assert client.get("/api/auth/users", headers=admin).status_code == 200
    viewer = make_user(client, admin, "viewer")
    assert client.get("/api/auth/users", headers=viewer).status_code == 403


def test_protected_endpoints_need_login(client: TestClient) -> None:
    for path in (
        "/api/metadata",
        "/api/suggestions",
        "/api/overview",
        "/api/history",
        "/api/dashboards",
    ):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/query", json={"question": "x"}).status_code == 401


# ------------------------------------------------------------ query + history


def test_query_answer_and_history(client: TestClient, admin: dict[str, str]) -> None:
    user = make_user(client, admin, "analyst")
    r = client.post("/api/query", json={"question": "Total sales in 2017"}, headers=user)
    body = r.json()
    assert r.status_code == 200 and body["status"] == "answered"
    assert body["answer_text"].startswith("Total Sales in 2017 was R$ ")
    for key in (
        "sql",
        "data",
        "columns",
        "chart",
        "explanation",
        "warnings",
        "assumptions",
        "confidence",
        "execution_ms",
        "steps",
    ):
        assert key in body
    refused = client.post("/api/query", json={"question": "What is our profit?"}, headers=user)
    assert refused.json()["status"] == "refused"
    hist = client.get("/api/history", headers=user).json()
    assert hist["total"] == 2
    assert [i["status"] for i in hist["items"]] == ["refused", "answered"]  # newest first
    only = client.get("/api/history", params={"status": "answered"}, headers=user).json()
    assert only["total"] == 1 and only["items"][0]["sql"]
    assert client.get("/api/history", params={"all_users": True}, headers=user).status_code == 403
    assert client.get("/api/history", params={"all_users": True}, headers=admin).status_code == 200
    item = hist["items"][0]["id"]
    assert client.delete(f"/api/history/{item}", headers=user).status_code == 204
    assert client.get("/api/history", headers=user).json()["total"] == 1


def test_query_validation_error_format(client: TestClient, admin: dict[str, str]) -> None:
    r = client.post("/api/query", json={"question": "x" * 3000}, headers=admin)
    assert r.status_code == 422 and r.json()["error"] == "validation_error"
    assert r.json()["detail"][0]["field"] == "question"


def test_query_plan_endpoint(client: TestClient, admin: dict[str, str]) -> None:
    r = client.post(
        "/api/query/plan",
        headers=admin,
        json={
            "question": "Orders by payment type",
            "plan": {"measures": ["order_count"], "dimensions": ["payment_type"]},
        },
    )
    assert r.status_code == 200 and r.json()["chart"]["type"] == "bar"


def test_metadata_suggestions_overview(client: TestClient, admin: dict[str, str]) -> None:
    meta = client.get("/api/metadata", params={"include_values": False}, headers=admin).json()
    assert len(meta["measures"]) >= 16
    sugg = client.get("/api/suggestions", headers=admin).json()["suggestions"]
    assert 8 <= len(sugg) <= 16 and all(s["question"] for s in sugg)
    widgets = client.get("/api/overview", headers=admin).json()["widgets"]
    ids = {w["id"]: w["result"] for w in widgets}
    assert set(ids) == {
        "kpis",
        "monthly_revenue",
        "top_categories",
        "sales_by_state",
        "payment_mix",
        "rating_distribution",
    }
    kpi = ids["kpis"]["data"][0]
    assert kpi["order_count"] == 99_441 and kpi["customer_count"] == 96_096
    assert ids["monthly_revenue"]["chart"]["type"] == "line"
    assert ids["payment_mix"]["chart"]["type"] == "pie"


def test_rate_limit(client: TestClient, admin: dict[str, str]) -> None:
    from app.config import get_settings

    user = make_user(client, admin, "viewer")
    limit = int(get_settings().query_rate_limit.split("/")[0])
    codes = [
        client.post(
            "/api/query", json={"question": "What is our profit?"}, headers=user
        ).status_code
        for _ in range(limit + 1)
    ]
    assert codes[:limit] == [200] * limit and codes[-1] == 429


# --------------------------------------------------------------- dashboards


def test_dashboard_lifecycle(client: TestClient, admin: dict[str, str]) -> None:
    analyst = make_user(client, admin, "analyst")
    other = make_user(client, admin, "analyst")
    viewer = make_user(client, admin, "viewer")

    assert client.post("/api/dashboards", json={"name": "Nope"}, headers=viewer).status_code == 403
    d = client.post(
        "/api/dashboards", json={"name": "Sales", "description": "KPIs"}, headers=analyst
    ).json()
    assert d["can_edit"] and d["widget_count"] == 0

    answer = client.post(
        "/api/query", json={"question": "Top 5 categories by revenue"}, headers=analyst
    ).json()
    w = client.post(
        f"/api/dashboards/{d['id']}/widgets",
        headers=analyst,
        json={
            "title": "Top categories",
            "question": answer["question"],
            "mode": "semantic",
            "plan": answer["plan"],
            "chart_type": answer["chart"]["type"],
        },
    )
    assert w.status_code == 201, w.text
    widget = w.json()
    assert widget["result"]["data"] == answer["data"]

    detail = client.get(f"/api/dashboards/{d['id']}", headers=viewer).json()  # viewers can view
    assert not detail["can_edit"] and len(detail["widgets"]) == 1
    fresh = detail["widgets"][0]["result"]
    assert (
        fresh["status"] == "answered" and fresh["data"][0]["product_category"] == "Health & Beauty"
    )
    listed = client.get(
        f"/api/dashboards/{d['id']}/widgets", params={"refresh": False}, headers=viewer
    ).json()
    assert listed[0]["result"] is None

    assert (
        client.patch(
            f"/api/dashboards/{d['id']}", json={"name": "Hacked"}, headers=other
        ).status_code
        == 403
    )
    r = client.patch(f"/api/dashboards/{d['id']}", json={"name": "Sales 2017"}, headers=analyst)
    assert r.json()["name"] == "Sales 2017"
    r = client.patch(
        f"/api/dashboards/{d['id']}/widgets/{widget['id']}",
        json={"title": "Best categories", "chart_type": "table"},
        headers=analyst,
    )
    assert r.json()["title"] == "Best categories" and r.json()["chart_type"] == "table"
    names = [x["name"] for x in client.get("/api/dashboards", headers=viewer).json()]
    assert "Sales 2017" in names

    assert (
        client.delete(
            f"/api/dashboards/{d['id']}/widgets/{widget['id']}", headers=analyst
        ).status_code
        == 204
    )
    assert client.delete(f"/api/dashboards/{d['id']}", headers=other).status_code == 403
    assert client.delete(f"/api/dashboards/{d['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/dashboards/{d['id']}", headers=analyst).status_code == 404


def test_cannot_pin_refused_or_unsafe(client: TestClient, admin: dict[str, str]) -> None:
    analyst = make_user(client, admin, "analyst")
    d = client.post("/api/dashboards", json={"name": "Pins"}, headers=analyst).json()
    refused = client.post(
        "/api/query", json={"question": "Orders in Atlantis"}, headers=analyst
    ).json()
    assert refused["status"] == "refused"
    r = client.post(
        f"/api/dashboards/{d['id']}/widgets",
        headers=analyst,
        json={"title": "x", "question": "Orders in Atlantis", "plan": refused["plan"]},
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/dashboards/{d['id']}/widgets",
        headers=analyst,
        json={
            "title": "x",
            "question": "q",
            "mode": "custom_sql",
            "custom_sql": "SELECT * FROM app.users",
        },
    )
    assert r.status_code == 422 and "cannot be pinned" in r.json()["detail"]
    r = client.post(
        f"/api/dashboards/{d['id']}/widgets",
        headers=analyst,
        json={"title": "x", "question": "q", "mode": "semantic"},
    )
    assert r.status_code == 422  # plan required


def test_custom_sql_widget_revalidated(client: TestClient, admin: dict[str, str]) -> None:
    analyst = make_user(client, admin, "analyst")
    d = client.post("/api/dashboards", json={"name": "Custom"}, headers=analyst).json()
    sql = (
        "SELECT d.day_name, COUNT(o.order_id) AS orders FROM analytics.fact_orders o "
        "JOIN analytics.dim_date d ON o.purchase_date = d.date_day GROUP BY d.day_name "
        "ORDER BY orders DESC LIMIT 7"
    )
    r = client.post(
        f"/api/dashboards/{d['id']}/widgets",
        headers=analyst,
        json={
            "title": "Weekdays",
            "question": "Orders by weekday",
            "mode": "custom_sql",
            "custom_sql": sql,
        },
    )
    assert r.status_code == 201 and r.json()["result"]["data"][0]["day_name"] == "Monday"


def test_unknown_route_json(client: TestClient) -> None:
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["error"] == "http_error"
    assert r.headers.get("x-request-id")


# ------------------------------------------------------------------- admin


def _user_id(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/api/auth/me", headers=headers).json()["id"]


def test_admin_changes_role_and_deactivates(client: TestClient, admin: dict[str, str]) -> None:
    email, password = new_email("managed"), "Passw0rd!x"
    created = client.post(
        "/api/auth/register",
        headers=admin,
        json={"email": email, "password": password, "role": "viewer"},
    ).json()
    user = login(client, email, password)
    assert client.post("/api/dashboards", json={"name": "x"}, headers=user).status_code == 403

    r = client.patch(f"/api/auth/users/{created['id']}", json={"role": "analyst"}, headers=admin)
    assert r.status_code == 200 and r.json()["role"] == "analyst"
    # the role is read from the database on every request, so it applies immediately
    assert client.post("/api/dashboards", json={"name": "Mine"}, headers=user).status_code == 201

    r = client.patch(f"/api/auth/users/{created['id']}", json={"is_active": False}, headers=admin)
    assert r.json()["is_active"] is False
    assert (
        client.get("/api/auth/me", headers=user).status_code == 401
    )  # existing token stops working
    bad = client.post("/api/auth/login", json={"email": email, "password": password})
    assert bad.status_code == 401


def test_user_admin_endpoints_are_admin_only(client: TestClient, admin: dict[str, str]) -> None:
    analyst = make_user(client, admin, "analyst")
    target = _user_id(client, analyst)
    assert (
        client.patch(
            f"/api/auth/users/{target}", json={"role": "admin"}, headers=analyst
        ).status_code
        == 403
    )
    assert (
        client.patch("/api/auth/users/999999", json={"role": "viewer"}, headers=admin).status_code
        == 404
    )
    assert (
        client.patch(f"/api/auth/users/{target}", json={"role": "boss"}, headers=admin).status_code
        == 422
    )


def test_admin_cannot_lock_themselves_out(client: TestClient, admin: dict[str, str]) -> None:
    me = _user_id(client, admin)
    for body in ({"role": "viewer"}, {"is_active": False}):
        r = client.patch(f"/api/auth/users/{me}", json=body, headers=admin)
        assert r.status_code == 400 and "yourself" in r.json()["detail"]


def test_admin_can_demote_another_admin(client: TestClient, admin: dict[str, str]) -> None:
    email, password = new_email("admin2"), "Passw0rd!x"
    second = client.post(
        "/api/auth/register",
        headers=admin,
        json={"email": email, "password": password, "role": "admin"},
    ).json()
    second_headers = login(client, email, password)
    assert client.get("/api/auth/users", headers=second_headers).status_code == 200
    r = client.patch(f"/api/auth/users/{second['id']}", json={"role": "viewer"}, headers=admin)
    assert r.status_code == 200 and r.json()["role"] == "viewer"
    assert client.get("/api/auth/users", headers=second_headers).status_code == 403


@pytest.mark.integration
def test_history_shows_user_email_for_admins(client: TestClient, admin: dict[str, str]) -> None:
    user = make_user(client, admin, "viewer")
    client.post("/api/query", json={"question": "What is our profit?"}, headers=user)
    items = client.get(
        "/api/history", params={"all_users": True, "limit": 200}, headers=admin
    ).json()["items"]
    me = client.get("/api/auth/me", headers=user).json()
    mine = [i for i in items if i["user_id"] == me["id"]]
    assert mine and mine[0]["user_email"] == me["email"]

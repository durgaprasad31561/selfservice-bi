# API reference

Base URL (development): `http://localhost:8000`. Interactive documentation with "Try it
out": **http://localhost:8000/docs** (OpenAPI JSON at `/openapi.json`). Use the
**Authorize** button there with an email and password.

All endpoints except `/api/health`, `/api/auth/login`, `/api/auth/token` and
`/api/auth/register` need a bearer token:

```
Authorization: Bearer <access_token>
```

## Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/health` | public | Database, LLM and semantic layer status |
| POST | `/api/auth/register` | public / admin | Create an account (viewer; analyst/admin only by an admin) |
| POST | `/api/auth/login` | public | Log in (JSON), returns a JWT |
| POST | `/api/auth/token` | public | Log in (OAuth2 form), used by `/docs` |
| GET | `/api/auth/me` | any role | The logged-in user |
| GET | `/api/auth/users` | admin | All users |
| POST | `/api/query` | any role | **Answer a question** (full pipeline), recorded in history, rate limited |
| POST | `/api/query/plan` | any role | Run a semantic plan directly, no LLM |
| GET | `/api/metadata` | any role | Measures, dimensions, allowed values, data coverage, unsupported concepts |
| GET | `/api/suggestions` | any role | Example questions generated from the semantic layer |
| GET | `/api/overview` | any role | Home dashboard widgets (KPIs and charts), cached 10 min |
| GET | `/api/dashboards` | any role | All dashboards (with `can_edit` per dashboard) |
| POST | `/api/dashboards` | analyst, admin | Create a dashboard |
| GET | `/api/dashboards/{id}` | any role | Dashboard with widgets re-run (`?refresh=false` to skip) |
| PATCH | `/api/dashboards/{id}` | owner analyst, admin | Rename / change description |
| DELETE | `/api/dashboards/{id}` | owner analyst, admin | Delete dashboard and widgets |
| GET | `/api/dashboards/{id}/widgets` | any role | Widgets, re-run for fresh data |
| POST | `/api/dashboards/{id}/widgets` | owner analyst, admin | Pin a result |
| PATCH | `/api/dashboards/{id}/widgets/{wid}` | owner analyst, admin | Rename, change chart type or position |
| DELETE | `/api/dashboards/{id}/widgets/{wid}` | owner analyst, admin | Remove a widget |
| GET | `/api/history` | any role | Your questions (`limit`, `offset`, `status`; admins `all_users=true`) |
| DELETE | `/api/history/{id}` | owner, admin | Delete a history entry |

Roles: **viewer** asks questions and views dashboards; **analyst** also creates and edits
their own dashboards; **admin** can do everything, including creating analyst/admin
accounts and seeing all history.

## Authentication

```http
POST /api/auth/login
Content-Type: application/json

{"email": "analyst@demo.com", "password": "Analyst@123"}
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": {"id": 2, "email": "analyst@demo.com", "full_name": "Demo Analyst",
           "role": "analyst", "is_active": true, "created_at": "2026-10-27T16:45:44Z"}
}
```

Tokens expire after `JWT_EXPIRE_MINUTES` (default 480). A missing, invalid or expired token
returns `401`.

## POST /api/query

```http
POST /api/query
Authorization: Bearer <token>
Content-Type: application/json

{"question": "Show total sales in São Paulo in 2018"}
```

Response (shortened):

```json
{
  "status": "answered_with_warning",
  "question": "Show total sales in São Paulo in 2018",
  "answer_text": "Total Sales for Customer City Sao Paulo in 2018 was R$ 1,270,521.80.",
  "reason": null,
  "suggestions": [],
  "clarification": null,
  "sql": "SELECT SUM(order_revenue) AS total_sales\nFROM analytics.fact_orders\nWHERE order_status NOT IN ('canceled', 'unavailable')\n  AND customer_city = 'sao paulo'\n  AND purchase_date BETWEEN DATE '2018-01-01' AND DATE '2018-12-31'\nLIMIT 1000",
  "data": [{"total_sales": 1270521.8}],
  "columns": [{"name": "total_sales", "label": "Total Sales", "role": "measure",
               "format": "currency", "dimension_type": null, "grain": null}],
  "chart": {"type": "kpi", "title": "Total Sales", "x": null, "y": ["total_sales"],
            "series": null, "reason": "single value"},
  "explanation": {
    "mode": "semantic",
    "definitions": [{"name": "total_sales", "label": "Total Sales",
                     "definition": "Revenue in BRL: the sum of all payments for orders, excluding canceled and unavailable orders. ..."}],
    "business_rules": ["Total Sales: Excludes canceled and unavailable orders."],
    "filters": ["Customer City Sao Paulo"],
    "time_range": "Order date from 2018-01-01 to 2018-12-31",
    "sources": ["analytics.fact_orders"],
    "notes": []
  },
  "warnings": ["The requested period extends beyond the available data (04 Sep 2016 to 17 Oct 2018); only the overlapping part is included. Data is incomplete for Sep 2018 (16 orders), Oct 2018 (4 orders), so these figures are not comparable with complete months."],
  "assumptions": ["'São Paulo' interpreted as the city; ask for 'São Paulo state' for the whole state."],
  "confidence": "medium",
  "plan": {"measures": ["total_sales"], "filters": [{"dimension": "customer_city", "operator": "=", "value": "São Paulo"}], "time_range": {"start": "2018-01-01", "end": "2018-12-31", "label": "2018"}, "...": "..."},
  "steps": [
    {"name": "understanding", "status": "ok", "ms": 2410, "detail": "model=openai/gpt-oss-120b"},
    {"name": "generating_sql", "status": "ok", "ms": 2, "detail": "compiled from the semantic layer"},
    {"name": "validating", "status": "ok", "ms": 6, "detail": "analytics.fact_orders"},
    {"name": "running", "status": "ok", "ms": 0, "detail": "1 rows in 21 ms"},
    {"name": "checking_results", "status": "warning", "ms": 0, "detail": null}
  ],
  "row_count": 1,
  "truncated": false,
  "execution_ms": 2466,
  "llm_model": "openai/gpt-oss-120b"
}
```

### Response fields

| Field | Meaning |
|---|---|
| `status` | `answered`, `answered_with_warning`, `refused`, `clarify` or `error` (LLM or database unavailable) |
| `answer_text` | Plain-English answer built from the result rows; for refusals always "I don't have sufficient data to answer that question." |
| `reason`, `suggestions` | Why it was refused / what to ask instead |
| `clarification` | `{question, options[]}` when `status = clarify` |
| `sql` | The SQL that ran (parameters inlined for display) |
| `data`, `columns` | Result rows (JSON values) and column metadata (`role`, `format`, time `grain`) |
| `chart` | Chosen visual: `kpi`, `line`, `bar`, `pie` or `table`, with `x`, `y`, `series` |
| `explanation` | Business definitions, default rules, filters, period, source tables, notes; `mode` is `semantic` or `custom_sql` |
| `warnings`, `assumptions`, `confidence` | See [safeguards.md](safeguards.md) |
| `plan` | The semantic plan (used to pin the result to a dashboard) |
| `steps` | Pipeline steps with status and timing |
| `execution_ms`, `row_count`, `truncated`, `llm_model` | Diagnostics |

### Refusal example

```json
{
  "status": "refused",
  "answer_text": "I don't have sufficient data to answer that question.",
  "reason": "The dataset contains sale prices and payments but no product or operating costs, so profit cannot be calculated.",
  "suggestions": ["Ask about Total Sales or Product Sales instead."],
  "confidence": "high",
  "steps": [{"name": "understanding", "status": "failed", "ms": 0, "detail": "unsupported"}]
}
```

`/api/query` is rate limited per user (`QUERY_RATE_LIMIT`, default `30/minute`); excess
requests return `429`.

## POST /api/query/plan

Runs a semantic plan without the LLM (all other safeguards apply). Used by dashboards,
the overview and the catalog.

```json
{
  "question": "Orders by payment type",
  "plan": {"measures": ["order_count"], "dimensions": ["payment_type"]}
}
```

Plan fields: `measures`, `dimensions`, `filters` (`{dimension, operator, value}`, operators
`= != in not_in > >= < <= between`; a measure name filters results), `time_range`
(`{start, end, label}` inclusive dates), `time_grain` (`day week month quarter year`),
`order_by` (`{field, direction}`), `limit`. Names are those in `GET /api/metadata`.

## Dashboards and widgets

```http
POST /api/dashboards
{"name": "Sales review", "description": "Monthly KPIs"}

POST /api/dashboards/7/widgets
{
  "title": "Top categories",
  "question": "Top 5 categories by revenue",
  "mode": "semantic",
  "plan": { ...the "plan" object from the /api/query response... },
  "chart_type": "bar"
}
```

For results produced by custom SQL use `"mode": "custom_sql"` and `"custom_sql": "<sql from the response>"`;
the SQL is validated again every time the widget runs. A widget stores the question and how
to re-run it, never the data; results that were refused or unsafe cannot be pinned (`422`).

## GET /api/metadata

Returns `measures` (name, label, description, format, synonyms, valid dimensions, default
filters), `dimensions` (name, label, description, type, grains, value count and values),
`coverage` (`min_date`, `max_date`, monthly `order_count` and `status`) and
`unsupported_concepts`. `?include_values=false` omits the value lists.

## GET /api/health

```json
{
  "status": "ok",
  "database": {"reader": {"ok": true, "detail": "ok"}, "admin": {"ok": true, "detail": "ok"}},
  "llm": {"ok": true, "provider": "groq", "models": ["openai/gpt-oss-120b", "openai/gpt-oss-20b"],
          "cooling_down": [], "detail": "configured"},
  "semantic_layer": {"ok": true, "measures": 19, "dimensions": 12}
}
```

`status` is `degraded` when a database role is unreachable or no LLM is configured.

## Errors

All errors are JSON with a request ID (also returned in the `X-Request-ID` header):

```json
{"detail": "Not authenticated. Please log in.", "error": "http_error", "request_id": "24eb02483908"}
```

| HTTP | `error` | When |
|---|---|---|
| 401 | `http_error` | Missing, invalid or expired token; wrong password |
| 403 | `http_error` | Role not allowed (e.g. viewer creating a dashboard) |
| 404 | `http_error` | Unknown dashboard, widget, history entry or route |
| 409 | `http_error` | Email already registered |
| 422 | `validation_error` | Invalid request body (`detail` lists `field` + `message`) or result cannot be pinned |
| 429 | `rate_limited` | Too many questions |
| 500 | `internal_error` | Unexpected error (logged with the request ID; no internals returned) |

Questions the data cannot answer are **not** HTTP errors: they return `200` with
`status: "refused"`.

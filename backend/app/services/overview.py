"""The home dashboard: fixed semantic plans run through the normal pipeline (no LLM)."""

from __future__ import annotations

import threading
import time
from typing import Any

from app.schemas.plan import QueryPlan
from app.services.query_service import QueryService

CACHE_SECONDS = 600

OVERVIEW_WIDGETS: list[dict[str, Any]] = [
    {
        "id": "kpis",
        "title": "Key figures",
        "question": "Key figures for all data",
        "plan": {
            "measures": [
                "total_sales",
                "order_count",
                "customer_count",
                "average_order_value",
                "average_rating",
                "late_delivery_rate",
            ]
        },
    },
    {
        "id": "monthly_revenue",
        "title": "Monthly revenue",
        "question": "Monthly total sales",
        "plan": {"measures": ["total_sales"], "dimensions": ["order_date"], "time_grain": "month"},
    },
    {
        "id": "top_categories",
        "title": "Top 10 categories",
        "question": "Top 10 product categories by product sales",
        "plan": {
            "measures": ["product_sales"],
            "dimensions": ["product_category"],
            "limit": 10,
            "order_by": [{"field": "product_sales", "direction": "desc"}],
        },
    },
    {
        "id": "sales_by_state",
        "title": "Sales by state",
        "question": "Total sales by customer state",
        "plan": {
            "measures": ["total_sales"],
            "dimensions": ["customer_state"],
            "limit": 15,
            "order_by": [{"field": "total_sales", "direction": "desc"}],
        },
    },
    {
        "id": "payment_mix",
        "title": "Payment type mix",
        "question": "Share of payments by payment type",
        "plan": {"measures": ["payment_amount"], "dimensions": ["payment_type"]},
    },
    {
        "id": "rating_distribution",
        "title": "Rating distribution",
        "question": "Number of orders by rating",
        "plan": {"measures": ["order_count"], "dimensions": ["rating"]},
    },
]

_lock = threading.Lock()
_cache: tuple[float, list[dict[str, Any]]] | None = None


def build_overview(service: QueryService, use_cache: bool = True) -> list[dict[str, Any]]:
    """Run every overview widget; results are cached briefly (the data is static)."""
    global _cache
    with _lock:
        if use_cache and _cache and time.monotonic() - _cache[0] < CACHE_SECONDS:
            return _cache[1]
    items = []
    for w in OVERVIEW_WIDGETS:
        resp = service.answer_plan(w["question"], QueryPlan(**w["plan"]))
        items.append({"id": w["id"], "title": w["title"], "result": resp})
    with _lock:
        _cache = (time.monotonic(), items)
    return items

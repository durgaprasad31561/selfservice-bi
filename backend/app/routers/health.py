"""GET /api/health — service status."""

from __future__ import annotations

from fastapi import APIRouter

from app.db import check_database, get_admin_engine, get_reader_engine
from app.nl2sql.llm import llm_status
from app.semantic.loader import get_model

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", summary="Database, LLM and semantic layer status")
def health() -> dict:
    """Report whether each dependency is reachable."""
    reader_ok, reader_detail = check_database(get_reader_engine())
    admin_ok, admin_detail = check_database(get_admin_engine())
    model = get_model()
    llm = llm_status()
    return {
        "status": "ok" if reader_ok and admin_ok and llm["ok"] else "degraded",
        "database": {
            "reader": {"ok": reader_ok, "detail": reader_detail},
            "admin": {"ok": admin_ok, "detail": admin_detail},
        },
        "llm": llm,
        "semantic_layer": {
            "ok": True,
            "measures": len(model.measures),
            "dimensions": len(model.dimensions),
        },
    }

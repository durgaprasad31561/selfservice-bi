"""POST /api/query (the full pipeline), saved-plan runs, suggestions and the overview."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.config import get_settings
from app.db import get_app_session
from app.models import User
from app.rate_limit import limiter
from app.schemas.plan import QueryPlan
from app.schemas.query import QueryRequest, QueryResponse
from app.semantic.catalog import SemanticCatalog
from app.semantic.state import get_catalog
from app.services.history import record
from app.services.overview import build_overview
from app.services.query_service import QueryService, get_query_service
from app.services.suggestions import build_suggestions

router = APIRouter(prefix="/api", tags=["query"])


class PlanRequest(BaseModel):
    question: str = Field("", max_length=2000)
    plan: QueryPlan


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Answer a business question (guard -> plan -> SQL -> checks)",
)
@limiter.limit(lambda: get_settings().query_rate_limit)
def query(
    request: Request,
    body: QueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_session),
    service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    response = service.answer(body.question)
    record(db, user, response)
    return response


@router.post(
    "/query/plan",
    response_model=QueryResponse,
    summary="Run a semantic plan directly (no LLM) - used by dashboards and the catalog",
)
def query_plan(
    body: PlanRequest,
    _: User = Depends(get_current_user),
    service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    return service.answer_plan(body.question, body.plan)


@router.get("/suggestions", summary="Example questions generated from the semantic layer")
def suggestions(
    _: User = Depends(get_current_user), catalog: SemanticCatalog = Depends(get_catalog)
) -> dict[str, Any]:
    return {"suggestions": build_suggestions(catalog)}


@router.get("/overview", summary="Home dashboard widgets, computed via the semantic layer")
def overview(
    _: User = Depends(get_current_user), service: QueryService = Depends(get_query_service)
) -> dict[str, Any]:
    return {"widgets": build_overview(service)}

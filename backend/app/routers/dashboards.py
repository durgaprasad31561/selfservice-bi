"""Dashboards and pinned widgets.

Every signed-in user can view dashboards (team BI). Analysts create dashboards and edit
their own; admins can edit any. Widgets store the question and plan (or validated
custom SQL) and are re-run on load, so the data is always fresh.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import can_edit_dashboards, get_current_user
from app.db import get_app_session
from app.models import Dashboard, Role, User, Widget
from app.models.base import utcnow
from app.schemas.dashboard import (
    DashboardCreate,
    DashboardDetail,
    DashboardOut,
    DashboardUpdate,
    WidgetCreate,
    WidgetOut,
    WidgetUpdate,
)
from app.schemas.plan import QueryPlan
from app.schemas.query import QueryResponse
from app.services.query_service import QueryService, get_query_service

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


def _can_edit(user: User, dashboard: Dashboard) -> bool:
    return user.role == Role.admin or (user.role == Role.analyst and dashboard.owner_id == user.id)


def _get(db: Session, dashboard_id: int) -> Dashboard:
    dashboard = db.get(Dashboard, dashboard_id)
    if dashboard is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard not found.")
    return dashboard


def _get_editable(db: Session, dashboard_id: int, user: User) -> Dashboard:
    dashboard = _get(db, dashboard_id)
    if not _can_edit(user, dashboard):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only change your own dashboards.")
    return dashboard


def _out(dashboard: Dashboard, user: User, widget_count: int) -> DashboardOut:
    out = DashboardOut.model_validate(dashboard)
    out.widget_count = widget_count
    out.can_edit = _can_edit(user, dashboard)
    return out


def run_widget(widget: Widget, service: QueryService) -> QueryResponse:
    """Re-run a widget from its saved plan / SQL (no LLM call)."""
    if widget.mode == "custom_sql" and widget.custom_sql:
        return service.answer_sql(widget.question, widget.custom_sql)
    return service.answer_plan(widget.question, QueryPlan.model_validate(widget.plan or {}))


def _widget_out(widget: Widget, service: QueryService | None) -> WidgetOut:
    out = WidgetOut.model_validate(widget)
    if service is not None:
        out.result = run_widget(widget, service)
    return out


# ------------------------------------------------------------- dashboards


@router.get("", response_model=list[DashboardOut], summary="All dashboards")
def list_dashboards(
    user: User = Depends(get_current_user), db: Session = Depends(get_app_session)
) -> list[DashboardOut]:
    counts = dict(
        db.execute(select(Widget.dashboard_id, func.count()).group_by(Widget.dashboard_id)).all()
    )
    dashboards = db.scalars(select(Dashboard).order_by(Dashboard.updated_at.desc()))
    return [_out(d, user, counts.get(d.id, 0)) for d in dashboards]


@router.post(
    "",
    response_model=DashboardOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a dashboard (analyst/admin)",
)
def create_dashboard(
    body: DashboardCreate,
    user: User = Depends(can_edit_dashboards),
    db: Session = Depends(get_app_session),
) -> DashboardOut:
    dashboard = Dashboard(
        owner_id=user.id, name=body.name.strip(), description=body.description.strip()
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return _out(dashboard, user, 0)


@router.get(
    "/{dashboard_id}",
    response_model=DashboardDetail,
    summary="A dashboard with its widgets re-run for fresh data",
)
def get_dashboard(
    dashboard_id: int,
    refresh: bool = Query(True, description="Re-run every widget"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_session),
    service: QueryService = Depends(get_query_service),
) -> DashboardDetail:
    dashboard = _get(db, dashboard_id)
    detail = DashboardDetail.model_validate(dashboard)
    detail.widgets = [_widget_out(w, service if refresh else None) for w in dashboard.widgets]
    detail.widget_count = len(detail.widgets)
    detail.can_edit = _can_edit(user, dashboard)
    return detail


@router.patch("/{dashboard_id}", response_model=DashboardOut, summary="Rename / describe")
def update_dashboard(
    dashboard_id: int,
    body: DashboardUpdate,
    user: User = Depends(can_edit_dashboards),
    db: Session = Depends(get_app_session),
) -> DashboardOut:
    dashboard = _get_editable(db, dashboard_id, user)
    if body.name is not None:
        dashboard.name = body.name.strip()
    if body.description is not None:
        dashboard.description = body.description.strip()
    db.commit()
    db.refresh(dashboard)
    return _out(dashboard, user, len(dashboard.widgets))


@router.delete(
    "/{dashboard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dashboard and its widgets",
)
def delete_dashboard(
    dashboard_id: int,
    user: User = Depends(can_edit_dashboards),
    db: Session = Depends(get_app_session),
) -> None:
    db.delete(_get_editable(db, dashboard_id, user))
    db.commit()


# ---------------------------------------------------------------- widgets


@router.get(
    "/{dashboard_id}/widgets",
    response_model=list[WidgetOut],
    summary="Widgets of a dashboard, re-run for fresh data",
)
def list_widgets(
    dashboard_id: int,
    refresh: bool = Query(True),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_app_session),
    service: QueryService = Depends(get_query_service),
) -> list[WidgetOut]:
    dashboard = _get(db, dashboard_id)
    return [_widget_out(w, service if refresh else None) for w in dashboard.widgets]


@router.post(
    "/{dashboard_id}/widgets",
    response_model=WidgetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Pin a query result",
)
def add_widget(
    dashboard_id: int,
    body: WidgetCreate,
    user: User = Depends(can_edit_dashboards),
    db: Session = Depends(get_app_session),
    service: QueryService = Depends(get_query_service),
) -> WidgetOut:
    dashboard = _get_editable(db, dashboard_id, user)
    plan = None
    if body.mode == "semantic":
        try:
            plan = QueryPlan.model_validate(body.plan).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid plan: {exc}"
            ) from exc
    position = max((w.position for w in dashboard.widgets), default=-1) + 1
    widget = Widget(
        dashboard_id=dashboard.id,
        title=body.title.strip(),
        question=body.question.strip(),
        mode=body.mode,
        plan=plan,
        custom_sql=body.custom_sql if body.mode == "custom_sql" else None,
        chart_type=body.chart_type,
        position=position,
    )
    result = run_widget(widget, service)  # must still be answerable and safe
    if result.status in ("refused", "error", "clarify"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"This result cannot be pinned: {result.reason or result.answer_text}",
        )
    db.add(widget)
    dashboard.updated_at = utcnow()
    db.commit()
    db.refresh(widget)
    out = WidgetOut.model_validate(widget)
    out.result = result
    return out


@router.patch(
    "/{dashboard_id}/widgets/{widget_id}",
    response_model=WidgetOut,
    summary="Rename, change chart or move a widget",
)
def update_widget(
    dashboard_id: int,
    widget_id: int,
    body: WidgetUpdate,
    user: User = Depends(can_edit_dashboards),
    db: Session = Depends(get_app_session),
) -> WidgetOut:
    _get_editable(db, dashboard_id, user)
    widget = db.get(Widget, widget_id)
    if widget is None or widget.dashboard_id != dashboard_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Widget not found.")
    for field in ("title", "chart_type", "position"):
        value = getattr(body, field)
        if value is not None:
            setattr(
                widget,
                field,
                value.strip() if isinstance(value, str) and field == "title" else value,
            )
    db.commit()
    db.refresh(widget)
    return WidgetOut.model_validate(widget)


@router.delete(
    "/{dashboard_id}/widgets/{widget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a widget",
)
def delete_widget(
    dashboard_id: int,
    widget_id: int,
    user: User = Depends(can_edit_dashboards),
    db: Session = Depends(get_app_session),
) -> None:
    _get_editable(db, dashboard_id, user)
    widget = db.get(Widget, widget_id)
    if widget is None or widget.dashboard_id != dashboard_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Widget not found.")
    db.delete(widget)
    db.commit()

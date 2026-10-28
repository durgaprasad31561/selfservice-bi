"""GET /api/history - questions asked, with their outcome."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_app_session
from app.models import QueryHistory, Role, User
from app.schemas.history import HistoryItem, HistoryPage

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=HistoryPage, summary="Your past questions (admins: all users)")
def history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    all_users: bool = Query(False, description="Admins only: include every user"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_app_session),
) -> HistoryPage:
    if all_users and user.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can see all users' history.")
    stmt = select(QueryHistory)
    if not all_users:
        stmt = stmt.where(QueryHistory.user_id == user.id)
    if status_filter:
        stmt = stmt.where(QueryHistory.status == status_filter)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(QueryHistory.created_at.desc(), QueryHistory.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(items)
    emails = (
        dict(
            db.execute(
                select(User.id, User.email).where(User.id.in_({r.user_id for r in rows}))
            ).all()
        )
        if rows
        else {}
    )
    out = []
    for r in rows:
        item = HistoryItem.model_validate(r)
        item.user_email = emails.get(r.user_id)
        out.append(item)
    return HistoryPage(
        items=out,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one of your history entries",
)
def delete_item(
    item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_app_session)
) -> None:
    item = db.get(QueryHistory, item_id)
    if item is None or (item.user_id != user.id and user.role != Role.admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "History entry not found.")
    db.delete(item)
    db.commit()

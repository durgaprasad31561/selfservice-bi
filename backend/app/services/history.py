"""Persist each answered question in app.query_history."""

from __future__ import annotations

import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import QueryHistory, User
from app.schemas.query import QueryResponse

log = logging.getLogger(__name__)


def record(db: Session, user: User, resp: QueryResponse) -> int | None:
    """Store the outcome; history problems never break the answer."""
    try:
        item = QueryHistory(
            user_id=user.id,
            question=resp.question[:2000],
            status=resp.status,
            answer_text=resp.answer_text,
            reason=resp.reason,
            sql=resp.sql,
            confidence=resp.confidence,
            mode=resp.explanation.mode,
            plan=resp.plan,
            warnings=resp.warnings or None,
            row_count=resp.row_count,
            execution_ms=resp.execution_ms,
            llm_model=resp.llm_model,
        )
        db.add(item)
        db.commit()
        return item.id
    except SQLAlchemyError as exc:
        db.rollback()
        log.error("could not save query history: %s", exc)
        return None

"""Database engines.

Two separate engines, never interchangeable:

* **admin** (``bi_admin`` locally, the database owner in the cloud) — app tables
  (users, dashboards, history) in schema ``app``.
* **reader** (``bi_reader``) — every user/LLM query. The role itself only has
  SELECT on ``analytics``; on top of that each connection is forced read-only and
  gets a statement timeout.

Session settings are applied with ``SET`` right after each connection opens (instead
of libpq startup ``options``), so the same code works on local PostgreSQL and on
managed services/poolers that do not accept startup options.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _apply_on_connect(engine: Engine, statements: list[str]) -> None:
    """Run SET statements on every new DBAPI connection of ``engine``."""

    @event.listens_for(engine, "connect")
    def _configure(dbapi_connection: Any, _record: Any) -> None:
        with dbapi_connection.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
        dbapi_connection.commit()


@lru_cache(maxsize=1)
def get_admin_engine() -> Engine:
    """Engine for application tables (schema ``app``)."""
    settings = get_settings()
    engine = create_engine(
        settings.admin_database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 10},
    )
    _apply_on_connect(engine, ["SET search_path = app"])
    return engine


@lru_cache(maxsize=1)
def get_reader_engine() -> Engine:
    """Read-only engine for analytics queries, with a server-side statement timeout."""
    settings = get_settings()
    engine = create_engine(
        settings.reader_database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
        connect_args={"connect_timeout": 10},
    )
    _apply_on_connect(
        engine,
        [
            f"SET statement_timeout = {int(settings.query_timeout_ms)}",
            "SET default_transaction_read_only = on",
            "SET search_path = analytics",
        ],
    )
    return engine


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_admin_engine(), expire_on_commit=False)


def get_app_session() -> Iterator[Session]:
    """FastAPI dependency: a session on the app schema (admin engine)."""
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_database(engine: Engine) -> tuple[bool, str]:
    """Return (ok, detail) after a trivial round trip."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - report any connectivity failure
        return False, f"{type(exc).__name__}: {exc}".splitlines()[0]

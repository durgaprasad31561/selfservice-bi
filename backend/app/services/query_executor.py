"""Execute validated SQL on the read-only connection.

Defence in depth on top of the SQL validator:
* only the ``bi_reader`` engine is accepted; the first use verifies on the server
  that the session user is not the admin role and is read-only;
* every query runs in a READ ONLY transaction with ``SET LOCAL statement_timeout``;
* at most ``max_rows`` rows are fetched; the transaction is always rolled back.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError

log = logging.getLogger(__name__)


class QueryExecutionError(RuntimeError):
    """A query failed; ``message`` is safe to show to users."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ExecutionResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int
    truncated: bool
    execution_ms: int


_PG_CODES = {
    "57014": (
        "timeout",
        "The query took too long and was stopped. Try a narrower question "
        "(e.g. a shorter period or fewer groups).",
    ),
    "42501": ("permission", "The query tried to access data it is not allowed to read."),
    "25006": ("read_only", "The query tried to change data, which is not allowed."),
}


class QueryExecutor:
    """Runs SQL on the read-only engine with a timeout and a row cap."""

    def __init__(
        self,
        engine: Engine,
        timeout_ms: int,
        max_rows: int,
        forbidden_users: tuple[str, ...] = ("bi_admin", "postgres"),
    ) -> None:
        user = (engine.url.username or "").lower()
        if user in forbidden_users:
            raise RuntimeError(f"Refusing to run user queries as privileged role '{user}'.")
        self.engine = engine
        self.timeout_ms = int(timeout_ms)
        self.max_rows = int(max_rows)
        self.forbidden_users = forbidden_users
        self._verified = False
        self._lock = threading.Lock()

    def verify_connection(self) -> None:
        """Check on the server that the session is unprivileged and read-only."""
        with self.engine.connect() as conn:
            user, read_only, superuser = conn.execute(
                text(
                    "SELECT current_user, current_setting('default_transaction_read_only'), "
                    "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user)"
                )
            ).one()
        if user in self.forbidden_users or superuser:
            raise RuntimeError(f"User queries must not run as '{user}'.")
        if read_only != "on":
            raise RuntimeError(f"Connection for '{user}' is not read-only.")
        self._verified = True
        log.info("query executor verified: user=%s read_only=%s", user, read_only)

    def run(self, sql: str, params: dict[str, Any] | None = None) -> ExecutionResult:
        """Execute ``sql`` (already validated) and return at most max_rows rows."""
        if not self._verified:
            with self._lock:
                if not self._verified:
                    self.verify_connection()
        started = time.perf_counter()
        try:
            with self.engine.connect() as conn:
                trans = conn.begin()
                try:
                    conn.execute(text("SET TRANSACTION READ ONLY"))
                    conn.execute(text(f"SET LOCAL statement_timeout = {self.timeout_ms}"))
                    result = conn.execute(text(sql), params or {})
                    columns = list(result.keys())
                    rows = [tuple(r) for r in result.fetchmany(self.max_rows + 1)]
                finally:
                    trans.rollback()
        except DBAPIError as exc:
            raise self._translate(exc) from exc
        except SQLAlchemyError as exc:
            log.warning("query failed before execution: %s", exc)
            raise QueryExecutionError(
                "db_error", "The query could not be prepared for the database."
            ) from exc
        truncated = len(rows) > self.max_rows
        return ExecutionResult(
            columns=columns,
            rows=rows[: self.max_rows],
            row_count=min(len(rows), self.max_rows),
            truncated=truncated,
            execution_ms=int((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _translate(exc: DBAPIError) -> QueryExecutionError:
        code = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if code in _PG_CODES:
            kind, message = _PG_CODES[code]
            log.warning("query rejected by database (%s): %s", code, str(exc.orig)[:200])
            return QueryExecutionError(kind, message)
        if isinstance(exc, OperationalError):
            log.error("database unavailable: %s", exc)
            return QueryExecutionError(
                "db_unavailable", "The analytics database is not reachable right now."
            )
        log.warning("query failed (%s): %s", code, str(getattr(exc, "orig", exc))[:300])
        return QueryExecutionError("db_error", "The database could not run this query.")

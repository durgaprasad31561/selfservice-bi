"""The only path from SQL to the database: validate, then execute read-only.

* :meth:`SafeSQLRunner.run_compiled` — SQL compiled from a semantic plan (bound
  parameters allowed) is validated too, as defence in depth.
* :meth:`SafeSQLRunner.run_generated` — Mode B: LLM-written SQL is validated; if it
  is rejected the LLM gets one chance to fix it with the validator's errors; if it is
  still rejected it is never executed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.nl2sql.sql_generator import GeneratedSQL, SQLGenerator
from app.safety.sql_validator import SQLValidator, ValidationResult
from app.semantic.compiler import CompiledQuery
from app.services.query_executor import ExecutionResult, QueryExecutor

log = logging.getLogger("app.safety")


class UnsafeSQLError(RuntimeError):
    """SQL failed validation and was not executed."""

    def __init__(self, validation: ValidationResult, sql: str) -> None:
        super().__init__(validation.message)
        self.validation = validation
        self.sql = sql


@dataclass
class SQLRun:
    """A validated and executed query."""

    sql: str  # SQL actually executed (may be wrapped to enforce LIMIT)
    display_sql: str  # what users see
    params: dict[str, Any]
    validation: ValidationResult
    result: ExecutionResult
    generated: GeneratedSQL | None = None
    repaired: bool = False
    notes: list[str] = field(default_factory=list)


class SafeSQLRunner:
    """Validator + read-only executor."""

    def __init__(self, validator: SQLValidator, executor: QueryExecutor) -> None:
        self.validator = validator
        self.executor = executor
        self.blocked_count = 0  # rejected queries (for monitoring/evaluation)

    def _check(self, sql: str, allow_parameters: bool) -> ValidationResult:
        validation = self.validator.validate(sql, allow_parameters=allow_parameters)
        if not validation.ok:
            self.blocked_count += 1
            log.warning("SQL blocked: %s | %s", validation.message, " ".join(sql.split())[:500])
        return validation

    def run_compiled(self, compiled: CompiledQuery) -> SQLRun:
        validation = self._check(compiled.sql, allow_parameters=True)
        if not validation.ok:
            raise UnsafeSQLError(validation, compiled.sql)
        result = self.executor.run(validation.sql, compiled.params)
        return SQLRun(validation.sql, compiled.display_sql, compiled.params, validation, result)

    def run_untrusted(self, sql: str) -> SQLRun:
        """Validate and run SQL from outside the compiler (e.g. a saved custom query)."""
        validation = self._check(sql, allow_parameters=False)
        if not validation.ok:
            raise UnsafeSQLError(validation, sql)
        result = self.executor.run(validation.sql)
        notes = (
            [f"Results were limited to {validation.limit} rows."]
            if validation.limit_enforced
            else []
        )
        return SQLRun(validation.sql, sql, {}, validation, result, notes=notes)

    def validate_generated(
        self, question: str, generator: SQLGenerator
    ) -> tuple[GeneratedSQL, ValidationResult | None, bool]:
        """Generate SQL and validate it, with one repair round. Nothing is executed."""
        generated = generator.generate(question)
        if not generated.can_answer or not generated.sql:
            return generated, None, False
        validation = self._check(generated.sql, allow_parameters=False)
        if validation.ok:
            return generated, validation, False
        retry = generator.generate(
            question, feedback=validation.message, previous_sql=generated.sql
        )
        if not retry.can_answer or not retry.sql:
            return retry, None, True
        return retry, self._check(retry.sql, allow_parameters=False), True

    def run_generated(self, question: str, generator: SQLGenerator) -> SQLRun | GeneratedSQL:
        """Mode B end to end. Returns the GeneratedSQL refusal when the LLM declines."""
        generated, validation, repaired = self.validate_generated(question, generator)
        if validation is None:
            return generated
        if not validation.ok:
            raise UnsafeSQLError(validation, generated.sql or "")
        result = self.executor.run(validation.sql)
        notes = []
        if validation.limit_enforced:
            notes.append(f"Results were limited to {validation.limit} rows.")
        return SQLRun(
            validation.sql,
            generated.sql or "",
            {},
            validation,
            result,
            generated=generated,
            repaired=repaired,
            notes=notes,
        )

"""Mode B (fallback): business question -> one SELECT against the analytics schema.

Used only when the planner says the question is answerable but cannot be expressed
as a semantic plan. The SQL returned here is UNTRUSTED: it must pass
``app.safety.sql_validator`` before it is ever executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.nl2sql.llm import LLMClient, get_llm_client
from app.nl2sql.prompts import sql_system_prompt
from app.semantic.catalog import SemanticCatalog


class LLMSql(BaseModel):
    """A single SQL query answering the question."""

    can_answer: bool = Field(True, description="False if the tables cannot answer it")
    reason: str | None = Field(None, description="Why it cannot be answered")
    sql: str | None = Field(None, description="One PostgreSQL SELECT statement, no semicolon")
    explanation: str | None = Field(None, description="One sentence: what the query computes")
    assumptions: list[str] = Field(default_factory=list)


@dataclass
class GeneratedSQL:
    can_answer: bool
    sql: str | None
    explanation: str | None
    reason: str | None
    model: str
    latency_ms: int
    assumptions: list[str] = field(default_factory=list)


class SQLGenerator:
    """Writes fallback SQL with the semantic layer as context."""

    def __init__(
        self, catalog: SemanticCatalog, max_rows: int, llm: LLMClient | None = None
    ) -> None:
        self.catalog = catalog
        self.max_rows = max_rows
        self._llm = llm

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    def generate(
        self, question: str, feedback: str | None = None, previous_sql: str | None = None
    ) -> GeneratedSQL:
        """Generate SQL; ``feedback`` (e.g. validator errors) triggers a corrected attempt."""
        messages = [
            SystemMessage(sql_system_prompt(self.catalog, self.max_rows)),
            HumanMessage(f"QUESTION: {question}"),
        ]
        if feedback:
            messages += [
                AIMessage(previous_sql or ""),
                HumanMessage(
                    f"That SQL was rejected: {feedback}\nReturn a corrected query "
                    "that follows every rule, or can_answer=false."
                ),
            ]
        result = self.llm.structured(
            messages, LLMSql, purpose="sql" if not feedback else "sql_repair"
        )
        parsed = result.parsed
        if not isinstance(parsed, LLMSql):
            try:
                parsed = LLMSql.model_validate_json(result.raw_text)
            except ValueError:
                return GeneratedSQL(
                    False,
                    None,
                    None,
                    "The AI model returned no usable SQL.",
                    result.model,
                    result.latency_ms,
                )
        sql = (parsed.sql or "").strip().rstrip(";").strip() or None
        can = parsed.can_answer and sql is not None
        return GeneratedSQL(
            can_answer=can,
            sql=sql if can else None,
            explanation=parsed.explanation,
            reason=parsed.reason if not can else None,
            model=result.model,
            latency_ms=result.latency_ms,
            assumptions=parsed.assumptions,
        )

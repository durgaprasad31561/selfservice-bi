"""Checks on the raw question, BEFORE any LLM call.

1. empty / too short / too long
2. prompt-injection attempts and SQL commands typed into the question
3. obviously off-topic requests
4. unsupported concepts from the semantic layer (profit, inventory, India ...)

Matching is case- and accent-insensitive on whole words/phrases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.semantic.catalog import SemanticCatalog, normalize
from app.semantic.loader import SemanticModel

MIN_LENGTH = 3
MAX_LENGTH = 500

#: Raw-text patterns (checked on the lowercased question, before normalization).
INJECTION_PATTERNS: list[tuple[str, str]] = [
    (
        r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(instruction|instructions|rules|"
        r"prompt|prompts|guardrails|above|previous|prior|system)\b",
        "instruction override",
    ),
    (
        r"\b(system prompt|developer mode|jailbreak|dan mode|you are now|act as|pretend to be|"
        r"roleplay as)\b",
        "role manipulation",
    ),
    (
        r"\b(reveal|show|print|repeat|leak)\b.{0,30}\b(prompt|instructions|system message|"
        r"api key|password|secret|credentials)\b",
        "prompt or secret extraction",
    ),
    (r"\b(drop|truncate|alter)\s+(table|database|schema|role|user)\b", "SQL command"),
    (
        r"\bdelete\s+from\b|\binsert\s+into\b|\bupdate\s+\w+\s+set\b|\bgrant\s+\w+|\brevoke\s+\w+",
        "SQL command",
    ),
    (r";\s*(select|drop|delete|update|insert|create|alter|grant|copy)\b", "SQL command"),
    (r"--|/\*|\*/", "SQL comment"),
    (
        r"\bunion\s+(all\s+)?select\b|\bpg_sleep\b|\bpg_read_file\b|\bdblink\b|\bxp_cmdshell\b|"
        r"\bcopy\s+.+\bto\b\s+program\b|\binformation_schema\b|\bpg_catalog\b|\bpg_shadow\b",
        "SQL injection",
    ),
    (r"\b(select|with)\b[\s\S]{0,200}\bfrom\b\s+(analytics|raw|app|public)\.", "raw SQL"),
]

#: Off-topic signals; only used when the question also mentions no business term.
OFF_TOPIC_KEYWORDS = {
    "weather",
    "poem",
    "joke",
    "recipe",
    "song",
    "lyrics",
    "story",
    "president",
    "capital of",
    "football",
    "movie",
    "translate",
    "write code",
    "python code",
    "javascript",
    "who are you",
    "what are you",
    "how are you",
    "hello",
    "hi",
    "hey",
    "thanks",
    "thank you",
    "good morning",
    "meaning of life",
    "horoscope",
    "bitcoin",
    "stock price",
    "news",
}


@dataclass
class GuardResult:
    """Outcome of the pre-LLM checks."""

    ok: bool
    code: str | None = None  # empty | too_long | injection | off_topic | unsupported
    reason: str | None = None
    suggestions: list[str] = field(default_factory=list)
    concept: str | None = None


def _contains_phrase(norm_text: str, phrase: str) -> bool:
    return f" {normalize(phrase)} " in f" {norm_text} "


def find_unsupported_concept(question: str, model: SemanticModel):
    """The first unsupported concept mentioned in the question, if any."""
    norm = normalize(question)
    for concept in model.unsupported_concepts:
        masked = norm
        for allowed in concept.except_:
            masked = f" {masked} ".replace(f" {normalize(allowed)} ", " _ok_ ").strip()
        if any(_contains_phrase(masked, kw) for kw in concept.keywords):
            return concept
    return None


def check_question(question: str, catalog: SemanticCatalog) -> GuardResult:
    """Run all pre-LLM checks on the question text."""
    text = (question or "").strip()
    if len(text) < MIN_LENGTH:
        return GuardResult(
            False,
            "empty",
            "The question is empty.",
            ["Ask a business question, e.g. 'Total sales in 2017'."],
        )
    if len(text) > MAX_LENGTH:
        return GuardResult(
            False,
            "too_long",
            f"The question is too long ({len(text)} characters; the limit is " f"{MAX_LENGTH}).",
            ["Ask one short, specific question at a time."],
        )

    lowered = text.lower()
    for pattern, label in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return GuardResult(
                False,
                "injection",
                f"The question contains instructions or commands ({label}) instead of a "
                "business question. Only read-only questions about the data can be answered.",
                ["Ask about the data, e.g. 'Top 5 categories by product sales in 2018'."],
            )

    concept = find_unsupported_concept(text, catalog.model)
    if concept is not None:
        suggestions = [concept.suggestion] if concept.suggestion else []
        if concept.name == "other_country":
            states = [v.display for v in catalog.values("customer_state")]
            if states:
                suggestions.append(
                    f"The data covers {len(states)} Brazilian states, for example São Paulo, "
                    "Rio de Janeiro and Minas Gerais."
                )
        return GuardResult(False, "unsupported", concept.reason, suggestions, concept.name)

    norm = normalize(text)
    terms = catalog.find_terms(text)
    has_business_term = bool(terms["measures"] or terms["dimensions"])
    if not has_business_term and any(_contains_phrase(norm, kw) for kw in OFF_TOPIC_KEYWORDS):
        return GuardResult(
            False,
            "off_topic",
            "This question is not about the e-commerce data I can analyse.",
            [
                "Ask about sales, orders, customers, products, sellers, payments, reviews or "
                "deliveries in Brazil between 2016 and 2018."
            ],
        )
    return GuardResult(True)

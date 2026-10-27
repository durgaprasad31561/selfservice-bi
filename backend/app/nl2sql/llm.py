"""LLM provider factory (Gemini / OpenAI via LangChain) with retries, fallback and logging.

* Provider and model names come from .env only.
* temperature 0, request timeout, exponential backoff on transient errors
  (429 / 5xx / timeouts), then the next configured fallback model.
* A model that keeps failing with transient errors is skipped for a cool-down
  period so requests go straight to a healthy fallback.
* Every call is logged (prompt, output, latency) to ``logs/llm_calls.jsonl``.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from app.config import PROJECT_ROOT, Settings, get_settings

log = logging.getLogger("app.llm")

LOG_FILE = PROJECT_ROOT / "logs" / "llm_calls.jsonl"
COOL_DOWN_SECONDS = 60.0
_TRANSIENT_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "UNAVAILABLE",
    "DEADLINE",
    "RESOURCE_EXHAUSTED",
    "overloaded",
    "high demand",
    "timed out",
    "timeout",
    "Timeout",
    "rate limit",
    "RateLimit",
    "Connection",
    "temporarily",
)


class LLMError(RuntimeError):
    """An LLM problem with a message safe to show to users."""


class LLMNotConfigured(LLMError):
    """No API key or model configured for the selected provider."""


class LLMUnavailable(LLMError):
    """All configured models failed with transient errors."""


@dataclass
class StructuredResult:
    """Outcome of a structured-output call."""

    parsed: BaseModel | None
    raw_text: str
    parsing_error: str | None
    model: str
    latency_ms: int
    attempts: int


_OVERLOAD_MARKERS = ("503", "504", "UNAVAILABLE", "DEADLINE", "overloaded", "high demand")


def is_overloaded(exc: BaseException) -> bool:
    """True when the model itself is overloaded: switch to a fallback instead of waiting."""
    text = f"{type(exc).__name__}: {exc}"
    return any(marker in text for marker in _OVERLOAD_MARKERS)


_QUOTA_MARKERS = ("RESOURCE_EXHAUSTED", "quota", "insufficient_quota")
DEFAULT_QUOTA_COOL_DOWN = 3600.0


def is_quota_exhausted(exc: BaseException) -> bool:
    """True when the API key's quota for this model is used up (retrying will not help)."""
    text = f"{type(exc).__name__}: {exc}"
    return any(marker in text for marker in _QUOTA_MARKERS)


def quota_retry_seconds(exc: BaseException) -> float:
    """Seconds until the quota resets, from the provider's message (default 1 hour)."""
    text = str(exc)
    m = re.search(r"retryDelay'?:\s*'?(\d+)s", text)
    if m:
        return min(float(m.group(1)), 86_400.0)
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", text)
    if m and any(m.groups()):
        h, mi, se = (float(g) if g else 0.0 for g in m.groups())
        return min(h * 3600 + mi * 60 + se, 86_400.0)
    return DEFAULT_QUOTA_COOL_DOWN


def is_transient(exc: BaseException) -> bool:
    """True for errors worth retrying (rate limits, overload, timeouts, 5xx)."""
    text = f"{type(exc).__name__}: {exc}"
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _message_text(message: Any) -> str:
    if message is None:
        return ""
    text = getattr(message, "text", None)
    if isinstance(text, str):  # langchain-core 1.x: str subclass (also callable)
        if text:
            return str(text)
    elif callable(text):  # older langchain-core
        text = text()
        if text:
            return str(text)
    content = getattr(message, "content", "")
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content)


def _write_log(entry: dict[str, Any]) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:  # logging must never break a request
        log.warning("cannot write LLM log: %s", exc)


class LLMClient:
    """Thin wrapper over LangChain chat models for one provider."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.llm_provider
        self.models = settings.llm_models
        self._chats: dict[str, BaseChatModel] = {}
        self._unhealthy_until: dict[str, float] = {}
        self._lock = threading.Lock()
        problem = self.configuration_problem()
        if problem:
            raise LLMNotConfigured(problem)

    # ------------------------------------------------------------- factory

    def configuration_problem(self) -> str | None:
        key_var = "GEMINI_API_KEY" if self.provider == "gemini" else "OPENAI_API_KEY"
        model_var = "GEMINI_MODEL" if self.provider == "gemini" else "OPENAI_MODEL"
        if not self.settings.llm_api_key:
            return (
                f"The AI model is not configured: {key_var} is empty in .env "
                f"(LLM_PROVIDER={self.provider})."
            )
        if not self.models:
            return f"The AI model is not configured: {model_var} is empty in .env."
        return None

    def _chat(self, model: str) -> BaseChatModel:
        with self._lock:
            if model not in self._chats:
                self._chats[model] = self._build(model)
            return self._chats[model]

    def _build(self, model: str) -> BaseChatModel:
        s = self.settings
        if self.provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            kwargs: dict[str, Any] = {}
            if s.gemini_thinking_level and model.startswith("gemini-3"):
                kwargs["thinking_level"] = s.gemini_thinking_level
            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=s.gemini_api_key,
                temperature=0,
                timeout=s.llm_timeout_seconds,
                max_retries=0,
                **kwargs,
            )
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=s.openai_api_key,
            temperature=0,
            timeout=s.llm_timeout_seconds,
            max_retries=0,
        )

    def _ordered_models(self) -> list[str]:
        now = time.monotonic()
        healthy = [m for m in self.models if self._unhealthy_until.get(m, 0) <= now]
        cooling = [m for m in self.models if m not in healthy]
        return healthy + cooling

    # ---------------------------------------------------------------- calls

    def structured(
        self, messages: list[BaseMessage], schema: type[BaseModel], purpose: str
    ) -> StructuredResult:
        """Call the model for ``schema``-shaped output; never raises on bad JSON."""
        method = "json_schema" if self.provider == "gemini" else "function_calling"
        attempts = 0
        last_error: BaseException | None = None
        started = time.perf_counter()
        models = self._ordered_models()
        all_quota, quota_seen = True, False
        for index, model in enumerate(models):
            has_fallback = index < len(models) - 1
            quota_hit = False
            runnable = self._chat(model).with_structured_output(
                schema, include_raw=True, method=method
            )
            for attempt in range(self.settings.llm_max_retries + 1):
                attempts += 1
                t0 = time.perf_counter()
                try:
                    out = runnable.invoke(messages)
                except Exception as exc:  # noqa: BLE001 - classified below
                    last_error = exc
                    latency = int((time.perf_counter() - t0) * 1000)
                    self._log(purpose, model, messages, None, latency, error=exc)
                    if not is_transient(exc):
                        raise LLMError(
                            f"The AI model request failed ({type(exc).__name__}). "
                            "Check the API key and model name in .env."
                        ) from exc
                    if is_quota_exhausted(exc):
                        cool = quota_retry_seconds(exc)
                        self._unhealthy_until[model] = time.monotonic() + cool
                        log.warning("quota exhausted for %s (resets in %.0f min)", model, cool / 60)
                        quota_hit = True
                        break  # retrying the same model cannot succeed
                    if is_overloaded(exc) and has_fallback:
                        break  # go straight to the next model
                    if attempt < self.settings.llm_max_retries:
                        time.sleep(min(2**attempt, 8))
                    continue
                latency = int((time.perf_counter() - t0) * 1000)
                raw_text = _message_text(out.get("raw"))
                error = out.get("parsing_error")
                parsed = out.get("parsed")
                self._unhealthy_until.pop(model, None)
                self._log(
                    purpose,
                    model,
                    messages,
                    raw_text,
                    latency,
                    error=error,
                    parsed=parsed is not None,
                )
                return StructuredResult(
                    parsed=parsed,
                    raw_text=raw_text,
                    parsing_error=str(error) if error else None,
                    model=model,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    attempts=attempts,
                )
            quota_seen = quota_seen or quota_hit
            all_quota = all_quota and quota_hit
            if not quota_hit:
                self._unhealthy_until[model] = time.monotonic() + COOL_DOWN_SECONDS
            log.warning("model %s unavailable, trying next fallback", model)
        if all_quota and quota_seen:
            raise LLMUnavailable(
                "The AI model's usage quota is used up for now (API plan limit). "
                "Try again later, or configure another model or provider in .env."
            ) from last_error
        raise LLMUnavailable(
            "The AI model is temporarily unavailable (high demand). Please try again in a minute."
        ) from last_error

    def _log(
        self,
        purpose: str,
        model: str,
        messages: list[BaseMessage],
        output: str | None,
        latency_ms: int,
        error: object = None,
        parsed: bool | None = None,
    ) -> None:
        log.info(
            "llm %s model=%s latency=%dms ok=%s%s",
            purpose,
            model,
            latency_ms,
            error is None,
            f" error={type(error).__name__}" if error else "",
        )
        _write_log(
            {
                "ts": datetime.now(UTC).isoformat(),
                "purpose": purpose,
                "provider": self.provider,
                "model": model,
                "latency_ms": latency_ms,
                "ok": error is None,
                "parsed": parsed,
                "error": f"{type(error).__name__}: {error}"[:500] if error else None,
                "prompt": [{"role": m.type, "content": _message_text(m)} for m in messages],
                "output": output,
            }
        )


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """The configured client; raises LLMNotConfigured with a clear message."""
    return LLMClient(get_settings())


def llm_status() -> dict[str, Any]:
    """Configuration status for /api/health (does not call the provider)."""
    settings = get_settings()
    try:
        client = get_llm_client()
    except LLMNotConfigured as exc:
        return {
            "ok": False,
            "provider": settings.llm_provider,
            "models": settings.llm_models,
            "detail": str(exc),
        }
    now = time.monotonic()
    return {
        "ok": True,
        "provider": client.provider,
        "models": client.models,
        "cooling_down": [m for m, t in client._unhealthy_until.items() if t > now],
        "detail": "configured",
    }

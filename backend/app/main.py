"""FastAPI application entry point."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.app_setup import init_app_database
from app.config import get_settings
from app.logging_config import configure_logging, request_id_var
from app.nl2sql.llm import llm_status
from app.rate_limit import limiter
from app.routers import auth, dashboards, health, history, metadata, query
from app.semantic.loader import get_model
from app.semantic.state import load_catalog

configure_logging()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Validate the semantic model (fail fast), prepare app tables, warm the catalog."""
    get_model()  # raises SemanticModelError on an invalid model.yaml -> app does not start
    try:
        init_app_database()
    except Exception as exc:  # noqa: BLE001 - reported clearly, app still serves /api/health
        log.error("cannot prepare app tables (is PostgreSQL running?): %s", exc)
    try:
        load_catalog()
    except Exception as exc:  # noqa: BLE001 - DB may come up later; catalog loads lazily
        log.error("database not reachable at startup, catalog will load on first use: %s", exc)
    llm = llm_status()
    if llm["ok"]:
        log.info("LLM provider %s, models %s", llm["provider"], llm["models"])
    else:
        log.error("LLM NOT CONFIGURED - questions cannot be answered: %s", llm["detail"])
    yield


def _error(status_code: int, detail: object, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "error": code, "request_id": request_id_var.get()},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Self-Service BI API",
        description=(
            "Ask business questions about the Olist Brazilian e-commerce dataset in plain "
            "English. Questions are interpreted through a YAML semantic layer, converted to "
            "SQL, validated, run read-only and checked before an answer is returned.\n\n"
            "Log in with **Authorize** (email + password) to try the protected endpoints."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.limiter = limiter

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                },
            )
            return response
        finally:
            request_id_var.reset(token)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limited(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        return _error(
            429,
            f"Too many questions; the limit is {exc.detail}. Please wait a moment.",
            "rate_limited",
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        response = _error(exc.status_code, exc.detail, "http_error")
        for key, value in (exc.headers or {}).items():
            response.headers[key] = value
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg")}
            for e in exc.errors()
        ]
        return _error(422, errors, "validation_error")

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error: %s", exc)
        return _error(500, "Internal server error. The problem has been logged.", "internal_error")

    for module in (health, auth, query, metadata, dashboards, history):
        app.include_router(module.router)
    return app


app = create_app()

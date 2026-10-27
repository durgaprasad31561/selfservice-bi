"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, metadata
from app.semantic.loader import get_model
from app.semantic.state import load_catalog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Validate the semantic model (fail fast) and warm the catalog."""
    get_model()  # raises SemanticModelError on an invalid model.yaml -> app does not start
    try:
        load_catalog()
    except Exception as exc:  # noqa: BLE001 - DB may come up later; catalog loads lazily
        log.error("database not reachable at startup, catalog will load on first use: %s", exc)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Self-Service BI API",
        description="Natural-language questions over the Olist dataset via a semantic layer.",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(metadata.router)
    return app


app = create_app()

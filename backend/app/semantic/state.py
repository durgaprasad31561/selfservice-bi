"""Process-wide access to the semantic catalog.

The semantic model is loaded (and validated) eagerly at startup. The catalog also
needs the database for allowed values and coverage; if the database is down at
startup the app still starts and the catalog is loaded on first use.
"""

from __future__ import annotations

import logging
import threading

from fastapi import HTTPException, status

from app.db import get_reader_engine
from app.semantic.catalog import SemanticCatalog
from app.semantic.loader import get_model

log = logging.getLogger(__name__)

_lock = threading.Lock()
_catalog: SemanticCatalog | None = None


def load_catalog() -> SemanticCatalog:
    """(Re)load the catalog from the database; raises on failure."""
    global _catalog
    with _lock:
        catalog = SemanticCatalog.from_database(get_model(), get_reader_engine())
        _catalog = catalog
        log.info(
            "semantic catalog loaded: %d measures, %d dimensions, data %s",
            len(catalog.model.measures),
            len(catalog.model.dimensions),
            catalog.coverage.describe() if catalog.coverage else "n/a",
        )
        return catalog


def get_catalog() -> SemanticCatalog:
    """FastAPI dependency: the loaded catalog, loading it lazily if needed."""
    if _catalog is not None:
        return _catalog
    try:
        return load_catalog()
    except Exception as exc:
        log.error("cannot load semantic catalog: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The analytics database is not reachable, so the data catalog is unavailable.",
        ) from exc


def set_catalog(catalog: SemanticCatalog | None) -> None:
    """Replace the catalog (used by tests)."""
    global _catalog
    with _lock:
        _catalog = catalog

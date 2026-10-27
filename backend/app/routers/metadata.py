"""GET /api/metadata — the business-friendly semantic catalog."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.semantic.catalog import SemanticCatalog
from app.semantic.state import get_catalog

router = APIRouter(prefix="/api", tags=["metadata"])


@router.get("/metadata", summary="Measures, dimensions, allowed values and data coverage")
def metadata(
    include_values: bool = Query(True, description="Include allowed values per dimension"),
    catalog: SemanticCatalog = Depends(get_catalog),
) -> dict:
    """Return the semantic layer as business users see it."""
    return catalog.metadata(include_values=include_values)

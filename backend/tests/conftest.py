"""Shared pytest fixtures.

Tests marked ``integration`` need the loaded PostgreSQL database and are skipped
automatically when it is not reachable.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from app.db import check_database, get_reader_engine
from app.semantic.catalog import SemanticCatalog
from app.semantic.loader import SemanticModel, get_model


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: needs the loaded PostgreSQL database")


@pytest.fixture(scope="session")
def model() -> SemanticModel:
    return get_model()


@pytest.fixture(scope="session")
def reader_engine() -> Engine:
    engine = get_reader_engine()
    ok, detail = check_database(engine)
    if not ok:
        pytest.skip(f"PostgreSQL not reachable: {detail}")
    return engine


@pytest.fixture(scope="session")
def catalog(model: SemanticModel, reader_engine: Engine) -> SemanticCatalog:
    return SemanticCatalog.from_database(model, reader_engine)

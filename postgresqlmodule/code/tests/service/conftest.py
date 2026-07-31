"""Django setup + a fake-backed foundation for shell tests (doc 13 §13.4)."""
from __future__ import annotations

import os

import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pgfoundation_service.settings")
django.setup()

from django.test import AsyncRequestFactory  # noqa: E402

from pgfoundation import DataFoundation, ResultSet  # noqa: E402
from pgfoundation._internal.config.loader import load_settings  # noqa: E402
from pgfoundation._internal.drivers.fake import FakeDriver  # noqa: E402

from pgfoundation_service import bootstrap  # noqa: E402
from pgfoundation_service.auth import AuthGate  # noqa: E402


@pytest.fixture
def arf() -> AsyncRequestFactory:
    return AsyncRequestFactory()


@pytest.fixture
async def foundation():
    def responder(spec):
        sql = spec.sql.strip().upper()
        if sql.startswith("SELECT"):
            return ResultSet(rows=[{"id": 1, "total": "9.90"}], rowcount=1, elapsed_ms=1.5)
        return ResultSet(rows=[], rowcount=2, elapsed_ms=0.8)

    settings = load_settings(
        {"datasources": [{"name": "orders", "dsn": "postgresql://x/orders"}]}
    )
    db = await DataFoundation.from_settings(settings, driver=FakeDriver(responder))
    bootstrap.set_foundation(db)
    bootstrap.set_auth_gate(AuthGate(enabled=False))  # auth disabled by default
    yield db
    await db.aclose()

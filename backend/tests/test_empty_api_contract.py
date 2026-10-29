"""Empty-result HTTP contracts using a fake DB, not PostgreSQL integration proof."""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_session
from app.main import app
from app.routes import costs, media, sitreps
from app.services import snapshots


class EmptyResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def one_or_none(self):
        return None

    def scalar_one_or_none(self):
        return None

    def scalar_one(self):
        return 0

    def scalar(self):
        return 0

    def __iter__(self):
        return iter(())


class EmptySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement, *args, **kwargs):
        return EmptyResult()


@pytest.fixture
def empty_api(monkeypatch):
    monkeypatch.setattr(settings, "live_ingestion_enabled", False)
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "admin_api_key", "")
    for module in (costs, media, sitreps, snapshots):
        monkeypatch.setattr(module, "async_session", EmptySession)
    async def dependency():
        yield EmptySession()
    app.dependency_overrides[get_session] = dependency
    try:
        # No lifespan: no background service or database is launched by this test.
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize("path,expected", [
    ("/events", []), ("/events/anomalies", []), ("/events/batch?ids=1,2", []),
    ("/events/time-range", {"earliest":None,"latest":None}),
    ("/media/intel", {"media":[],"total":0}), ("/sitreps/", []),
    ("/sitreps/latest", {"sitrep":None}),
    ("/tracking/snapshots?start=2026-10-28T00:00:00Z&end=2026-10-29T00:00:00Z", []),
])
def test_empty_database_http_contract(empty_api, path, expected):
    response = empty_api.get(path)
    assert response.status_code == 200, response.text
    assert response.json() == expected


@pytest.mark.parametrize("path", ["/events/123", "/events/123/imagery", "/sitreps/123", "/sitreps/123/events"])
def test_missing_records_are_404_not_500(empty_api, path):
    assert empty_api.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/events?limit=501", "/events/anomalies?limit=201",
    "/events?min_reliability=6", "/media/intel?limit=61", "/sitreps/?limit=51",
    "/events?after=not-a-date", "/market/history?days=91"])
def test_declared_query_limits_reject_before_io(empty_api, path):
    assert empty_api.get(path).status_code == 422


def test_empty_cost_configuration_does_not_claim_measured_total(empty_api):
    response = empty_api.get("/costs/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["measurement_status"] == "unconfigured"
    assert data["total_spend_usd"] is None
    assert data["pricing_verified"] is False


def test_auth_session_routes_are_not_registered_for_public_release(empty_api):
    paths = app.openapi()["paths"]
    assert not any(path.startswith("/auth/telegram") for path in paths)

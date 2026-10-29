"""Admin authentication does not imply arbitrary data/model activity is enabled."""
import copy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.routes import events
from app.services import telegram


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "fixture-admin")
    monkeypatch.setattr(settings, "live_ingestion_enabled", False)
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    return TestClient(app)


HEADERS = {"X-Admin-Key": "fixture-admin"}


def test_destructive_dedup_does_not_enter_database(client, monkeypatch):
    db = Mock(side_effect=AssertionError("database access must not occur"))
    monkeypatch.setattr(events, "make_session", db)
    response = client.delete("/events/admin/dedup", headers=HEADERS)
    assert response.status_code == 409
    assert "match-candidates" in response.text
    db.assert_not_called()


def test_unqualified_import_never_fetches_or_writes(client, monkeypatch):
    network = Mock(side_effect=AssertionError("external request must not occur"))
    db = Mock(side_effect=AssertionError("database access must not occur"))
    monkeypatch.setattr(events.urllib.request, "urlopen", network)
    monkeypatch.setattr(events, "make_session", db)
    response = client.post("/events/admin/import-osint-dataset", headers=HEADERS)
    assert response.status_code == 501
    assert "No data was fetched or imported" in response.text
    network.assert_not_called()
    db.assert_not_called()


@pytest.mark.parametrize("path", ["fix-null-coords", "reclassify-locations", "backfill"])
def test_correct_admin_key_cannot_override_collection_disabled(client, monkeypatch, path):
    start = Mock(side_effect=AssertionError("must not schedule"))
    monkeypatch.setattr(events, "_start_admin_review", start)
    response = client.post("/events/admin/" + path, headers=HEADERS)
    assert response.status_code == 503
    start.assert_not_called()


def test_reclassification_requires_provider_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "live_ingestion_enabled", True)
    response = client.post("/events/admin/reclassify-locations", headers=HEADERS)
    assert response.status_code == 503
    assert "provider" in response.text


def test_backfill_requires_live_listener(client, monkeypatch):
    monkeypatch.setattr(settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "fixture-only")
    monkeypatch.setattr(telegram, "_shared_client", None)
    response = client.post("/events/admin/backfill", headers=HEADERS)
    assert response.status_code == 503
    assert "listener" in response.text


@pytest.mark.asyncio
async def test_location_review_proposes_without_mutating_existing_evidence(monkeypatch):
    monkeypatch.setattr(settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(settings, "demo_mode", False)
    event = SimpleNamespace(id=77, location_name="Natanz", raw_text="Original source statement",
                            lat=None, lon=None, severity=3, summary="Original extracted summary")
    original = copy.deepcopy(vars(event))
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [event]))
    session = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock())
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(events, "make_session", lambda: context)
    monkeypatch.setattr(events, "geocode", AsyncMock(return_value=(33.72, 51.72)))
    await events._build_location_candidates(reclassify=False)
    assert vars(event) == original
    session.commit.assert_not_awaited()
    state = await events.location_candidates()
    assert state["mutates_events"] is False
    assert state["candidates"][0]["status"] == "needs_review"
    assert state["candidates"][0]["geolocation_precision"] == "unknown"


@pytest.mark.asyncio
async def test_failed_model_cannot_generate_location_proposal(monkeypatch):
    monkeypatch.setattr(settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "anthropic_api_key", "fixture-only")
    event = SimpleNamespace(id=77, location_name="Unknown", raw_text="Source statement")
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [event]))
    session = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock())
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(events, "make_session", lambda: context)
    monkeypatch.setattr(events, "classify_message", AsyncMock(return_value={"location_name": "Natanz"}))
    geocode = AsyncMock()
    monkeypatch.setattr(events, "geocode", geocode)
    await events._build_location_candidates(reclassify=True)
    state = await events.location_candidates()
    assert state["status"] == "incomplete"
    assert state["candidates"] == []
    geocode.assert_not_awaited()
    session.commit.assert_not_awaited()

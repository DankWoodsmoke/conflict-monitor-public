"""Public hosting denies unapproved retained data, operators and provider work."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from app import main
from app.config import Settings, settings
from app.public_access import public_http_denial
from app.routes import market, ws
from app.security import require_admin_key


@pytest.fixture(autouse=True)
def public_mode(monkeypatch):
    monkeypatch.setattr(settings, "public_read_only", True)
    monkeypatch.setattr(settings, "public_reports_enabled", False)
    monkeypatch.setattr(settings, "public_tracking_enabled", False)
    monkeypatch.setattr(settings, "demo_mode", False)


def test_public_policy_is_explicit_opt_in_without_changing_private_defaults():
    configured = Settings(_env_file=None)
    assert not configured.public_read_only
    assert not configured.public_reports_enabled
    assert not configured.public_tracking_enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("path,expected", [
    ("/events", 503), ("/events/time-range", 503), ("/events/1", 503),
    ("/events/batch", 503), ("/events/anomalies", 503),
    ("/events/delivery/baseline", 503), ("/events/delivery/changes", 503),
    ("/events/1/location-candidates", 503), ("/tracking/aircraft", 503),
    ("/tracking/aircraft/abc123/track", 503), ("/tracking/vessels", 503),
    ("/tracking/snapshots", 503), ("/satellite/hotspots", 503),
    ("/market", 403), ("/market/history", 403), ("/costs/summary", 403),
    ("/events/admin/ingestion", 403), ("/events/match-candidates", 403),
    ("/events/1/imagery", 403), ("/channels", 403), ("/sitreps/", 403),
    ("/sitreps/latest", 403), ("/sitreps/1/events", 403),
    ("/media", 403), ("/briefing/status", 403), ("/briefing/video/latest", 403),
    ("/report-analysis/status", 403), ("/history", 403),
    ("/docs", 403), ("/openapi.json", 403), ("/unknown-future-endpoint", 403),
])
async def test_public_http_gate_runs_before_handlers_and_does_not_admit_admin_key(monkeypatch, path, expected):
    monkeypatch.setattr(settings, "admin_api_key", "fixture-key")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://fixture") as client:
        response = await client.get(path, headers={"X-Admin-Key": "fixture-key"})
    assert response.status_code == expected
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("POST", "/satellite/poll"), ("POST", "/events/admin/backfill"),
                                         ("POST", "/briefing/analysis"), ("DELETE", "/channels/1"),
                                         ("PUT", "/config"), ("PATCH", "/events/1")])
async def test_every_write_method_is_denied_even_with_valid_operator_key(monkeypatch, method, path):
    monkeypatch.setattr(settings, "admin_api_key", "fixture-key")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://fixture") as client:
        response = await client.request(method, path, headers={"X-Admin-Key": "fixture-key"})
    assert response.status_code == 403
    with pytest.raises(HTTPException) as error:
        await require_admin_key("fixture-key")
    assert error.value.status_code == 403


@pytest.mark.parametrize("reports,tracking", [(False, False), (True, False), (False, True), (True, True)])
def test_surface_grants_do_not_unlock_mixed_or_derived_data(monkeypatch, reports, tracking):
    monkeypatch.setattr(settings, "public_reports_enabled", reports)
    monkeypatch.setattr(settings, "public_tracking_enabled", tracking)
    assert public_http_denial("GET", "/events")[0] == 503
    assert public_http_denial("GET", "/tracking/vessels")[0] == 503
    for path in ["/tracking/snapshots", "/satellite/hotspots"]:
        assert public_http_denial("GET", path)[0] == 503
    for path in ["/sitreps", "/briefing/video/latest", "/market", "/costs/summary", "/events/1/imagery"]:
        assert public_http_denial("GET", path)[0] == 403
    assert public_http_denial("POST", "/events")[0] == 403


@pytest.mark.asyncio
async def test_public_bootstrap_and_status_do_not_expose_private_capabilities(monkeypatch):
    for key in ["enable_local_ai", "enable_video_generation", "enable_sitrep_generation", "live_ingestion_enabled", "demo_mode"]:
        monkeypatch.setattr(settings, key, True)
    monkeypatch.setattr(settings, "sentinel_hub_instance_id", "private-instance")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://fixture") as client:
        config = (await client.get("/config")).json()
        status = (await client.get("/status")).json()
    assert config["public_read_only"] is True
    for key in ["public_reports_enabled", "public_tracking_enabled", "public_media_enabled", "generation_enabled",
                "video_generation_enabled", "local_ai_enabled", "live_ingestion_enabled", "demo_mode"]:
        assert config[key] is False
    assert config["sentinel_hub_instance_id"] == ""
    assert status["mode"] == "public_read_only"
    assert not {"telegram", "workers", "classification", "news_feeds", "event_delivery"}.intersection(status)
    assert "private-instance" not in str(config) + str(status)


@pytest.mark.asyncio
async def test_ws_rejects_before_accept_or_broadcaster_subscription(monkeypatch):
    connect = AsyncMock()
    monkeypatch.setattr(ws.broadcaster, "connect", connect)
    socket = SimpleNamespace(close=AsyncMock(), accept=AsyncMock())
    await ws.websocket_events(socket)
    socket.close.assert_awaited_once_with(code=1008)
    socket.accept.assert_not_awaited()
    connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_yahoo_provider_and_cached_market_payloads_are_disabled_in_public_mode(monkeypatch):
    monkeypatch.setattr(settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(market, "_cache", [{"price": 123, "private": True}])
    provider = Mock(side_effect=AssertionError("Public mode reached Yahoo provider"))
    quotes = await market.get_market_data()
    history = await market.get_market_history(30)
    assert quotes["data"] == [] and quotes["status"] == "disabled"
    assert history["history"] == {} and history["status"] == "disabled"
    with pytest.raises(RuntimeError, match="disabled in public"):
        await market._run_provider(provider)
    provider.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("reports", [False, True])
async def test_public_lifespan_does_not_start_inherited_collectors_or_generators(monkeypatch, reports):
    from app.services import broadcaster, classifier
    started = []
    def start(name, coroutine):
        started.append(name)
        coroutine.close()
    for key in ["live_ingestion_enabled", "demo_mode", "enable_sitrep_generation", "x_ingestion_enabled"]:
        monkeypatch.setattr(settings, key, True)
    monkeypatch.setattr(settings, "public_reports_enabled", reports)
    monkeypatch.setattr(main, "runtime", SimpleNamespace(start=start, stop=AsyncMock()))
    monkeypatch.setattr(main, "engine", SimpleNamespace(dispose=AsyncMock()))
    monkeypatch.setattr(market, "start_market", Mock())
    monkeypatch.setattr(market, "stop_market", AsyncMock())
    monkeypatch.setattr(classifier, "stop_classifier", AsyncMock())
    monkeypatch.setattr(broadcaster.broadcaster, "start", Mock())
    monkeypatch.setattr(broadcaster.broadcaster, "stop", AsyncMock())
    async with main.lifespan(main.app):
        pass
    assert started == []

"""Readiness is a database/task assertion; lifecycle owns its started resources."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app import main
from app.routes import market
from app.services import broadcaster as broadcast_module, classifier
from app.services.runtime import Runtime


class SchemaSession:
    def __init__(self, *, missing=False):
        self.statements = []
        self.missing = missing
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def execute(self, query):
        self.statements.append(str(query))
        if self.missing:
            raise RuntimeError("private database URL and password must never be reflected")


@pytest.mark.asyncio
@pytest.mark.parametrize("missing,failures,code,status", [
    (False, {}, 200, "healthy"), (False, {"rss": "ValueError"}, 503, "degraded"),
    (False, {"manual_unknown": "RuntimeError"}, 503, "degraded"),
    (True, {}, 503, "unavailable")])
async def test_health_checks_every_required_table_and_does_not_reflect_provider_or_database_errors(
    monkeypatch, missing, failures, code, status
):
    session = SchemaSession(missing=missing)
    monkeypatch.setattr(main, "async_session", lambda: session)
    monkeypatch.setattr(main, "runtime", SimpleNamespace(failures=failures))
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://fixture") as client:
        response = await client.get("/health")
    assert response.status_code == code
    assert response.json()["status"] == status
    assert "private" not in response.text and "password" not in response.text
    if not missing:
        assert {query.split()[3] for query in session.statements} == {
            "events", "source_reports", "sitreps", "intel_media", "usage_log", "cost_config",
            "tracking_snapshots", "channel_checkpoints"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["cache-control"] == "no-store"


@pytest.fixture
def owned_lifecycle(monkeypatch):
    started = []
    def start(name, coroutine):
        started.append(name)
        coroutine.close()  # fake scheduler never starts provider work
    runtime = SimpleNamespace(start=start, stop=AsyncMock(), failures={})
    resources = SimpleNamespace(runtime=runtime, started=started, market_start=Mock(),
                                market_stop=AsyncMock(), broker_start=Mock(), broker_stop=AsyncMock(),
                                classifier_stop=AsyncMock(), engine_dispose=AsyncMock())
    monkeypatch.setattr(main, "runtime", runtime)
    monkeypatch.setattr(market, "start_market", resources.market_start)
    monkeypatch.setattr(market, "stop_market", resources.market_stop)
    monkeypatch.setattr(broadcast_module.broadcaster, "start", resources.broker_start)
    monkeypatch.setattr(broadcast_module.broadcaster, "stop", resources.broker_stop)
    monkeypatch.setattr(classifier, "stop_classifier", resources.classifier_stop)
    monkeypatch.setattr(main, "engine", SimpleNamespace(dispose=resources.engine_dispose))
    monkeypatch.setattr(main.settings, "demo_mode", False)
    monkeypatch.setattr(main.settings, "live_ingestion_enabled", False)
    return resources


@pytest.mark.asyncio
@pytest.mark.parametrize("body_fails", [False, True])
async def test_collection_disabled_lifespan_starts_no_collectors_and_always_closes_resources(
    owned_lifecycle, body_fails
):
    resources = owned_lifecycle
    if body_fails:
        with pytest.raises(RuntimeError, match="fixture request failure"):
            async with main.lifespan(main.app):
                raise RuntimeError("fixture request failure")
    else:
        async with main.lifespan(main.app):
            pass
    assert resources.started == []
    resources.market_start.assert_called_once()
    resources.broker_start.assert_called_once()
    for cleanup in (resources.runtime.stop, resources.market_stop, resources.classifier_stop,
                    resources.broker_stop, resources.engine_dispose):
        cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_startup_failure_releases_already_started_resources(owned_lifecycle, monkeypatch):
    """A schema/seed startup error must not strand a market executor or broker."""
    from app.services import demo
    resources = owned_lifecycle
    monkeypatch.setattr(main.settings, "demo_mode", True)
    monkeypatch.setattr(demo, "seed_demo_history", AsyncMock(side_effect=RuntimeError("fixture seed failure")))
    with pytest.raises(RuntimeError, match="fixture seed failure"):
        async with main.lifespan(main.app):
            pytest.fail("A failed startup yielded a running app")
    assert resources.started == []
    for cleanup in (resources.runtime.stop, resources.market_stop, resources.classifier_stop,
                    resources.broker_stop, resources.engine_dispose):
        cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_one_cleanup_failure_does_not_orphan_remaining_resources(owned_lifecycle, caplog):
    resources = owned_lifecycle
    resources.market_stop.side_effect = ValueError("private key-bearing shutdown diagnostic")
    async with main.lifespan(main.app):
        pass
    for cleanup in (resources.runtime.stop, resources.market_stop, resources.classifier_stop,
                    resources.broker_stop, resources.engine_dispose):
        cleanup.assert_awaited_once()
    assert "private key-bearing" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("api_key,x_opt_in,expect_x", [
    ("", False, False), ("fixture-provider", False, False),
    ("", True, False), ("fixture-provider", True, True)])
async def test_live_free_worker_selection_never_spends_merely_because_an_old_key_exists(
    owned_lifecycle, monkeypatch, api_key, x_opt_in, expect_x
):
    resources = owned_lifecycle
    for name, value in {"live_ingestion_enabled": True, "telegram_api_id": 0, "telegram_api_hash": "",
        "telegram_session": "", "telegram_channels": "", "aisstream_api_key": "", "firms_map_key": "",
        "enable_sitrep_generation": False, "anthropic_api_key": api_key, "x_ingestion_enabled": x_opt_in}.items():
        monkeypatch.setattr(main.settings, name, value)
    async with main.lifespan(main.app):
        pass
    expected = {"aircraft", "satellites", "rss", "source_digest", "snapshots", "match_review"}
    if expect_x:
        expected.add("x")
    assert set(resources.started) == expected


@pytest.mark.asyncio
async def test_configured_optional_collectors_and_model_generation_have_separate_gates(owned_lifecycle, monkeypatch):
    for name, value in {"live_ingestion_enabled": True, "telegram_api_id": 1, "telegram_api_hash": "fixture",
        "telegram_session": "fixture", "telegram_channels": "publicfixture", "aisstream_api_key": "fixture",
        "firms_map_key": "fixture", "enable_sitrep_generation": True, "anthropic_api_key": "fixture-provider",
        "x_ingestion_enabled": False}.items():
        monkeypatch.setattr(main.settings, name, value)
    async with main.lifespan(main.app):
        pass
    assert set(owned_lifecycle.started) == {"telegram", "aircraft", "satellites", "maritime", "rss", "source_digest",
        "snapshots", "match_review", "thermal_observations", "sitreps"}


@pytest.mark.asyncio
@pytest.mark.parametrize("optional", ["local_analysis", "local_video", "manual_firms", "manual_sitrep", "sitrep_video", "location_review", "telegram_backfill"])
async def test_optional_job_failure_remains_visible_without_taking_readiness_down(monkeypatch, optional):
    runtime = Runtime()
    async def rejected():
        raise ValueError("private rejected model result")
    task = runtime.start(optional, rejected())
    import asyncio
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    monkeypatch.setattr(main, "runtime", runtime)
    monkeypatch.setattr(main, "async_session", lambda: SchemaSession())
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://fixture") as client:
            health = await client.get("/health")
            status = await client.get("/status")
        assert health.status_code == 200 and health.json()["status"] == "healthy"
        assert health.json()["optional_job_failures"] == {optional: "ValueError"}
        worker = status.json()["workers"][optional]
        assert worker["state"] == "failed" and worker["error_type"] == "ValueError"
        assert "private rejected" not in health.text + status.text
        runtime.failures["rss"] = "RuntimeError"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://fixture") as client:
            degraded = await client.get("/health")
        assert degraded.status_code == 503 and degraded.json()["status"] == "degraded"
        assert degraded.json()["optional_job_failures"] == {optional: "ValueError"}
    finally:
        await runtime.stop()

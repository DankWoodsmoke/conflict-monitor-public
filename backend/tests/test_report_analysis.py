"""No real database, model or network calls: selected-source proposal invariants."""

import asyncio
import copy
import hashlib
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlunsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import report_analysis as route
from app.services import local_briefing as local
from app.services import report_analysis as service


def event(**changes):
    value = dict(id=17, source="rss_test", channel_name="Publisher",
                 timestamp=local.clock() - timedelta(minutes=2),
                 raw_text="Officials denied an airstrike in Beirut.",
                 summary="Inherited generated summary must not become input",
                 source_url="https://example.org/report", reports=[])
    value.update(changes)
    return SimpleNamespace(**value)


def model_result(frozen):
    raw = json.dumps({"reports": [{"id": 17, "relevance": "relevant", "stance": "denied",
        "place_mentions": ["Beirut"], "actor_mentions": ["Officials"], "quantity_mentions": []}]})
    return local.validate_extraction(raw, frozen["snapshot"]), {"model": "qwen3.5:4b", "model_digest": "a"*64}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "_jobs", {})
    monkeypatch.setattr(service.runtime, "tasks", {})
    monkeypatch.setattr(service.runtime, "failures", {})
    monkeypatch.setattr(local, "_lock", asyncio.Lock())
    monkeypatch.setattr(local, "_state", {"state": "idle"})
    monkeypatch.setattr(service.settings, "enable_local_ai", True)
    monkeypatch.setattr(service.settings, "demo_mode", False)
    monkeypatch.setattr(service.settings, "briefing_artifact_dir", str(tmp_path))


def test_freeze_raw_text_not_inherited_summary_and_model_excerpt_bound():
    raw = "🛰️ Beirut " + "x" * 3000
    frozen = service.freeze_source(event(raw_text=raw))
    assert frozen["source"]["text"] == raw
    assert frozen["snapshot"][0]["text"] == raw[:2500]
    assert frozen["snapshot"][0]["headline"] == raw[:500]
    assert frozen["snapshot"][0]["text_truncated"] is True
    assert frozen["source"]["original_text_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


@pytest.mark.parametrize("changes", [
    {"raw_text": ""}, {"raw_text": None}, {"raw_text": "x" * 12001},
    {"source": "demo"}, {"timestamp": local.clock() - timedelta(days=3)},
    {"timestamp": local.clock() + timedelta(days=1)}, {"source_url": "javascript:alert(1)"},
    # Construct a deliberately invalid credential-bearing test URL; no real secret is present.
    {"source_url": urlunsplit(("https", "fixture-user:fixture-password@example.invalid", "", "", ""))}, {"reports": ["invalid"]}, {"reports": {}},
])
def test_ineligible_source_rejected(changes):
    with pytest.raises(service.SourceUnavailable):
        service.freeze_source(event(**changes))


@pytest.mark.parametrize("changes", [
    {"source": "telegram"}, {"source_url": "https://T.ME./example/1"},
    {"reports": [{"source": "telegram", "source_url": ""}]},
    {"reports": [{"source": "rss_test", "collector_source": "telegram"}]},
    {"reports": [{"source": "rss_test", "source_platform": "telegram", "source_url": "https://mirror.example"}]},
])
def test_parent_and_every_retained_child_permission_preserved(changes):
    with pytest.raises(local.SourcePermissionRequired):
        service.freeze_source(event(**changes))


@pytest.mark.asyncio
async def test_expected_source_hash_prevents_inference(monkeypatch):
    frozen = service.freeze_source(event())
    monkeypatch.setattr(service, "load_source", AsyncMock(return_value=frozen))
    infer = AsyncMock()
    monkeypatch.setattr(local, "request_extraction", infer)
    with pytest.raises(service.SourceChanged):
        await service.enqueue(17, "f"*64)
    infer.assert_not_awaited()
    assert not service._jobs and not service.runtime.tasks


@pytest.mark.asyncio
async def test_selected_result_bound_and_does_not_overwrite_batch_or_sources(monkeypatch, tmp_path):
    row = event()
    original = copy.deepcopy(row.__dict__)
    frozen = service.freeze_source(row)
    monkeypatch.setattr(service, "load_source", AsyncMock(return_value=frozen))
    infer = AsyncMock(return_value=model_result(frozen))
    monkeypatch.setattr(local, "request_extraction", infer)
    artifact = tmp_path / "analysis.json"
    artifact.write_text('preserved batch artifact')
    queued = await service.enqueue(17, frozen["source"]["original_text_sha256"])
    await service.runtime.tasks["local_analysis"]
    result = await service.get_job(queued["job_id"])
    assert result["status"] == "available" and result["event_id"] == 17
    proposal = result["result"]
    assert proposal["source"]["text"] == row.raw_text
    assert proposal["report"]["stance"] == "denied"
    assert proposal["place_review"]["source_sha256"] == queued["source_sha256"]
    assert proposal["coordinates"] is proposal["severity"] is None
    assert not proposal["critical_alert_eligible"] and not proposal["mutates_events"]
    assert all(not item["automatically_plottable"] for item in proposal["place_review"]["mentions"])
    assert artifact.read_text() == 'preserved batch artifact' and row.__dict__ == original
    assert infer.await_count == 1
    # Caller mutations cannot contaminate a subsequent result.
    proposal["source"]["text"] = "forged"
    assert (await service.get_job(queued["job_id"]))["result"]["source"]["text"] == row.raw_text
    receipt = json.loads((tmp_path / "local-calls.jsonl").read_text())
    assert receipt["paid_api"] is False and receipt["job_id"] == queued["job_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["before", "after", "read"])
async def test_changed_source_citation_or_provenance_never_returns_stale_result(monkeypatch, stage):
    frozen = service.freeze_source(event())
    changed = service.freeze_source(event(source_url="https://example.org/corrected"))
    sources = [frozen, changed] if stage == "before" else [frozen, frozen, changed] if stage == "after" else [frozen, frozen, frozen, changed]
    monkeypatch.setattr(service, "load_source", AsyncMock(side_effect=sources))
    infer = AsyncMock(return_value=model_result(frozen))
    monkeypatch.setattr(local, "request_extraction", infer)
    queued = await service.enqueue(17, frozen["source"]["original_text_sha256"])
    await service.runtime.tasks["local_analysis"]
    result = await service.get_job(queued["job_id"])
    assert result["status"] == "source_changed" and "result" not in result
    assert infer.await_count == (0 if stage == "before" else 1)


@pytest.mark.asyncio
async def test_new_restricted_provenance_withholds_completed_result(monkeypatch):
    frozen = service.freeze_source(event())
    monkeypatch.setattr(service, "load_source", AsyncMock(side_effect=[frozen, frozen, frozen, local.SourcePermissionRequired()]))
    monkeypatch.setattr(local, "request_extraction", AsyncMock(return_value=model_result(frozen)))
    queued = await service.enqueue(17, frozen["source"]["original_text_sha256"])
    await service.runtime.tasks["local_analysis"]
    result = await service.get_job(queued["job_id"])
    assert result["status"] == "source_permission_required" and "result" not in result


@pytest.mark.asyncio
async def test_busy_and_cancel_release_single_model_lock(monkeypatch):
    frozen = service.freeze_source(event())
    monkeypatch.setattr(service, "load_source", AsyncMock(return_value=frozen))
    started = asyncio.Event()
    async def infer(snapshot):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(local, "request_extraction", infer)
    queued = await service.enqueue(17, frozen["source"]["original_text_sha256"])
    await started.wait()
    with pytest.raises(service.AnalysisBusy):
        await service.enqueue(17, frozen["source"]["original_text_sha256"])
    task = service.runtime.tasks["local_analysis"]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not local._lock.locked()
    assert (await service.get_job(queued["job_id"]))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancellation_before_coroutine_start_does_not_leak_queued_slot(monkeypatch):
    frozen = service.freeze_source(event())
    monkeypatch.setattr(service, "load_source", AsyncMock(return_value=frozen))
    queued = await service.enqueue(17, frozen["source"]["original_text_sha256"])
    task = service.runtime.tasks["local_analysis"]
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert (await service.get_job(queued["job_id"]))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_retention_and_restart_are_explicitly_unavailable(monkeypatch):
    frozen = service.freeze_source(event())
    monkeypatch.setattr(service, "load_source", AsyncMock(return_value=frozen))
    monkeypatch.setattr(local, "request_extraction", AsyncMock(return_value=model_result(frozen)))
    for _ in range(service.MAX_JOBS + 2):
        queued = await service.enqueue(17, frozen["source"]["original_text_sha256"])
        await service.runtime.tasks["local_analysis"]
    assert len(service._jobs) == service.MAX_JOBS
    monkeypatch.setattr(local, "clock", lambda: frozen_time + timedelta(hours=2))
    frozen_time = service._jobs[queued["job_id"]]["_created"]
    assert await service.get_job(queued["job_id"]) is None
    assert await service.get_job("unknown") is None


def test_admin_routes_validate_requests_and_do_not_run_on_get(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    monkeypatch.setattr(service.settings, "admin_api_key", "fixture-admin")
    enqueue = AsyncMock(return_value={"status": "queued"})
    read = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "enqueue", enqueue)
    monkeypatch.setattr(service, "get_job", read)
    with TestClient(app) as client:
        assert client.post("/report-analysis/17", json={"expected_source_sha256": "a"*64}).status_code == 403
        assert client.get("/report-analysis/jobs/11111111-1111-4111-8111-111111111111").status_code == 403
        headers = {"X-Admin-Key": "fixture-admin"}
        assert client.post("/report-analysis/17", headers=headers, json={"expected_source_sha256": 3}).status_code == 422
        assert client.post("/report-analysis/17", headers=headers, json={"expected_source_sha256": "a"*64, "severity": 9}).status_code == 422
        assert client.get("/report-analysis/jobs/11111111-1111-4111-8111-111111111111", headers=headers).status_code == 404
        enqueue.assert_not_awaited()
        assert client.post("/report-analysis/17", headers=headers, json={"expected_source_sha256": "a"*64}).status_code == 202


@pytest.mark.asyncio
async def test_source_read_timeout_awaits_query_cancellation_and_session_cleanup(monkeypatch):
    order = []
    class Session:
        async def __aenter__(self):
            order.append("connection")
            return self
        async def __aexit__(self, *exc):
            await asyncio.sleep(0.01)
            order.append("released")
        async def execute(self, query):
            order.append("query")
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.01)
                order.append("query_cancelled")
    monkeypatch.setattr(service, "async_session", Session)
    monkeypatch.setattr(service, "SOURCE_READ_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(TimeoutError):
        await service.load_source(17)
    assert order == ["connection", "query", "query_cancelled", "released"]
    await asyncio.sleep(0.02)
    assert order == ["connection", "query", "query_cancelled", "released"]


@pytest.mark.asyncio
async def test_source_read_deadline_also_bounds_connection_acquisition(monkeypatch):
    cancelled = asyncio.Event()
    class Session:
        async def __aenter__(self):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        async def __aexit__(self, *exc):
            raise AssertionError("Context was never acquired")
    monkeypatch.setattr(service, "async_session", Session)
    monkeypatch.setattr(service, "SOURCE_READ_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(TimeoutError):
        await service.load_source(17)
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_database_timeout_marks_job_failed_not_source_changed(monkeypatch):
    frozen = service.freeze_source(event())
    monkeypatch.setattr(service, "load_source", AsyncMock(side_effect=[frozen, TimeoutError()]))
    infer = AsyncMock()
    monkeypatch.setattr(local, "request_extraction", infer)
    queued = await service.enqueue(17, frozen["source"]["original_text_sha256"])
    await service.runtime.tasks["local_analysis"]
    result = await service.get_job(queued["job_id"])
    assert result["status"] == "failed" and result["error_type"] == "TimeoutError"
    infer.assert_not_awaited()

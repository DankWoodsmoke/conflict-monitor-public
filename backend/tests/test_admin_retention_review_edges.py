import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.routes import events as subject


@pytest.mark.asyncio
@pytest.mark.parametrize("cutoff", [datetime(2020, 1, 1), datetime.now(timezone.utc)+timedelta(days=1)])
async def test_retention_rejects_ambiguous_or_future_cutoffs_before_database_access(cutoff):
    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    with pytest.raises(HTTPException) as failure:
        await subject.purge_old_events(cutoff, session)
    assert failure.value.status_code == 422
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_retention_deletes_only_event_rows_below_strict_cutoff_and_waits_for_commit():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(rowcount=3)), commit=AsyncMock())
    cutoff = datetime.now(timezone.utc)-timedelta(days=1)
    result = await subject.purge_old_events(cutoff, session)
    query = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert str(query).startswith("DELETE FROM events WHERE events.timestamp <")
    assert "source_reports" not in str(query) and cutoff in query.params.values()
    assert result["deleted"] == 3 and "receipts are retained" in result["scope"]
    session.commit.assert_awaited_once()
    session.commit.side_effect = RuntimeError("fixture commit failure")
    with pytest.raises(RuntimeError, match="commit failure"):
        await subject.purge_old_events(cutoff, session)


@pytest.fixture
def review(monkeypatch):
    monkeypatch.setattr(subject.settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(subject.settings, "demo_mode", False)
    monkeypatch.setattr(subject, "_location_review", {"status": "not_started"})


def setup_review(monkeypatch, rows=None, error=None):
    execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows or [])), side_effect=error)
    session = SimpleNamespace(execute=execute, commit=AsyncMock())
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(subject, "make_session", lambda: context)
    return session


@pytest.mark.asyncio
async def test_location_review_is_bounded_and_rejects_unknown_boolean_and_missing_candidates_without_mutation(review, monkeypatch):
    rows = [SimpleNamespace(id=i, location_name=name, raw_text="Original source text")
            for i, name in enumerate(["Unknown", "", "AlphaFixture", "BetaFixture", "GammaFixture"], start=1)]
    original = copy.deepcopy([vars(row) for row in rows])
    session = setup_review(monkeypatch, rows)
    geocode = AsyncMock(side_effect=[(True, 45), None, (31, 45)])
    monkeypatch.setattr(subject, "geocode", geocode)
    await subject._build_location_candidates(reclassify=False)
    state = await subject.location_candidates()
    assert state["status"] == "complete" and state["examined"] == 5
    assert [row["event_id"] for row in state["candidates"]] == [5]
    assert state["candidates"][0]["geolocation_precision"] == "unknown"
    assert state["candidates"][0]["status"] == "needs_review"
    assert [vars(row) for row in rows] == original
    session.commit.assert_not_awaited()
    query = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert 100 in query.params.values() and "ORDER BY events.id" in str(query)


@pytest.mark.asyncio
async def test_location_review_preserves_per_source_errors_without_private_exception_text(review, monkeypatch):
    session = setup_review(monkeypatch, [SimpleNamespace(id=7, location_name="AlphaFixture", raw_text="original")])
    monkeypatch.setattr(subject, "geocode", AsyncMock(side_effect=ValueError("private URL key")))
    await subject._build_location_candidates(reclassify=False)
    state = await subject.location_candidates()
    assert state["status"] == "incomplete" and state["errors"] == [{"event_id": 7, "reason": "ValueError"}]
    assert state["candidates"] == [] and "private URL" not in str(state)
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_location_review_database_failure_is_visible_and_never_claims_completion(review, monkeypatch):
    session = setup_review(monkeypatch, error=RuntimeError("private database URL"))
    with pytest.raises(RuntimeError):
        await subject._build_location_candidates(reclassify=False)
    state = await subject.location_candidates()
    assert state["status"] == "failed" and state["errors"] == [{"reason": "RuntimeError"}]
    assert "private database" not in str(state)
    session.commit.assert_not_awaited()


def test_running_review_conflict_does_not_even_construct_a_second_coroutine(monkeypatch):
    import app.services.runtime as runtime_module
    runtime = SimpleNamespace(tasks={"location_review": SimpleNamespace(done=lambda: False)}, start=Mock())
    monkeypatch.setattr(runtime_module, "runtime", runtime)
    factory = Mock()
    with pytest.raises(HTTPException) as failure:
        subject._start_admin_review("location_review", factory)
    assert failure.value.status_code == 409
    factory.assert_not_called()
    runtime.start.assert_not_called()

import asyncio
import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.services import retro_matcher as subject
import app.db as database


NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def event(identity, **changes):
    return SimpleNamespace(**{"id": identity, "timestamp": NOW, "event_type": "military", "lat": 30, "lon": 45,
        "summary": "The source reports an incident outside the hospital in the city this morning", **changes})


def test_review_pairs_obey_time_type_coordinate_and_distance_guards_without_mutating_evidence():
    rows = [event(1), event(2, timestamp=NOW-timedelta(hours=6)),
            event(3, timestamp=NOW-timedelta(hours=7)), event(4, lat=None), event(5, event_type="economic"),
            event(6, lat=35), event(7, summary="Unrelated diplomatic meeting in another region"), event(8, timestamp=None)]
    frozen = copy.deepcopy([vars(row) for row in rows])
    candidates = subject.find_review_candidates(rows)
    assert [row["event_ids"] for row in candidates] == [[1, 2], [2, 3]]
    assert candidates[0]["time_difference_hours"] == 6
    assert candidates[0]["status"] == "needs_review" and candidates[0]["verification"] == "unassessed"
    assert [vars(row) for row in rows] == frozen


def test_review_output_cap_and_tie_order_remain_stable():
    candidates = subject.find_review_candidates([event(i) for i in range(1, 23)])
    assert len(candidates) == 200
    assert candidates[0]["event_ids"] == [1, 2]
    assert all(row["status"] == "needs_review" and row["verification"] == "unassessed" for row in candidates)


@pytest.mark.asyncio
async def test_periodic_scan_is_read_only_and_samples_bounded_recent_rows(monkeypatch):
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda:
        SimpleNamespace(all=lambda: [event(1), event(2)]))), commit=AsyncMock())
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(database, "async_session", lambda: context)
    monkeypatch.setattr(subject, "_last_candidates", [])
    monkeypatch.setattr(subject, "_checked_at", "")
    assert await subject.run_retro_match() == 0
    state = subject.get_retro_candidates()
    assert state["automatic_merges"] == 0 and len(state["candidates"]) == 1
    assert datetime.fromisoformat(state["checked_at"]).tzinfo is not None
    query = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert 400 in query.params.values() and "events.report_count >" in str(query)
    assert "ORDER BY events.timestamp DESC, events.id DESC" in str(query)
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_scan_recovers_query_failure_and_cancellation_stops_it(monkeypatch):
    calls = []
    async def sleep(delay):
        calls.append(delay)
        if len(calls) == 3:
            raise asyncio.CancelledError()
    scan = AsyncMock(side_effect=[RuntimeError("fixture database unavailable"), 0])
    monkeypatch.setattr(subject, "run_retro_match", scan)
    monkeypatch.setattr(subject.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await subject.start_retro_matcher()
    assert scan.await_count == 2 and calls == [300, 7200, 7200]

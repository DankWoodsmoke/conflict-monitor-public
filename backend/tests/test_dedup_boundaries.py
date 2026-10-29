from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.services import dedup
from app.services.evidence import make_report, valid_coordinates


def event(identity=1, **changes):
    values = dict(id=identity, source="telegram", channel_name="publisher", timestamp=datetime.now(timezone.utc),
        source_url="https://example.invalid/report/12", raw_text="Original report text",
        summary="A source reports an incident outside the city hospital during the morning hours",
        event_type="military", severity=3, lat=30, lon=45, reporting_channels="publisher", report_count=1,
        telegram_message_id=12, classification_status="extracted", geolocation_precision="unknown", reports=[])
    values.update(changes)
    return SimpleNamespace(**values)


def session(rows):
    return SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))))


@pytest.mark.asyncio
async def test_same_source_url_replay_matches_only_same_source_and_unchanged_raw_content():
    candidate = event()
    report = make_report(candidate)
    saved = session([candidate])
    assert await dedup.check_duplicate(saved, candidate.summary, "military", None, None, None,
        source_name="publisher", report=report) is candidate
    changed = make_report(event(raw_text="Correction: original report withdrawn"))
    assert await dedup.check_duplicate(saved, candidate.summary, "military", None, None, None,
        source_name="publisher", report=changed) is None
    assert await dedup.check_duplicate(saved, candidate.summary, "military", None, None, None,
        source_name="different-publisher", report=report) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("lat,lon", [(None, None), (True, 45), (30, float("nan")), (91, 45)])
async def test_invalid_positions_cannot_trigger_a_geographic_duplicate_query(lat, lon):
    saved = session([])
    assert await dedup._query_candidates(saved, "military", datetime.now(timezone.utc),
        datetime.now(timezone.utc), lat, lon) == []
    saved.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_spatial_candidate_query_is_meter_based_bounded_and_stably_ordered():
    saved = session([])
    now = datetime.now(timezone.utc)
    assert await dedup._query_candidates(saved, "military", now-timedelta(minutes=15), now+timedelta(minutes=15), 30, 45) == []
    statement = saved.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    query = str(statement)
    assert "ST_DWithin(CAST(events.geometry AS geography" in query
    assert 2000 in statement.params.values() and 40 in statement.params.values()
    assert "ORDER BY events.timestamp DESC, events.id DESC" in query
    assert "events.event_type =" in query and "events.report_count >" in query


@pytest.mark.asyncio
async def test_lexical_tie_uses_stable_oldest_identity_and_polarity_remains_unmerged(monkeypatch):
    original = event()
    first, second = event(9), event(3)
    monkeypatch.setattr(dedup, "_query_candidates", AsyncMock(return_value=[first, second]))
    assert await dedup.check_duplicate(session([]), original.summary, "military", 30, 45, original.timestamp) is second
    rejected = event(summary="No incident occurred at the city hospital and the source denies the morning report")
    monkeypatch.setattr(dedup, "_query_candidates", AsyncMock(return_value=[rejected]))
    assert await dedup.check_duplicate(session([]), original.summary, "military", 30, 45, original.timestamp) is None


@pytest.mark.parametrize("lat,lon,valid", [(True, 45, False), (30, False, False),
    (10**1000, 45, False), (30, 10**1000, False), (0, 0, True), (-90, 180, True),
    (-25, 80, False), (float("inf"), 40, False)])
def test_shared_coordinate_validator_rejects_boolean_and_overflow_without_inventing_positions(lat, lon, valid):
    assert valid_coordinates(lat, lon) is valid

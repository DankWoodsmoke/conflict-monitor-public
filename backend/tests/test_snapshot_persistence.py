"""Replay persistence contracts; no provider or database stand-ins count as live proof."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.services import snapshots as subject


def test_aircraft_replay_filters_airlines_but_keeps_emergencies_and_boundary_positions():
    common = {"icao24": "abc123", "lat": 8, "lon": 28, "callsign": " uae123 ",
              "aircraft_category": "civilian", "altitude": 0, "heading": 0, "velocity": 0}
    rows = [common, {**common, "is_emergency": True},
            {**common, "callsign": " TEST01 ", "lat": 42, "lon": 67},
            {**common, "aircraft_category": "military"},
            {**common, "on_ground": True, "is_emergency": True},
            {**common, "lat": None}, {**common, "lon": 67.0001}]
    result = subject._compact_aircraft(rows)
    assert [row["c"] for row in result] == ["UAE123", "TEST01", "UAE123"]
    assert result[0]["e"] is True
    assert result[0]["a"] == result[0]["h"] == result[0]["v"] == 0
    assert result[1]["la"] == 42 and result[1]["lo"] == 67
    assert rows[0]["callsign"] == " uae123 "  # caller-owned source snapshot is unchanged


def test_vessel_replay_keeps_zero_positions_units_and_rounds_without_mutating_source():
    source = {"mmsi": "123456789", "name": "TEST", "lat": 0, "lon": 1.12345678,
              "speed": 0, "heading": 0, "vessel_category": "civilian", "flag_code": "??"}
    assert subject._compact_vessels([source, {**source, "lon": None}]) == [{
        "m": "123456789", "n": "TEST", "la": 0, "lo": 1.12346,
        "sp": 0, "h": 0, "k": "civilian", "f": "??", "st": ""}]
    assert source["lon"] == 1.12345678


class Session:
    def __init__(self, *, rowcount=0, error=None, values=None):
        self.added = []
        self.statements = []
        self.rowcount = rowcount
        self.error = error
        self.values = iter(values or [])
        self.commit = AsyncMock()
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    def add(self, row):
        self.added.append(row)
    async def execute(self, statement):
        self.statements.append(statement)
        if self.error:
            raise self.error
        return next(self.values, SimpleNamespace(rowcount=self.rowcount))


@pytest.mark.asyncio
async def test_record_snapshot_commits_all_caches_at_one_aware_collection_clock(monkeypatch):
    session = Session()
    monkeypatch.setattr(subject, "async_session", lambda: session)
    monkeypatch.setattr(subject, "get_aircraft", lambda: [{"icao24": "test", "lat": 30, "lon": 45}])
    monkeypatch.setattr(subject, "get_vessels", lambda: [{"mmsi": "123", "lat": 0, "lon": 0}])
    monkeypatch.setattr(subject, "get_jamming_zones", lambda: [{"lat": 31, "lon": 46, "radius_km": 5,
                                                            "aircraft_count": 3, "intensity": "low"}])
    before = datetime.now(timezone.utc)
    await subject._record_snapshot()
    row, = session.added
    assert before <= row.timestamp <= datetime.now(timezone.utc)
    assert row.timestamp.utcoffset() == timedelta(0)
    assert row.aircraft[0]["i"] == "test" and row.vessels[0]["la"] == 0
    assert row.jamming_zones == [{"la": 31, "lo": 46, "r": 5, "c": 3, "i": "low"}]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_snapshot_commit_is_visible_to_supervisor(monkeypatch):
    session = Session()
    session.commit.side_effect = RuntimeError("fixture database write failure")
    monkeypatch.setattr(subject, "async_session", lambda: session)
    for getter in ("get_aircraft", "get_vessels", "get_jamming_zones"):
        monkeypatch.setattr(subject, getter, lambda: [])
    with pytest.raises(RuntimeError, match="database write failure"):
        await subject._record_snapshot()


@pytest.mark.asyncio
@pytest.mark.parametrize("rowcount", [0, 3])
async def test_retention_uses_aware_strict_cutoff_and_commits_only_deleted_rows(monkeypatch, rowcount):
    session = Session(rowcount=rowcount)
    monkeypatch.setattr(subject, "async_session", lambda: session)
    before = datetime.now(timezone.utc) - timedelta(days=subject.RETENTION_DAYS)
    await subject._prune_old_snapshots()
    query = session.statements[0].compile(dialect=postgresql.dialect())
    cutoff, = query.params.values()
    assert before <= cutoff <= datetime.now(timezone.utc) - timedelta(days=subject.RETENTION_DAYS)
    assert "tracking_snapshots.timestamp <" in str(query)
    assert session.commit.await_count == bool(rowcount)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 501])
async def test_replay_rejects_unbounded_payload_request_before_opening_database(monkeypatch, limit):
    monkeypatch.setattr(subject, "async_session", lambda: pytest.fail("Invalid bound opened database"))
    with pytest.raises(ValueError, match="between 1 and 500"):
        await subject.get_snapshots(datetime.now(timezone.utc), datetime.now(timezone.utc), limit)


@pytest.mark.asyncio
async def test_replay_samples_ids_in_sql_before_loading_jsonb(monkeypatch):
    timestamp = datetime(2026, 10, 1, tzinfo=timezone.utc)
    row = SimpleNamespace(timestamp=timestamp, aircraft=[{"i": "test"}], vessels=[], jamming_zones=[])
    session = Session(values=[SimpleNamespace(scalar_one=lambda: 1001),
                              SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [row]))])
    monkeypatch.setattr(subject, "async_session", lambda: session)
    result = await subject.get_snapshots(timestamp, timestamp + timedelta(days=1), 100)
    assert result == [{"ts": timestamp.isoformat(), "aircraft": [{"i": "test"}], "vessels": [], "jamming": []}]
    query = session.statements[1].compile(dialect=postgresql.dialect())
    assert "row_number() OVER (ORDER BY tracking_snapshots.timestamp, tracking_snapshots.id)" in str(query)
    assert "JOIN" in str(query) and "LIMIT" in str(query)
    assert 11 in query.params.values() and 100 in query.params.values()


@pytest.mark.asyncio
async def test_recorder_recovers_write_failure_and_cancellation_escapes(monkeypatch):
    calls = []
    async def sleep(delay):
        calls.append(delay)
        if len(calls) == 3:
            raise asyncio.CancelledError()
    record = AsyncMock(side_effect=[RuntimeError("fixture unavailable"), None])
    prune = AsyncMock()
    monkeypatch.setattr(subject.asyncio, "sleep", sleep)
    monkeypatch.setattr(subject, "_record_snapshot", record)
    monkeypatch.setattr(subject, "_prune_old_snapshots", prune)
    with pytest.raises(asyncio.CancelledError):
        await subject.start_snapshot_recorder()
    assert record.await_count == 2
    prune.assert_awaited_once()
    assert calls == [30, subject.SNAPSHOT_INTERVAL, subject.SNAPSHOT_INTERVAL]

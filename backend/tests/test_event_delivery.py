import asyncio
from datetime import datetime, timezone
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.routes import event_delivery as routes
from app.services import event_delivery as worker


class Results:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def one(self):
        row, = self.rows
        return row

    def all(self):
        return self.rows

    def scalars(self):
        return self


class Session:
    def __init__(self, last=13, floor=2, changes=(), events=()):
        self.calls = []
        self.state = SimpleNamespace(epoch="fixture", last_offset=last, retired_through=floor)
        self.changes = changes
        self.events = events

    async def execute(self, query, params=None):
        sql = str(query)
        self.calls.append((sql, params))
        if "SET TRANSACTION" in sql:
            assert len(self.calls) == 1 and "REPEATABLE READ, READ ONLY" in sql
            return None
        if "FROM public.event_delivery_state" in sql:
            return Results([self.state])
        if "FROM public.event_deliveries" in sql:
            return Results(self.changes)
        assert "FROM events" in sql
        return Results(self.events)


def event(identity):
    stamp = datetime(2026, 11, 1, tzinfo=timezone.utc)
    return SimpleNamespace(id=identity, source="rss_fixture", channel_name="fixture", raw_text="synthetic",
        summary="synthetic", event_type="unclassified", severity=0, lat=None, lon=None, timestamp=stamp, created_at=stamp)


def change(offset, event_id, action="upsert"):
    return SimpleNamespace(publication_offset=offset, event_id=event_id, action=action)


@pytest.fixture
def client_for(monkeypatch):
    monkeypatch.setattr(routes.settings, "demo_mode", False)

    def create(session):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[routes.get_session] = lambda: session
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture")

    return create


@pytest.mark.asyncio
async def test_baseline_uses_same_read_snapshot_for_offset_and_source_view(client_for):
    session = Session(last=9007199254740993, events=[event(7)])
    async with client_for(session) as client:
        response = await client.get("/events/delivery/baseline?limit=1")
    assert response.status_code == 200
    assert response.json()["after"] == "9007199254740993"
    assert response.json()["epoch"] == "fixture-live"
    assert [row["id"] for row in response.json()["events"]] == [7]
    assert "ORDER BY events.timestamp DESC, events.id DESC" in session.calls[-1][0]


@pytest.mark.asyncio
async def test_page_keeps_gaps_and_explicit_deletions_and_uses_lookahead(client_for):
    session = Session(changes=[change(4, 7), change(8, 3), change(9, 2, "delete"), change(11, 1)], events=[event(7)])
    async with client_for(session) as client:
        response = await client.get("/events/delivery/changes?epoch=fixture-live&after=2&limit=3")
    assert response.status_code == 200
    data = response.json()
    assert [(row["offset"], row["event_id"], row["action"]) for row in data["changes"]] == [
        ("4", 7, "upsert"), ("8", 3, "delete"), ("9", 2, "delete")]
    assert data["changes"][0]["event"]["id"] == 7 and all(row["event"] is None for row in data["changes"][1:])
    assert data["next_after"] == "9" and data["has_more"] is True
    assert session.calls[2][1] == {"stream": "live", "offset": 2, "limit": 4}


@pytest.mark.asyncio
@pytest.mark.parametrize(("epoch", "after", "reason"), [
    ("fixture-demo", "2", "epoch_changed"), ("fixture-live", "1", "cursor_expired"),
    ("fixture-live", "14", "cursor_ahead"),
])
async def test_invalid_epoch_or_retention_boundary_reseeds_without_reading_rows(client_for, epoch, after, reason):
    session = Session()
    async with client_for(session) as client:
        response = await client.get("/events/delivery/changes", params={"epoch": epoch, "after": after})
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "delivery_baseline_required", "reason": reason}}
    assert len(session.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("after", ["01", "-1", "+1", "1.5", "1\n", "9223372036854775808"])
async def test_invalid_offsets_are_rejected_without_using_database(client_for, after):
    session = Session()
    async with client_for(session) as client:
        response = await client.get("/events/delivery/changes", params={"epoch": "fixture-live", "after": after})
    assert response.status_code == 422 and not session.calls


@pytest.mark.asyncio
async def test_empty_page_preserves_acknowledgement_and_demo_epoch(client_for, monkeypatch):
    monkeypatch.setattr(routes.settings, "demo_mode", True)
    session = Session()
    async with client_for(session) as client:
        response = await client.get("/events/delivery/changes?epoch=fixture-demo&after=2")
    assert response.json() == {"epoch": "fixture-demo", "changes": [], "next_after": "2", "has_more": False}
    assert session.calls[2][1]["stream"] == "demo"


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_type', [SQLAlchemyError, TimeoutError, ConnectionRefusedError, ConnectionResetError, socket.gaierror])
async def test_worker_recovers_transient_failure_and_yields_between_full_batches(monkeypatch, caplog, failure_type):
    monkeypatch.setattr(worker, "_state", worker.delivery_status())
    monkeypatch.setattr(worker, "publish_once", AsyncMock(side_effect=[failure_type("private password"), -1, 100, 0]))
    intervals, observed = [], []

    async def sleep(seconds):
        intervals.append(seconds)
        observed.append(worker.delivery_status())
        if len(intervals) == 4:
            raise asyncio.CancelledError()

    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await worker.start_event_delivery()
    assert intervals == [2, .5, .05, .5]
    assert [status["status"] for status in observed] == ["retrying", "busy", "ok", "ok"]
    assert observed[0]["error_type"] == failure_type.__name__
    assert observed[2]["last_published_at"] == observed[3]["last_published_at"]
    assert "private password" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid_result', [None, True, -2, 101, '0'])
async def test_worker_does_not_retry_invalid_publication_results(monkeypatch, invalid_result):
    monkeypatch.setattr(worker, 'publish_once', AsyncMock(return_value=invalid_result))
    sleep = AsyncMock()
    monkeypatch.setattr(worker.asyncio, 'sleep', sleep)
    with pytest.raises(RuntimeError, match='Invalid report publication result'):
        await worker.start_event_delivery()
    sleep.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_type', [ValueError, asyncio.CancelledError])
async def test_worker_preserves_programming_failure_and_cancellation(monkeypatch, failure_type):
    monkeypatch.setattr(worker, 'publish_once', AsyncMock(side_effect=failure_type()))
    sleep = AsyncMock()
    monkeypatch.setattr(worker.asyncio, 'sleep', sleep)
    with pytest.raises(failure_type):
        await worker.start_event_delivery()
    sleep.assert_not_awaited()

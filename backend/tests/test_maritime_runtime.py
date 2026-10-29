"""Bounded socket recovery, cache preservation and sanitized provider failures."""
import asyncio
import json
from collections import OrderedDict
from unittest.mock import AsyncMock, Mock

import pytest
import websockets

from app.services import maritime as subject


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(subject.settings, "demo_mode", False)
    monkeypatch.setattr(subject.settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(subject.settings, "aisstream_api_key", "fixture-private-ais-key")
    monkeypatch.setattr(subject, "_cache", {"vessels": OrderedDict(), "last_update": None, "last_attempt": None,
        "last_message": None, "last_prune": 0, "connected": False, "error": None,
        "rejected_messages": 0, "evicted_records": 0, "compression_enabled": None})


def position():
    return json.dumps({"MessageType": "PositionReport", "MetaData": {"MMSI": 413123456, "ShipName": "TEST"},
        "Message": {"PositionReport": {"Valid": True, "UserID": 413123456, "Latitude": 30, "Longitude": 45,
            "Sog": 0, "Cog": 0, "TrueHeading": 511}}})


@pytest.mark.asyncio
async def test_malformed_frame_does_not_destroy_last_good_position_and_provider_rejection_is_not_silenced(state, monkeypatch):
    class Socket:
        def __init__(self):
            self.send = AsyncMock()
            self.recv = AsyncMock(side_effect=[position(), "bad json", json.dumps({"MessageType": "Error",
                "error": "private subscription provider diagnostic"})])
            self.closed = False
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            self.closed = True
    socket = Socket()
    connect = Mock(return_value=socket)
    monkeypatch.setattr(websockets, "connect", connect)
    with pytest.raises(RuntimeError, match="rejected the subscription"):
        await subject._run_websocket()
    assert socket.closed
    request = json.loads(socket.send.await_args.args[0])
    assert request["APIKey"] == "fixture-private-ais-key"
    assert request["FilterMessageTypes"] == ["PositionReport", "ShipStaticData"]
    assert request["BoundingBoxes"] == subject.BOUNDING_BOXES
    assert connect.call_args.kwargs["max_size"] <= 65536 and connect.call_args.kwargs["max_queue"] <= 16
    assert connect.call_args.kwargs["ping_timeout"] <= 20 and connect.call_args.kwargs["close_timeout"] <= 5
    rows = subject.get_vessels()
    assert len(rows) == 1 and rows[0]["lat"] == 30 and rows[0]["speed"] == 0
    assert rows[0]["heading"] == 0 and rows[0]["heading_basis"] == "course_over_ground"
    assert subject._cache["rejected_messages"] == 1


@pytest.mark.asyncio
async def test_reconnect_backoff_is_capped_and_cancellation_leaves_disconnected_state(state, monkeypatch, caplog):
    attempts, delays = [], []
    async def failed_connection():
        attempts.append(True)
        subject._cache["connected"] = True
        raise RuntimeError("private AIS APIKey provider diagnostic")
    async def sleep(delay):
        assert subject._cache["connected"] is False
        delays.append(delay)
        if len(delays) == 7:
            raise asyncio.CancelledError()
    monkeypatch.setattr(subject, "_run_websocket", failed_connection)
    monkeypatch.setattr(subject.random, "uniform", lambda a, b: 0)
    monkeypatch.setattr(subject.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await subject.start_maritime_poller()
    assert len(attempts) == 7 and delays == [10, 20, 40, 80, 160, 300, 300]
    assert subject._cache["connected"] is False and subject._cache["error"] == "RuntimeError"
    assert "private AIS APIKey" not in caplog.text


@pytest.mark.asyncio
async def test_cancellation_during_active_connection_is_not_retried_or_logged_as_provider_failure(state, monkeypatch):
    async def cancelled_connection():
        subject._cache["connected"] = True
        raise asyncio.CancelledError()
    sleeper = AsyncMock(side_effect=AssertionError("Cancelled collector must not retry"))
    monkeypatch.setattr(subject, "_run_websocket", cancelled_connection)
    monkeypatch.setattr(subject.asyncio, "sleep", sleeper)
    with pytest.raises(asyncio.CancelledError):
        await subject.start_maritime_poller()
    assert subject._cache["connected"] is False and subject._cache["error"] is None
    sleeper.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_key_performs_no_socket_allocation(state, monkeypatch):
    monkeypatch.setattr(subject.settings, "aisstream_api_key", "")
    connection = AsyncMock(side_effect=AssertionError("Unconfigured AIS connection"))
    monkeypatch.setattr(subject, "_run_websocket", connection)
    await subject.start_maritime_poller()
    connection.assert_not_awaited()

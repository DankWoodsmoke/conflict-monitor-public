import asyncio
import gzip
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import WebSocketDisconnect

from app.routes import ws as subject
from app.services.tracking_contract import bounded_json


class Socket:
    def __init__(self, origin=None, messages=()):
        self.headers = {"host": "127.0.0.1:5190"}
        if origin is not None:
            self.headers["origin"] = origin
        self.receive_text = AsyncMock(side_effect=[*messages, WebSocketDisconnect()])
        self.close = AsyncMock()


@pytest.fixture
def broker(monkeypatch):
    from types import SimpleNamespace
    broker = SimpleNamespace(connect=AsyncMock(return_value=True), disconnect=AsyncMock())
    monkeypatch.setattr(subject, "broadcaster", broker)
    monkeypatch.setattr(subject.settings, "cors_origins", "http://trusted.fixture:5173")
    return broker


@pytest.mark.asyncio
async def test_foreign_browser_origin_is_closed_before_client_allocation(broker):
    socket = Socket("https://untrusted.fixture")
    await subject.websocket_events(socket)
    socket.close.assert_awaited_once_with(code=1008)
    broker.connect.assert_not_awaited()
    socket.receive_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["http://[", "ftp://127.0.0.1:5190", "//127.0.0.1:5190", "null"])
async def test_malformed_or_nonweb_origin_closes_as_policy_rejection_not_server_error(broker, origin):
    socket = Socket(origin)
    await subject.websocket_events(socket)
    socket.close.assert_awaited_once_with(code=1008)
    broker.connect.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [None, "http://trusted.fixture:5173", "http://127.0.0.1:5190"])
async def test_configured_origin_same_proxy_host_and_nonbrowser_clients_can_connect_and_cleanup(broker, origin):
    socket = Socket(origin, ["ping"])
    await subject.websocket_events(socket)
    broker.connect.assert_awaited_once_with(socket)
    broker.disconnect.assert_awaited_once_with(socket)
    assert socket.receive_text.await_count == 2


@pytest.mark.asyncio
async def test_capacity_refusal_never_enters_receive_loop(broker):
    broker.connect.return_value = False
    socket = Socket()
    await subject.websocket_events(socket)
    socket.receive_text.assert_not_awaited()
    broker.disconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_oversized_client_text_closes_and_releases_sender(broker):
    socket = Socket(messages=["x" * 4097])
    await subject.websocket_events(socket)
    socket.close.assert_awaited_once_with(code=1009)
    broker.disconnect.assert_awaited_once_with(socket)


@pytest.mark.asyncio
async def test_server_cancellation_releases_sender(broker):
    socket = Socket()
    socket.receive_text.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await subject.websocket_events(socket)
    broker.disconnect.assert_awaited_once_with(socket)


@pytest.mark.asyncio
async def test_provider_compression_cannot_bypass_decoded_byte_budget():
    compressed = gzip.compress(b'{"records": []' + b' ' * 1000 + b'}')
    assert len(compressed) < 64
    response = lambda request: httpx.Response(200, content=compressed,
        headers={"Content-Encoding": "gzip", "Content-Length": str(len(compressed))})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(ValueError, match="byte limit"):
            await bounded_json(client, "https://fixture.invalid", max_bytes=64)


@pytest.mark.asyncio
@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
async def test_nonfinite_json_never_reaches_tracking_normalizers(constant):
    response = lambda request: httpx.Response(200, text='{"position":' + constant + '}')
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(ValueError, match="Nonfinite JSON"):
            await bounded_json(client, "https://fixture.invalid")


@pytest.mark.asyncio
async def test_failed_http_response_is_not_treated_as_empty_valid_tracking_coverage():
    response = lambda request: httpx.Response(429, json={"states": []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await bounded_json(client, "https://fixture.invalid")

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services import telegram


def setup_client(monkeypatch):
    config = SimpleNamespace(telegram_session="fixture-session",telegram_api_id=1,
        telegram_api_hash="fixture-hash",telegram_phone="")
    monkeypatch.setattr(telegram,"settings",config)
    monkeypatch.setattr(telegram,"StringSession",lambda token: token)
    monkeypatch.setattr(telegram,"_get_channels",lambda:["fixture-channel"])
    monkeypatch.setattr(telegram,"_get_conflict_cutoff",lambda:datetime(2026,1,1,tzinfo=timezone.utc))
    monkeypatch.setattr(telegram,"_shared_client",None)
    client=MagicMock()
    client.connect=AsyncMock()
    client.is_user_authorized=AsyncMock(return_value=True)
    client.disconnect=AsyncMock()
    monkeypatch.setattr(telegram,"TelegramClient",lambda *a,**k:client)
    return client


@pytest.mark.asyncio
async def test_no_resolved_channel_disconnects_and_clears_shared_handle(monkeypatch):
    client=setup_client(monkeypatch)
    client.get_entity=AsyncMock(side_effect=RuntimeError("fixture resolution failure"))
    await telegram.start_telegram_listener()
    client.disconnect.assert_awaited_once()
    assert telegram._shared_client is None


@pytest.mark.asyncio
async def test_unauthorized_session_disconnects_without_interactive_prompt(monkeypatch):
    client=setup_client(monkeypatch)
    client.is_user_authorized=AsyncMock(return_value=False)
    await telegram.start_telegram_listener()
    client.disconnect.assert_awaited_once()
    client.start.assert_not_called()
    assert telegram._shared_client is None


@pytest.mark.asyncio
async def test_cancelled_connect_still_disconnects(monkeypatch):
    client=setup_client(monkeypatch)
    started=asyncio.Event()
    async def blocked_connect():
        started.set()
        await asyncio.Event().wait()
    client.connect=blocked_connect
    task=asyncio.create_task(telegram.start_telegram_listener())
    await asyncio.wait_for(started.wait(),timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.disconnect.assert_awaited_once()
    assert telegram._shared_client is None

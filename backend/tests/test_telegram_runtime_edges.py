"""Public Telegram read-only lifecycle, including partial provider failures."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import telegram
from app.services.runtime import Runtime
import app.services.runtime as runtime_module


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(telegram, "settings", SimpleNamespace(
        telegram_session="fixture-session", telegram_api_id=1, telegram_api_hash="fixture-hash",
        telegram_processing_mode="reports", telegram_startup_max_messages=3,
        live_ingestion_enabled=True, telegram_channels="publicone,publictwo"))
    monkeypatch.setattr(telegram, "_shared_client", None)
    monkeypatch.setattr(telegram, "_get_channels", lambda: ["publicone", "publictwo"])
    monkeypatch.setattr(telegram, "StringSession", lambda value: value)
    monkeypatch.setattr(telegram, "_state", {})
    return Runtime()


class PublicClient:
    def __init__(self, *, fail_one=False, broadcast=True):
        self.connect = AsyncMock()
        self.disconnect = AsyncMock()
        self.is_user_authorized = AsyncMock(return_value=True)
        self.handlers = []
        self.broadcast = broadcast
        self.fail_one = fail_one
        self.run_until_disconnected = AsyncMock()
    async def get_entity(self, name):
        if self.fail_one and name == "publicone":
            raise RuntimeError("private token diagnostic")
        return SimpleNamespace(username=name, broadcast=self.broadcast)
    def on(self, subscription):
        def decorator(handler):
            self.handlers.append((subscription, handler))
            return handler
        return decorator


@pytest.mark.asyncio
async def test_partial_resolution_failure_stays_visible_and_both_live_edit_handlers_use_raw_metadata(state, monkeypatch):
    client = PublicClient(fail_one=True)
    monkeypatch.setattr(telegram, "TelegramClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(runtime_module, "runtime", state)
    backfill = AsyncMock()
    process = AsyncMock(return_value="reported")
    monkeypatch.setattr(telegram, "_backfill_entity", backfill)
    monkeypatch.setattr(telegram, "_process_message", process)
    await telegram.start_telegram_listener()
    assert telegram._state["channels"]["publicone"] == {"status": "failed", "error_type": "RuntimeError"}
    assert "private token" not in str(telegram._state)
    assert len(client.handlers) == 2
    assert {type(subscription).__name__ for subscription, _ in client.handlers} == {"NewMessage", "MessageEdited"}
    message = SimpleNamespace(text="Original publisher text", date=telegram._stamp(), id=123)
    event = SimpleNamespace(chat=SimpleNamespace(username="PublicTwo"), message=message)
    for _, handler in client.handlers:
        await handler(event)
    assert process.await_count == 2
    process.assert_awaited_with(message.text, "publictwo", message.date, 123)
    backfill.assert_awaited_once()
    client.disconnect.assert_awaited_once()
    assert telegram._shared_client is None
    assert all(task.done() for task in state.tasks.values())
    assert telegram._state["error_type"] == "Disconnected"
    await state.stop()


@pytest.mark.asyncio
async def test_nonbroadcast_entity_is_rejected_before_subscription_or_history(state, monkeypatch):
    client = PublicClient(broadcast=False)
    monkeypatch.setattr(telegram, "TelegramClient", lambda *args, **kwargs: client)
    backfill = AsyncMock()
    monkeypatch.setattr(telegram, "_backfill_entity", backfill)
    await telegram.start_telegram_listener()
    assert telegram._state["error_type"] == "NoPublicChannelsResolved"
    assert client.handlers == []
    backfill.assert_not_awaited()
    client.run_until_disconnected.assert_not_awaited()
    client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_credential_does_not_construct_client_or_prompt(state, monkeypatch):
    telegram.settings.telegram_session = ""
    constructor = Mock(side_effect=AssertionError("No Telegram I/O is authorized with no session"))
    monkeypatch.setattr(telegram, "TelegramClient", constructor)
    await telegram.start_telegram_listener()
    assert telegram._state["status"] == "disabled"
    assert telegram._state["error_type"] == "MissingCredentialsOrChannelSelection"
    constructor.assert_not_called()


@pytest.mark.asyncio
async def test_session_parse_failure_exposes_type_only_without_constructing_client(state, monkeypatch, caplog):
    monkeypatch.setattr(telegram, "StringSession", Mock(side_effect=ValueError("private session credential")))
    constructor = Mock()
    monkeypatch.setattr(telegram, "TelegramClient", constructor)
    await telegram.start_telegram_listener()
    assert telegram._state["status"] == "failed" and telegram._state["error_type"] == "ValueError"
    assert "private session" not in str(telegram._state) + caplog.text
    constructor.assert_not_called()


@pytest.mark.asyncio
async def test_disconnect_failure_is_explicit_and_never_retains_shared_client(state, monkeypatch):
    client = PublicClient(broadcast=False)
    client.disconnect.side_effect = RuntimeError("private disconnect secret")
    monkeypatch.setattr(telegram, "TelegramClient", lambda *args, **kwargs: client)
    await telegram.start_telegram_listener()
    assert telegram._shared_client is None
    assert telegram._state["status"] == "failed" and telegram._state["error_type"] == "DisconnectRuntimeError"
    assert "private disconnect" not in str(telegram._state)

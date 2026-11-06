"""Offline same-process transport faults. No provider, DB, or credentials used."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.services import telegram as tg
from app.services.runtime import Runtime
import app.services.runtime as runtime_module


class Client:
    def __init__(self, *, connect_error=None, run_error=None, auth=True, cleanup_error=None):
        self.connect_error, self.run_error = connect_error, run_error
        self.auth, self.cleanup_error = auth, cleanup_error
        self.connected = False
        self.started = asyncio.Event()
        self.disconnect_signal = asyncio.Event()
        self.handlers = []
        self.connect_calls = self.disconnect_calls = 0
        self.cleanup_task = None
        self.order = []

    async def connect(self):
        self.connect_calls += 1
        if self.connect_error:
            raise self.connect_error
        self.connected = True

    async def is_user_authorized(self):
        return self.auth

    def is_connected(self):
        return self.connected

    async def get_entity(self, name):
        return SimpleNamespace(username=name, broadcast=True)

    def on(self, subscription):
        def decorator(handler):
            self.handlers.append(handler)
            return handler
        return decorator

    async def run_until_disconnected(self):
        try:
            self.started.set()
            if self.run_error:
                raise self.run_error
            await self.disconnect_signal.wait()
        finally:
            await self.disconnect()

    def disconnect(self):
        if self.cleanup_task is None:
            async def cleanup():
                self.disconnect_calls += 1
                if self.cleanup_error:
                    raise self.cleanup_error
                self.connected = False
                self.disconnect_signal.set()
                self.order.append("disconnected")
            self.cleanup_task = asyncio.create_task(cleanup())
        return asyncio.shield(self.cleanup_task)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(tg, "settings", SimpleNamespace(telegram_session="fixture-authored",
        telegram_api_id=1, telegram_api_hash="fixture", telegram_processing_mode="reports",
        telegram_startup_max_messages=3, telegram_transport="session", live_ingestion_enabled=True, demo_mode=False))
    monkeypatch.setattr(tg, "StringSession", lambda value: value)
    monkeypatch.setattr(tg, "_get_channels", lambda: ["public_fixture"])
    monkeypatch.setattr(tg, "_get_conflict_cutoff", lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(tg, "_shared_client", None)
    monkeypatch.setattr(tg, "_listener_owner", None)
    monkeypatch.setattr(tg, "_listener_cleanup_unconfirmed", False)
    monkeypatch.setattr(tg, "_manual_backfills", {})
    monkeypatch.setattr(tg, "_state", {"channels": {}, "last_success_at": None, "last_published_at": None})
    backfill = AsyncMock()
    monkeypatch.setattr(tg, "_backfill_entity", backfill)
    runtime = Runtime()
    monkeypatch.setattr(runtime_module, "runtime", runtime)
    return SimpleNamespace(backfill=backfill, runtime=runtime)


async def stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["connect", "run", "normal_disconnect", "resolve", "catch_up"])
async def test_transport_failure_rebinds_one_client_after_cleanup(setup, monkeypatch, phase):
    first = Client(connect_error=ConnectionError() if phase == "connect" else None,
        run_error=ConnectionError() if phase == "run" else None)
    second = Client()
    if phase == "normal_disconnect":
        first.disconnect_signal.set()
    if phase == "resolve":
        first.get_entity = AsyncMock(side_effect=ConnectionError())
    if phase == "catch_up":
        setup.backfill.side_effect = [ConnectionError(), None]
    clients = [first, second]
    constructs, delays = [], []
    def factory(*a, **kw):
        if constructs:
            assert not first.is_connected() and first.cleanup_task.done()
            assert setup.runtime.tasks.get("telegram_periodic") is None or setup.runtime.tasks["telegram_periodic"].done()
        client = clients[len(constructs)]
        constructs.append(client)
        return client
    async def sleep(delay):
        assert tg._shared_client is None
        assert tg.get_telegram_status()["status"] == "retrying"
        delays.append(delay)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    monkeypatch.setattr(tg, "_retry_sleep", sleep)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(second.started.wait(), 1)
    assert constructs == [first, second] and delays == [5]
    assert tg._shared_client is second and tg._state["status"] == "ok"
    assert first.disconnect_calls == 1
    await stop(task)
    assert second.disconnect_calls == 1
    assert tg._shared_client is tg._listener_owner is None
    assert all(task.done() for task in setup.runtime.tasks.values())


@pytest.mark.asyncio
async def test_persistent_failure_backoff_caps_and_cancellation_stops(setup, monkeypatch):
    clients, delays = [], []
    blocked = asyncio.Event()
    def factory(*a, **kw):
        client = Client(connect_error=ConnectionError("secret session diagnostic"))
        clients.append(client)
        return client
    async def sleep(delay):
        delays.append(delay)
        if len(delays) == 9:
            blocked.set()
            await asyncio.Event().wait()
    monkeypatch.setattr(tg, "TelegramClient", factory)
    monkeypatch.setattr(tg, "_retry_sleep", sleep)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(blocked.wait(), 1)
    assert delays == [5, 10, 20, 40, 80, 160, 300, 300, 300]
    assert len(clients) == 9 and all(c.disconnect_calls == 1 for c in clients)
    assert tg._state["reconnect_attempts"] == 9
    assert "secret" not in str(tg._state)
    await stop(task)
    assert len(clients) == 9 and tg._state["status"] == "disabled"


@pytest.mark.asyncio
async def test_second_listener_does_not_replace_owner_or_create_session(setup, monkeypatch):
    client = Client()
    factory = Mock(return_value=client)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(client.started.wait(), 1)
    await tg.start_telegram_listener()
    factory.assert_called_once()
    assert tg._listener_owner is task and tg._shared_client is client
    await stop(task)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ValueError("secret"), tg.errors.AuthKeyError(None, "BAD_KEY"),
    tg.errors.UnauthorizedError(None, "SESSION_REVOKED"), tg.errors.AuthKeyNotFound(),
    tg.errors.FloodWaitError(None, 1234)])
async def test_nontransport_and_permission_errors_are_terminal(setup, monkeypatch, error):
    client = Client(connect_error=error)
    factory = Mock(return_value=client)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    sleep = AsyncMock(side_effect=AssertionError("Terminal failure must not retry"))
    monkeypatch.setattr(tg, "_retry_sleep", sleep)
    await tg.start_telegram_listener()
    factory.assert_called_once()
    sleep.assert_not_awaited()
    assert tg._state["status"] == "failed" and tg._state["error_type"] == type(error).__name__
    assert "secret" not in str(tg._state)


@pytest.mark.asyncio
async def test_unauthorized_and_model_permissions_do_not_retry(setup, monkeypatch):
    client = Client(auth=False)
    factory = Mock(return_value=client)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    await tg.start_telegram_listener()
    assert tg._state["error_type"] == "UnauthorizedSession"
    factory.assert_called_once()
    tg.settings.telegram_processing_mode = "model"
    await tg.start_telegram_listener()
    assert tg._state["error_type"] == "SourcePermissionRequired"
    factory.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_failure_quarantines_future_starts(setup, monkeypatch):
    client = Client(connect_error=ConnectionError(), cleanup_error=RuntimeError("secret teardown"))
    factory = Mock(return_value=client)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    await tg.start_telegram_listener()
    assert tg._listener_cleanup_unconfirmed and tg._state["error_type"] == "DisconnectRuntimeError"
    await tg.start_telegram_listener()
    factory.assert_called_once()
    assert tg._state["error_type"] == "CleanupUnconfirmed" and "secret" not in str(tg._state)


@pytest.mark.asyncio
async def test_repeated_cancel_waits_for_actual_cleanup_and_never_rebinds(setup, monkeypatch):
    client = Client()
    entered, release = asyncio.Event(), asyncio.Event()
    async def cleanup():
        client.disconnect_calls += 1
        entered.set()
        await release.wait()
        client.connected = False
    def disconnect():
        if client.cleanup_task is None:
            client.cleanup_task = asyncio.create_task(cleanup())
        return asyncio.shield(client.cleanup_task)
    client.disconnect = disconnect
    factory = Mock(return_value=client)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(client.started.wait(), 1)
    task.cancel()
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and client.connected and tg._shared_client is None
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not client.connected and client.disconnect_calls == 1
    factory.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_timeout_remains_quarantined_even_after_late_cleanup(setup, monkeypatch):
    client = Client(connect_error=ConnectionError())
    release = asyncio.Event()
    async def close():
        await release.wait()
        client.connected = False
    def disconnect():
        if client.cleanup_task is None:
            client.cleanup_task = asyncio.create_task(close())
        return asyncio.shield(client.cleanup_task)
    client.disconnect = disconnect
    monkeypatch.setattr(tg, "_CLEANUP_TIMEOUT", .01)
    factory = Mock(return_value=client)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    try:
        await tg.start_telegram_listener()
        assert tg._listener_cleanup_unconfirmed and not client.cleanup_task.done()
        await tg.start_telegram_listener()
        factory.assert_called_once()
    finally:
        release.set()
        await client.cleanup_task


@pytest.mark.asyncio
async def test_cancel_during_failing_cleanup_is_not_swallowed(setup, monkeypatch):
    client = Client(connect_error=ConnectionError())
    entered, release = asyncio.Event(), asyncio.Event()
    async def close():
        entered.set()
        await release.wait()
        raise RuntimeError("private cleanup error")
    def disconnect():
        if client.cleanup_task is None:
            client.cleanup_task = asyncio.create_task(close())
        return asyncio.shield(client.cleanup_task)
    client.disconnect = disconnect
    monkeypatch.setattr(tg, "TelegramClient", lambda *a, **k: client)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert tg._listener_cleanup_unconfirmed and tg._state["error_type"] == "DisconnectRuntimeError"
    assert tg._listener_owner is None


@pytest.mark.asyncio
async def test_worker_ignoring_cancel_prevents_any_successor(setup, monkeypatch):
    client = Client()
    entered, release = asyncio.Event(), asyncio.Event()
    async def stubborn_run():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
        finally:
            await client.disconnect()
    client.run_until_disconnected = stubborn_run
    monkeypatch.setattr(tg, "_CLEANUP_TIMEOUT", .01)
    factory = Mock(return_value=client)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(entered.wait(), 1)
    try:
        await stop(task)
        assert tg._listener_cleanup_unconfirmed and tg._state["error_type"] == "WorkerCleanupTimeout"
        assert client.disconnect_calls == 1 and not client.connected
        await tg.start_telegram_listener()
        factory.assert_called_once()
    finally:
        release.set()
        while client.cleanup_task is None:
            await asyncio.sleep(0)
        await client.cleanup_task


@pytest.mark.asyncio
async def test_real_telethon_disconnect_wrapper_is_one_shielded_join(monkeypatch):
    real_class = tg.TelegramClient
    client = object.__new__(real_class)
    entered, release = asyncio.Event(), asyncio.Event()
    async def close(self):
        entered.set()
        await release.wait()
    base = AsyncMock(side_effect=close)
    # Explicit descriptor binds self like the real superclass method.
    calls = []
    async def original(self):
        calls.append(self)
        await close(self)
    monkeypatch.setattr(tg._TelethonClient, "disconnect", original)
    first, second = client.disconnect(), client.disconnect()
    await asyncio.wait_for(entered.wait(), 1)
    first.cancel()
    assert not client._owned_disconnect.done()
    release.set()
    await second
    await client.disconnect()
    assert calls == [client]


@pytest.mark.asyncio
async def test_installed_telethon_shield_and_run_finally_share_one_disconnect(monkeypatch):
    # Use installed public run/disconnect methods, replacing only provider I/O.
    client = object.__new__(tg.TelegramClient)
    connection = asyncio.get_running_loop().create_future()
    client._sender = SimpleNamespace(disconnected=connection)
    client._updates_error = None
    entered, release = asyncio.Event(), asyncio.Event()
    async def internal_cleanup():
        entered.set()
        await release.wait()
    underlying = AsyncMock(side_effect=internal_cleanup)
    client._disconnect_coro = underlying
    async def request(self, *args, **kwargs):
        return None
    monkeypatch.setattr(tg._TelethonClient, "__call__", request)
    running = asyncio.create_task(client.run_until_disconnected())
    connection.set_exception(ConnectionError("authored transport loss"))
    await asyncio.wait_for(entered.wait(), 1)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(client.disconnect(), .01)
    assert not client._owned_disconnect.done() and not running.done()
    release.set()
    with pytest.raises(ConnectionError):
        await running
    await client.disconnect()
    underlying.assert_awaited_once()


@pytest.mark.asyncio
async def test_periodic_transport_failure_reconnects_without_waiting_for_push_loss(setup, monkeypatch):
    first, second = Client(), Client()
    clients = iter([first, second])
    monkeypatch.setattr(tg, "TelegramClient", lambda *a, **kw: next(clients))
    monkeypatch.setattr(tg, "_retry_sleep", AsyncMock())
    original_sleep = asyncio.sleep
    async def fast_poll(seconds):
        await original_sleep(0 if seconds == 300 else seconds)
    monkeypatch.setattr(tg.asyncio, "sleep", fast_poll)
    calls = 0
    async def backfill(client, entity, cutoff):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionError("periodic transport fault")
    monkeypatch.setattr(tg, "_backfill_entity", backfill)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(second.started.wait(), 1)
    assert first.cleanup_task.done() and first.disconnect_calls == 1
    assert tg._shared_client is second
    await stop(task)


@pytest.mark.asyncio
async def test_flapping_does_not_reset_backoff_but_sustained_session_does(setup, monkeypatch):
    clients = []
    delays = []
    ready = asyncio.Event()
    def factory(*a, **kw):
        client = Client()
        clients.append(client)
        async def disconnect_quickly():
            if len(clients) == 4:
                tg._state["connected_since_monotonic"] -= tg._STABLE_SECONDS + 1
            await client.disconnect()
        client.run_until_disconnected = disconnect_quickly
        return client
    async def delay(seconds):
        delays.append(seconds)
        if len(delays) == 4:
            ready.set()
            await asyncio.Event().wait()
    monkeypatch.setattr(tg, "TelegramClient", factory)
    monkeypatch.setattr(tg, "_retry_sleep", delay)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(ready.wait(), 1)
    assert delays == [5, 10, 20, 5]
    await stop(task)


@pytest.mark.asyncio
async def test_stale_push_and_manual_job_do_not_cross_rebind(setup, monkeypatch):
    first, second = Client(), Client()
    clients = iter([first, second])
    monkeypatch.setattr(tg, "TelegramClient", lambda *a, **k: next(clients))
    monkeypatch.setattr(tg, "_retry_sleep", AsyncMock())
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(first.started.wait(), 1)
    entered = asyncio.Event()
    async def blocked_entity(name):
        entered.set()
        await asyncio.Event().wait()
    first.get_entity = blocked_entity
    manual = asyncio.create_task(tg.trigger_backfill())
    await asyncio.wait_for(entered.wait(), 1)
    first.disconnect_signal.set()
    await asyncio.wait_for(second.started.wait(), 1)
    assert manual.cancelled() and not tg._manual_backfills
    process = AsyncMock()
    monkeypatch.setattr(tg, "_process_message", process)
    await first.handlers[0](object())
    process.assert_not_awaited()
    assert tg._shared_client is second
    await stop(task)


@pytest.mark.asyncio
async def test_startup_failure_disconnects_even_if_manual_worker_ignores_cancel(setup, monkeypatch):
    client = Client()
    factory = Mock(return_value=client)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    monkeypatch.setattr(tg, "_CLEANUP_TIMEOUT", .01)
    startup, manual_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = 0
    async def backfill(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            startup.set()
            await manual_started.wait()
            raise ConnectionError("startup transport failure")
        manual_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
    monkeypatch.setattr(tg, "_backfill_entity", backfill)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(startup.wait(), 1)
    manual = asyncio.create_task(tg.trigger_backfill())
    try:
        await asyncio.wait_for(task, 1)
        assert tg._listener_cleanup_unconfirmed
        assert tg._state["error_type"] == "WorkerCleanupTimeout"
        assert client.disconnect_calls == 1 and not client.connected
        assert not manual.done() and tg._shared_client is None
        await tg.start_telegram_listener()
        factory.assert_called_once()
    finally:
        release.set()
        await manual


@pytest.mark.asyncio
@pytest.mark.parametrize("entity", [SimpleNamespace(username="public_fixture", broadcast=False),
    SimpleNamespace(username="different_public", broadcast=True)])
async def test_manual_catchup_requires_selected_public_broadcast(setup, monkeypatch, entity):
    client = Client()
    client.get_entity = AsyncMock(return_value=entity)
    monkeypatch.setattr(tg, "_shared_client", client)
    result = await tg.trigger_backfill()
    assert result["status"] == "partial" and result["channels"] == {"public_fixture": "failed"}
    setup.backfill.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [tg.errors.FloodPremiumWaitError(None, 1234),
    tg.errors.FloodTestPhoneWaitError(None, 1234)])
async def test_every_flood_subclass_is_terminal_during_resolution(setup, monkeypatch, error):
    client = Client()
    client.get_entity = AsyncMock(side_effect=error)
    factory = Mock(return_value=client)
    monkeypatch.setattr(tg, "TelegramClient", factory)
    sleep = AsyncMock(side_effect=AssertionError("Provider wait must not be shortened"))
    monkeypatch.setattr(tg, "_retry_sleep", sleep)
    await tg.start_telegram_listener()
    assert tg._state["error_type"] == type(error).__name__
    factory.assert_called_once()
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_periodic_transport_retry_does_not_mark_core_readiness_failed(setup, monkeypatch):
    from app import main
    from test_api_lifecycle import SchemaSession
    client = Client()
    monkeypatch.setattr(tg, "TelegramClient", lambda *a, **kw: client)
    original_sleep = asyncio.sleep
    async def fast_poll(seconds):
        await original_sleep(0 if seconds == 300 else seconds)
    monkeypatch.setattr(tg.asyncio, "sleep", fast_poll)
    calls = 0
    async def backfill(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionError("authored periodic failure")
    monkeypatch.setattr(tg, "_backfill_entity", backfill)
    ready = asyncio.Event()
    async def retry(delay):
        ready.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(tg, "_retry_sleep", retry)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(ready.wait(), 1)
    monkeypatch.setattr(main, "runtime", setup.runtime)
    monkeypatch.setattr(main, "async_session", SchemaSession)
    monkeypatch.setattr(main, "delivery_status", lambda: {"status": "ok"})
    try:
        assert tg.get_telegram_status()["status"] == "retrying"
        assert setup.runtime.failures == {}
        assert (await main.health()).status_code == 200
    finally:
        await stop(task)

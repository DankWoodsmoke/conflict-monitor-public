"""Transport recovery around the real report/checkpoint functions, mocked storage."""
import asyncio
import copy
from types import SimpleNamespace

import pytest
from app.services import telegram as tg
from app.services.runtime import Runtime
import app.services.runtime as runtime_module
from test_free_telegram import free, RAW, STAMP, ingest
from test_telegram_reconnect_prototype import Client, stop


@pytest.fixture(autouse=True)
def session_transport(monkeypatch):
    monkeypatch.setattr(tg.settings, "telegram_transport", "session")
    monkeypatch.setattr(tg.settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(tg.settings, "demo_mode", False)


@pytest.mark.asyncio
async def test_reconnect_resumes_committed_prefix_and_reuses_incomplete_receipt(free, monkeypatch):
    monkeypatch.setattr(tg, "_shared_client", None)
    monkeypatch.setattr(tg, "_listener_owner", None)
    monkeypatch.setattr(tg, "_listener_cleanup_unconfirmed", False)
    monkeypatch.setattr(tg, "_manual_backfills", {})
    monkeypatch.setattr(tg, "StringSession", lambda value: value)
    monkeypatch.setattr(tg.settings, "telegram_api_id", 1)
    monkeypatch.setattr(tg.settings, "telegram_api_hash", "fixture")
    monkeypatch.setattr(tg.settings, "telegram_session", "fixture")
    runtime = Runtime()
    monkeypatch.setattr(runtime_module, "runtime", runtime)
    checkpoints = {"fixture_public": 100}
    changes, pages = [], []
    async def read(channel):
        return checkpoints[channel]
    async def advance(channel, message_id):
        checkpoints[channel] = max(checkpoints[channel], message_id)
        changes.append(message_id)
    monkeypatch.setattr(tg, "_get_checkpoint", read)
    monkeypatch.setattr(tg, "_save_checkpoint", advance)
    # An already-retained original is never changed by transport recovery.
    assert await ingest(RAW + " archived", message_id=99) == "reported"
    old_event = copy.deepcopy({k: v for k, v in free.store.events[0].__dict__.items() if not k.startswith("_sa_")})
    old_receipt_id = next(iter(free.ledger.records))
    old_receipt = copy.deepcopy(free.ledger.records[old_receipt_id])
    first, second = Client(), Client()
    async def page(entity, **options):
        pages.append(dict(options))
        for i in (101, 102):
            if i > options["min_id"]:
                yield SimpleNamespace(id=i, text=RAW + str(i), date=STAMP)
    first.iter_messages = second.iter_messages = page
    interrupted = False
    async def finish(receipt, status, event_id=None):
        nonlocal interrupted
        if not interrupted and free.ledger.records[receipt]["report"]["telegram_message_id"] == 101:
            interrupted = True
            raise ConnectionError("after Event commit before receipt completion")
        await free.ledger.finish(receipt, status, event_id)
    monkeypatch.setattr(tg, "finish_report", finish)
    clients = iter([first, second])
    monkeypatch.setattr(tg, "TelegramClient", lambda *a, **k: next(clients))
    async def retry(delay):
        assert delay == 5 and checkpoints["fixture_public"] == 100
        assert [e.telegram_message_id for e in free.store.events] == [99, 101]
        # Newer push still cannot certify the missing ordered prefix.
        assert await ingest(RAW + "102", message_id=102) == "reported"
        assert checkpoints["fixture_public"] == 100
    monkeypatch.setattr(tg, "_retry_sleep", retry)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(second.started.wait(), 1)
    await stop(task)
    assert pages == [{"limit": 3, "min_id": 100, "reverse": True}] * 2
    assert changes == [101, 102] and checkpoints["fixture_public"] == 102
    assert [e.telegram_message_id for e in free.store.events] == [99, 101, 102]
    assert {k: v for k, v in free.store.events[0].__dict__.items() if not k.startswith("_sa_")} == old_event
    assert free.ledger.records[old_receipt_id] == old_receipt
    assert {r["status"] for r in free.ledger.records.values()} == {"reported"}
    assert all(e.source == "telegram" and e.source_url.startswith("https://t.me/fixture_public/")
               and e.timestamp == STAMP and e.severity == 0 and e.lat is None and e.lon is None
               for e in free.store.events)
    free.forbidden.assert_not_awaited()
    assert free.broadcast.await_count == 3


@pytest.mark.asyncio
async def test_reconnect_retains_last_good_clocks_and_blocked_page_diagnostics(free, monkeypatch):
    monkeypatch.setattr(tg, "_listener_owner", None)
    monkeypatch.setattr(tg, "_listener_cleanup_unconfirmed", False)
    monkeypatch.setattr(tg, "_manual_backfills", {})
    monkeypatch.setattr(tg, "StringSession", lambda value: value)
    monkeypatch.setattr(tg.settings, "telegram_api_id", 1)
    monkeypatch.setattr(tg.settings, "telegram_api_hash", "fixture")
    monkeypatch.setattr(tg.settings, "telegram_session", "fixture")
    tg._state.update(last_success_at=STAMP, last_published_at=STAMP)
    tg._state["channels"]["fixture_public"] = {"checkpoint_message_id": 100, "blocked_message_id": 101}
    monkeypatch.setattr(tg, "TelegramClient", lambda *a, **k: Client(connect_error=ConnectionError()))
    at_backoff = asyncio.Event()
    async def retry(delay):
        at_backoff.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(tg, "_retry_sleep", retry)
    task = asyncio.create_task(tg.start_telegram_listener())
    await asyncio.wait_for(at_backoff.wait(), 1)
    assert tg._state["last_success_at"] == tg._state["last_published_at"] == STAMP
    assert tg._state["channels"]["fixture_public"] == {"checkpoint_message_id": 100, "blocked_message_id": 101}
    await stop(task)

"""Exercise real delivery/cache state machines without provider or socket I/O."""
import asyncio
import threading
import time

import pytest

from app.routes import market
from app.services.broadcaster import Broadcaster


class Socket:
    def __init__(self, *, hold_send=False, hold_accept=False, hold_close=False):
        self.accept_started = asyncio.Event()
        self.accept_gate = asyncio.Event()
        self.send_started = asyncio.Event()
        self.send_gate = asyncio.Event()
        self.close_started = asyncio.Event()
        self.close_gate = asyncio.Event()
        self.received = asyncio.Queue()
        self.close_codes = []
        if not hold_send:
            self.send_gate.set()
        if not hold_accept:
            self.accept_gate.set()
        if not hold_close:
            self.close_gate.set()

    async def accept(self):
        self.accept_started.set()
        await self.accept_gate.wait()

    async def send_text(self, message):
        self.send_started.set()
        await self.send_gate.wait()
        self.received.put_nowait(message)

    async def close(self, code=1000):
        self.close_codes.append(code)
        self.close_started.set()
        await self.close_gate.wait()


async def completed(awaitable):
    # A delivery blocked on a gate cannot accidentally pass on a fast machine.
    return await asyncio.wait_for(awaitable, timeout=1)


@pytest.mark.asyncio
async def test_broadcaster_capacity_rejects_without_allocating_a_sender():
    broker = Broadcaster(max_clients=1, queue_size=2)
    accepted, rejected = Socket(), Socket()
    try:
        assert await broker.connect(accepted) is True
        assert await broker.connect(rejected) is False
        assert rejected.close_codes == [1013]
        assert set(broker._clients) == {accepted}
        assert set(broker._senders) == {accepted}
    finally:
        await completed(broker.stop())


@pytest.mark.asyncio
async def test_slow_consumer_cannot_delay_other_clients_or_publish():
    broker = Broadcaster(queue_size=3)
    slow, fast = Socket(hold_send=True), Socket()
    try:
        await broker.connect(slow)
        await broker.connect(fast)
        await completed(broker.broadcast("first"))
        await completed(slow.send_started.wait())
        assert await completed(fast.received.get()) == "first"
        await completed(broker.broadcast("second"))
        assert await completed(fast.received.get()) == "second"
        assert slow.received.empty()
    finally:
        await completed(broker.stop())


@pytest.mark.asyncio
async def test_queue_overflow_disconnects_slow_consumer_and_preserves_peer():
    broker = Broadcaster(queue_size=1)
    slow, fast = Socket(hold_send=True), Socket()
    try:
        await broker.connect(slow)
        await broker.connect(fast)
        slow_sender = broker._senders[slow]
        for message in ("in flight", "queued", "overflow"):
            await completed(broker.broadcast(message))
            assert await completed(fast.received.get()) == message
            if message == "in flight":
                await completed(slow.send_started.wait())
        await completed(slow.close_started.wait())
        await completed(asyncio.gather(slow_sender, return_exceptions=True))
        assert slow not in broker._clients
        assert slow not in broker._senders
        assert fast in broker._clients
    finally:
        await completed(broker.stop())


@pytest.mark.asyncio
async def test_stop_finishes_all_owned_senders_even_if_close_never_completes():
    broker = Broadcaster(queue_size=2)
    sockets = [Socket(hold_send=True), Socket(hold_close=True), Socket()]
    for ws in sockets:
        await broker.connect(ws)
    senders = set(broker._senders.values())
    await broker.broadcast("queued")
    await completed(sockets[0].send_started.wait())
    await completed(broker.stop())
    assert not broker._clients
    assert not broker._senders
    assert all(task.done() for task in senders)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["accept", "capacity_close"])
async def test_stuck_handshake_cannot_lock_out_existing_client_publish(phase):
    broker = Broadcaster(max_clients=1 if phase == "capacity_close" else 2)
    active = Socket()
    pending = Socket(hold_accept=phase == "accept", hold_close=phase == "capacity_close")
    await broker.connect(active)
    connect_task = asyncio.create_task(broker.connect(pending))
    try:
        started = pending.accept_started if phase == "accept" else pending.close_started
        await completed(started.wait())
        await completed(broker.broadcast("existing client remains live"))
        assert await completed(active.received.get()) == "existing client remains live"
    finally:
        pending.accept_gate.set()
        pending.close_gate.set()
        await completed(asyncio.gather(connect_task, return_exceptions=True))
        await completed(broker.stop())


@pytest.mark.asyncio
async def test_repeated_connect_does_not_orphan_original_sender_on_shutdown():
    broker = Broadcaster()
    ws = Socket()
    await broker.connect(ws)
    original_sender = broker._senders[ws]
    try:
        await broker.connect(ws)
        owned = {original_sender, *broker._senders.values()}
        await completed(broker.stop())
        assert all(task.done() for task in owned)
    finally:
        # Also clean up a failing implementation so no tasks escape this test.
        original_sender.cancel()
        await asyncio.gather(original_sender, return_exceptions=True)
        await completed(broker.stop())


@pytest.mark.asyncio
async def test_pending_handshake_reserves_capacity_and_shutdown_cancels_it():
    broker = Broadcaster(max_clients=1)
    pending = Socket(hold_accept=True)
    caller = asyncio.create_task(broker.connect(pending))
    await completed(pending.accept_started.wait())
    owned = set(broker._pending.values())
    rejected = Socket()
    assert await completed(broker.connect(rejected)) is False
    assert not rejected.accept_started.is_set()
    await completed(broker.stop())
    await completed(asyncio.gather(caller, return_exceptions=True))
    assert all(task.done() for task in owned)
    assert not broker._pending and not broker._senders and not broker._clients
    assert await broker.connect(Socket()) is False


@pytest.fixture
async def market_state(monkeypatch):
    monkeypatch.setattr(market.settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(market, "_cache", None)
    monkeypatch.setattr(market, "_cache_ts", 0)
    monkeypatch.setattr(market, "_hist_by_days", {})
    monkeypatch.setattr(market, "_quote_task", None)
    monkeypatch.setattr(market, "_stopping", False)
    monkeypatch.setattr(market, "_quote_retry_at", 0)
    monkeypatch.setattr(market, "_history_retry_at", {})
    monkeypatch.setattr(market, "_provider_slots", asyncio.Semaphore(2))
    monkeypatch.setattr(market, "_provider_jobs", set())
    if hasattr(market, "_history_task"):
        monkeypatch.setattr(market, "_history_task", None)
    if hasattr(market, "_history_tasks"):
        monkeypatch.setattr(market, "_history_tasks", {})
    yield
    tasks = {value for value in vars(market).values() if isinstance(value, asyncio.Task)}
    for value in vars(market).values():
        if isinstance(value, dict):
            tasks.update(item for item in value.values() if isinstance(item, asyncio.Task))
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_disabled_market_performs_no_fetch_even_with_cached_values(market_state, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled market attempted provider I/O")

    monkeypatch.setattr(market.settings, "live_ingestion_enabled", False)
    monkeypatch.setattr(market, "_fetch_quotes", forbidden)
    monkeypatch.setattr(market, "_fetch_history_sync", forbidden)
    monkeypatch.setattr(market, "_cache", [{"symbol": "fixture"}])
    market._hist_by_days[30] = (time.monotonic(), {"fixture": []})
    quotes, history = await asyncio.gather(market.get_market_data(), market.get_market_history(30))
    assert quotes["status"] == history["status"] == "disabled"
    assert quotes["data"] == [] and history["history"] == {}
    assert market._quote_task is None


@pytest.mark.asyncio
async def test_concurrent_quote_requests_singleflight_then_use_cache(market_state, monkeypatch):
    calls = 0
    async def quotes():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return [{"symbol": "fixture", "price": 123.4}]

    monkeypatch.setattr(market, "_fetch_quotes", quotes)
    results = await asyncio.gather(*(market.get_market_data() for _ in range(12)))
    assert calls == 1
    assert all(result["data"] == results[0]["data"] and not result["stale"] for result in results)
    assert (await market.get_market_data())["data"] == results[0]["data"]
    assert calls == 1


@pytest.mark.asyncio
async def test_cancelling_one_quote_request_preserves_shared_refresh(market_state, monkeypatch):
    started, finish = asyncio.Event(), asyncio.Event()
    calls = 0
    async def quotes():
        nonlocal calls
        calls += 1
        started.set()
        await finish.wait()
        return [{"symbol": "fixture", "price": 1}]

    monkeypatch.setattr(market, "_fetch_quotes", quotes)
    first = asyncio.create_task(market.get_market_data())
    await completed(started.wait())
    second = asyncio.create_task(market.get_market_data())
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    finish.set()
    result = await completed(second)
    assert result["data"][0]["price"] == 1 and calls == 1


@pytest.mark.asyncio
async def test_empty_quote_refresh_preserves_last_good_age(market_state, monkeypatch):
    snapshot = [{"symbol": "fixture", "price": 100}]
    stamp = time.monotonic() - market.CACHE_TTL - 20
    monkeypatch.setattr(market, "_cache", snapshot)
    monkeypatch.setattr(market, "_cache_ts", stamp)
    async def empty():
        return []
    monkeypatch.setattr(market, "_fetch_quotes", empty)
    result = await market.get_market_data()
    assert result["data"] == snapshot
    assert result["stale"] is True
    assert market._cache_ts == stamp


@pytest.mark.asyncio
async def test_history_singleflight_for_same_range_and_cache_is_range_scoped(market_state, monkeypatch):
    calls = []
    def history(symbols, days):
        calls.append(days)
        return {"fixture": [{"date": "2026-01-01", "close": days}]}
    monkeypatch.setattr(market, "_fetch_history_sync", history)
    results = await asyncio.gather(*(market.get_market_history(5) for _ in range(10)))
    assert calls == [5]
    assert all(item["history"]["fixture"][0]["close"] == 5 for item in results)
    other = await market.get_market_history(30)
    again = await market.get_market_history(5)
    assert other["history"]["fixture"][0]["close"] == 30
    assert again["history"]["fixture"][0]["close"] == 5
    assert calls == [5, 30]


@pytest.mark.asyncio
async def test_concurrent_different_history_ranges_each_get_their_requested_data(market_state, monkeypatch):
    calls = []
    def history(symbols, days):
        calls.append(days)
        return {"fixture": [{"date": "2026-01-01", "close": days}]}
    monkeypatch.setattr(market, "_fetch_history_sync", history)
    five, thirty = await asyncio.gather(market.get_market_history(5), market.get_market_history(30))
    assert sorted(calls) == [5, 30]
    assert five["history"]["fixture"][0]["close"] == 5
    assert thirty["history"]["fixture"][0]["close"] == 30


@pytest.mark.asyncio
async def test_failed_refreshes_back_off_and_retry_after_cooldown(market_state, monkeypatch):
    calls = {"quotes": 0, "history": 0}
    async def quotes():
        calls["quotes"] += 1
        raise ValueError("fixture provider unavailable")
    def history(*args):
        calls["history"] += 1
        raise ValueError("fixture provider unavailable")
    monkeypatch.setattr(market, "_fetch_quotes", quotes)
    monkeypatch.setattr(market, "_fetch_history_sync", history)
    for _ in range(3):
        q, h = await asyncio.gather(market.get_market_data(), market.get_market_history(30))
        assert q["status"] == h["status"] == "unavailable"
        assert q["retry_after"] >= 29 and h["retry_after"] >= 29
    assert calls == {"quotes": 1, "history": 1}
    monkeypatch.setattr(market, "_quote_retry_at", time.monotonic() - 1)
    market._history_retry_at[30] = time.monotonic() - 1
    await asyncio.gather(market.get_market_data(), market.get_market_history(30))
    assert calls == {"quotes": 2, "history": 2}


@pytest.mark.asyncio
async def test_many_history_ranges_bound_tasks_and_actual_provider_jobs(market_state, monkeypatch):
    release = threading.Event()
    started_two = asyncio.Event()
    loop = asyncio.get_running_loop()
    calls = []
    lock = threading.Lock()
    def history(symbols, days):
        with lock:
            calls.append(days)
            if len(calls) == 2:
                loop.call_soon_threadsafe(started_two.set)
        if not release.wait(5):
            raise RuntimeError("Test did not release provider fixture")
        return {"fixture": [{"date": "2026-01-01", "close": days}]}
    monkeypatch.setattr(market, "_fetch_history_sync", history)
    callers = [asyncio.create_task(market.get_market_history(days)) for days in (5, 10, 15, 20, 25, 30)]
    try:
        await completed(started_two.wait())
        assert len(calls) == 2
        assert len(market._provider_jobs) == 2
        assert market._active_refresh_count() == market.MAX_REFRESH_TASKS == 4
        denied = await completed(market.get_market_history(90))
        assert denied["history"] == {} and denied["retry_after"] > 0
        assert 90 not in market._history_tasks
    finally:
        release.set()
        await completed(asyncio.gather(*callers, return_exceptions=True))
    assert sorted(calls) == [5, 10, 15, 20]


@pytest.mark.asyncio
async def test_cancelled_waiters_do_not_release_running_thread_permits(market_state):
    release = threading.Event()
    started_two = asyncio.Event()
    third_started = asyncio.Event()
    loop = asyncio.get_running_loop()
    calls = []
    lock = threading.Lock()
    def provider(index):
        with lock:
            calls.append(index)
            if len(calls) == 2:
                loop.call_soon_threadsafe(started_two.set)
            if index == 3:
                loop.call_soon_threadsafe(third_started.set)
        release.wait(5)
        return index
    first = [asyncio.create_task(market._run_provider(provider, n)) for n in (1, 2)]
    third = None
    try:
        await completed(started_two.wait())
        for task in first:
            task.cancel()
        await asyncio.gather(*first, return_exceptions=True)
        third = asyncio.create_task(market._run_provider(provider, 3))
        # Pump the event loop so the third job has a chance to violate the bound.
        await asyncio.sleep(.03)
        assert not third_started.is_set()
        assert len(market._provider_jobs) == 2
    finally:
        release.set()
        if third is not None:
            assert await completed(third) == 3
        jobs = list(market._provider_jobs)
        if jobs:
            await completed(asyncio.gather(*(asyncio.wrap_future(job) for job in jobs), return_exceptions=True))


@pytest.mark.asyncio
async def test_market_shutdown_cancels_owned_async_work_without_claiming_thread_termination(market_state, monkeypatch):
    release = threading.Event()
    started = asyncio.Event()
    loop = asyncio.get_running_loop()
    def history(*args):
        loop.call_soon_threadsafe(started.set)
        release.wait(5)
        return {"fixture": [{"date": "2026-01-01", "close": 1}]}
    monkeypatch.setattr(market, "_fetch_history_sync", history)
    caller = asyncio.create_task(market.get_market_history(30))
    try:
        await completed(started.wait())
        tasks = set(market._history_tasks.values())
        jobs = set(market._provider_jobs)
        await completed(market.stop_market())
        await completed(asyncio.gather(caller, return_exceptions=True))
        assert all(task.done() for task in tasks)
        assert not market._history_tasks and market._quote_task is None
        assert (await market.get_market_history(30))["status"] == "disabled"
        assert jobs and any(not job.done() for job in jobs)
    finally:
        release.set()
        if market._provider_jobs:
            await completed(asyncio.gather(*(asyncio.wrap_future(job) for job in list(market._provider_jobs)), return_exceptions=True))


def test_new_lifespan_does_not_rebind_an_old_loop_semaphore_or_overbook_threads(monkeypatch):
    release = threading.Event()
    calls = []
    lock = threading.Lock()
    monkeypatch.setattr(market, "_provider_jobs", set())
    monkeypatch.setattr(market, "_provider_slots", asyncio.Semaphore(2))
    monkeypatch.setattr(market, "_stopping", False)
    monkeypatch.setattr(market, "_executor", None)
    def provider(index):
        with lock:
            calls.append(index)
        release.wait(5)
        return index
    async def first_lifespan():
        market.start_market()
        callers = [asyncio.create_task(market._run_provider(provider, n)) for n in (1, 2, 3)]
        while len(calls) < 2:
            await asyncio.sleep(.001)
        for task in callers:
            task.cancel()
        await asyncio.gather(*callers, return_exceptions=True)
        await market.stop_market()
    async def second_lifespan():
        market.start_market()
        next_job = asyncio.create_task(market._run_provider(provider, 4))
        try:
            await asyncio.sleep(.03)
            assert calls == [1, 2]
        finally:
            release.set()
        assert await completed(next_job) == 4
        await market.stop_market()
    try:
        asyncio.run(first_lifespan())
        asyncio.run(second_lifespan())
    finally:
        release.set()




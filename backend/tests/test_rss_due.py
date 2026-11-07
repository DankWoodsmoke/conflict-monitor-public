"""Due-time recovery, with in-memory ledger/queue and mocked publisher HTTP."""
import asyncio
import copy
from datetime import timedelta, timezone, datetime
import httpx
import pytest
from unittest.mock import AsyncMock
from app.services import news_feeds as rss
from app.services.ingest_ledger import report_identity
from test_free_rss import free, ingest, STAMP, TITLE, FEED, xml

@pytest.mark.asyncio
async def test_due_original_retries_once_preserving_raw_hash_clock_and_identity(free, monkeypatch):
    due = STAMP + timedelta(hours=2)
    assert await ingest(stamp=due) == "future_source_time"
    identity, stored = next(iter(free.ledger.records.items()))
    preserved = copy.deepcopy(stored)
    monkeypatch.setattr(rss, "_clock", lambda: due)
    assert await ingest(stamp=due) == "reported"
    assert await ingest(stamp=due) == "duplicate"
    assert len(free.ledger.records) == len(free.store.events) == 1
    assert stored["report"] == preserved["report"]
    assert stored["content_hash"] == preserved["content_hash"]
    assert report_identity(stored["report"])[0] == identity
    assert free.store.events[0].timestamp == due
    assert free.store.events[0].raw_text == preserved["report"]["raw_text"]
    assert free.broadcast.await_count == 1
    free.forbidden.assert_not_awaited()

@pytest.mark.asyncio
async def test_not_yet_due_is_skipped_without_processing_quota(free, monkeypatch):
    due = STAMP + timedelta(hours=2)
    assert await ingest(stamp=due) == "future_source_time"
    report = next(iter(free.ledger.records.values()))["report"]
    identity = report_identity(report)[0]
    monkeypatch.setattr(rss, "_clock", lambda: due - timedelta(seconds=1))
    assert await rss._terminal_identities([report]) == {identity}
    process = AsyncMock(side_effect=AssertionError("not-yet-due work must not use quota"))
    monkeypatch.setattr(rss, "_process_article", process)
    document = f"<rss><channel><item><title>{TITLE}</title><link>{report['source_url']}</link><description>Publisher-provided excerpt.</description><pubDate>Wed, 28 Oct 2026 14:00:00 GMT</pubDate></item></channel></rss>"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=document))) as client:
        assert await rss._poll_feed(FEED, client, max_items=1) == 0
    process.assert_not_awaited()
    assert not free.store.events
    assert rss._feed_health[FEED["source"]]["skipped_terminal_items"] == 1

@pytest.mark.asyncio
async def test_due_retries_respect_shared_quota_then_remaining_work_proceeds(free, monkeypatch):
    due = STAMP + timedelta(hours=2)
    articles = []
    for i in range(3):
        url = f"https://example.org/due/{i}"
        assert await ingest(url=url, stamp=due) == "future_source_time"
        articles.append({"title": TITLE, "description": "Publisher-provided excerpt.", "url": url, "published": due})
    monkeypatch.setattr(rss, "_clock", lambda: due)
    # Passing fetched still requires the same per-attempt state initialized by
    # the actual fetch path; use a synthetic XML HTTP response for both cycles.
    document = "<rss><channel>" + "".join(f"<item><title>{TITLE}</title><link>{a['url']}</link><description>Publisher-provided excerpt.</description><pubDate>Wed, 28 Oct 2026 14:00:00 GMT</pubDate></item>" for a in articles) + "</channel></rss>"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200,text=document))) as client:
        assert await rss._poll_feed(FEED, client, max_items=2) == 2
        assert len(free.store.events) == 2
        assert sum(r["status"] == "future_source_time" for r in free.ledger.records.values()) == 1
        assert await rss._poll_feed(FEED, client, max_items=2) == 1
    assert len(free.store.events) == 3
    assert free.broadcast.await_count == 3
    free.forbidden.assert_not_awaited()

@pytest.mark.asyncio
async def test_due_receipt_cannot_resume_without_owned_lock(free, monkeypatch):
    due = STAMP + timedelta(hours=2)
    assert await ingest(stamp=due) == "future_source_time"
    report = next(iter(free.ledger.records.values()))["report"]
    monkeypatch.setattr(rss, "_clock", lambda: due)
    assert rss._owned_receipt.get() is None
    assert await rss._capture_rss_report(report) == (None, "pending_receipt", None)
    assert not free.store.events

@pytest.mark.asyncio
async def test_corrected_input_clock_does_not_overwrite_retained_original(free, monkeypatch):
    due = STAMP + timedelta(hours=2)
    assert await ingest(stamp=due) == "future_source_time"
    stored = next(iter(free.ledger.records.values()))
    original = copy.deepcopy(stored["report"])
    assert await ingest(stamp=STAMP) == "future_source_time"
    assert not free.store.events and stored["report"] == original
    monkeypatch.setattr(rss, "_clock", lambda: due)
    assert await ingest(stamp=STAMP) == "reported"
    assert free.store.events[0].timestamp == due
    assert stored["report"] == original
    # Clock-correction capture/review remains a separate unapplied design.
    assert len(free.ledger.records) == 1

@pytest.mark.asyncio
async def test_model_mode_remains_terminal_no_implicit_provider_retry(free, monkeypatch):
    due = STAMP + timedelta(hours=2)
    assert await ingest(stamp=due) == "future_source_time"
    report = next(iter(free.ledger.records.values()))["report"]
    monkeypatch.setattr(rss, "_clock", lambda: due)
    monkeypatch.setattr(rss.settings, "rss_processing_mode", "model")
    assert await rss._terminal_identities([report]) == {report_identity(report)[0]}
    assert await rss._capture_rss_report(report) == (None, "duplicate", None)
    free.forbidden.assert_not_awaited()

@pytest.mark.parametrize("stamp", [None, "invalid", "2026-10-28T12:00:00", "999999-01-01T00:00:00Z"])
def test_malformed_original_clock_is_not_due(free, stamp):
    assert not rss._future_receipt_due({"timestamp": stamp})

@pytest.mark.asyncio
async def test_changed_body_cannot_be_resumed_under_original_identity(free, monkeypatch):
    due = STAMP + timedelta(hours=2)
    assert await ingest(stamp=due) == "future_source_time"
    identity, stored = next(iter(free.ledger.records.items()))
    original = copy.deepcopy(stored["report"])
    monkeypatch.setattr(rss, "_clock", lambda: due)
    stored["report"]["raw_text"] += " corrupted fixture"
    with pytest.raises(ValueError, match="source identity"):
        await ingest(stamp=due)
    assert not free.store.events


async def queued(free, monkeypatch):
    due = STAMP + timedelta(hours=2)
    assert await ingest(stamp=due) == "future_source_time"
    identity, row = next(iter(free.ledger.records.items()))
    item = rss.rss_retries.RetryItem(identity, "fixture-token", "bbc_mideast", due, 1,
                                    copy.deepcopy(row["report"]), row["content_hash"])
    monkeypatch.setattr(rss, "_clock", lambda: due)
    claim = AsyncMock(return_value=[item])
    finish = AsyncMock(return_value=True)
    monkeypatch.setattr(rss.rss_retries, "claim_due", claim)
    monkeypatch.setattr(rss.rss_retries, "finish_attempt", finish)
    return item, claim, finish


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status", [200, 403])
async def test_removed_item_replays_from_queue_with_empty_or_failed_feed(free, monkeypatch, http_status):
    item, claim, finish = await queued(free, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(http_status, text="<rss><channel/></rss>"))) as client:
        assert await rss._poll_feed(FEED, client, max_items=4) == 1
    assert len(free.store.events) == 1
    assert free.store.events[0].raw_text == item.report["raw_text"]
    assert free.store.events[0].timestamp == item.due_at
    assert finish.await_args.args[1] == "reported"
    assert rss._feed_health[FEED["source"]]["retry_outcomes"] == {"reported": 1}
    free.forbidden.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_and_new_work_share_single_feed_budget(free, monkeypatch):
    _, claim, finish = await queued(free, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, text=xml(5)))) as client:
        assert await rss._poll_feed(FEED, client, max_items=2) == 2
    assert len(free.store.events) == 2
    assert claim.await_args.args[1] == 1
    assert rss._feed_health[FEED["source"]]["attempted_items"] == 2


@pytest.mark.asyncio
async def test_one_item_quota_alternates_backlog_and_new_source_work(free, monkeypatch):
    _, claim, finish = await queued(free, monkeypatch)
    monkeypatch.setattr(rss, "_retry_one_item_turn", {"bbc_mideast": False})
    # Real claim helper returns no rows for zero quota; fixture respects that.
    claim.return_value = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, text=xml(2)))) as client:
        assert await rss._poll_feed(FEED, client, max_items=1) == 1
    assert claim.await_args.args[1] == 0
    finish.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_retry_leaves_claim_for_durable_expiry(free, monkeypatch):
    _, claim, finish = await queued(free, monkeypatch)
    entered = asyncio.Event()
    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(rss, "_process_retained_future", blocked)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, text="<rss><channel/></rss>"))) as client:
        task = asyncio.create_task(rss._poll_feed(FEED, client, max_items=4))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finish.assert_not_awaited()
    assert not free.store.events


@pytest.mark.asyncio
async def test_failed_retry_is_acknowledged_as_failure_not_success(free, monkeypatch):
    _, claim, finish = await queued(free, monkeypatch)
    monkeypatch.setattr(rss, "_process_retained_future", AsyncMock(side_effect=TimeoutError()))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, text="<rss><channel/></rss>"))) as client:
        assert await rss._poll_feed(FEED, client, max_items=4) == 1
    assert finish.await_args.args[1] == "retryable_error"
    assert finish.await_args.args[3] == "TimeoutError"
    assert not free.store.events


@pytest.mark.asyncio
async def test_unknown_or_wrong_channel_snapshot_never_publishes(free, monkeypatch):
    item, _, _ = await queued(free, monkeypatch)
    assert await rss._process_retained_future(item, {**FEED, "source": "other"}) == "invalid_retry_source"
    item.report["processing_mode"] = "unknown"
    assert await rss._process_retained_future(item, FEED) == "invalid_retry_source"
    assert not free.store.events


@pytest.mark.parametrize("stamp", ["2026-02-30T12:00:00Z", "2026-01-01T24:00:00Z", "2026-01-01T23:59:60Z", "0000-01-01T00:00:00Z", "2026-01-01T00:00:00+15:00"])
def test_clock_parser_rejects_noncanonical_or_invalid_calendar_time(stamp):
    assert rss.rss_retries.parse_source_clock(stamp) is None


@pytest.mark.parametrize("stamp", ["2024-02-29T12:00:00Z", "2026-01-01T00:00:00.123456+14:00", "2026-01-01T00:00:00-13:59"])
def test_clock_parser_preserves_explicit_offset_instant(stamp):
    assert rss.rss_retries.parse_source_clock(stamp) == datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)

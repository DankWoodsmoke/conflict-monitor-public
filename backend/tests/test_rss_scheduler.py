"""Fair ingestion, durable recovery and connector failure boundaries."""
import asyncio
import copy
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import news_feeds as rss
from test_free_rss import FEED, STAMP, TITLE, free, ingest, xml  # noqa: F401 - fixture import


@pytest.fixture
def schedule(monkeypatch):
    for name, value in {"rss_max_items_per_feed":5, "rss_max_ingest_per_cycle":200,
        "rss_relevance_mode":"selected_sources", "rss_processing_mode":"reports",
        "rss_poll_interval_seconds":60}.items():
        monkeypatch.setattr(rss.settings, name, value)
    monkeypatch.setattr(rss, "_feed_health", {})
    monkeypatch.setattr(rss, "_cycle_status", {})
    monkeypatch.setattr(rss, "_poll_cursor", 0)


def test_catalog_defaults_and_candidate_admission_are_explicit(monkeypatch):
    assert len(rss.FEEDS) == 34
    monkeypatch.setattr(rss.settings, "rss_sources", "")
    admitted = rss.configured_feeds()
    assert len(admitted) == 31
    assert not {"who_news_candidate", "un_news_candidate", "lyn_alden_candidate"} & {row["source"] for row in admitted}
    monkeypatch.setattr(rss.settings, "rss_sources", "un_news_candidate,who_news_candidate")
    assert len(rss.configured_feeds()) == 2
    assert all(row["reliability"] is None for row in rss.FEEDS[16:])
    assert all(row["role"] and row["prior_status"] for row in rss.FEEDS)


@pytest.mark.parametrize("count", [1, 3, 31, 34])
@pytest.mark.parametrize("global_limit", [1, 2, 17, 200, 500])
def test_reserved_quotas_obey_global_per_feed_and_fair_remainder(count, global_limit):
    quotas = rss._feed_quotas(count, 5, global_limit)
    assert len(quotas) == count
    assert sum(quotas) == min(global_limit, count * 5)
    assert all(0 <= quota <= 5 for quota in quotas)
    assert max(quotas) - min(quotas) <= 1


@pytest.mark.asyncio
async def test_slow_fetch_does_not_delay_fast_ingestion_and_processing_is_serial(schedule, monkeypatch):
    feeds = [{**FEED, "source": name} for name in ("slow", "fast", "third", "fourth", "fifth")]
    release = asyncio.Event()
    fast_saved = asyncio.Event()
    active_fetches = active_processors = peak_fetches = peak_processors = 0
    async def read(feed, client):
        nonlocal active_fetches, peak_fetches
        active_fetches += 1
        peak_fetches = max(peak_fetches, active_fetches)
        try:
            if feed["source"] == "slow":
                await release.wait()
            else:
                await asyncio.sleep(.01)
            return xml(3).encode(), {"http_status":200}
        finally:
            active_fetches -= 1
    async def process(*args, **kwargs):
        nonlocal active_processors, peak_processors
        active_processors += 1
        peak_processors = max(peak_processors, active_processors)
        try:
            await asyncio.sleep(.005)
            if args[4] == "fast":
                fast_saved.set()
            return "reported"
        finally:
            active_processors -= 1
    monkeypatch.setattr(rss, "configured_feeds", lambda:feeds)
    monkeypatch.setattr(rss, "_read_feed_response", read)
    monkeypatch.setattr(rss, "_terminal_identities", AsyncMock(return_value=set()))
    monkeypatch.setattr(rss, "_process_article", process)
    task = asyncio.create_task(rss.poll_news_once())
    try:
        await asyncio.wait_for(fast_saved.wait(), 1)
        assert not task.done()
        assert peak_fetches <= 4 and peak_processors == 1
    finally:
        release.set()
        await task
    assert rss._cycle_status["attempted_items"] == 15
    assert rss._cycle_status["classifier_invocations_upper_bound"] == 0


@pytest.mark.asyncio
async def test_small_global_budget_is_reserved_fairly_independent_of_fetch_speed(schedule, monkeypatch):
    monkeypatch.setattr(rss.settings, "rss_max_ingest_per_cycle", 2)
    feeds = [{**FEED,"source":str(i)} for i in range(3)]
    async def read(feed, client):
        await asyncio.sleep(.01 if feed["source"] == "0" else 0)
        return xml(8).encode(), {"http_status":200}
    process = AsyncMock(return_value="reported")
    monkeypatch.setattr(rss, "configured_feeds", lambda:feeds)
    monkeypatch.setattr(rss, "_read_feed_response", read)
    monkeypatch.setattr(rss, "_terminal_identities", AsyncMock(return_value=set()))
    monkeypatch.setattr(rss, "_process_article", process)
    observed=[]
    for _ in range(3):
        start=process.await_count
        await rss.poll_news_once()
        observed.append({call.args[4] for call in process.await_args_list[start:]})
        assert rss._cycle_status["attempted_items"] == 2
    assert observed == [{"0","1"},{"1","2"},{"0","2"}]


@pytest.mark.asyncio
async def test_terminal_duplicate_prefix_does_not_consume_new_processing_quota(free, monkeypatch):
    monkeypatch.setattr(rss.settings, "rss_max_items_per_feed", 1)
    for article in rss._parse_rss(xml(20)):
        await rss._process_article(article["title"],article["description"],article["url"],article["published"],"bbc_mideast",4)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=xml(21)))) as client:
        assert await rss._poll_feed(FEED,client,max_items=1) == 1
    assert len(free.store.events) == 21
    assert rss._feed_health["bbc_mideast"]["skipped_terminal_items"] == 20
    assert rss._feed_health["bbc_mideast"]["attempted_items"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["received","pending_receipt","retryable_error","provider_error"])
async def test_interrupted_receipt_resumes_without_mutating_source_content(free,status):
    report=rss._rss_report(TITLE,"Publisher-provided excerpt.","https://example.org/report",STAMP,"bbc_mideast")
    identity=await free.ledger.capture(report)
    free.ledger.records[identity]["status"]=status
    original=copy.deepcopy(free.ledger.records[identity]["report"])
    assert await ingest() == "reported"
    assert free.ledger.records[identity]["report"] == original
    assert len(free.store.events) == 1


@pytest.mark.asyncio
async def test_resume_uses_original_publication_clock_not_new_retrieval_metadata(free):
    report=rss._rss_report(TITLE,"Publisher-provided excerpt.","https://example.org/report",STAMP,"bbc_mideast")
    await free.ledger.capture(report)
    assert await ingest(stamp=STAMP+timedelta(minutes=30)) == "reported"
    assert free.store.events[0].timestamp == STAMP
    assert free.store.events[0].reports[0]["published_at"] == STAMP.isoformat()


@pytest.mark.asyncio
@pytest.mark.parametrize("original_clock,expected",[(None,"undated_source"),(STAMP+timedelta(days=1),"future_source_time")])
async def test_refetch_cannot_repair_interrupted_unknown_or_future_original_clock(free,original_clock,expected):
    report=rss._rss_report(TITLE,"Publisher-provided excerpt.","https://example.org/report",original_clock,"bbc_mideast")
    await free.ledger.capture(report)
    assert await ingest(stamp=STAMP) == expected
    assert not free.store.events


@pytest.mark.asyncio
async def test_unknown_receipt_is_pending_not_terminal_or_republished(free):
    report=rss._rss_report(TITLE,"Publisher-provided excerpt.","https://example.org/report",STAMP,"bbc_mideast")
    identity=await free.ledger.capture(report)
    free.ledger.records[identity]["status"]="awaiting_operator"
    assert await ingest() == "pending_receipt"
    assert free.ledger.records[identity]["status"] == "awaiting_operator"
    assert not free.store.events


@pytest.mark.asyncio
async def test_event_commit_before_ledger_finish_recovers_same_event_once(free,monkeypatch):
    original_finish=free.ledger.finish
    failed=False
    async def finish(identity,status,event_id=None):
        nonlocal failed
        if status == "reported" and not failed:
            failed=True
            raise RuntimeError("fixture commit-before-ledger-finish interruption")
        await original_finish(identity,status,event_id)
    monkeypatch.setattr(rss,"finish_report",finish)
    with pytest.raises(RuntimeError):
        await ingest()
    assert len(free.store.events) == 1
    assert next(iter(free.ledger.records.values()))["status"] == "retryable_error"
    assert await ingest() == "recovered"
    assert len(free.store.events) == 1 and free.broadcast.await_count == 1
    assert next(iter(free.ledger.records.values()))["status"] == "reported"


@pytest.mark.asyncio
async def test_changed_body_after_interruption_is_retained_for_review(free):
    assert await ingest() == "reported"
    report=rss._rss_report(TITLE,"Changed source body.","https://example.org/report",STAMP,"bbc_mideast")
    identity=await free.ledger.capture(report)
    assert await ingest(desc="Changed source body.") == "source_revision_needs_review"
    assert free.ledger.records[identity]["status"] == "source_revision_needs_review"
    assert len(free.store.events) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,relevance,expected",[("reports","selected_sources",1),("reports","keywords",0),("model","selected_sources",0)])
async def test_all_selected_source_preservation_is_explicit_and_free_only(schedule,monkeypatch,mode,relevance,expected):
    monkeypatch.setattr(rss.settings,"rss_processing_mode",mode)
    monkeypatch.setattr(rss.settings,"rss_relevance_mode",relevance)
    async def read(*args):
        return xml().replace(TITLE,"تحديث عام عن المكتبة").encode(), {"http_status":200}
    monkeypatch.setattr(rss,"_read_feed_response",read)
    monkeypatch.setattr(rss,"_terminal_identities",AsyncMock(return_value=set()))
    process=AsyncMock(return_value="reported")
    monkeypatch.setattr(rss,"_process_article",process)
    async with httpx.AsyncClient() as client:
        assert await rss._poll_feed(FEED,client) == expected
    assert process.await_count == expected


@pytest.mark.asyncio
async def test_retry_after_backoff_is_bounded_and_recovers_without_fake_source_clock(free,monkeypatch):
    calls=0
    now=[STAMP+timedelta(hours=1)]
    monkeypatch.setattr(rss,"_clock",lambda:now[0])
    def response(request):
        nonlocal calls
        calls+=1
        return httpx.Response(429,headers={"retry-after":"999999"}) if calls == 1 else httpx.Response(200,text=xml())
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        assert await rss._poll_feed(FEED,client) == 0
        assert rss._feed_health["bbc_mideast"]["next_attempt_at"] == now[0]+timedelta(hours=1)
        await rss._poll_feed(FEED,client)
        assert calls == 1 and rss._feed_health["bbc_mideast"]["backoff_active"]
        now[0]+=timedelta(hours=1)
        assert await rss._poll_feed(FEED,client) == 1
    assert rss._feed_health["bbc_mideast"]["last_published_at"] == STAMP
    assert rss._feed_health["bbc_mideast"]["consecutive_failures"] == 0


def test_parser_item_limit_is_a_failed_feed_not_silent_partial_success():
    assert len(rss._parse_rss(xml(1000))) == 1000
    with pytest.raises(ValueError,match="item count"):
        rss._parse_rss(xml(1001))


@pytest.mark.asyncio
async def test_no_conditional_headers_can_hide_unprocessed_items(schedule,monkeypatch):
    observed=[]
    def response(request):
        observed.append(dict(request.headers))
        return httpx.Response(200,text=xml(),headers={"etag":'"fixture-validator"',"last-modified":"Wed, 28 Oct 2026 12:00:00 GMT"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        await rss._read_feed_bytes(FEED,client)
        await rss._read_feed_bytes(FEED,client)
    assert all("if-none-match" not in headers and "if-modified-since" not in headers for headers in observed)


@pytest.mark.asyncio
async def test_future_source_clock_stays_quarantined_across_successful_refetches(free):
    body=xml().replace("Wed, 28 Oct 2026 12:00:00 GMT","Thu, 29 Oct 2026 12:00:00 GMT")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=body))) as client:
        assert await rss._poll_feed(FEED,client) == 1
        assert await rss._poll_feed(FEED,client) == 0
    state=rss.get_feed_status()["feeds"][0]
    assert state["publication_in_future"] is True
    assert state["last_published_at"].startswith("2026-10-29T12:00:00")
    assert not free.store.events
    assert next(iter(free.ledger.records.values()))["status"] == "future_source_time"


@pytest.mark.asyncio
async def test_cancelled_processing_leaves_received_source_resumable(free,monkeypatch):
    captured=asyncio.Event()
    original=rss._process_article_unlocked
    async def interrupted(title,description,url,published,source,reliability,**kwargs):
        await rss._capture_rss_report(rss._rss_report(title,description,url,published,source))
        captured.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(rss,"_process_article_unlocked",interrupted)
    task=asyncio.create_task(ingest())
    await captured.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert next(iter(free.ledger.records.values()))["status"] == "received"
    assert not free.store.events
    monkeypatch.setattr(rss,"_process_article_unlocked",original)
    assert await ingest() == "reported"


@pytest.mark.asyncio
async def test_cancelling_cycle_reaps_all_owned_fetch_tasks(schedule,monkeypatch):
    started=asyncio.Event()
    active=0
    async def read(*args):
        nonlocal active
        active+=1
        if active==4:
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active-=1
    monkeypatch.setattr(rss,"configured_feeds",lambda:[{**FEED,"source":str(i)} for i in range(8)])
    monkeypatch.setattr(rss,"_read_feed_response",read)
    task=asyncio.create_task(rss.poll_news_once())
    await asyncio.wait_for(started.wait(),1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert active == 0

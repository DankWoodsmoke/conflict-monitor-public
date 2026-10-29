"""Actual free-report handler and HTTP parser behavior; no paid providers."""
import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import news_feeds as rss
from test_ingestion_integration import EventStore, Ledger

STAMP = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
TITLE = "Iran officials announce a new round of diplomatic talks"
FEED = {"source":"bbc_mideast", "url":"https://feeds.example.test/rss", "reliability":4}


@pytest.fixture
def free(monkeypatch):
    order = []
    store = EventStore()
    ledger = Ledger(order)
    store.ledger = ledger
    monkeypatch.setattr(rss.settings, "rss_processing_mode", "reports")
    monkeypatch.setattr(rss.settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(rss.settings, "rss_sources", "bbc_mideast")
    monkeypatch.setattr(rss, "_feed_health", {})
    monkeypatch.setattr(rss, "_clock", lambda: STAMP + timedelta(hours=1))
    monkeypatch.setattr(rss, "capture_report", ledger.capture)
    monkeypatch.setattr(rss, "finish_report", ledger.finish)
    monkeypatch.setattr(rss, "async_session", store.session)
    forbidden = AsyncMock(side_effect=AssertionError("Free reports must not invoke paid or inferred enrichment"))
    monkeypatch.setattr(rss, "classify_message", forbidden)
    monkeypatch.setattr(rss, "geocode", forbidden)
    monkeypatch.setattr(rss, "analyze_anomaly", forbidden)
    broadcast = AsyncMock()
    monkeypatch.setattr(rss.broadcaster, "broadcast", broadcast)
    return SimpleNamespace(store=store, ledger=ledger, forbidden=forbidden, broadcast=broadcast)


async def ingest(title=TITLE, desc="Publisher-provided excerpt.", url="https://example.org/report", stamp=STAMP):
    return await rss._process_article(title, desc, url, stamp, "bbc_mideast", 4)


@pytest.mark.asyncio
async def test_free_report_preserves_publisher_headline_and_unscored_unknowns(free):
    assert await ingest() == "reported"
    assert len(free.store.events) == 1
    event = free.store.events[0]
    assert event.summary == TITLE
    assert event.event_type == "unclassified" and event.severity == 0
    assert event.classification_status == "not_requested"
    assert event.lat is None and event.lon is None and event.geometry is None
    assert event.location_name == "" and event.geolocation_precision == "unknown"
    assert event.reports[0]["content_sha256"] and event.reports[0]["raw_text"].startswith(TITLE)
    assert event.source_reliability == 4  # editorial prior, not factual confidence
    assert next(iter(free.ledger.records.values()))["status"] == "reported"
    free.forbidden.assert_not_awaited()
    assert '"classification_status":"not_requested"' in free.broadcast.await_args.args[0]
    assert '"verification_basis":"none"' in free.broadcast.await_args.args[0]


@pytest.mark.asyncio
async def test_replay_is_idempotent_but_revision_is_preserved(free):
    assert await ingest() == "reported"
    assert await ingest() == "duplicate"
    assert await ingest(desc="Correction to the publisher's earlier excerpt.") == "source_revision_needs_review"
    assert len(free.store.events) == 1 and len(free.ledger.records) == 2
    assert free.broadcast.await_count == 1


@pytest.mark.asyncio
async def test_distinct_source_urls_are_not_auto_clustered(free):
    assert await ingest() == "reported"
    assert await ingest(url="https://example.org/other-report") == "reported"
    assert len(free.store.events) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stamp,status", [(None,"undated_source"),
    (datetime(2026,10,28,12),"undated_source"),
    (STAMP+timedelta(days=1),"future_source_time")])
async def test_bad_source_clock_has_receipt_but_no_current_event(free, stamp, status):
    assert await ingest(stamp=stamp) == status
    assert not free.store.events
    assert next(iter(free.ledger.records.values()))["status"] == status
    free.forbidden.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_source_link_is_not_published(free):
    assert await ingest(url="javascript:alert(1)") == "invalid_source_metadata"
    assert not free.store.events and free.ledger.records


@pytest.mark.asyncio
async def test_oversized_report_retains_explicit_truncated_failure_receipt(free):
    assert await ingest(desc="x"*13000) == "input_too_large"
    receipt = next(iter(free.ledger.records.values()))
    assert receipt["report"]["raw_text_truncated"] is True
    assert receipt["report"]["original_text_sha256"]
    assert len(receipt["report"]["raw_text"]) == 12000
    assert not free.store.events


def xml(items=1, dated=True):
    stamp = "<pubDate>Wed, 28 Oct 2026 12:00:00 GMT</pubDate>" if dated else ""
    return "<rss><channel>" + "".join(f"<item><title>{TITLE} {i}</title><link>https://example.org/report/{i}</link><description>Publisher excerpt</description>{stamp}</item>" for i in range(items)) + "</channel></rss>"


@pytest.mark.asyncio
async def test_streamed_feed_budget_and_health_clock(free, monkeypatch):
    monkeypatch.setattr(rss.settings,"rss_max_items_per_feed",2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=xml(5)))) as client:
        assert await rss._poll_feed(FEED,client,max_items=1) == 1
    assert len(free.store.events) == 1
    state = rss.get_feed_status()["feeds"][0]
    assert state["status"] == "ok" and state["parsed_items"] == 5
    assert state["attempted_items"] == 1 and state["published_items"] == 1
    assert state["cache_age_seconds"] == 0
    assert state["publication_age_seconds"] == 3600
    context = free.store.events[0].reports[0]["feed_context"]
    assert context["feed_url"] == FEED["url"]
    assert len(context["feed_content_sha256"]) == 64
    assert context["retrieved_at"] == state["last_success_at"]


@pytest.mark.asyncio
@pytest.mark.parametrize("body,status", [("<rss><channel/></rss>","empty"),
    ("not xml","failed"), ("<html><body>Denied</body></html>","failed"),
    ('<!DOCTYPE rss [<!ENTITY secret "injected">]><rss><channel>&secret;</channel></rss>',"failed")])
async def test_empty_failed_and_unsafe_feeds_remain_distinct(free, body, status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=body))) as client:
        await rss._poll_feed(FEED,client)
    state = rss.get_feed_status()["feeds"][0]
    assert state["status"] == status
    assert state.get("error_type") is not None if status=="failed" else state["last_success_at"] is not None
    assert not free.store.events


@pytest.mark.asyncio
async def test_failed_fetch_keeps_last_success_and_source_clock(free):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=xml()))) as client:
        await rss._poll_feed(FEED,client)
    previous=copy.deepcopy(rss.get_feed_status()["feeds"][0])
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(429,text="limit"))) as client:
        await rss._poll_feed(FEED,client)
    state=rss.get_feed_status()["feeds"][0]
    assert state["status"] == "failed" and state["error_type"] == "HTTPStatusError"
    assert state["last_success_at"] == previous["last_success_at"]
    assert state["last_published_at"] == previous["last_published_at"]


@pytest.mark.asyncio
async def test_declared_and_actual_response_byte_limits(free, monkeypatch):
    monkeypatch.setattr(rss.settings,"rss_max_response_bytes",1024)
    for headers in ({"content-length":"5000"},{}):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b"x"*2048,headers=headers))) as client:
            await rss._poll_feed(FEED,client)
        assert rss.get_feed_status()["feeds"][0]["status"] == "failed"
    assert not free.store.events


def test_health_can_be_disabled_stale_and_misconfigured(free, monkeypatch):
    rss._feed_health["bbc_mideast"]={"status":"ok","last_success_at":STAMP-timedelta(hours=2),"last_published_at":STAMP-timedelta(days=2)}
    state=rss.get_feed_status()["feeds"][0]
    assert state["status"] == "stale" and state["publication_stale"] is True
    monkeypatch.setattr(rss.settings,"live_ingestion_enabled",False)
    assert rss.get_feed_status()["feeds"][0]["status"] == "disabled"
    monkeypatch.setattr(rss.settings,"rss_sources","not-a-provider")
    assert rss.get_feed_status()["status"] == "misconfigured"


def test_declared_non_utf8_feed_encoding_preserves_headline():
    body = '<?xml version="1.0" encoding="ISO-8859-1"?><rss><channel><item><title>Iran diplomatie café</title><link>https://example.org/source</link></item></channel></rss>'.encode("iso-8859-1")
    assert rss._parse_rss(body)[0]["title"] == "Iran diplomatie café"

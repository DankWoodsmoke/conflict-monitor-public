from unittest.mock import Mock

import pytest

from app.services import news_feeds as subject


@pytest.mark.asyncio
@pytest.mark.parametrize("live,demo,x_opt_in", [(False, False, True), (True, True, True), (True, False, False)])
async def test_paid_x_background_entrypoint_obeys_opt_in_even_when_old_bearer_exists(monkeypatch, live, demo, x_opt_in):
    monkeypatch.setenv("TWITTER_BEARER_TOKEN", "fixture-unused-bearer")
    for key, value in {"live_ingestion_enabled": live, "demo_mode": demo, "x_ingestion_enabled": x_opt_in}.items():
        monkeypatch.setattr(subject.settings, key, value)
    constructor = Mock(side_effect=AssertionError("Opted-out X attempted provider allocation"))
    monkeypatch.setattr(subject.httpx, "AsyncClient", constructor)
    await subject.start_x_poller()
    constructor.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("live,demo", [(False, False), (True, True)])
async def test_rss_background_entrypoint_cannot_collect_real_reports_in_disabled_or_demo_mode(monkeypatch, live, demo):
    monkeypatch.setattr(subject.settings, "live_ingestion_enabled", live)
    monkeypatch.setattr(subject.settings, "demo_mode", demo)
    constructor = Mock(side_effect=AssertionError("Disabled RSS attempted provider allocation"))
    monkeypatch.setattr(subject.httpx, "AsyncClient", constructor)
    await subject.start_news_feed_poller()
    constructor.assert_not_called()


@pytest.mark.asyncio
async def test_round_robin_feed_budget_cannot_starve_later_configured_publishers(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    feeds = [{"source": name} for name in ("one", "two", "three")]
    calls = []
    async def poll(feed, client, *, max_items, fetch_semaphore, processing_lock):
        calls.append((feed["source"], max_items))
        return min(2, max_items)
    monkeypatch.setattr(subject.settings, "rss_max_ingest_per_cycle", 3)
    monkeypatch.setattr(subject, "_poll_cursor", 1)
    monkeypatch.setattr(subject, "configured_feeds", lambda: feeds)
    monkeypatch.setattr(subject, "get_feed_status", lambda: {"scope": "test metadata"})
    monkeypatch.setattr(subject.httpx, "AsyncClient", Client)
    monkeypatch.setattr(subject, "_poll_feed", poll)
    for expected in (["two", "three", "one"], ["three", "one", "two"], ["one", "two", "three"]):
        before = len(calls)
        assert await subject.poll_news_once() == {"scope": "test metadata"}
        assert calls[before:] == [(name, 1) for name in expected]


def test_atom_publisher_article_link_is_preferred_over_feed_self_representation():
    xml = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title>Attributed report — وصول المساعدات</title><summary>Original publisher summary</summary>
      <link rel="self" type="application/atom+xml" href="https://example.invalid/api/entry/12"/>
      <link rel="alternate" type="text/html" href="https://example.invalid/article/12"/>
      <published>2026-10-28T12:34:00Z</published></entry></feed>'''
    row, = subject._parse_rss(xml)
    assert row["url"] == "https://example.invalid/article/12"
    assert row["title"].endswith("وصول المساعدات")
    assert row["published"].utcoffset().total_seconds() == 0


def test_atom_missing_publication_uses_explicit_updated_clock_and_invalid_publication_stays_unknown():
    xml = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Attributed report</title>
      <link href="https://example.invalid/article/12"/><updated>2026-10-28T12:34:00+03:00</updated>
      </entry></feed>'''
    row, = subject._parse_rss(xml)
    assert row["published"].utcoffset().total_seconds() == 3 * 3600
    assert row["source_time_basis"] == "source_updated_time"
    invalid = xml.replace("<updated>", "<published>invalid</published><updated>")
    assert subject._parse_rss(invalid)[0]["published"] is None

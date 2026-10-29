"""Exercise actual Telegram/RSS handlers with in-memory persistence substitutes.

No HTTP/Telegram/model/PostgreSQL calls. SQL construction is real; persistence,
provider output, and websocket transport are controlled at dependency boundaries.
These tests cannot certify PostGIS behavior or concurrent transaction isolation.
"""
import copy
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models import Event, SourceReport
from app.services import telegram, news_feeds, classifier
from app.services.ingest_ledger import report_identity

STAMP = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
RAW = "Officials reported an exercise outside the capital with no injuries or damage recorded."


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def scalar_one(self):
        assert len(self.rows) == 1
        return self.rows[0]

    def scalars(self):
        return self

    def all(self):
        return self.rows


class EventStore:
    def __init__(self):
        self.events = []
        self.statements = []
        self.ledger = None

    def session(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        # Handler fixture only: real PostgreSQL lock ownership is qualified
        # independently. This supplies the transaction/SELECT adapter boundary.
        return self

    async def execute(self, statement, parameters=None):
        self.statements.append(statement)
        if str(statement).startswith("SELECT pg_try_advisory_xact_lock"):
            assert type(parameters["key"]) is int and -(2**63) <= parameters["key"] < 2**63
            return Result([True])
        params = statement.compile().params
        if getattr(statement, "column_descriptions", [{}])[0].get("entity") is SourceReport:
            assert self.ledger is not None
            records = self.ledger.records
            if "identity_1" in params and isinstance(params["identity_1"], str):
                row = records.get(params["identity_1"])
                column = next(iter(statement.selected_columns)).name
                return Result([row[column]] if row else [])
            identities = params.get("identity_1", [])
            statuses = params.get("status_1", [])
            return Result([identity for identity, row in records.items() if identity in identities and row["status"] in statuses])
        rows = list(self.events)
        # Query predicates remain in production code. These fixtures supply rows
        # for the exact-ID lookups used by the real handlers with null locations.
        for column in ("telegram_message_id", "channel_name", "source", "source_url"):
            key = next((k for k in params if re.fullmatch(re.escape(column) + r"_\d+", k)), None)
            if key:
                rows = [row for row in rows if getattr(row, column) == params[key]]
        only_id = len(statement.selected_columns) == 1
        return Result([row.id for row in rows] if only_id else rows)

    def add(self, item):
        assert isinstance(item, Event)
        item.id = len(self.events) + 1
        item.created_at = STAMP
        for key, default in {"report_count": 1, "confirmed_networks": "", "reporting_channels": "",
                             "anomaly_score": 0, "anomaly_analysis": "", "reports": []}.items():
            if getattr(item, key) is None:
                setattr(item, key, default)
        self.events.append(item)

    async def commit(self):
        return None

    async def refresh(self, item):
        return None


class Ledger:
    def __init__(self, order):
        self.records = {}
        self.order = order

    async def capture(self, report):
        identity, _ = report_identity(report)
        self.order.append("capture")
        if identity in self.records:
            return None
        self.records[identity] = {"report": copy.deepcopy(report), "status": "received", "event_id": None}
        return identity

    async def finish(self, identity, status, event_id=None):
        self.records[identity].update(status=status, event_id=event_id)
        self.order.append("finish")


@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setattr(news_feeds.settings, "rss_processing_mode", "model")
    monkeypatch.setattr(telegram.settings, "telegram_processing_mode", "model")
    order = []
    store = EventStore()
    ledger = Ledger(order)
    store.ledger = ledger
    extracted = {"classification_status": "extracted", "event_type": "military", "severity": 4,
                 "location_name": "Unknown", "summary": RAW, "is_noise": False}

    async def classify(text):
        order.append("classify")
        return dict(extracted)

    model = AsyncMock(side_effect=classify)
    geocode = AsyncMock(return_value=None)
    broadcast = AsyncMock()
    for module in (telegram, news_feeds):
        monkeypatch.setattr(module, "capture_report", ledger.capture)
        monkeypatch.setattr(module, "finish_report", ledger.finish)
        monkeypatch.setattr(module, "async_session", store.session)
        monkeypatch.setattr(module, "classify_message", model)
        monkeypatch.setattr(module, "geocode", geocode)
        monkeypatch.setattr(module.broadcaster, "broadcast", broadcast)
        monkeypatch.setattr(module, "analyze_anomaly", AsyncMock(side_effect=AssertionError("unexpected paid analysis")))
    monkeypatch.setattr(telegram, "_save_checkpoint", AsyncMock())
    monkeypatch.setattr(telegram, "_get_conflict_cutoff", lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    return SimpleNamespace(store=store, ledger=ledger, order=order, model=model,
                           geocode=geocode, broadcast=broadcast, extracted=extracted)


async def ingest(kind, raw=RAW, channel="observer", message_id=42, url="https://example.org/story"):
    if kind == "telegram":
        await telegram._process_message(raw, channel, STAMP, message_id)
    else:
        await news_feeds._process_article(raw, "", url, STAMP, channel, 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["telegram", "rss"])
async def test_unknown_location_saves_null_geometry_and_raw_receipt(pipeline, kind):
    await ingest(kind)
    assert pipeline.order[0:2] == ["capture", "classify"]
    assert len(pipeline.store.events) == 1
    row = pipeline.store.events[0]
    assert row.lat is None and row.lon is None and row.geometry is None
    assert row.geolocation_precision == "unknown"
    assert row.reports[0]["raw_text"] == RAW
    assert row.reports[0]["report_id"]
    receipt = next(iter(pipeline.ledger.records.values()))
    assert receipt["status"] == "extracted"
    assert receipt["report"]["raw_text"] == RAW
    assert "summary" not in receipt["report"]  # capture snapshot is immutable
    payload = pipeline.broadcast.await_args.args[0]
    assert '"lat":null' in payload
    assert '"verification_basis":"none"' in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["telegram", "rss"])
async def test_provider_failure_is_retained_but_not_published(pipeline, kind):
    pipeline.model.side_effect = None
    pipeline.model.return_value = classifier._build_fallback(RAW)
    await ingest(kind)
    assert not pipeline.store.events
    assert next(iter(pipeline.ledger.records.values()))["status"] == "unavailable"
    pipeline.geocode.assert_not_awaited()
    pipeline.broadcast.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["telegram", "rss"])
async def test_delivery_replay_is_idempotent(pipeline, kind):
    await ingest(kind)
    await ingest(kind)
    assert len(pipeline.store.events) == 1
    assert len(pipeline.ledger.records) == 1
    assert pipeline.model.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["telegram", "rss"])
async def test_source_edit_is_preserved_for_review(pipeline, kind):
    await ingest(kind)
    await ingest(kind, raw="Correction: officials withdrew the earlier exercise report after reviewing the original evidence.")
    assert len(pipeline.store.events) == 1
    assert pipeline.store.events[0].raw_text == RAW
    assert len(pipeline.ledger.records) == 2
    assert [r["status"] for r in pipeline.ledger.records.values()] == ["extracted", "source_revision_needs_review"]


@pytest.mark.asyncio
async def test_equal_message_id_in_different_telegram_channels_is_not_collision(pipeline):
    await ingest("telegram", channel="observer_one", message_id=42)
    await ingest("telegram", channel="observer_two", message_id=42)
    assert len(pipeline.store.events) == 2
    assert len(pipeline.ledger.records) == 2
    ids = {event.reports[0]["report_id"] for event in pipeline.store.events}
    assert len(ids) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["telegram", "rss"])
async def test_missing_extraction_status_cannot_publish(pipeline, kind):
    pipeline.extracted.pop("classification_status")
    await ingest(kind)
    assert not pipeline.store.events
    assert next(iter(pipeline.ledger.records.values()))["status"] == "invalid"


@pytest.mark.asyncio
async def test_low_severity_rss_receipt_is_terminal(pipeline):
    pipeline.extracted["severity"] = 2
    await ingest("rss")
    assert not pipeline.store.events
    assert next(iter(pipeline.ledger.records.values()))["status"] != "received"


@pytest.mark.asyncio
async def test_short_substantive_telegram_report_reaches_extractor(pipeline):
    await ingest("telegram", raw="Explosion reported in Beirut")
    pipeline.model.assert_awaited_once()


@pytest.mark.asyncio
async def test_embedded_promo_does_not_erase_telegram_event(pipeline):
    await ingest("telegram", raw=RAW + " Subscribe for updates.")
    pipeline.model.assert_awaited_once()


@pytest.mark.asyncio
async def test_undated_rss_source_is_retained_without_fabricated_current_time(pipeline):
    await news_feeds._process_article(RAW, "", "https://example.org/undated", None, "observer", 3)
    receipt = next(iter(pipeline.ledger.records.values()))
    assert receipt["report"]["timestamp"] is None
    assert receipt["status"] == "undated_source"
    assert not pipeline.store.events
    pipeline.model.assert_not_awaited()


@pytest.mark.parametrize("date_xml", ["", "<pubDate>invalid-date</pubDate>"])
def test_rss_parser_does_not_supply_a_publication_date(date_xml):
    xml = f"<rss><channel><item><title>Report</title><link>https://example.org/source</link>{date_xml}</item></channel></rss>"
    articles = news_feeds._parse_rss(xml)
    assert articles[0]["published"] is None

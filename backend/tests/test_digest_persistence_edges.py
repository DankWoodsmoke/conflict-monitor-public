import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import source_digest as subject


def report():
    return SimpleNamespace(id=77, source="rss_fixture", channel_name="Publisher", summary="Attributed test statement",
        raw_text="Original statement", source_url="https://example.invalid/original", timestamp=datetime(2026, 10, 28, tzinfo=timezone.utc))


class Session:
    def __init__(self, previous):
        self.previous = previous
        self.added = []
        self.queries = []
        self.commit = AsyncMock()
        self.refresh = AsyncMock(side_effect=self.assign_id)
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    def add(self, row):
        self.added.append(row)
    async def assign_id(self, row):
        row.id = 123
    async def execute(self, query):
        self.queries.append(query)
        if len(self.queries) == 1:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [report()]))
        return SimpleNamespace(scalar_one_or_none=lambda: self.previous)


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["not JSON", "[" * 2000 + "]" * 2000, " " * 2_000_001])
async def test_corrupt_previous_digest_does_not_prevent_new_attributed_compilation(monkeypatch, raw):
    session = Session(SimpleNamespace(id=5, raw_response=raw))
    monkeypatch.setattr(subject, "async_session", lambda: session)
    monkeypatch.setattr(subject, "_lock", asyncio.Lock())
    result = await subject.generate_source_digest()
    assert result == {"status": "created", "sitrep_id": 123}
    row, = session.added
    assert row.trigger == "source_digest" and row.escalation_level == "UNASSESSED" and row.escalation_score == 0
    assert row.key_event_ids == "77" and "[src:77]" in row.situation
    assert json.loads(row.raw_response)["_provenance"]["model"] is None
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(row)


@pytest.mark.asyncio
async def test_same_frozen_sources_do_not_create_duplicate_brief(monkeypatch):
    previous = subject.build_source_digest([report()])
    session = Session(SimpleNamespace(id=5, raw_response=previous["raw_response"]))
    monkeypatch.setattr(subject, "async_session", lambda: session)
    monkeypatch.setattr(subject, "_lock", asyncio.Lock())
    assert await subject.generate_source_digest() == {"status": "unchanged", "sitrep_id": 5}
    assert session.added == []
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_digest_commit_failure_is_not_reported_as_created(monkeypatch):
    session = Session(None)
    session.commit.side_effect = RuntimeError("fixture database offline")
    monkeypatch.setattr(subject, "async_session", lambda: session)
    monkeypatch.setattr(subject, "_lock", asyncio.Lock())
    with pytest.raises(RuntimeError, match="database offline"):
        await subject.generate_source_digest()
    session.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_generator_recovers_failure_without_logging_private_exception_text(monkeypatch, caplog):
    calls = []
    async def sleep(delay):
        calls.append(delay)
        if len(calls) == 3:
            raise asyncio.CancelledError()
    generator = AsyncMock(side_effect=[RuntimeError("private DB password URL"), {"status": "no_reports"}])
    monkeypatch.setattr(subject, "generate_source_digest", generator)
    monkeypatch.setattr(subject.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await subject.start_source_digest()
    assert generator.await_count == 2 and calls == [10, 300, 300]
    assert "private DB password" not in caplog.text

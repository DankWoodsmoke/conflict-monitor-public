import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.routes import sitreps as subject


def brief(**changes):
    return SimpleNamespace(**{"id": 12, "trigger": "source_digest", "generated_at": datetime.now(timezone.utc),
        "events_analyzed": 3, "key_questions": "[]", "key_event_ids": "5,2,7", "headline": "Attributed brief",
        "situation": "PRIVATE FULL SOURCE SNAPSHOT TEXT", "escalation_level": "UNASSESSED", "escalation_score": 0,
        "escalation_text": "No assessment", "economic_exposure": "", "game_theory": "", "humanitarian_ground": "",
        "historical_analogue": "", "raw_response": json.dumps({"_provenance": {"method": "attributed_report_compilation",
            "model": None, "source_snapshot": ["PRIVATE SOURCE TEXT"], "private_key": "DO NOT EXPOSE"}}), **changes})


def event(identity, source="rss_fixture"):
    return SimpleNamespace(id=identity, source=source, channel_name="Publisher", summary="source statement",
        source_url="https://example.invalid/", severity=0, event_type="unclassified", location_name="",
        timestamp=datetime.now(timezone.utc), reporting_channels="", confirmed_networks="", source_reliability=None)


def scalar(row):
    return SimpleNamespace(scalar_one_or_none=lambda: row)


def many(rows):
    return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))


class Session:
    def __init__(self, results):
        self.results = iter(results)
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def execute(self, statement):
        return next(self.results)


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(subject.router)
    return app


@pytest.mark.asyncio
async def test_history_index_exposes_unknown_score_and_public_provenance_but_not_private_source_bodies(app, monkeypatch):
    session = Session([many([brief()])])
    monkeypatch.setattr(subject, "async_session", lambda: session)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/sitreps/")
    assert response.status_code == 200
    row, = response.json()
    assert row["escalation_score"] is None and row["analysis_status"] == "attributed_source_digest"
    assert row["provenance"] == {"method": "attributed_report_compilation", "model": None}
    assert "PRIVATE" not in response.text and "DO NOT EXPOSE" not in response.text
    assert "situation" not in row


@pytest.mark.asyncio
async def test_citation_cards_restore_frozen_reference_order_and_preserve_unscored_source_metadata(app, monkeypatch):
    session = Session([scalar(brief()), many([event(7, "telegram"), event(5), event(2)])])
    monkeypatch.setattr(subject, "async_session", lambda: session)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/sitreps/12/events")
    rows = response.json()["events"]
    assert [row["id"] for row in rows] == [5, 2, 7]
    assert rows[0]["severity"] == 0 and rows[0]["location_name"] == ""
    assert rows[0]["network"] == "RSS" and rows[-1]["network"] == "TG"
    assert response.json()["source_reference_status"] == "available"


@pytest.mark.asyncio
async def test_deleted_source_events_are_explicit_instead_of_qualified_as_available(app, monkeypatch):
    session = Session([scalar(brief()), many([event(5), event(2)])])
    monkeypatch.setattr(subject, "async_session", lambda: session)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/sitreps/12/events")
    body = response.json()
    assert body["total"] == 2 and body["missing_source_ids"] == [7]
    assert body["source_reference_status"] == "missing_source_events"

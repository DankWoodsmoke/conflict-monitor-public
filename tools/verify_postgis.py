"""Required integration gate. Run only against an isolated test database.

DATABASE_URL must name conflict_monitor_test. Absence is an incomplete check,
not success. Alembic must already have initialized the empty test database.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


async def verify():
    url = os.environ.get("DATABASE_URL", "")
    if not url or urlsplit(url).path != "/conflict_monitor_test":
        raise RuntimeError("INCOMPLETE: set DATABASE_URL to an isolated conflict_monitor_test database")
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select, func
    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point
    from app.db import async_session, engine
    from app.main import app
    from app.config import settings
    from app.models import Event, SourceReport
    from app.services.dedup import check_duplicate, merge_duplicate
    from app.services.evidence import make_report
    from app.services.ingest_ledger import capture_report, finish_report
    settings.live_ingestion_enabled = False
    settings.admin_api_key = ""
    now = datetime.now(timezone.utc)
    run_id = uuid4().hex[:12]
    channel_a, channel_b, channel_c = [f"integration_{run_id}_{suffix}" for suffix in ("alpha", "beta", "gamma")]
    raw = {"source":"telegram", "channel_name":channel_a, "telegram_message_id":42,
           "raw_text":"A fictional vessel delay at the demonstration port is reported by a fixture",
           "source_url":f"https://example.org/test/{run_id}/alpha/42", "timestamp":now.isoformat()}
    receipt = await capture_report(raw)
    assert receipt is not None
    assert await capture_report(raw) is None
    assert await capture_report({**raw, "channel_name":channel_b}) is not None
    async with async_session() as session:
        event = Event(source="telegram", channel_name=channel_a, raw_text=raw["raw_text"],
                      summary=raw["raw_text"], event_type="economic", severity=3,
                      lat=25., lon=55., geometry=from_shape(Point(55,25),srid=4326), timestamp=now,
                      telegram_message_id=42, reports=[make_report(raw)], classification_status="extracted")
        session.add(event)
        session.add(Event(source="telegram",channel_name=channel_b,telegram_message_id=42,
                          raw_text="Different origin",summary="Different report",event_type="economic",
                          severity=2,timestamp=now))
        await session.commit()
        await session.refresh(event)
        event_id = event.id
        found = await check_duplicate(session,event.summary,"economic",25.,55.,now)
        assert found and found.id == event.id
        assert await check_duplicate(session,event.summary,"economic",None,None,now) is None
        await merge_duplicate(session,event,channel_c,3,25.,55.,report={**raw,
            "channel_name":channel_c,"source_url":f"https://example.org/test/{run_id}/gamma/42"})
        assert event.report_count == 2 and len(event.reports) == 2
    await finish_report(receipt,"extracted",event_id)
    async with async_session() as session:
        saved = await session.get(SourceReport,receipt)
        assert saved.status == "extracted" and saved.report["raw_text"] == raw["raw_text"]
    async with AsyncClient(transport=ASGITransport(app),base_url="http://test") as client:
        for path in ["/health", "/config", "/status", "/events", f"/events/{event_id}",
                     "/channels", "/sitreps/latest", "/sitreps/", "/media/intel", "/costs/summary",
                     "/tracking/aircraft", "/tracking/vessels", "/tracking/tle", "/market", "/market/history"]:
            response = await client.get(path)
            assert response.status_code == 200, (path,response.status_code,response.text[:150])
        payload = (await client.get(f"/events/{event_id}")).json()
        assert payload["evidence"]["independent_origin_count"] is None
        assert payload["evidence"]["unique_source_count"] >= 2
        assert (await client.post("/sitreps/generate")).status_code == 503
    await engine.dispose()
    print("PASS: fresh PostGIS schema, real persistence, scoped IDs, report ledger, spatial dedup and read API")


if __name__ == "__main__":
    try:
        asyncio.run(verify())
    except Exception as exc:
        print(f"FAIL/INCOMPLETE: {type(exc).__name__}: {str(exc)[:250]}",file=sys.stderr)
        raise SystemExit(2)

"""Real PostGIS + TCP/WebSocket gate, isolated fixtures and optional public RSS.

Never run against a display/live database. This appends explicitly synthetic
qualification rows only to a database named conflict_monitor_test. No model
key, paid model, Telegram session or original database is required.
"""
import argparse
import asyncio
import json
import os
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def require_test_database(url):
    if urlsplit(url).path != "/conflict_monitor_test":
        raise RuntimeError("INCOMPLETE: DATABASE_URL must name isolated conflict_monitor_test")


async def verify(*, public_feed=False):
    require_test_database(os.environ.get("DATABASE_URL", ""))
    import httpx
    import uvicorn
    import websockets
    from sqlalchemy import select, func, text
    from app.config import settings
    from app.db import async_session, engine
    from app.main import app
    from app.models import Event, SourceReport, TrackingSnapshot, UsageLog, ChannelCheckpoint, Sitrep
    from app.services import news_feeds, telegram
    from app.services.source_digest import generate_source_digest
    from app.services.snapshots import get_snapshots

    settings.live_ingestion_enabled = False
    settings.demo_mode = False
    settings.rss_processing_mode = "reports"
    settings.telegram_processing_mode = "reports"
    settings.anthropic_api_key = ""
    settings.enable_sitrep_generation = False
    settings.enable_video_generation = False
    settings.admin_api_key = ""
    run_id = uuid4().hex[:12]
    source_name = "qualification_" + run_id
    published = datetime.now(timezone.utc)
    report_url = f"https://example.org/qualification/{run_id}/report"
    title = "QUALIFICATION FIXTURE: وصول المساعدات — aid-delivery report"
    body = "Synthetic integration fixture. No occurrence, actor, location or severity is asserted."
    receipt = {"scope":"isolated_qualification_database", "run_id":run_id, "checks":{},
               "public_feed_requested":public_feed, "model_calls":0}
    async with async_session() as session:
        usage_before = (await session.execute(select(func.count()).select_from(UsageLog))).scalar_one()

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on", ws_max_size=4096))
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(100):
            if server.started:
                break
            if server_task.done():
                await server_task
                raise RuntimeError("Server stopped before readiness")
            await asyncio.sleep(.05)
        if not server.started:
            raise RuntimeError("Server readiness deadline exceeded")
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
            assert (await client.get("/health")).status_code == 200
            async with websockets.connect(f"ws://127.0.0.1:{port}/ws/events", origin=base_url) as ws:
                result = await news_feeds._process_article(title, body, report_url, published, source_name, None)
                assert result == "reported", result
                delivered = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                assert delivered["type"] == "new_event"
                event_id = delivered["event"]["id"]
                assert delivered["event"]["classification_status"] == "not_requested"
                event = (await client.get(f"/events/{event_id}")).json()
                assert event["severity"] == 0 and event["event_type"] == "unclassified"
                assert event["lat"] is None and event["lon"] is None
                assert "وصول المساعدات" in event["raw_text"]
                assert event["evidence"]["independent_origin_count"] is None
                receipt["checks"]["free_rss_to_postgis_tcp_api_and_websocket"] = "PASS"

                duplicate = await news_feeds._process_article(title, body, report_url, published, source_name, None)
                assert duplicate == "duplicate", duplicate
                changed = await news_feeds._process_article(title, body + " Correction retained.", report_url, published, source_name, None)
                assert changed == "source_revision_needs_review", changed
                async with async_session() as session:
                    saved = await session.get(Event, event_id)
                    assert "Correction retained" not in saved.raw_text
                    reports = (await session.execute(select(SourceReport).where(
                        SourceReport.report["source_url"].astext == report_url))).scalars().all()
                    assert len(reports) == 2
                    assert {r.status for r in reports} == {"reported", "source_revision_needs_review"}
                receipt["checks"]["replay_and_immutable_unicode_revision"] = "PASS"

                undated_url = report_url + "/undated"
                assert await news_feeds._process_article(title, body, undated_url, None, source_name, None) == "undated_source"
                async with async_session() as session:
                    row = (await session.execute(select(SourceReport).where(
                        SourceReport.report["source_url"].astext == undated_url))).scalar_one()
                    assert row.status == "undated_source" and row.event_id is None
                receipt["checks"]["undated_source_failure_is_persisted_not_fabricated"] = "PASS"

                # Actual Telegram processor and monotonic Postgres cursor, with
                # an explicitly synthetic test message (no Telegram API login).
                telegram_channel = f"qual_{run_id}_telegram"
                tg_result = await telegram._process_message(
                    "QUALIFICATION FIXTURE: " + title,telegram_channel,published,42)
                assert tg_result == "reported", tg_result
                tg_payload = json.loads(await asyncio.wait_for(ws.recv(),timeout=5))
                assert tg_payload["event"]["source"] == "telegram"
                assert tg_payload["event"]["classification_status"] == "not_requested"
                assert tg_payload["event"]["severity"] == 0 and tg_payload["event"]["lat"] is None
                await asyncio.gather(*(telegram._save_checkpoint(telegram_channel,n) for n in (73,71,72)))
                async with async_session() as session:
                    cursor = await session.get(ChannelCheckpoint,telegram_channel)
                    assert cursor.last_message_id == 73
                assert await telegram._process_message("QUALIFICATION FIXTURE: " + title,
                    telegram_channel,published,42) == "duplicate"
                async with async_session() as session:
                    cursor = await session.get(ChannelCheckpoint,telegram_channel)
                    assert cursor.last_message_id == 73
                receipt["checks"]["free_telegram_processor_and_atomic_monotonic_checkpoint"] = "PASS"

                # Oversized originals can share the full retained prefix. Their
                # separate failure receipts must preserve the original hashes.
                prefix = "QUALIFICATION OVERSIZED FIXTURE " + "x" * 12000
                for suffix in ("original A", "original B"):
                    assert await telegram._process_message(prefix+suffix,telegram_channel,published,43) == "input_too_large"
                assert await telegram._process_message(prefix+"original A",telegram_channel,published,43) == "duplicate"
                async with async_session() as session:
                    failed = (await session.execute(select(SourceReport).where(
                        SourceReport.report["source_url"].astext == f"https://t.me/{telegram_channel}/43"))).scalars().all()
                    assert len(failed) == 2 and {row.status for row in failed} == {"input_too_large"}
                    assert len({row.content_hash for row in failed}) == 2
                    assert len({row.report["stored_raw_sha256"] for row in failed}) == 1
                    assert all(row.content_hash == row.report["original_text_sha256"] for row in failed)
                receipt["checks"]["distinct_oversized_source_failure_identities_and_prefix_hashes"] = "PASS"

            # Same timestamp must be fully pageable without losing boundary rows.
            async with async_session() as session:
                fixtures = [Event(source=source_name,channel_name=source_name,
                    summary=f"QUALIFICATION CURSOR FIXTURE {i}",raw_text="synthetic cursor fixture",
                    event_type="unclassified",severity=0,timestamp=published,
                    classification_status="not_requested") for i in range(5)]
                session.add_all(fixtures)
                await session.commit()
                expected = {row.id for row in fixtures}
            seen, cursor, before_id = set(), published.isoformat(), None
            for _ in range(20):
                params = {"limit":2,"after":published.isoformat(),"before":cursor}
                if before_id is not None:
                    params["before_id"] = before_id
                page = (await client.get("/events",params=params)).json()
                assert isinstance(page,list), page
                if not page:
                    break
                assert not seen.intersection(row["id"] for row in page)
                seen.update(row["id"] for row in page)
                cursor,before_id = page[-1]["timestamp"],page[-1]["id"]
            assert expected <= seen
            receipt["checks"]["real_sql_compound_timestamp_id_pagination"] = "PASS"

            # A report created during an outage can carry an old publication date.
            # Reconciliation follows creation IDs, not the source-time timeline.
            creation_cursor = max(expected)
            async with async_session() as session:
                late = [Event(source=source_name,channel_name=source_name,
                    summary=f"QUALIFICATION LATE-PUBLICATION FIXTURE {i}",raw_text="synthetic reconnect fixture",
                    event_type="unclassified",severity=0,timestamp=published-timedelta(days=10+i),
                    classification_status="not_requested") for i in range(3)]
                session.add_all(late)
                await session.commit()
                expected_late = [row.id for row in late]
            recovered = []
            for _ in range(3):
                response = await client.get("/events",params={"after_id":creation_cursor,"limit":2})
                assert response.status_code == 200
                page = response.json()
                if not page:
                    break
                recovered.extend(row["id"] for row in page)
                assert all(row["id"] > creation_cursor for row in page)
                creation_cursor = page[-1]["id"]
            assert recovered == sorted(expected_late)
            receipt["checks"]["creation_id_recovery_includes_old_dated_reports"] = "PASS"

            # SQL bounds JSONB materialization; use isolated far-past fixture range.
            start = datetime(2001,1,1,tzinfo=timezone.utc) + timedelta(days=int(run_id[:4],16))
            async with async_session() as session:
                session.add_all([TrackingSnapshot(timestamp=start+timedelta(seconds=i),
                    aircraft=[{"i":"fixture","la":25.,"lo":55.}],vessels=[],jamming_zones=[]) for i in range(601)])
                await session.commit()
            snapshots = await get_snapshots(start,start+timedelta(seconds=601),max_points=17)
            assert 1 <= len(snapshots) <= 17
            assert all(row["aircraft"][0]["i"] == "fixture" for row in snapshots)
            receipt["checks"]["real_jsonb_snapshot_sampling_bound"] = "PASS"

            digest = await generate_source_digest()
            assert digest["status"] in {"created","unchanged"}
            detail = (await client.get(f"/sitreps/{digest['sitrep_id']}")).json()["sitrep"]
            assert detail["analysis_status"] == "attributed_source_digest"
            assert detail["escalation_score"] is None and detail["provenance"]["model"] is None
            assert (await generate_source_digest())["status"] == "unchanged"
            receipt["checks"]["free_persistent_attributed_brief_no_risk_inference"] = "PASS"

            # Historical malformed JSON and a missing source row must abstain
            # explicitly through real SQL + TCP, without deleting any records.
            async with async_session() as session:
                missing_id = (await session.execute(select(func.max(Event.id)))).scalar_one() + 1_000_000
                historical = Sitrep(trigger="source_digest", generated_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
                    headline="QUALIFICATION MALFORMED LEGACY BRIEF", escalation_level="UNASSESSED", escalation_score=0,
                    key_event_ids=f"{event_id},{missing_id}", key_questions="[" * 2000 + "]" * 2000,
                    raw_response="[" * 2000 + "]" * 2000)
                session.add(historical)
                await session.commit()
                legacy_id = historical.id
            legacy_response = await client.get(f"/sitreps/{legacy_id}")
            assert legacy_response.status_code == 200
            legacy = legacy_response.json()["sitrep"]
            assert legacy["provenance_status"] == "invalid_legacy_provenance"
            # Valid deep JSON is rejected by decoder depth on CPython 3.11,
            # or by the question schema after decoding on CPython 3.12.
            assert legacy["question_status"] in {"invalid_legacy_json", "invalid_legacy_shape"}
            assert legacy["key_questions"] == [] and legacy["escalation_score"] is None
            async with async_session() as session:
                malformed = await session.get(Sitrep, legacy_id)
                malformed.key_questions = '[{"q":'
                await session.commit()
            invalid_json = (await client.get(f"/sitreps/{legacy_id}")).json()["sitrep"]
            assert invalid_json["question_status"] == "invalid_legacy_json"
            assert invalid_json["key_questions"] == [] and invalid_json["escalation_score"] is None
            source_response = await client.get(f"/sitreps/{legacy_id}/events")
            assert source_response.status_code == 200
            sources = source_response.json()
            assert sources["source_reference_status"] == "missing_source_events"
            assert sources["missing_source_ids"] == [missing_id]
            assert [row["id"] for row in sources["events"]] == [event_id]
            receipt["checks"]["real_sql_legacy_json_abstention_and_missing_citation_disclosure"] = "PASS"
            for path in ("/sitreps/generate","/sitreps/digest","/satellite/poll"):
                assert (await client.post(path)).status_code == 503
            receipt["checks"]["paid_and_admin_operations_fail_closed"] = "PASS"

            if public_feed:
                # Read only a bounded public feed, run the actual free processor,
                # and require a persisted report rather than accepting empty work.
                parsed_articles = []
                parser = news_feeds._parse_rss
                def observe_parser(raw):
                    # Pass-through instrumentation records the real HTTP parser
                    # output; no provider response or processing is substituted.
                    articles = parser(raw)
                    parsed_articles.extend(articles)
                    return articles
                news_feeds._parse_rss = observe_parser
                try:
                    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
                        feed = next(row for row in news_feeds.FEEDS if row["source"] == "bbc_mideast")
                        attempted = await news_feeds._poll_feed(feed, http, max_items=2)
                        health = news_feeds._feed_health.get("bbc_mideast", {})
                        assert health.get("status") == "ok" and attempted > 0, "INCOMPLETE: current public feed attempt failed/empty"
                        assert health.get("rejected_items") == 0, "INCOMPLETE: selected current source items require review or failed validation"
                finally:
                    news_feeds._parse_rss = parser
                expected_urls = [item["url"] for item in parsed_articles
                    if news_feeds._is_conflict_relevant(item["title"], item["description"])][:2]
                assert len(expected_urls) == attempted
                async with async_session() as session:
                    real = (await session.execute(select(Event).where(
                        Event.source == "rss_bbc_mideast",Event.classification_status == "not_requested",
                        Event.source_url.in_(expected_urls))
                        .order_by(Event.created_at.desc()).limit(2))).scalars().all()
                    assert len(real) == attempted, "INCOMPLETE: selected current feed URLs did not resolve to persisted free reports"
                    receipt["public_feed"] = {"source":"bbc_mideast","persisted_records":len(real),
                        "selected_current_urls_matched":True,"rejected_items":health["rejected_items"],
                        "source_urls":[row.source_url for row in real],"classification":"not_requested"}
                receipt["checks"]["bounded_public_rss_to_actual_database"] = "PASS"

        async with async_session() as session:
            usage_after = (await session.execute(select(func.count()).select_from(UsageLog))).scalar_one()
            assert usage_after == usage_before
            indexes = (await session.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename='events'"))).scalars().all()
            assert {"ix_events_timestamp_id","ix_events_source_url","ix_events_type_timestamp"} <= set(indexes)
        receipt["checks"]["no_paid_usage_and_required_query_indexes"] = "PASS"
        receipt["status"] = "PASS"
        print(json.dumps(receipt,ensure_ascii=False,indent=2))
        return receipt
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task,timeout=10)
        finally:
            listener.close()
            await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-feed",action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(verify(public_feed=args.public_feed))
    except Exception as exc:
        print(f"FAIL/INCOMPLETE: {type(exc).__name__}: {str(exc)[:250]}",file=sys.stderr)
        raise SystemExit(2)

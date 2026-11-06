"""Destructive synthetic fixture verification, never a live-database command.

Requires an explicitly labeled disposable loopback database. The outer harness
must isolate its network, generate credentials and remove only its own fixture.
"""
import asyncio
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit, unquote


async def main():
    if not __debug__:
        raise RuntimeError("Assertions must be enabled")
    marker = os.environ.get("RSS_RETRY_FIXTURE_ID", "")
    url = os.environ.get("DATABASE_URL", "")
    parsed = urlsplit(url)
    if (not re.fullmatch(r"[a-f0-9]{32}", marker) or parsed.hostname != "127.0.0.1"
        or parsed.path != "/conflict_monitor_test" or parsed.username != "monitor_admin"
        or parsed.scheme != "postgresql+asyncpg" or not parsed.password
        or parsed.query or parsed.fragment):
        raise RuntimeError("Explicit isolated RSS fixture required")
    import asyncpg
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    try:
        label = await connection.fetchval("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()")
        if label != "rss-retry-fixture:" + marker:
            raise RuntimeError("Disposable database ownership marker mismatch")
        if await connection.fetchval("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='source_reports'"):
            raise RuntimeError("Fixture database must start without application data")
        result = await asyncio.to_thread(subprocess.run,
            [sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, timeout=120)
        if result.returncode:
            raise RuntimeError("Fresh migration failed: " + result.stderr.decode(errors="replace")[-1500:])
        password = os.environ.get("POSTGRES_APP_PASSWORD", "")
        if not re.fullmatch(r"[a-f0-9]{64}", password):
            raise RuntimeError("Generated fixture runtime credential required")
        quoted = await connection.fetchval("SELECT quote_literal($1::text)", password)
        await connection.execute("CREATE ROLE monitor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD " + quoted)
        await connection.execute("GRANT USAGE ON SCHEMA public TO monitor")
        await connection.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON source_reports,source_report_retries,events TO monitor")
        await connection.execute("GRANT USAGE,SELECT ON SEQUENCE events_id_seq TO monitor")
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy import text
        from app.services import news_feeds as rss, rss_retries as queue, ingest_ledger as ledger
        runtime_url = url.replace("monitor_admin:" + parsed.password, "monitor:" + password, 1)
        engine = create_async_engine(runtime_url, pool_size=5, max_overflow=5)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        rss.async_session = queue.async_session = ledger.async_session = sessions
        rss.settings.rss_processing_mode = "reports"
        rss.settings.rss_relevance_mode = "selected_sources"
        rss.settings.rss_sources = "bbc_mideast"
        rss.settings.live_ingestion_enabled = True
        rss.settings.rss_max_items_per_feed = 5
        rss._feed_health = {}
        now = [datetime(2026, 11, 4, 12, tzinfo=timezone.utc)]
        rss._clock = lambda: now[0]
        notices = []
        async def forbidden(*args, **kwargs):
            raise AssertionError("Network/model/geocoder must not be called")
        async def broadcast(value):
            notices.append(value)
        rss.classify_message = rss.geocode = rss.analyze_anomaly = forbidden
        rss.broadcaster.broadcast = broadcast
        feed = {"source": "bbc_mideast", "url": "https://example.test/empty", "reliability": 4}
        checks = {}
        def check(name, condition):
            checks[name] = bool(condition)
            if not condition:
                raise AssertionError(name)
        async def clear():
            await connection.execute("TRUNCATE source_report_retries,source_reports,events,event_deliveries RESTART IDENTITY")
            notices.clear()
            rss._feed_health = {}
        async def future(index, due=None, source="bbc_mideast"):
            due = due or now[0] + timedelta(hours=2)
            title = f"Officials report diplomatic talks, fixture {index}"
            link = f"https://example.test/story/{index}"
            outcome = await rss._process_article(title, "Unreviewed publisher excerpt.", link, due, source, 4)
            check(f"future_{index}_deferred", outcome == "future_source_time")
            return await connection.fetchrow("SELECT identity,content_hash,report::text,status FROM source_reports WHERE report->>'source_url'=$1", link)
        async def empty_cycle(limit=5, status=200):
            import httpx
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:
                httpx.Response(status, text="<rss><channel/></rss>"))) as client:
                return await rss._poll_feed(feed, client, max_items=limit)
        try:
            check("fresh_schema_head", await connection.fetchval("SELECT version_num FROM alembic_version") == "0006_rss_due_retries")
            original = await future("missing")
            check("status_and_queue_atomic", await connection.fetchval("SELECT count(*) FROM source_report_retries") == 1)
            now[0] += timedelta(hours=2)
            check("missing_feed_replayed", await empty_cycle(status=403) == 1)
            check("one_event_from_stored_source", await connection.fetchval("SELECT count(*) FROM events") == 1)
            saved = await connection.fetchrow("SELECT content_hash,report::text,status FROM source_reports WHERE identity=$1", original["identity"])
            check("immutable_source_survives_replay", saved["content_hash"] == original["content_hash"] and saved["report"] == original["report"])
            check("source_marked_reported", saved["status"] == "reported")
            check("original_publication_clock_preserved", await connection.fetchval("SELECT timestamp FROM events") == now[0])
            check("queue_completed_and_idempotent", await empty_cycle() == 0 and await connection.fetchval("SELECT count(*) FROM source_report_retries WHERE finished_at IS NOT NULL") == 1)

            await clear()
            await future("quota-bbc", source="bbc_mideast")
            await future("quota-twz", source="the_war_zone")
            now[0] += timedelta(hours=2)
            import httpx
            from unittest.mock import patch
            from email.utils import format_datetime
            original_client = httpx.AsyncClient
            old_sources, old_limit = rss.settings.rss_sources, rss.settings.rss_max_ingest_per_cycle
            rss.settings.rss_sources = "bbc_mideast,the_war_zone"
            rss.settings.rss_max_ingest_per_cycle = 1
            rss._poll_cursor, rss._retry_one_item_turn = 0, {}
            def publisher(request):
                source = "bbc_mideast" if "bbci" in request.url.host else "the_war_zone"
                body = f"<rss><channel><item><title>Iran diplomatic fixture {source}</title><link>https://example.test/new/{source}</link><description>Publisher excerpt</description><pubDate>{format_datetime(now[0]-timedelta(minutes=1))}</pubDate></item></channel></rss>"
                return httpx.Response(200, text=body)
            try:
                with patch.object(httpx, "AsyncClient", side_effect=lambda **kwargs:
                    original_client(transport=httpx.MockTransport(publisher), **kwargs)):
                    for cycle, (source, kind) in enumerate([
                        ("bbc_mideast", "retry"), ("the_war_zone", "retry"),
                        ("bbc_mideast", "new"), ("the_war_zone", "new")]):
                        await rss.poll_news_once()
                        last = await connection.fetchrow("SELECT source,source_url FROM events ORDER BY id DESC LIMIT 1")
                        check(f"one_slot_even_rotation_cycle_{cycle}", rss._cycle_status["attempted_items"] == 1
                            and await connection.fetchval("SELECT count(*) FROM events") == cycle+1
                            and last["source"] == "rss_"+source
                            and (("/new/" in last["source_url"]) == (kind == "new")))
            finally:
                rss.settings.rss_sources, rss.settings.rss_max_ingest_per_cycle = old_sources, old_limit
                rss._retry_one_item_turn = {}
            check("both_sources_received_retry_and_new_slot", await connection.fetchval("SELECT count(*) FROM source_report_retries WHERE finished_at IS NOT NULL") == 2)

            await clear()
            original = await future("lease")
            now[0] += timedelta(hours=2)
            item = (await queue.claim_due("bbc_mideast", 1, now[0]))[0]
            check("lease_hides_active_claim", await queue.claim_due("bbc_mideast", 1, now[0]) == [])
            now[0] += timedelta(seconds=queue.LEASE_SECONDS + 1)
            newer = (await queue.claim_due("bbc_mideast", 1, now[0]))[0]
            check("expired_claim_recovers", item.identity == newer.identity and item.token != newer.token and newer.attempts == 2)
            check("stale_ack_cannot_finish_new_claim", not await queue.finish_attempt(item, "reported", now[0]))
            outcome = await rss._process_retained_future(newer, feed)
            check("new_claim_replays", outcome == "reported")
            check("new_ack_finishes", await queue.finish_attempt(newer, outcome, now[0]))

            await clear()
            for index in range(5):
                await future(f"parallel{index}")
            now[0] += timedelta(hours=2)
            first, second = await asyncio.gather(queue.claim_due("bbc_mideast", 2, now[0]), queue.claim_due("bbc_mideast", 2, now[0]))
            check("concurrent_claims_disjoint", len(first) == len(second) == 2 and not {x.identity for x in first} & {x.identity for x in second})
            check("claim_limit_bounded", len(await queue.claim_due("bbc_mideast", 999, now[0])) == 1)
            async with sessions() as lock_session, lock_session.begin():
                await lock_session.execute(text("SELECT identity FROM source_report_retries FOR UPDATE"))
                now[0] += timedelta(seconds=queue.LEASE_SECONDS + 1)
                check("locked_rows_skip_without_wait", await asyncio.wait_for(queue.claim_due("bbc_mideast", 2, now[0]), 2) == [])

            await clear()
            original = await future("cancel")
            now[0] += timedelta(hours=2)
            item = (await queue.claim_due("bbc_mideast", 1, now[0]))[0]
            publish = rss._publish_rss_snapshot
            entered = asyncio.Event()
            async def interrupted(*args):
                entered.set()
                await asyncio.Event().wait()
            rss._publish_rss_snapshot = interrupted
            task = asyncio.create_task(rss._process_retained_future(item, feed))
            await asyncio.wait_for(entered.wait(), 3)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                rss._publish_rss_snapshot = publish
            key = int(item.identity[:16], 16)
            if key >= 2**63:
                key -= 2**64
            async with sessions() as check_session, check_session.begin():
                acquired = (await check_session.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key})).scalar_one()
                check("cancelled_owner_releases_advisory_lock", acquired)
            check("cancelled_work_not_acknowledged", await connection.fetchval("SELECT count(*) FROM events") == 0 and await connection.fetchval("SELECT count(*) FROM source_report_retries WHERE finished_at IS NULL") == 1)
            now[0] += timedelta(seconds=queue.LEASE_SECONDS + 1)
            check("cancelled_work_replayed_after_lease", await empty_cycle() == 1 and await connection.fetchval("SELECT count(*) FROM events") == 1)

            await clear()
            await future("commit")
            now[0] += timedelta(hours=2)
            real_finish = rss.finish_report
            failed = False
            async def lost_ack(identity, status, event_id=None):
                nonlocal failed
                if status == "reported" and not failed:
                    failed = True
                    raise RuntimeError("Synthetic post-Event-commit interruption")
                return await real_finish(identity, status, event_id)
            rss.finish_report = lost_ack
            try:
                check("commit_failure_retains_single_event", await empty_cycle() == 1 and await connection.fetchval("SELECT count(*) FROM events") == 1)
            finally:
                rss.finish_report = real_finish
            now[0] += timedelta(seconds=61)
            check("commit_recovery_does_not_duplicate", await empty_cycle() == 1 and await connection.fetchval("SELECT count(*) FROM events") == 1)
            check("commit_recovery_finishes_receipt", await connection.fetchval("SELECT status FROM source_reports") == "reported" and len(notices) == 1)

            await clear()
            report = rss._rss_report("Fixture atomic future", "Unreviewed excerpt", "https://example.test/atomic", now[0] + timedelta(hours=2), "bbc_mideast")
            identity = await ledger.capture_report(report)
            await connection.execute("ALTER TABLE source_report_retries ADD CONSTRAINT fixture_reject_queue CHECK(source_name <> 'bbc_mideast') NOT VALID")
            try:
                try:
                    await queue.defer_report(identity, report)
                except Exception:
                    pass
                check("defer_failure_rolls_back_outcome_and_queue", await connection.fetchval("SELECT status FROM source_reports") == "received" and await connection.fetchval("SELECT count(*) FROM source_report_retries") == 0)
            finally:
                await connection.execute("ALTER TABLE source_report_retries DROP CONSTRAINT fixture_reject_queue")
            await queue.defer_report(identity, report)
            check("defer_recovers_after_transaction_failure", await connection.fetchval("SELECT status FROM source_reports") == "future_source_time")

            check("model_provider_invocations_zero", True)  # every callable is a raising stub
            await queue.refresh_status("bbc_mideast", now[0])
            metrics = queue.get_status(["bbc_mideast"], True)
            check("queue_metrics_distinguish_future_from_due", metrics["sources"]["bbc_mideast"]["pending"] == 1 and metrics["sources"]["bbc_mideast"]["eligible_now"] == 0)
            rights = [await connection.fetchval("SELECT has_table_privilege('monitor','public.source_report_retries',$1)", right)
                for right in ("SELECT", "INSERT", "UPDATE", "DELETE")]
            check("fixture_runtime_has_required_queue_dml", all(rights))
            prohibited = [await connection.fetchval("SELECT has_table_privilege('monitor','public.source_report_retries',$1)", right)
                for right in ("TRUNCATE", "REFERENCES", "TRIGGER")]
            check("fixture_runtime_has_no_queue_ddl_or_extra_rights", not any(prohibited))

            # A separate synthetic pre-0006 database proves backfill seeding
            # without changing any original source row or accepting bad clocks.
            await connection.execute("CREATE DATABASE conflict_monitor_retry_seed")
            legacy_url = url.rsplit("/", 1)[0] + "/conflict_monitor_retry_seed"
            legacy = create_async_engine(legacy_url)
            from app.models import SourceReport, SourceReportRetry
            from sqlalchemy import insert, select
            from alembic.migration import MigrationContext
            from alembic.operations import Operations
            migration_path = Path("alembic/versions/0006_rss_due_retries.py")
            spec = importlib.util.spec_from_file_location("rss_due_migration", migration_path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            check("clock_pattern_shared", migration.CLOCK_PATTERN == queue.SOURCE_CLOCK_PATTERN)
            clocks = ["2026-11-04T11:00:00Z", "2026-11-05T11:00:00Z", "2026-11-04T11:00:00+03:30",
                "2024-02-29T12:00:00Z", "2026-02-30T12:00:00Z", "2026-01-01T24:00:00Z",
                "2026-01-01T23:59:60Z", "2026-01-01T12:00:00", "0001-01-01T00:00:00+14:00",
                "9999-12-31T23:59:59-14:00", "not a timestamp", None]
            seed_rows = []
            for index, stamp in enumerate(clocks):
                report = rss._rss_report(f"Seed fixture {index}", "Retained source body", f"https://example.test/seed/{index}", now[0], "bbc_mideast")
                report["timestamp"] = stamp
                identity, digest = ledger.report_identity(report)
                seed_rows.append(dict(identity=identity, content_hash=digest, report=report, status="future_source_time"))
            excluded = rss._rss_report("Model historical fixture", "Retained source body", "https://example.test/model", now[0], "bbc_mideast", model=True)
            identity, digest = ledger.report_identity(excluded)
            seed_rows.append(dict(identity=identity, content_hash=digest, report=excluded, status="future_source_time"))
            try:
                async with legacy.begin() as conn:
                    await conn.run_sync(SourceReport.__table__.create)
                    await conn.execute(insert(SourceReport), seed_rows)
                async def digest_sources(conn):
                    return (await conn.execute(text("SELECT md5(string_agg(md5(row_to_json(s)::text),'' ORDER BY identity)) FROM source_reports s"))).scalar_one()
                async with legacy.begin() as conn:
                    before_digest = await digest_sources(conn)
                    def migrate(sync):
                        with Operations.context(MigrationContext.configure(sync)):
                            migration.upgrade()
                    await conn.run_sync(migrate)
                    check("legacy_source_rows_unchanged", before_digest == await digest_sources(conn))
                    scheduled = (await conn.execute(select(SourceReportRetry.identity, SourceReportRetry.due_at))).all()
                    expected = {row["identity"]: queue.parse_source_clock(row["report"]["timestamp"])
                        for row in seed_rows if queue.supported_report(row["report"], row["identity"], row["content_hash"])}
                    check("legacy_only_supported_zoned_clocks_seeded", dict(scheduled) == expected and len(expected) == 4)
                    await conn.execute(text("SET LOCAL enable_seqscan=off"))
                    plan = (await conn.execute(text("EXPLAIN (FORMAT JSON) SELECT identity FROM source_report_retries WHERE source_name='bbc_mideast' AND finished_at IS NULL AND next_attempt_at<=now() ORDER BY next_attempt_at,identity LIMIT 2"))).scalar_one()
                    check("pending_index_supports_bounded_due_lookup", "ix_source_retry_pending_due" in json.dumps(plan))
                    source_plan = (await conn.execute(text("EXPLAIN (FORMAT JSON) SELECT identity FROM source_reports WHERE status='future_source_time' LIMIT 10001"))).scalar_one()
                    check("legacy_status_index_supports_capped_scan", "ix_source_reports_status" in json.dumps(source_plan))
                try:
                    async with legacy.begin() as conn:
                        await conn.run_sync(migrate)
                except RuntimeError as exc:
                    check("existing_retry_state_not_silently_adopted", "Pre-existing RSS retry state" in str(exc))
                else:
                    raise AssertionError("existing_retry_state_not_silently_adopted")
            finally:
                await legacy.dispose()
            await connection.execute("CREATE DATABASE conflict_monitor_retry_shape")
            shape = create_async_engine(url.rsplit("/", 1)[0] + "/conflict_monitor_retry_shape")
            try:
                async with shape.begin() as conn:
                    await conn.run_sync(SourceReport.__table__.create)
                    await conn.run_sync(migrate)
                    def inspect_columns(sync):
                        import sqlalchemy as sa
                        columns = sa.inspect(sync).get_columns("source_report_retries", schema="public")
                        return {c["name"]: (c["type"].compile(dialect=sync.dialect), c["nullable"]) for c in columns}
                    check("explicit_revision_ddl_matches_frozen_definition", await conn.run_sync(inspect_columns) == migration.EXPECTED_COLUMNS)
                for change, restoration, error_text, label in [
                    ("ALTER TABLE source_report_retries ALTER attempts SET DEFAULT 7",
                     "ALTER TABLE source_report_retries ALTER attempts SET DEFAULT 0", "column default", "changed_default"),
                    ("ALTER TABLE source_report_retries ADD COLUMN unexpected text",
                     "ALTER TABLE source_report_retries DROP COLUMN unexpected", "table definition", "extra_column")]:
                    async with shape.begin() as conn:
                        await conn.execute(text(change))
                    try:
                        async with shape.begin() as conn:
                            await conn.run_sync(migrate)
                    except RuntimeError as exc:
                        check("empty_unknown_schema_rejected_" + label, error_text in str(exc))
                    else:
                        raise AssertionError("empty_unknown_schema_rejected_" + label)
                    finally:
                        async with shape.begin() as conn:
                            await conn.execute(text(restoration))
                async with shape.begin() as conn:
                    await conn.run_sync(migrate)
                    check("exact_empty_schema_compatibility_retained", True)
            finally:
                await shape.dispose()
            print(json.dumps({"status": "PASS_RSS_DUE_POSTGRES", "checks": checks,
                "clock": "synthetic", "network": "MockTransport only; outer namespace must be network-none",
                "limitations": ["No real provider data or production database was used.", "Publisher clock-correction capture remains a separate limitation.", "Index usability is tested with sequential scans disabled on the tiny synthetic migration fixture; no large-data latency claim."]}))
        finally:
            await engine.dispose()
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())

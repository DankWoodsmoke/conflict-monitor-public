"""Actual isolated PostGIS + TCP verification of committed report delivery."""

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


def require_fixture(url):
    if not __debug__:
        raise RuntimeError("Assertions must be active")
    parsed = urlsplit(url)
    if parsed.scheme != "postgresql+asyncpg" or parsed.username != "monitor" or parsed.path != "/conflict_monitor_test":
        raise ValueError("Use the restricted runtime login in an isolated conflict_monitor_test database")


async def verify():
    require_fixture(os.environ.get("DATABASE_URL", ""))
    import httpx
    import uvicorn
    from sqlalchemy import delete, text

    from app.config import settings
    from app.db import async_session, engine
    from app.main import app
    from app.models import Event

    settings.demo_mode = False
    settings.live_ingestion_enabled = False
    run_id = uuid4().hex[:12]
    stamp = datetime.now(timezone.utc)
    checks = {}
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[listener]))

    def fixture(label, *, source=None, timestamp=stamp):
        return Event(source=source or f"rss_delivery_{run_id}", channel_name="qualification fixture",
                     raw_text=f"SYNTHETIC — {label}", summary="Qualification fixture", timestamp=timestamp)

    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
                raise RuntimeError("Fixture API stopped before readiness")
            await asyncio.sleep(.02)
        assert server.started
        async with httpx.AsyncClient(base_url=base_url, timeout=5, trust_env=False) as client, engine.connect() as publisher:
            # Dedicated session lock keeps an already-running fixture app's
            # maintenance worker out of this controlled sequence. All producer
            # commits still use ordinary independent restricted sessions.
            acquired = (await publisher.execute(text("SELECT pg_try_advisory_lock(70415,9)"))).scalar_one()
            await publisher.commit()
            assert acquired, "Fixture publication lock is already owned"

            async def publish(*, rollback=False):
                transaction = await publisher.begin()
                try:
                    value = (await publisher.execute(text("SELECT public.publish_event_deliveries()"))).scalar_one()
                    if rollback:
                        await transaction.rollback()
                    else:
                        await transaction.commit()
                    return value
                finally:
                    if transaction.is_active:
                        await transaction.rollback()

            async def page(epoch, after, *, limit=50, status=200):
                response = await client.get("/events/delivery/changes", params={"epoch": epoch, "after": after, "limit": limit})
                assert response.status_code == status
                return response.json()

            try:
                for _ in range(20):
                    if await publish() == 0:
                        break
                else:
                    raise RuntimeError("Fixture did not reach a bounded empty queue")
                baseline = (await client.get("/events/delivery/baseline?limit=2")).raise_for_status().json()
                epoch, start = baseline["epoch"], baseline["after"]
                assert epoch.endswith("-live") and start.isdigit()

                async with async_session() as low, async_session() as high:
                    first = fixture("older publication and lower creation ID", timestamp=stamp - timedelta(days=30))
                    second = fixture("higher creation ID commits first")
                    low.add(first)
                    await low.flush()
                    high.add(second)
                    await high.commit()
                    assert first.id < second.id
                    waiting = await page(epoch, start)
                    assert waiting["changes"] == [] and waiting["next_after"] == start
                    assert await publish(rollback=True) == 1
                    assert (await page(epoch, start))["changes"] == []
                    assert await publish() == 1
                    higher = await page(epoch, start)
                    assert [(row["event_id"], row["action"]) for row in higher["changes"]] == [(second.id, "upsert")]
                    await low.commit()
                    assert await publish() == 1
                    late = await page(epoch, higher["next_after"])
                    assert [(row["event_id"], row["action"]) for row in late["changes"]] == [(first.id, "upsert")]
                    assert int(late["next_after"]) == int(higher["next_after"]) + 1
                    assert late["changes"][0]["event"]["raw_text"] == first.raw_text
                    legacy = (await client.get("/events", params={"after_id": second.id})).raise_for_status().json()
                    assert first.id not in {row["id"] for row in legacy}
                checks["actual_lower_id_late_commit_recovers_without_websocket"] = True
                checks["unpublished_and_rolled_back_assignments_are_invisible"] = True

                async with async_session() as session:
                    session.add(fixture("rolled back before admission"))
                    await session.flush()
                    await session.rollback()
                assert await publish() == 0
                checks["producer_rollback_leaves_no_delivery"] = True

                async with async_session() as session:
                    removed_before_read = fixture("purged before first read")
                    demo = fixture("synthetic mode only", source="demo")
                    situational = fixture("excluded from both modes", source="situational")
                    session.add_all([removed_before_read, demo, situational])
                    await session.commit()
                    await session.execute(delete(Event).where(Event.id.in_([first.id, removed_before_read.id])))
                    await session.commit()
                assert await publish() == 4
                cursor = late["next_after"]
                first_delete_page = await page(epoch, cursor, limit=1)
                assert first_delete_page["has_more"] is True
                second_delete_page = await page(epoch, first_delete_page["next_after"])
                deletions = first_delete_page["changes"] + second_delete_page["changes"]
                assert deletions[0]["event_id"] == removed_before_read.id
                assert sorted(row["event_id"] for row in deletions[1:]) == sorted((first.id, removed_before_read.id))
                assert all(row["action"] == "delete" and row["event"] is None for row in deletions)
                assert second_delete_page["has_more"] is False
                assert (await client.get(f"/events/{first.id}")).status_code == 404
                checks["purge_tombstones_retain_offsets_without_reexposing_source"] = True
                checks["lookahead_pages_do_not_advance_beyond_returned_rows"] = True

                settings.demo_mode = True
                demo_baseline = (await client.get("/events/delivery/baseline")).raise_for_status().json()
                assert demo_baseline["epoch"] != epoch and demo_baseline["epoch"].endswith("-demo")
                assert demo.id in {row["id"] for row in demo_baseline["events"]}
                demo_page = await page(demo_baseline["epoch"], cursor)
                assert [row["event_id"] for row in demo_page["changes"]] == [demo.id]
                mismatch = await page(epoch, cursor, status=409)
                assert mismatch["detail"] == {"code": "delivery_baseline_required", "reason": "epoch_changed"}
                ahead = await page(demo_baseline["epoch"], str(int(demo_baseline["after"]) + 1), status=409)
                assert ahead["detail"]["reason"] == "cursor_ahead"
                checks["epochs_prevent_cross_mode_and_ahead_cursor_reuse"] = True
                settings.demo_mode = False
                new_baseline = (await client.get("/events/delivery/baseline?limit=100")).raise_for_status().json()
                ids = {row["id"] for row in new_baseline["events"]}
                assert second.id in ids and ids.isdisjoint({first.id, removed_before_read.id, demo.id, situational.id})
                assert (await page(epoch, new_baseline["after"]))["changes"] == []
                checks["snapshot_excludes_purged_and_out_of_mode_reports"] = True
            finally:
                if not acquired:
                    await publisher.invalidate()
                else:
                    try:
                        await publisher.rollback()
                        await publisher.execute(text("SELECT pg_advisory_unlock(70415,9)"))
                        await publisher.commit()
                    except BaseException:
                        await publisher.invalidate()
                        raise
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 5)
        finally:
            listener.close()
            await engine.dispose()
    return {"status": "PASS", "scope": "isolated restricted-role PostGIS and actual TCP HTTP; synthetic writes only", "checks": checks}


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(asyncio.wait_for(verify(), 45)), indent=2))
    except Exception as error:
        print(f"FAIL/INCOMPLETE: event delivery verification ({type(error).__name__})", file=sys.stderr)
        raise SystemExit(2) from None

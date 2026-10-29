"""Capture/compare persistence around an explicitly coordinated backend restart.

This tool never restarts a container. Raw publisher text and credentials stay in
process memory; receipts contain hashes/counts only. New ingestion is allowed,
but every previously observed source row must remain byte-identical.
"""
import argparse
import asyncio
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx


SQL_METADATA = r'''
import asyncio,hashlib,json
from sqlalchemy import select,func
from app.db import async_session,engine
from app.models import Event,SourceReport,ChannelCheckpoint,UsageLog
async def main():
 async with async_session() as session:
  events=(await session.execute(select(Event.id,Event.raw_text))).all()
  reports=(await session.execute(select(SourceReport.identity,SourceReport.content_hash))).all()
  cursors=(await session.execute(select(ChannelCheckpoint.channel_name,ChannelCheckpoint.last_message_id))).all()
  usage=(await session.execute(select(func.count()).select_from(UsageLog))).scalar_one()
 print(json.dumps({'events':{str(i):hashlib.sha256((text or '').encode('utf8')).hexdigest() for i,text in events},
  'source_reports':{identity:content_hash for identity,content_hash in reports},
  'checkpoints':dict(cursors),'usage_rows':usage}))
 await engine.dispose()
asyncio.run(main())
'''


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf8")).hexdigest()


def docker(arguments, *, source=None):
    result = subprocess.run(["docker", *arguments], input=source, capture_output=True, text=True,
                            encoding="utf8", timeout=25)
    if result.returncode:
        raise RuntimeError("Container metadata capture unavailable; inspect local diagnostics privately")
    return result.stdout


async def capture(base, container):
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("This qualification helper is limited to the local deployment")
    identity = json.loads(docker(["inspect", "--format",
        '{"id":{{json .Id}},"image":{{json .Image}},"started_at":{{json .State.StartedAt}}}', container]))
    database = json.loads(docker(["exec", "-i", container, "python", "-"], source=SQL_METADATA))
    if not database["events"] or not database["source_reports"]:
        raise RuntimeError("An existing nonempty source/receipt database is required")
    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        health = await client.get("/api/health")
        if health.status_code != 200:
            raise RuntimeError("Core application is not ready")
        state_response = await client.get("/api/briefing/status")
        state_response.raise_for_status()
        states = state_response.json()
        if any(states.get(name, {}).get("state") == "running" for name in ("local_ai", "video")):
            raise RuntimeError("Generation must be idle during the coordinated persistence comparison")
        manifest_response = await client.get("/api/briefing/video/manifest")
        manifest_response.raise_for_status()
        manifest = manifest_response.json()
        filename = manifest.get("filename", "")
        if manifest.get("status") != "available" or not re.fullmatch(r"[a-f0-9]{32}\.mp4", filename):
            raise RuntimeError("An actual validated narrated artifact is required")
        digest, length = hashlib.sha256(), 0
        async with client.stream("GET", f"/api/briefing/video/{filename}") as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                length += len(chunk)
                if length > 40_000_000:
                    raise RuntimeError("Narrated artifact exceeds the declared size bound")
                digest.update(chunk)
        if digest.hexdigest() != manifest.get("sha256") or length != manifest.get("bytes"):
            raise RuntimeError("Artifact full SHA/size does not match its manifest")
        if filename != digest.hexdigest()[:32]+".mp4" or not length:
            raise RuntimeError("Artifact filename is not bound to its complete content hash")
        immutable_manifest = {key: value for key, value in manifest.items()
            if key not in {"runtime_state", "age_seconds", "stale"}}
        analysis_response = await client.get("/api/briefing/latest")
        analysis_response.raise_for_status()
        analysis = analysis_response.json()
        if analysis.get("status") != "available" or not analysis.get("reports"):
            raise RuntimeError("An actual validated analysis artifact is required")
        immutable_analysis = {key: value for key, value in analysis.items()
            if key not in {"runtime_state", "age_seconds", "stale"}}
    return {"observed_at": datetime.now(timezone.utc).isoformat(), "container": identity,
        "database": database, "video": {"filename": filename, "sha256": digest.hexdigest(), "bytes": length,
            "manifest_sha256": canonical_hash(immutable_manifest)},
        "analysis_sha256": canonical_hash(immutable_analysis)}


def compare(before, after, *, expected_upgrade_image=None):
    if expected_upgrade_image is not None and not re.fullmatch(r'sha256:[a-f0-9]{64}',expected_upgrade_image):
        raise ValueError('Declare the qualified immutable image ID for an intentional upgrade')
    checks = {
        "nonempty_existing_sources_and_receipts_captured": bool(before["database"]["events"]) and bool(before["database"]["source_reports"]),
        "backend_start_changed": before["container"]["started_at"] != after["container"]["started_at"],
        "backend_image_unchanged": before["container"]["image"] == after["container"]["image"],
        "all_existing_event_raw_hashes_preserved": all(after["database"]["events"].get(key) == value
            for key, value in before["database"]["events"].items()),
        "all_existing_source_receipt_hashes_preserved": all(after["database"]["source_reports"].get(key) == value
            for key, value in before["database"]["source_reports"].items()),
        "checkpoints_preserved_or_advanced": all(after["database"]["checkpoints"].get(key, -1) >= value
            for key, value in before["database"]["checkpoints"].items()),
        "video_name_full_sha_size_and_manifest_preserved": before["video"] == after["video"],
        "analysis_artifact_preserved": before["analysis_sha256"] == after["analysis_sha256"],
    }
    if expected_upgrade_image is not None:
        checks.pop('backend_image_unchanged')
        checks['backend_matches_declared_upgrade_image']=after['container']['image']==expected_upgrade_image
    return {"scope": "coordinated_database_upgrade_existing_data_and_local_artifact_persistence" if expected_upgrade_image else "coordinated_backend_restart_existing_data_and_local_artifact_persistence",
        "status": "PASS" if all(checks.values()) else "FAIL/INCOMPLETE", "checks": checks,
        "before_at": before["observed_at"], "after_at": after["observed_at"],
        "backend_image": after["container"]["image"],
        "declared_upgrade_image": expected_upgrade_image,
        "events_before": len(before["database"]["events"]), "events_after": len(after["database"]["events"]),
        "source_receipts_before": len(before["database"]["source_reports"]),
        "source_receipts_after": len(after["database"]["source_reports"]),
        "source_hash_map_before_sha256": canonical_hash(before["database"]["events"]),
        "source_receipt_hash_map_before_sha256": canonical_hash(before["database"]["source_reports"]),
        "usage_rows_before": before["database"]["usage_rows"], "usage_rows_after": after["database"]["usage_rows"],
        "video": after["video"], "limitations": [
            "Byte persistence is not report truth, model correctness or listener audibility.",
            "New provider ingestion is allowed; only previously observed IDs are required to remain unchanged.",
            "Dynamic runtime/age/stale API fields are excluded from persisted artifact comparison.",
            "This helper never performs the restart; operator coordination is required."]}


async def main(args):
    if args.expected_upgrade_image and not args.before:
        raise ValueError('An intentional upgrade requires a preserved before snapshot')
    after = await capture(args.base_url, args.container)
    result = compare(json.loads(Path(args.before).read_text(encoding="utf8")), after,
        expected_upgrade_image=args.expected_upgrade_image) if args.before else after
    destination = Path(args.output)
    if destination.exists():
        raise ValueError("Preserve prior receipt; choose a fresh output filename")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2)+"\n", encoding="utf8")
    print(json.dumps({"output": str(destination), "status": result.get("status", "SNAPSHOT_CAPTURED")}))
    if args.before and result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5190")
    parser.add_argument("--container", default="cmonitor-live-backend-1")
    parser.add_argument("--before")
    parser.add_argument("--expected-upgrade-image")
    parser.add_argument("--output", required=True)
    asyncio.run(main(parser.parse_args()))

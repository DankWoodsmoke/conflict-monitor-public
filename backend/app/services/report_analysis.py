"""Operator-requested local proposals bound to one immutable source snapshot.

The bounded registry is process-local and intentionally disappears on restart.
It never updates an Event or overwrites the batch briefing artifact.
"""

import asyncio
import copy
import hashlib
import re
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.config import settings
from app.db import async_session
from app.models import Event
from app.services import local_briefing as local
from app.services.location_candidates import place_mentions
from app.services.runtime import runtime

CONTRACT = "selected-report-local-analysis-v1"
RETENTION_SECONDS = 3600
MAX_JOBS = 16
SOURCE_READ_TIMEOUT_SECONDS = 10
_jobs: dict[str, dict] = {}


class AnalysisDisabled(ValueError):
    pass


class AnalysisBusy(ValueError):
    pass


class SourceChanged(ValueError):
    pass


class SourceUnavailable(ValueError):
    pass


def _permission(event):
    if local.restricted_source(event):
        raise local.SourcePermissionRequired()
    reports = getattr(event, "reports", None)
    if reports is None:
        reports = []
    if not isinstance(reports, list) or len(reports) > 200:
        raise SourceUnavailable("Source provenance is unavailable")
    candidates = []
    for report in reports:
        if not isinstance(report, dict):
            raise SourceUnavailable("Source provenance is unavailable")
        candidates.extend([report, {"collector_source": report.get("source", "")}])
    local.ensure_artifact_source_permission({"reports": candidates})


def freeze_source(event):
    """Use raw source text only; an inherited generated summary is not evidence."""
    if event is None:
        raise SourceUnavailable("Source report is unavailable")
    _permission(event)
    if str(event.source or "") in {"demo", "synthetic", "simulation", "situational"}:
        raise SourceUnavailable("A real source report is required")
    now = local.clock()
    stamp = event.timestamp
    if not stamp or stamp.tzinfo is None or not (
        now - timedelta(hours=settings.briefing_max_age_hours) <= stamp <= now
    ):
        raise SourceUnavailable("Source report is stale, future dated or undated")
    raw = event.raw_text
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 12_000:
        raise SourceUnavailable("Raw source text is empty or oversized")
    from urllib.parse import urlsplit

    url = str(event.source_url or "")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise SourceUnavailable("A public source citation is required")
    source = {
        "id": event.id,
        "source": local.source_display_name(event),
        "source_platform": str(event.source or ""),
        "channel_name": str(event.channel_name or ""),
        "published_at": stamp.isoformat(),
        "source_url": url,
        "text": raw,
        "original_text_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }
    snapshot = [{**source, "text": raw[:2500], "text_truncated": len(raw) > 2500,
                 "headline": raw[:500]}]
    # Bind every retained report's provenance, including children not supplied to
    # the model, so a later merge/permission change cannot reuse this result.
    identity = local.canonical_hash({"source": source, "reports": getattr(event, "reports", None) or []})
    return {"source": source, "snapshot": snapshot, "identity": identity}


async def load_source(event_id):
    # Includes pool acquisition, SELECT and session cleanup. A timeout is an
    # availability failure, never evidence that the report itself changed.
    async with asyncio.timeout(SOURCE_READ_TIMEOUT_SECONDS):
        async with async_session() as session:
            event = (await session.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
            return freeze_source(event)


def _available():
    if not settings.enable_local_ai or settings.demo_mode:
        raise AnalysisDisabled("Local analysis is disabled")


def _busy():
    task = runtime.tasks.get("local_analysis")
    return local._lock.locked() or bool(task and not task.done())


def _prune():
    now = local.clock()
    for key, job in list(_jobs.items()):
        if job["status"] not in {"queued", "running"} and (now - job["_created"]).total_seconds() >= RETENTION_SECONDS:
            del _jobs[key]
    while len(_jobs) >= MAX_JOBS:
        oldest = next((key for key, job in _jobs.items() if job["status"] not in {"queued", "running"}), None)
        if oldest is None:
            raise AnalysisBusy("Local analysis retention is full")
        del _jobs[oldest]


def _public(job):
    return copy.deepcopy({key: value for key, value in job.items() if not key.startswith("_")})


def _terminal(job, status, error_type=None):
    job.pop("result", None)
    job.update(status=status, completed_at=local.clock().isoformat())
    if error_type:
        job["error_type"] = error_type


async def enqueue(event_id, expected_source_sha256):
    _available()
    if type(event_id) is not int or event_id <= 0 or not isinstance(expected_source_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_source_sha256):
        raise SourceUnavailable("A positive source ID and source SHA256 are required")
    if _busy():
        raise AnalysisBusy("A local analysis is already running")
    frozen = await load_source(event_id)
    if frozen["source"]["original_text_sha256"] != expected_source_sha256:
        raise SourceChanged("The selected source has changed")
    # No await between the second admission check and reservation of the task.
    _available()
    if _busy():
        raise AnalysisBusy("A local analysis is already running")
    _prune()
    now = local.clock()
    job_id = str(uuid4())
    job = {"job_id": job_id, "event_id": event_id, "source_sha256": expected_source_sha256,
           "status": "queued", "status_url": f"/report-analysis/jobs/{job_id}",
           "created_at": now.isoformat(), "retention_seconds": RETENTION_SECONDS,
           "_created": now, "_identity": frozen["identity"]}
    _jobs[job_id] = job
    coroutine = _run(job, frozen)
    try:
        task = runtime.start("local_analysis", coroutine)
        # Cancellation before the coroutine's first instruction otherwise leaves
        # a permanently queued record in the bounded registry.
        def finished(completed):
            if job["status"] in {"queued", "running"}:
                _terminal(job, "cancelled" if completed.cancelled() else "failed",
                          "CancelledError" if completed.cancelled() else "AnalysisIncomplete")
        task.add_done_callback(finished)
    except BaseException:
        coroutine.close()
        _jobs.pop(job_id, None)
        raise
    return _public(job)


async def _assert_current(job):
    current = await load_source(job["event_id"])
    if current["identity"] != job["_identity"]:
        raise SourceChanged("The selected source or its provenance has changed")


async def get_job(job_id):
    job = _jobs.get(job_id)
    if job is None:
        return None
    if job["status"] not in {"queued", "running"} and (local.clock() - job["_created"]).total_seconds() >= RETENTION_SECONDS:
        del _jobs[job_id]
        return None
    if job["status"] == "available":
        try:
            await _assert_current(job)
        except local.SourcePermissionRequired:
            _terminal(job, "source_permission_required", "SourcePermissionRequired")
        except (SourceChanged, SourceUnavailable):
            _terminal(job, "source_changed", "SourceChanged")
    return _public(job)


async def _run(job, frozen):
    attempted = False
    received = False
    provenance = None
    try:
        _available()
        if local._lock.locked():
            raise AnalysisBusy("A local analysis is already running")
        async with local._lock:
            job["status"] = "running"
            local._state.update(state="running", error_type=None, last_attempt_at=local.clock().isoformat())
            # Permission/provenance can change between queue admission and work.
            await _assert_current(job)
            attempted = True
            reports, provenance = await local.request_extraction(frozen["snapshot"])
            received = True
            await _assert_current(job)
            excerpt = frozen["snapshot"][0]["text"]
            result = {
                "contract_version": CONTRACT, "source": frozen["source"],
                "report": reports[0], "place_review": place_mentions(frozen["source"]["text"]),
                "provenance": provenance,
                "model_excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                "model_excerpt_characters": len(excerpt),
                "source_snapshot_sha256": local.canonical_hash(frozen["snapshot"]),
                "coordinates": None, "severity": None, "critical_alert_eligible": False,
                "mutates_events": False,
                "validation_scope": "exact_source_spans_and_identity; narrow_negation_guard",
                "semantic_entailment": "unreviewed; no factual or geographic verification",
            }
            local.record_local_call({"status": "validated", "generated_at": local.clock().isoformat(),
                "job_id": job["job_id"], "contract_version": CONTRACT,
                "inference_attempted": True, "model_response_received": True,
                "source_snapshot_sha256": result["source_snapshot_sha256"], "provenance": provenance})
            job.update(status="available", result=result, completed_at=local.clock().isoformat())
            local._state.update(state="ready", last_success_at=job["completed_at"])
    except (Exception, asyncio.CancelledError) as exc:
        status = "cancelled" if isinstance(exc, asyncio.CancelledError) else (
            "source_permission_required" if isinstance(exc, local.SourcePermissionRequired) else
            "source_changed" if isinstance(exc, (SourceChanged, SourceUnavailable)) else "failed")
        _terminal(job, status, type(exc).__name__)
        local._state.update(state="failed", error_type=type(exc).__name__)
        try:
            local.record_local_call({"status": status, "generated_at": local.clock().isoformat(),
                "job_id": job["job_id"], "contract_version": CONTRACT,
                "inference_attempted": attempted, "model_response_received": received,
                "model": settings.local_ai_model, "provenance": provenance,
                "error_type": type(exc).__name__})
        except Exception:
            pass
        if isinstance(exc, asyncio.CancelledError):
            raise

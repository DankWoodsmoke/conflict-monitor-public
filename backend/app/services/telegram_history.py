"""Opt-in, finite historical report collection with durable independent progress.

No model, media download, channel join or live checkpoint update is used. Source
receipts remain authoritative; a pending receipt never permits cursor advance.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import engine
from app.models import TelegramBackfillItem, TelegramBackfillJob
from app.services import telegram
from app.services.ingest_ledger import report_identity

UTC = timezone.utc
PAGE_LIMIT = 50
BATCH_SECONDS = 60
HISTORY_LOCK = 56182843097261030
JOBS = TelegramBackfillJob.__table__
ITEMS = TelegramBackfillItem.__table__


class HistoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    channel_name: str = Field(pattern=r"^@?[A-Za-z][A-Za-z0-9_]{3,31}$")
    start_at: datetime
    end_at: datetime
    max_messages: int = Field(default=200, strict=True, ge=1, le=5000)

    @field_validator("start_at", "end_at")
    @classmethod
    def aware_seconds(cls, value):
        if value.tzinfo is None or value.microsecond:
            raise ValueError("History boundaries require a timezone and whole-second precision")
        return value.astimezone(UTC)


class HistoryFailure(Exception):
    pass


def require_collection(channel=None):
    if not settings.live_ingestion_enabled or settings.demo_mode or settings.telegram_processing_mode != "reports":
        raise HTTPException(503, "Historical collection requires enabled, nonsynthetic report mode")
    if settings.telegram_transport != "session":
        raise HTTPException(503, "Historical collection requires the explicitly enabled session transport")
    try:
        channels = telegram._get_channels()
    except ValueError:
        raise HTTPException(503, "Selected public channels are invalid")
    if channel is not None and channel not in channels:
        raise HTTPException(403, "History is limited to explicitly selected public channels")


def request_values(request: HistoryRequest, *, now=None):
    channel = request.channel_name.lstrip("@").lower()
    require_collection(channel)
    now = now or datetime.now(UTC)
    if not telegram._get_conflict_cutoff() <= request.start_at < request.end_at <= now:
        raise HTTPException(422, "Require configured cutoff <= start < end <= now")
    if request.end_at - request.start_at > timedelta(days=31):
        raise HTTPException(422, "One history job is limited to 31 days")
    canonical = {"channel_name": channel, "start_at": request.start_at.isoformat(),
                 "end_at": request.end_at.isoformat(), "max_messages": request.max_messages}
    return {"id": str(request.request_id), "request_hash": hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()).hexdigest(),
        **canonical, "start_at": request.start_at, "end_at": request.end_at,
        "status": "queued", "cursor_message_id": 0, "processed_messages": 0, "outcomes": {}}


def public_job(job):
    return {**job, "requested_window_complete": job["status"] == "completed",
        "history_complete": False, "batch_limit": PAGE_LIMIT, "batch_timeout_seconds": BATCH_SECONDS,
        "scope": "Selected public channel; provider-visible source-publication window [start,end), frozen upper message ID. Not incident chronology or complete platform history.",
        "live_checkpoint_mutated": False,
        "limitations": ["Deleted, unavailable, edited and provider-omitted messages are not reconstructed.",
            "Report ingestion does not establish factual truth, precise location, independence or redistribution/AI permission.",
            "Pending source receipts pause progress; successful HTTP alone is not historical completion."]}


async def create_job(request):
    values = request_values(request)
    async with engine.begin() as connection:
        await connection.execute(pg_insert(JOBS).values(**values).on_conflict_do_nothing(index_elements=[JOBS.c.id]))
        job = dict((await connection.execute(select(JOBS).where(JOBS.c.id == values["id"]))).mappings().one())
        if job["request_hash"] != values["request_hash"]:
            raise HTTPException(409, "request_id is already bound to different history parameters")
    return public_job(job)


async def get_job(job_id):
    async with engine.connect() as connection:
        row = (await connection.execute(select(JOBS).where(JOBS.c.id == str(job_id)))).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "History job not found")
    return public_job(dict(row))


async def list_jobs():
    async with engine.connect() as connection:
        rows = (await connection.execute(select(JOBS).order_by(JOBS.c.created_at.desc(), JOBS.c.id).limit(50))).mappings().all()
    return [public_job(dict(row)) for row in rows]


def _message_id(message):
    value = getattr(message, "id", None)
    if type(value) is not int or not 0 < value < 2**63 - 1:
        raise HistoryFailure("InvalidMessageIdentity")
    return value


def _receipt_item(job, message, outcome, source_identity=None):
    raw = str(getattr(message, "text", "") or "")
    stamp = getattr(message, "date", None)
    return {"job_id": job["id"], "message_id": message.id,
        "content_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "source_report_identity": source_identity, "outcome": outcome,
        "source_timestamp": stamp if isinstance(stamp, datetime) and stamp.tzinfo else None}


async def _finish_cleanup(awaitable):
    """Do not return a connection while its shielded cleanup still uses it."""
    task = asyncio.create_task(awaitable)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


async def run_page(job, client, persist):
    """One bounded provider page. Persist item+cursor together after source commit."""
    if job["status"] in {"completed", "budget_exhausted"}:
        return
    require_collection(job["channel_name"])
    job.update(status="running", last_error_type=None, blocked_message_id=None, completed_at=None)
    await persist(job)
    try:
        async with asyncio.timeout(BATCH_SECONDS):
            entity = await client.get_entity(job["channel_name"])
            entity_id = getattr(entity, "id", None)
            if (type(entity_id) is not int or entity_id <= 0 or
                getattr(entity, "broadcast", False) is not True or
                (getattr(entity, "username", "") or "").lower() != job["channel_name"]):
                raise HistoryFailure("PublicChannelIdentityMismatch")
            if job["source_entity_id"] not in {None, entity_id}:
                raise HistoryFailure("PublicChannelIdentityChanged")
            if job["source_entity_id"] is None:
                job["source_entity_id"] = entity_id
                await persist(job)
            if job["upper_message_id"] is None:
                fence = None
                async for message in client.iter_messages(entity, limit=1, offset_date=job["end_at"], wait_time=0):
                    fence = _message_id(message)
                    stamp = getattr(message, "date", None)
                    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp >= job["end_at"]:
                        raise HistoryFailure("InvalidUpperFenceTime")
                    break
                job["upper_message_id"] = fence or 0
                await persist(job)
            if job["upper_message_id"] == 0 or job["cursor_message_id"] >= job["upper_message_id"]:
                job.update(status="completed", completed_at=datetime.now(UTC))
                await persist(job)
                return
            remaining = job["max_messages"] - job["processed_messages"]
            if remaining <= 0:
                job["status"] = "budget_exhausted"
                await persist(job)
                return
            limit = min(PAGE_LIMIT, remaining)
            options = {"limit": limit, "reverse": True, "min_id": job["cursor_message_id"],
                       "max_id": job["upper_message_id"] + 1, "wait_time": 0}
            if job["cursor_message_id"] == 0:
                # Telegram offsets are exclusive and second-granular.
                options["offset_date"] = job["start_at"] - timedelta(seconds=1)
            seen = 0
            async for message in client.iter_messages(entity, **options):
                message_id = _message_id(message)
                if not job["cursor_message_id"] < message_id <= job["upper_message_id"]:
                    raise HistoryFailure("MessageOutsideFrozenIdOrder")
                stamp = getattr(message, "date", None)
                raw = str(getattr(message, "text", "") or "")
                source_identity = None
                if isinstance(stamp, datetime) and stamp.tzinfo and not job["start_at"] <= stamp < job["end_at"]:
                    outcome = "outside_requested_window"
                else:
                    outcome = await telegram._process_report_message(raw, job["channel_name"], stamp,
                        message_id)
                    if outcome == "pending_receipt":
                        job.update(status="paused", last_error_type="PendingSourceReceipt", blocked_message_id=message_id)
                        await persist(job)
                        return
                    if outcome not in telegram.REPORT_TERMINAL_OUTCOMES:
                        raise HistoryFailure("NonterminalSourceOutcome")
                    if outcome != "no_text_or_caption":
                        source_identity = report_identity({"source": "telegram", "channel_name": job["channel_name"],
                            "telegram_message_id": message_id, "source_url": telegram._build_source_url(job["channel_name"], message_id),
                            "raw_text": raw})[0]
                next_job = {**job, "outcomes": {**job["outcomes"]}}
                next_job["cursor_message_id"] = message_id
                next_job["processed_messages"] += 1
                next_job["outcomes"][outcome] = next_job["outcomes"].get(outcome, 0) + 1
                await persist(next_job, _receipt_item(job, message, outcome, source_identity))
                job.update(next_job)
                seen += 1
                if seen >= limit:  # Enforce the bound even if a provider ignores it.
                    break
            if seen < limit or job["cursor_message_id"] >= job["upper_message_id"]:
                job.update(status="completed", completed_at=datetime.now(UTC))
            elif job["processed_messages"] >= job["max_messages"]:
                job["status"] = "budget_exhausted"
            else:
                job["status"] = "paused"
            await persist(job)
    except asyncio.CancelledError:
        job.update(status="paused", last_error_type="Cancelled")
        await _finish_cleanup(persist(job, status_only=True))
        raise
    except Exception as error:
        reason = str(error) if isinstance(error, HistoryFailure) else type(error).__name__
        job.update(status="paused", last_error_type=reason[:80])
        await persist(job, status_only=True)


async def _persist_progress(connection, job_id, value, item=None, *, status_only=False):
    # A commit may succeed before cancellation/lost acknowledgement reaches this
    # task. Error handlers must never write their older in-memory cursor back.
    keys = ("status", "last_error_type", "blocked_message_id", "completed_at")
    if not status_only:
        keys += ("source_entity_id", "upper_message_id", "cursor_message_id",
                 "processed_messages", "outcomes")
    fields = {key: value[key] for key in keys}
    fields["updated_at"] = datetime.now(UTC)
    try:
        if item is not None:
            if status_only:
                raise ValueError("Status-only recovery cannot insert a progress receipt")
            await connection.execute(insert(ITEMS).values(**item))
        row = (await connection.execute(update(JOBS).where(JOBS.c.id == job_id)
            .values(**fields).returning(JOBS))).mappings().one()
        await connection.commit()
    except BaseException:
        await connection.rollback()
        raise
    # Refresh after a status-only recovery to reflect any acknowledged or
    # previously unacknowledged durable progress, including the frozen fence.
    value.update(dict(row))


async def run_job(job_id):
    require_collection()
    client = telegram._shared_client
    if client is None or not client.is_connected():
        raise HTTPException(503, "Telegram listener is not connected")
    async with engine.connect() as connection:
        locked = False
        try:
            locked = bool((await connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": HISTORY_LOCK})).scalar_one())
            await connection.commit()  # Dedicated connection retains session lock.
            if not locked:
                raise HTTPException(409, "Another historical page is already running")
            row = (await connection.execute(select(JOBS).where(JOBS.c.id == str(job_id)))).mappings().one_or_none()
            await connection.commit()
            if row is None:
                raise HTTPException(404, "History job not found")
            job = dict(row)

            async def persist(value, item=None, *, status_only=False):
                await _persist_progress(connection, job["id"], value, item, status_only=status_only)

            await run_page(job, client, persist)
            return public_job(job)
        finally:
            # Also release when cancellation arrives after PostgreSQL acquired
            # the lock but before Python received the SELECT result.
            async def unlock():
                try:
                    await connection.rollback()
                    await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": HISTORY_LOCK})
                    await connection.commit()
                except BaseException:
                    await connection.invalidate()
                    raise
            await _finish_cleanup(unlock())

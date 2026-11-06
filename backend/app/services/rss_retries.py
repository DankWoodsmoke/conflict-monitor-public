"""Bounded free-RSS due queue; never rewrite source text or publication clocks."""
from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.db import async_session
from app.models import SourceReport, SourceReportRetry
from app.services.ingest_ledger import report_identity

LEASE_SECONDS = 120
MAX_PER_FEED = 2
DATABASE_TIMEOUT_SECONDS = 10
# Same strict lexical form is used by the migration before pg_input_is_valid.
SOURCE_CLOCK_PATTERN = r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(Z|[+-]((0[0-9]|1[0-3]):[0-5][0-9]|14:00))$"
_CLOCK = re.compile(SOURCE_CLOCK_PATTERN)
_TERMINAL = frozenset({"reported", "recovered", "duplicate", "source_revision_needs_review",
    "invalid_source_metadata", "input_too_large", "undated_source", "invalid_retry_source"})
_health: dict[str, dict] = {}


def parse_source_clock(value):
    if not isinstance(value, str) or not _CLOCK.fullmatch(value):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not 1970 <= stamp.year <= 9998:
            return None
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def supported_report(report, identity=None, content_hash=None):
    if not isinstance(report, dict):
        return False
    channel = report.get("channel_name")
    if (not isinstance(channel, str) or not 1 <= len(channel) <= 255
        or report.get("source") != "rss_" + channel
        or report.get("processing_mode") != "publisher_metadata"
        or report.get("classification_status") != "not_requested"
        or not isinstance(report.get("raw_text"), str) or len(report["raw_text"]) > 12000 or report.get("raw_text_truncated")
        or not isinstance(report.get("summary"), str) or not report["summary"].strip()
        or not isinstance(report.get("source_url"), str) or not isinstance(report.get("feed_context"), dict)
        or parse_source_clock(report.get("timestamp")) is None):
        return False
    actual = report_identity(report)
    return (identity is None or actual[0] == identity) and (content_hash is None or actual[1] == content_hash)


async def defer_report(identity, report):
    """Commit future outcome and schedule atomically, validating original bytes."""
    if not supported_report(report, identity):
        raise ValueError("Unsupported deferred source snapshot")
    due = parse_source_clock(report["timestamp"])
    async with asyncio.timeout(DATABASE_TIMEOUT_SECONDS), async_session() as session, session.begin():
        row = (await session.execute(select(SourceReport).where(SourceReport.identity == identity)
                                    .with_for_update())).scalar_one()
        if row.report != report or not supported_report(row.report, identity, row.content_hash):
            raise ValueError("Deferred receipt differs from original snapshot")
        if row.status not in {"received", "pending_receipt", "retryable_error", "provider_error",
                              "unavailable", "disabled", "invalid", "future_source_time"}:
            raise ValueError("Deferred source outcome changed")
        row.status = "future_source_time"
        await session.execute(insert(SourceReportRetry).values(identity=identity,
            source_name=report["channel_name"], due_at=due, next_attempt_at=due)
            .on_conflict_do_nothing(index_elements=[SourceReportRetry.identity]))


@dataclass(frozen=True)
class RetryItem:
    identity: str
    token: str
    source_name: str
    due_at: datetime
    attempts: int
    report: dict
    content_hash: str


async def claim_due(source_name, limit, now):
    limit = max(0, min(MAX_PER_FEED, int(limit)))
    if not limit:
        return []
    async with asyncio.timeout(DATABASE_TIMEOUT_SECONDS), async_session() as session, session.begin():
        rows = (await session.execute(select(SourceReportRetry, SourceReport).join(SourceReport,
            SourceReport.identity == SourceReportRetry.identity).where(
                SourceReportRetry.source_name == source_name, SourceReportRetry.finished_at.is_(None),
                SourceReportRetry.next_attempt_at <= now, SourceReportRetry.due_at <= now)
            .order_by(SourceReportRetry.next_attempt_at, SourceReportRetry.identity).limit(limit)
            .with_for_update(of=SourceReportRetry, skip_locked=True))).all()
        items = []
        for queue, receipt in rows:
            token = str(uuid4())
            queue.attempts += 1
            queue.claim_token = token
            queue.last_attempt_at = now
            queue.next_attempt_at = now + timedelta(seconds=LEASE_SECONDS)
            queue.last_outcome, queue.last_error_type = "claimed", None
            items.append(RetryItem(queue.identity, token, queue.source_name, queue.due_at,
                queue.attempts, copy.deepcopy(receipt.report), receipt.content_hash))
        return items


async def finish_attempt(item, outcome, now, error_type=None):
    terminal = outcome in _TERMINAL
    delay = min(3600, 60 * 2 ** min(max(item.attempts - 1, 0), 6))
    values = dict(last_outcome=outcome, last_error_type=error_type, claim_token=None,
                  next_attempt_at=now + timedelta(seconds=delay))
    if terminal:
        values["finished_at"] = now
    async with asyncio.timeout(DATABASE_TIMEOUT_SECONDS), async_session() as session, session.begin():
        result = await session.execute(update(SourceReportRetry).where(
            SourceReportRetry.identity == item.identity, SourceReportRetry.claim_token == item.token,
            SourceReportRetry.finished_at.is_(None)).values(**values))
        return result.rowcount == 1


async def refresh_status(source_name, now):
    async with asyncio.timeout(DATABASE_TIMEOUT_SECONDS), async_session() as session:
        row = (await session.execute(select(func.count(),
            func.count().filter(SourceReportRetry.next_attempt_at <= now, SourceReportRetry.due_at <= now),
            func.min(SourceReportRetry.due_at), func.min(SourceReportRetry.next_attempt_at))
            .where(SourceReportRetry.source_name == source_name, SourceReportRetry.finished_at.is_(None)))).one()
    _health[source_name] = {"status": "ok", "observed_at": now.isoformat(),
        "pending": row[0], "eligible_now": row[1], "oldest_original_due_at": row[2].isoformat() if row[2] else None,
        "next_attempt_at": row[3].isoformat() if row[3] else None, "error_type": None}


def failed_status(source_name, now, error):
    _health[source_name] = {**_health.get(source_name, {}), "status": "failed",
        "last_attempt_at": now.isoformat(), "error_type": type(error).__name__}


def get_status(source_names, enabled):
    return {"enabled": enabled, "max_per_feed_per_cycle": MAX_PER_FEED,
        "claim_lease_seconds": LEASE_SECONDS, "retry_backoff_max_seconds": 3600,
        "expiry_policy": "Claims expire; source records and original clocks are never expired or rewritten.",
        "sources": {name: dict(_health.get(name, {"status": "not_checked"})) for name in source_names},
        "limitations": ["Only selected free RSS source snapshots with supported explicit timezone clocks are eligible.",
            "Publisher clock corrections remain unreviewed; a later feed timestamp cannot replace the original.",
            "Queue health and replay do not establish factual truth or complete publisher history."]}

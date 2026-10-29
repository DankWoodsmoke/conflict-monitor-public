"""Persist source content before extraction. Failed work remains inspectable."""
import hashlib
import json
import re
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from app.db import async_session
from app.models import SourceReport


def report_identity(report: dict) -> tuple[str, str]:
    content_hash = hashlib.sha256(report.get("raw_text", "").encode("utf-8")).hexdigest()
    if report.get("raw_text_truncated"):
        original_hash = report.get("original_text_sha256")
        if not isinstance(original_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", original_hash):
            raise ValueError("Truncated reports require the adapter-computed original content hash")
        # The retained prefix is not the original content identity. Distinct
        # oversized originals can share every retained byte and must not collide.
        content_hash = original_hash.lower()
    identity = [report.get("source"), report.get("channel_name"),
        report.get("telegram_message_id"), report.get("source_url"), content_hash]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest(), content_hash


async def capture_report(report: dict) -> str | None:
    """An edited source is a new immutable revision. Duplicate delivery is idempotent."""
    identity, content_hash = report_identity(report)
    stored_report = report
    if report.get("raw_text_truncated"):
        stored_report = {**report, "stored_raw_sha256": hashlib.sha256(
            report.get("raw_text", "").encode("utf-8")).hexdigest()}
    async with async_session() as session:
        row = await session.execute(insert(SourceReport).values(
            identity=identity, content_hash=content_hash, report=stored_report, status="received"
        ).on_conflict_do_nothing(index_elements=[SourceReport.identity]).returning(SourceReport.identity))
        created = row.scalar_one_or_none()
        await session.commit()
        return created


async def finish_report(identity: str, status: str, event_id: int | None = None):
    async with async_session() as session:
        await session.execute(update(SourceReport).where(SourceReport.identity == identity).values(
            status=status, event_id=event_id))
        await session.commit()

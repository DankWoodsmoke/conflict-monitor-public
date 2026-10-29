"""Free attributed source compilation; no model, causal or severity inference."""
import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from app.db import async_session
from app.models import Event, Sitrep

logger = logging.getLogger(__name__)
_lock = asyncio.Lock()


def build_source_digest(events, *, generated_at=None):
    """Keep publisher text inside an explicitly attributed report list."""
    stamp = generated_at or datetime.now(timezone.utc)
    snapshot = []
    for event in events:
        if event.source in {"demo", "synthetic", "simulation", "situational"}:
            continue
        summary = re.sub(r"\s+", " ", str(event.summary or event.raw_text or "")).strip()
        # A publisher's citation-looking token is source text, never our link.
        summary = re.sub(r"\[src:[^\]]*\]", "[source citation text]", summary, flags=re.I)[:500]
        if not summary:
            continue
        snapshot.append({"id": event.id, "source": str(event.channel_name or event.source),
            "summary": summary, "source_url": str(event.source_url or ""),
            "published_at": event.timestamp.isoformat(),
            "raw_sha256": hashlib.sha256(str(event.raw_text or "").encode("utf-8")).hexdigest()})
    if not snapshot:
        return None
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    source_count = len({row["source"] for row in snapshot})
    return {
        "headline": f"Source digest · {len(snapshot)} reports from {source_count} publisher labels",
        "situation": "\n".join(f"• {row['source']} reports: {row['summary']} [src:{row['id']}]" for row in snapshot),
        "escalation_text": "No automated risk assessment has been made. Reporting volume does not establish conflict intensity.",
        "economic_exposure": "", "humanitarian_ground": "", "game_theory": "", "historical_analogue": "",
        "key_questions": json.dumps([
            {"q": "Which claims have independent corroboration?", "a": "Not assessed by this compilation.", "watch": "Inspect the original source and its underlying evidence."},
            {"q": "When did the described events occur?", "a": "The listed times are publisher timestamps; event time may differ.", "watch": "Look for dated primary evidence or a source correction."},
        ]),
        "key_event_ids": ",".join(str(row["id"]) for row in snapshot),
        "events_analyzed": len(snapshot),
        "raw_response": json.dumps({"_provenance": {
            "contract_version": "source-digest-v1", "model": None,
            "method": "attributed_report_compilation", "generated_at": stamp.isoformat(),
            "validation_scope": "source_id_membership_and_exact_compilation",
            "semantic_entailment": "not_claimed; source statements are attributed",
            "source_snapshot_sha256": digest, "source_snapshot": snapshot}}, ensure_ascii=False),
    }


async def generate_source_digest(max_reports=12):
    if not 1 <= max_reports <= 50:
        raise ValueError("max_reports must be between 1 and 50")
    async with _lock:
        async with async_session() as session:
            rows = await session.execute(select(Event).where(
                Event.source.not_in(["demo", "synthetic", "simulation", "situational"]),
                Event.timestamp >= datetime.now(timezone.utc) - timedelta(hours=24),
            ).order_by(Event.timestamp.desc(), Event.id.desc()).limit(max_reports))
            data = build_source_digest(rows.scalars().all())
            if data is None:
                return {"status": "no_reports", "sitrep_id": None}
            prior = await session.execute(select(Sitrep).where(Sitrep.trigger == "source_digest")
                .order_by(Sitrep.generated_at.desc(), Sitrep.id.desc()).limit(1))
            previous = prior.scalar_one_or_none()
            if previous:
                try:
                    previous_raw = previous.raw_response or "{}"
                    if not isinstance(previous_raw, str) or len(previous_raw) > 2_000_000:
                        raise ValueError("Legacy digest exceeds parse budget")
                    old = json.loads(previous_raw)["_provenance"]["source_snapshot_sha256"]
                    new = json.loads(data["raw_response"])["_provenance"]["source_snapshot_sha256"]
                    if old == new:
                        return {"status": "unchanged", "sitrep_id": previous.id}
                except (ValueError, KeyError, TypeError, RecursionError):
                    pass
            row = Sitrep(trigger="source_digest", escalation_level="UNASSESSED", escalation_score=0, **data)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return {"status": "created", "sitrep_id": row.id}


async def start_source_digest():
    await asyncio.sleep(10)
    while True:
        try:
            await generate_source_digest()
        except Exception as exc:
            logger.warning("Source digest unavailable (%s)", type(exc).__name__)
        await asyncio.sleep(300)

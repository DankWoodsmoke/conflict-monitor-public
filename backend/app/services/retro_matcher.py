"""Retrospective match candidates for review, without destructive auto-merges.

Historical network-pair and Jaccard rules erased contradictory source records.
This pass now preserves every event and exposes bounded, explicitly unreviewed
suggestions. Similarity is not corroboration.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from app.services.dedup import _normalize, _jaccard
from app.services.evidence import compatible_claims, valid_coordinates

logger = logging.getLogger(__name__)
_last_candidates: list[dict] = []
_checked_at: str = ""


def _distance_km(a, b):
    import math
    lat1, lat2 = math.radians(float(a.lat)), math.radians(float(b.lat))
    dlat = lat2 - lat1
    dlon = math.radians(float(b.lon) - float(a.lon))
    term = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(max(0, min(1, term))))


def find_review_candidates(events) -> list[dict]:
    candidates = []
    for i, a in enumerate(events):
        if not a.timestamp or not valid_coordinates(a.lat, a.lon):
            continue
        for b in events[i + 1:]:
            if a.event_type != b.event_type or not b.timestamp or not valid_coordinates(b.lat, b.lon):
                continue
            ta = a.timestamp.replace(tzinfo=timezone.utc) if a.timestamp.tzinfo is None else a.timestamp
            tb = b.timestamp.replace(tzinfo=timezone.utc) if b.timestamp.tzinfo is None else b.timestamp
            hours = abs((ta - tb).total_seconds()) / 3600
            if hours > 6:
                continue
            similarity = _jaccard(_normalize(a.summary), _normalize(b.summary))
            if similarity < .5:
                continue
            distance = _distance_km(a, b)
            if distance > 10:
                continue
            candidates.append({
                "event_ids": [a.id, b.id], "similarity": round(similarity, 4),
                "distance_km": round(distance, 3), "time_difference_hours": round(hours, 3),
                "status": "needs_review",
                "polarity_or_numeric_conflict": not compatible_claims(a.summary, b.summary),
                "verification": "unassessed",
            })
    return sorted(candidates, key=lambda c: (-c["similarity"], c["event_ids"]))[:200]


def get_retro_candidates() -> dict:
    return {"candidates": list(_last_candidates), "checked_at": _checked_at,
            "automatic_merges": 0, "scope": "lexical_spatiotemporal_review_candidates"}


async def run_retro_match() -> int:
    from sqlalchemy import select
    from app.db import async_session
    from app.models import Event
    global _last_candidates, _checked_at
    cutoff = datetime.now(timezone.utc) - timedelta(hours=8)
    async with async_session() as session:
        result = await session.execute(select(Event).where(
            Event.timestamp >= cutoff, Event.report_count > 0,
        ).order_by(Event.timestamp.desc(), Event.id.desc()).limit(400))
        events = list(result.scalars().all())
    _last_candidates = find_review_candidates(events)
    _checked_at = datetime.now(timezone.utc).isoformat()
    logger.info("Retro review: %d candidates from %d events; no sources merged or confirmed",
                len(_last_candidates), len(events))
    return 0


async def start_retro_matcher():
    await asyncio.sleep(300)
    while True:
        try:
            await run_retro_match()
        except Exception:
            logger.exception("Retro review scan failed")
        await asyncio.sleep(7200)

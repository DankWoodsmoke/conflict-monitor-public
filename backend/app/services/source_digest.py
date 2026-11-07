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
DIGEST_CONTRACT = "source-digest-v2"
DIGEST_METHOD = "attributed_report_compilation"


def digest_source_excerpt(event):
    """Project stored source text and its clock, never an analysis summary."""
    raw = event.raw_text or ""
    text = re.sub(r"\s+", " ", raw).strip()
    # Citation-looking tokens in source-controlled text cannot create our links.
    text = re.sub(r"\[src:[^\]]*\]", "[source citation text]", text, flags=re.I)
    stamp = event.timestamp.isoformat() if event.timestamp else None
    raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    source_kind = "source_report"
    time_basis = "source_time_unknown_basis"
    if event.source == "satellite_firms":
        source_kind = "thermal_observation"
        time_basis = "sensor_acquisition_time"
    elif event.source == "telegram":
        time_basis = "source_publication_time"
    elif str(event.source or "").startswith("rss_"):
        for report in getattr(event, "reports", None) or []:
            if not isinstance(report, dict) or report.get("content_sha256") != raw_hash or report.get("published_at") != stamp:
                continue
            context = report.get("feed_context")
            basis = context.get("source_time_basis") if isinstance(context, dict) else None
            if basis in {"source_publication_time", "source_updated_time"}:
                time_basis = basis
                break
    return {"summary": text[:499] + "…" if len(text) > 500 else text,
            "source_kind": source_kind, "source_time": stamp,
            "source_time_basis": time_basis if stamp else "unknown", "raw_sha256": raw_hash}


def build_source_digest(events, *, generated_at=None):
    """Compile bounded source excerpts and distinguish sensor observations."""
    stamp = generated_at or datetime.now(timezone.utc)
    snapshot = []
    for event in events:
        if event.source in {"demo", "synthetic", "simulation", "situational"}:
            continue
        source = digest_source_excerpt(event)
        if not source["summary"]:
            continue
        snapshot.append({"id": event.id, "source": str(event.channel_name or event.source), **source,
            "source_url": str(event.source_url or "")})
    if not snapshot:
        return None
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    source_count = len({row["source"] for row in snapshot})
    return {
        "headline": f"Source digest · {len(snapshot)} records from {source_count} source labels",
        "situation": "\n".join(
            f"• {row['source']} · "
            f"{'thermal observation (cause unassessed)' if row['source_kind'] == 'thermal_observation' else 'source excerpt'}: "
            f"{row['summary']} [src:{row['id']}]" for row in snapshot),
        "escalation_text": "No automated risk assessment has been made. Reporting volume does not establish conflict intensity.",
        "economic_exposure": "", "humanitarian_ground": "", "game_theory": "", "historical_analogue": "",
        "key_questions": json.dumps([
            {"q": "Which claims have independent corroboration?", "a": "Not assessed by this compilation.", "watch": "Inspect the original source and its underlying evidence."},
            {"q": "When did the described events occur?",
             "a": "Source publication, update and sensor acquisition clocks do not establish incident time. Some source clocks have unknown basis.",
             "watch": "Look for dated primary evidence or a source correction."},
        ]),
        "key_event_ids": ",".join(str(row["id"]) for row in snapshot),
        "events_analyzed": len(snapshot),
        "raw_response": json.dumps({"_provenance": {
            "contract_version": DIGEST_CONTRACT, "model": None,
            "method": DIGEST_METHOD, "generated_at": stamp.isoformat(),
            "validation_scope": "source_id_membership_and_bounded_raw_excerpts",
            "semantic_entailment": "not_claimed; source text and thermal observations have separate labels",
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
                    prior_provenance = json.loads(previous_raw)["_provenance"]
                    old = prior_provenance["source_snapshot_sha256"]
                    new = json.loads(data["raw_response"])["_provenance"]["source_snapshot_sha256"]
                    if prior_provenance.get("contract_version") == DIGEST_CONTRACT and old == new:
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

"""GET /sitreps — SITREP history, latest, source events."""
import json as _json

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select, text

from app.db import async_session
from app.security import require_admin_key
from app.models import Sitrep, Event

router = APIRouter(prefix="/sitreps", tags=["sitreps"])


def _parse_questions(raw):
    if raw is not None and (not isinstance(raw, str) or len(raw) > 100000):
        return [], "invalid_legacy_length"
    try:
        data = _json.loads(raw or "[]")
    except (ValueError, TypeError, RecursionError):
        return [], "invalid_legacy_json"
    if not isinstance(data, list):
        return [], "invalid_legacy_shape"
    valid = []
    for row in data[:20]:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("q", "a", "watch")):
            return [], "invalid_legacy_shape"
        valid.append({key: row[key][:2000] for key in ("q", "a", "watch")})
    return valid, "available" if len(data) <= 20 else "truncated_legacy_questions"


def _parse_ids(raw):
    if not isinstance(raw, str) or len(raw) > 100000:
        return [], "invalid_legacy_shape"
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    valid = list(dict.fromkeys(int(part) for part in parts[:160] if part.isascii() and part.isdigit() and len(part) <= 19 and 0 < int(part) < 2**63))[:80]
    return valid, "available" if len(valid) == len(parts) else "incomplete_legacy_references"


def _sitrep_to_dict(s: Sitrep) -> dict:
    free = s.trigger == "source_digest"
    questions, question_status = _parse_questions(s.key_questions)
    ids, reference_status = _parse_ids(s.key_event_ids)
    provenance = {}
    provenance_status = "unavailable"
    try:
        raw_response = s.raw_response or "{}"
        if not isinstance(raw_response, str) or len(raw_response) > 2_000_000:
            raise ValueError("Legacy provenance exceeds parse budget")
        stored = _json.loads(raw_response).get("_provenance", {})
        if isinstance(stored, dict):
            for key in ("contract_version", "model", "method", "validation_scope", "semantic_entailment", "source_snapshot_sha256"):
                if key in stored and isinstance(stored[key], (str, type(None))):
                    provenance[key] = stored.get(key)
            if provenance:
                provenance_status = "available"
        else:
            provenance_status = "invalid_legacy_shape"
    except (ValueError, TypeError, AttributeError, RecursionError):
        provenance_status = "invalid_legacy_provenance"
    return {
        "analysis_status": "attributed_source_digest" if free else "model_generated_unreviewed",
        "provenance": provenance, "provenance_status": provenance_status,
        "question_status": question_status, "source_reference_status": reference_status,
        "source_reference_scope": "stored_identifier_syntax; resolve source cards to check availability",
        "id": s.id, "generated_at": s.generated_at.isoformat() if s.generated_at else None,
        "trigger": s.trigger, "events_analyzed": s.events_analyzed,
        "headline": s.headline, "situation": s.situation, "escalation_text": s.escalation_text,
        "escalation_level": "UNASSESSED" if free else s.escalation_level,
        "escalation_score": None if free else getattr(s, "escalation_score", None),
        "economic_exposure": s.economic_exposure, "game_theory": s.game_theory,
        "humanitarian_ground": s.humanitarian_ground, "historical_analogue": s.historical_analogue,
        "key_questions": questions, "key_event_ids": ids,
    }


def _event_to_source(e: Event) -> dict:
    """Minimal source card for attribution display."""
    # Derive a display network from source string
    src = e.source or ""
    ch  = e.channel_name or ""
    if src.startswith("x_") or "twitter" in src:
        network = "X"
    elif src.startswith("tg_") or src.startswith("telegram"):
        network = "TG"
    elif src.startswith("rss_"):
        network = "RSS"
    else:
        network = src.upper()[:6]

    return {
        "id":                e.id,
        "source":            src,
        "channel_name":      ch,
        "network":           network,
        "summary":           (e.summary or "")[:280],
        "source_url":        e.source_url or "",
        "severity":          e.severity,
        "event_type":        e.event_type or "",
        "location_name":     e.location_name or "",
        "timestamp":         e.timestamp.isoformat() if e.timestamp else None,
        "reporting_channels": e.reporting_channels or "",
        "confirmed_networks": e.confirmed_networks or "",
        "source_reliability": e.source_reliability,
    }


@router.get("/latest")
async def get_latest_sitrep():
    async with async_session() as session:
        result = await session.execute(
            select(Sitrep).order_by(Sitrep.generated_at.desc()).limit(1)
        )
        sitrep = result.scalar_one_or_none()
        if sitrep is None:
            return {"sitrep": None}
        return {"sitrep": _sitrep_to_dict(sitrep)}


@router.get("/")
async def list_sitreps(limit: int = Query(20, ge=1, le=50)):
    async with async_session() as session:
        result = await session.execute(
            select(Sitrep).order_by(Sitrep.generated_at.desc()).limit(min(limit, 50))
        )
        sitreps = result.scalars().all()
        fields = {"id", "generated_at", "trigger", "events_analyzed", "headline", "escalation_level",
                  "escalation_score", "key_event_ids", "analysis_status", "provenance", "provenance_status", "source_reference_status", "source_reference_scope"}
        return [{key: value for key, value in _sitrep_to_dict(s).items() if key in fields} for s in sitreps]


@router.get("/{sitrep_id}")
async def get_sitrep(sitrep_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Sitrep).where(Sitrep.id == sitrep_id)
        )
        sitrep = result.scalar_one_or_none()
        if sitrep is None:
            raise HTTPException(status_code=404, detail="SITREP not found")
        return {"sitrep": _sitrep_to_dict(sitrep)}


@router.get("/{sitrep_id}/events")
async def get_sitrep_events(sitrep_id: int):
    """Return the key source events that drove this SITREP's analysis."""
    async with async_session() as session:
        # Get sitrep
        result = await session.execute(
            select(Sitrep).where(Sitrep.id == sitrep_id)
        )
        sitrep = result.scalar_one_or_none()
        if sitrep is None:
            raise HTTPException(status_code=404, detail="SITREP not found")

        key_ids, reference_status = _parse_ids(sitrep.key_event_ids)
        if not key_ids:
            return {"events": [], "sitrep_id": sitrep_id, "total": 0,
                    "source_reference_status": reference_status, "missing_source_ids": []}

        # Fetch those events
        result = await session.execute(
            select(Event).where(Event.id.in_(key_ids))
        )
        events = result.scalars().all()

        # Sort by original key_ids order (most important first)
        id_order = {eid: i for i, eid in enumerate(key_ids)}
        events_sorted = sorted(events, key=lambda e: id_order.get(e.id, 999))
        found_ids = {event.id for event in events_sorted}
        missing_ids = [identity for identity in key_ids if identity not in found_ids]
        if missing_ids and reference_status == "available":
            reference_status = "missing_source_events"

        return {
            "events":     [_event_to_source(e) for e in events_sorted],
            "sitrep_id":  sitrep_id,
            "total":      len(events_sorted),
            "source_reference_status": reference_status,
            "missing_source_ids": missing_ids,
        }


@router.post("/generate", dependencies=[Depends(require_admin_key)])
async def force_generate_sitrep():
    """Manually trigger a fresh SITREP generation."""
    import asyncio
    from app.services.sitrep_generator import _generate_sitrep
    from app.config import settings
    if not settings.enable_sitrep_generation or not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="SITREP generation is not configured")
    from app.services.runtime import runtime
    current = runtime.tasks.get("manual_sitrep")
    if current and not current.done():
        raise HTTPException(status_code=409, detail="A generation is already running")
    runtime.start("manual_sitrep", _generate_sitrep("manual"))
    return {"status": "generating", "message": "SITREP generation triggered — check /sitreps/latest in ~30 seconds"}


@router.post("/digest", dependencies=[Depends(require_admin_key)])
async def create_source_digest():
    from app.services.source_digest import generate_source_digest
    return await generate_source_digest()

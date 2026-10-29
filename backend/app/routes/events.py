import asyncio
import json
import logging
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import delete, func, select, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session as make_session, get_session
from app.models import Event
from app.schemas import EventRead
from app.services.classifier import classify_message
from app.services.geocoder import geocode

logger = logging.getLogger(__name__)


from app.security import require_admin_key


router = APIRouter(prefix="/events", tags=["events"])

_UNKNOWN_LAT = -25.0
_UNKNOWN_LON = 80.0


@router.get("", response_model=list[EventRead])
async def list_events(
    limit: int = Query(50, ge=1, le=500),
    event_type: str | None = Query(None),
    after: datetime | None = Query(None),
    before: datetime | None = Query(None),
    before_id: int | None = Query(None, ge=1),
    after_id: int | None = Query(None, ge=0),
    min_reliability: int | None = Query(None, ge=1, le=5),
    session: AsyncSession = Depends(get_session),
):
    if any(dt is not None and dt.tzinfo is None for dt in (after, before)):
        raise HTTPException(status_code=422, detail="Time filters require a timezone")
    if after and before and after > before:
        raise HTTPException(status_code=422, detail="after must not be later than before")
    if before_id is not None and before is None:
        raise HTTPException(status_code=422, detail="before_id requires before timestamp")
    # Creation-ID reconciliation catches late/old-dated reports after reconnect.
    ordering = (Event.id.asc(),) if after_id is not None else (Event.timestamp.desc(), Event.id.desc())
    stmt = select(Event).order_by(*ordering).limit(limit)
    if after_id is not None:
        stmt = stmt.where(Event.id > after_id)
    # Exclude synthetic demo events — these were seeded before real ingestion started
    stmt = stmt.where(Event.source == "demo" if settings.demo_mode else Event.source != "demo")
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if after:
        stmt = stmt.where(Event.timestamp >= after)
    if before:
        if before_id is not None:
            stmt = stmt.where(or_(Event.timestamp < before,
                (Event.timestamp == before) & (Event.id < before_id)))
        else:
            stmt = stmt.where(Event.timestamp <= before)
    if min_reliability:
        stmt = stmt.where(Event.source_reliability >= min_reliability)
    stmt = stmt.where(Event.source != "situational")
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/anomalies", response_model=list[EventRead])
async def list_anomalies(
    limit: int = Query(50, ge=1, le=200),
    min_score: int = Query(3, ge=1, le=10),
    session: AsyncSession = Depends(get_session),
):
    """Return events flagged as anomalous, ordered by anomaly_score descending."""
    stmt = (
        select(Event)
        .where(Event.anomaly_score >= min_score)
        .where(Event.source != "demo")
        .where(Event.source != "situational")
        .where(Event.source != "demo")
        .order_by(Event.anomaly_score.desc(), Event.timestamp.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/time-range")
async def event_time_range(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(func.min(Event.timestamp), func.max(Event.timestamp)).where(Event.source != "demo").where(Event.source != "situational").where(Event.source != "demo")
    )
    row = result.one_or_none()
    if row and row[0] and row[1]:
        return {"earliest": row[0].isoformat(), "latest": row[1].isoformat()}
    return {"earliest": None, "latest": None}



@router.get("/batch", response_model=list[EventRead])
async def get_events_batch(
    ids: str,  # comma-separated event IDs e.g. "123,456,789"
    session: AsyncSession = Depends(get_session),
):
    """Fetch multiple events by ID in one request. Used by frontend citation badges."""
    try:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
    except ValueError:
        raise HTTPException(status_code=400, detail="ids must be comma-separated integers")
    if not id_list:
        return []
    id_list = id_list[:50]  # hard cap — prevent abuse
    result = await session.execute(select(Event).where(Event.id.in_(id_list)))
    return result.scalars().all()


@router.get("/match-candidates")
async def match_candidates():
    from app.services.retro_matcher import get_retro_candidates
    return get_retro_candidates()


@router.get("/admin/ingestion", dependencies=[Depends(require_admin_key)])
async def ingestion_receipts(limit: int = Query(50, ge=1, le=200), session: AsyncSession = Depends(get_session)):
    from app.models import SourceReport
    result = await session.execute(select(SourceReport).order_by(SourceReport.received_at.desc()).limit(limit))
    return [{"identity": row.identity, "content_hash": row.content_hash, "status": row.status,
             "event_id": row.event_id, "received_at": row.received_at, "report": row.report}
            for row in result.scalars()]


@router.get("/{event_id}", response_model=EventRead)
async def get_event(event_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/{event_id}/imagery")
async def get_event_imagery(event_id: int, session: AsyncSession = Depends(get_session)):
    """Return satellite imagery URLs for any event with lat/lon coordinates.

    Used by the frontend popup to lazy-load Sentinel-2 thumbnails for
    high-severity events — the same WMS pipeline as FIRMS hotspots.
    Returns JSON with pre-signed URLs ready for use in <img> tags.
    """
    result = await session.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.lat is None or event.lon is None:
        raise HTTPException(status_code=404, detail="Event has no coordinates")

    from app.services.satellite_firms import _sentinel_wms_thumb, _eo_browser_url
    from app.config import settings as _settings

    ts = event.timestamp if event.timestamp else datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    lat = float(event.lat)
    lon = float(event.lon)
    d = 0.08  # ~9 km bounding box half-width

    # NASA Worldview deep link — VIIRS daily true-color composite
    worldview_url = (
        f"https://worldview.earthdata.nasa.gov/"
        f"?v={lon-d:.4f},{lat-d:.4f},{lon+d:.4f},{lat+d:.4f}"
        f"&t={ts.strftime('%Y-%m-%d')}"
        f"&l=VIIRS_NOAA20_CorrectedReflectance_TrueColor,Reference_Labels_15m,Coastlines_15m"
    )

    # UNOSAT search URL — often has damage assessments for Middle East conflict zones
    loc = (event.location_name or "").strip()
    unosat_url = f"https://unosat.org/products/?q={quote(loc)}" if loc else "https://unosat.org/products/"

    # Copernicus Browser — deep link to exact location on exact date
    cop_url = _eo_browser_url(lat, lon, ts)

    # ArcGIS World Imagery — free, no API key, correct location guaranteed by bbox
    # Uses Maxar/Esri global satellite mosaic (sub-meter resolution in Middle East)
    pad = 0.04  # ~4.4km box around event
    arcgis_thumbnail = (
        f"https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export"
        f"?bbox={lon-pad:.4f},{lat-pad:.4f},{lon+pad:.4f},{lat+pad:.4f}"
        f"&bboxSR=4326&size=320,240&imageSR=4326&format=jpg&transparent=false&f=image"
    )
    # Keep sentinel hub as optional if configured
    instance_id = _settings.sentinel_hub_instance_id or ""
    s2_thumbnail = arcgis_thumbnail  # Always use ArcGIS — guaranteed to work, correct coords

    return {
        "s2_thumbnail": arcgis_thumbnail,  # ArcGIS World Imagery — always available
        "arcgis_url": arcgis_thumbnail,
        "copernicus_browser_url": cop_url,
        "worldview_url": worldview_url,
        "google_maps_url": f"https://maps.google.com/?q={lat},{lon}&z=14&t=k",
        "unosat_url": unosat_url,
        "has_imagery": True,
        "imagery_kind": "basemap_reference",
        "capture_date": None,
        "incident_evidence": False,
        "limitations": ["Basemap acquisition date is unknown; this is not imagery of the reported event."],
    }


# ──────────────────────────────────────────────────────────────────────────────
# ADMIN: Retroactively fix events that have null or Indian Ocean coordinates
# ──────────────────────────────────────────────────────────────────────────────


async def _fix_null_coords_task():
    """Generate bounded location-review candidates; preserve published events."""
    await _build_location_candidates(reclassify=False)


@router.post("/admin/fix-null-coords", dependencies=[Depends(require_admin_key)])

async def fix_null_coords(background_tasks: BackgroundTasks):
    _require_live_collection()
    _start_admin_review("location_review", _fix_null_coords_task)
    return {"status": "started", "mutates_events": False,
            "message": "Location candidates are staged at /events/admin/location-candidates; no event is changed."}


@router.post("/admin/reclassify-locations", dependencies=[Depends(require_admin_key)])

async def reclassify_locations(background_tasks: BackgroundTasks):
    _require_live_collection()
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="Classification provider is not configured")
    _start_admin_review("location_review", _reclassify_vague_locations_task)
    return {"status": "started", "mutates_events": False,
            "message": "Bounded model proposals are staged for review; no event is changed."}


# Country names and other vague location terms that should be reclassified
_VAGUE_LOCATIONS = {
    "iran", "israel", "lebanon", "syria", "iraq", "yemen", "saudi arabia",
    "jordan", "kuwait", "qatar", "uae", "bahrain", "oman", "egypt", "turkey",
    "united states", "russia", "china", "unknown", "n/a", "", "middle east",
    "region", "area", "various",
}


async def _reclassify_vague_locations_task():
    """Generate extraction proposals; model output does not rewrite evidence."""
    await _build_location_candidates(reclassify=True)


@router.post("/admin/backfill", dependencies=[Depends(require_admin_key)])

async def trigger_backfill(background_tasks: BackgroundTasks):
    _require_live_collection()
    from app.services import telegram
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="Classification provider is not configured")
    if telegram._shared_client is None or not telegram._shared_client.is_connected():
        raise HTTPException(status_code=503, detail="Telegram listener is not connected")
    _start_admin_review("telegram_backfill", telegram.trigger_backfill)
    return {"status": "started", "message": "Historical collection uses configured sources and cutoff; inspect ingestion receipts."}


@router.delete("/admin/purge-old", dependencies=[Depends(require_admin_key)])

async def purge_old_events(
    before: datetime = Query(..., description="Explicit timezone-aware retention cutoff"),
    session: AsyncSession = Depends(get_session),
):
    if before.tzinfo is None or before >= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Cutoff must include a timezone and be in the past")
    result = await session.execute(delete(Event).where(Event.timestamp < before))
    await session.commit()
    return {"deleted": result.rowcount, "cutoff": before.isoformat(),
            "scope": "event records only; immutable source-report receipts are retained"}


@router.delete("/admin/dedup", dependencies=[Depends(require_admin_key)])

async def dedup_events():
    raise HTTPException(status_code=409, detail=(
        "Destructive deduplication is disabled: equal text does not establish a duplicate source. "
        "Use /events/match-candidates for non-destructive review."))


@router.get("/admin/geo-stats", dependencies=[Depends(require_admin_key)])
async def geo_stats(session: AsyncSession = Depends(get_session)):
    """Show counts of geolocated vs unknown-location events."""
    total = (await session.execute(select(func.count(Event.id)))).scalar_one()
    geolocated = (await session.execute(
        select(func.count(Event.id)).where(
            Event.lat.between(-90, 90), Event.lon.between(-180, 180),
            or_(Event.lat != _UNKNOWN_LAT, Event.lon != _UNKNOWN_LON),
        )
    )).scalar_one()
    unknown = total - geolocated
    return {
        "total": total,
        "geolocated": geolocated,
        "unknown_location": unknown,
        "geo_rate": f"{(geolocated / total * 100):.1f}%" if total else "0%",
    }


# ──────────────────────────────────────────────────────────────────────────────
# ADMIN: One-time import of danielrosehill OSINT confirmed wave dataset
# Source: https://github.com/danielrosehill/Iran-Israel-War-2026-OSINT-Data
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/admin/import-osint-dataset", dependencies=[Depends(require_admin_key)])
async def import_osint_dataset(background_tasks: BackgroundTasks):
    raise HTTPException(status_code=501, detail=(
        "This inherited dataset adapter is not qualified for release. "
        "No data was fetched or imported. A versioned source/license review, raw provenance, "
        "timestamp validation, and coordinate precision are required before enabling it."))


_location_review = {"status": "not_started", "candidates": [], "errors": [], "checked_at": None}


def _require_live_collection():
    if not settings.live_ingestion_enabled or settings.demo_mode:
        raise HTTPException(status_code=503, detail="Live collection is disabled")


def _start_admin_review(name, coroutine_factory):
    from app.services.runtime import runtime
    prior = runtime.tasks.get(name)
    if prior is not None and not prior.done():
        raise HTTPException(status_code=409, detail="This operation is already running")
    runtime.start(name, coroutine_factory())


async def _build_location_candidates(*, reclassify: bool):
    """Review-only: bounded work, explicit errors, no source or event writes."""
    import hashlib
    from app.services.evidence import valid_coordinates
    global _location_review
    _require_live_collection()
    if reclassify and not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="Classification provider is not configured")
    _location_review = {"status": "running", "candidates": [], "errors": [], "checked_at": None,
                        "limit": 100, "mutates_events": False}
    try:
        async with make_session() as session:
            predicate = (func.lower(Event.location_name).in_(_VAGUE_LOCATIONS) if reclassify else
                         or_(Event.lat.is_(None), Event.lon.is_(None),
                             (Event.lat == _UNKNOWN_LAT) & (Event.lon == _UNKNOWN_LON)))
            result = await session.execute(select(Event).where(predicate, Event.report_count > 0)
                                           .order_by(Event.id).limit(100))
            events = list(result.scalars().all())
        _location_review["examined"] = len(events)
        _location_review["may_be_truncated"] = len(events) == 100
        for event in events:
            location = (event.location_name or "").strip()
            try:
                if reclassify:
                    result = await classify_message(event.raw_text or "")
                    if result.get("classification_status") != "extracted" or result.get("is_noise"):
                        _location_review["errors"].append({"event_id": event.id, "reason": "extraction_unavailable_or_filtered"})
                        continue
                    location = result.get("location_name", "Unknown").strip()
                if not location or location.lower() in _VAGUE_LOCATIONS:
                    continue
                coordinates = await geocode(location)
                if not coordinates or not valid_coordinates(*coordinates):
                    continue
                _location_review["candidates"].append({
                    "event_id": event.id, "original_location": event.location_name,
                    "candidate_location": location, "lat": coordinates[0], "lon": coordinates[1],
                    "geolocation_precision": "unknown", "status": "needs_review",
                    "source_sha256": hashlib.sha256((event.raw_text or "").encode("utf-8")).hexdigest(),
                    "basis": "model_extraction_and_gazetteer" if reclassify else "gazetteer",
                })
            except Exception as exc:
                _location_review["errors"].append({"event_id": event.id, "reason": type(exc).__name__})
        _location_review["status"] = "incomplete" if _location_review["errors"] else "complete"
        _location_review["checked_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        _location_review["status"] = "failed"
        _location_review["errors"].append({"reason": type(exc).__name__})
        raise


@router.get("/admin/location-candidates", dependencies=[Depends(require_admin_key)])
async def location_candidates():
    return _location_review

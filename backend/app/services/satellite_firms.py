"""NASA FIRMS thermal observations and noncausal proximity links.

Thermal pixels can reflect wildfire, agriculture, industrial activity, or other
sources. A nearby detection never confirms a strike, supplies an actor, or
replaces an incident coordinate. VIIRS confidence is categorical, not a probability
that a reported military event occurred. See docs/METHODOLOGY.md.
"""

import asyncio
import csv
import io
import json
import hashlib
import logging
import math
import re
from datetime import datetime, timezone, timedelta

import httpx
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select, text

from app.config import settings
from app.db import async_session
from app.models import Event
from app.schemas import EventRead, EventWS
from app.services.broadcaster import broadcaster
from app.services.evidence import make_report, valid_coordinates

logger = logging.getLogger("app.services.satellite")

# ── Configuration ─────────────────────────────────────────────────────────────
FIRMS_BASE         = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_SOURCE       = "VIIRS_NOAA20_NRT"   # Explicit source product, not a quality ranking
ME_BBOX            = "25,10,65,42"         # Middle East: west,south,east,north
DAY_RANGE          = 2                     # Last 48 hours (ensures full VIIRS pass coverage)
MAX_RESPONSE_BYTES = 5_000_000
MAX_CSV_ROWS = 20_000
MAX_ASSOCIATION_EVENTS = 5000
POLL_INTERVAL_HRS  = 3                     # Poll every 3 hours
MATCH_RADIUS_KM    = 25                    # Spatial match threshold (km)
MATCH_WINDOW_HRS   = 12                     # Temporal match window (hours)
MIN_CONFIDENCE     = 0                     # Accept all confidence levels (NRT data often lacks conf string)
MIN_FRP            = 10                    # Operator display threshold in MW, not an accuracy gate
NEW_EVENT_FRP      = 80                    # Observation display threshold; no causal interpretation
CONFIRMATION_NET   = "SATELLITE"  # descriptive source type only

# ── Known gas flare / industrial zones (NOT conflict events) ──────────────────
# These are chronic VIIRS detections from petroleum infrastructure.
# Hotspots inside these boxes are tagged probable_flare=True and shown
# with a different marker style on the frontend.
# Format: (lat_min, lat_max, lon_min, lon_max, label)
GAS_FLARE_ZONES = [
    # Persian Gulf catchall — covers the main Gulf water body + nearshore all states.
    # Broad contextual zone only; membership does not determine a detection cause.
    (22.0, 30.5, 47.5, 57.5, "Persian Gulf Infrastructure"),
    # Khuzestan / SW Iran onshore (Ahvaz, Marun, Aghajari, Rag-e Sefid fields)
    (29.5, 33.5, 47.5, 51.5, "Iran Khuzestan Flares"),
    # Iraq Basra / Rumaila onshore (Al-Faw Peninsula, Zubair fields)
    (29.5, 31.5, 46.0, 48.5, "Iraq Basra Flares"),
    # Kuwait / Burgan onshore + offshore
    (27.5, 30.5, 45.5, 49.0, "Kuwait Oil Flares"),
    # Saudi Arabia Eastern Province: Ghawar, Khurais, Safaniya onshore
    (22.0, 30.0, 44.0, 52.0, "Saudi Aramco Flares"),
    # Oman / PDO: Fahud, Yibal, Marmul, Khazzan onshore + offshore
    (19.5, 25.5, 54.5, 60.0, "Oman Gas Flares"),
    # UAE onshore: ADNOC Ruwais, Murban, Bab fields (Abu Dhabi interior)
    (22.5, 25.5, 51.0, 57.5, "UAE Gas Flares"),
    # Qatar / North Dome + offshore South Pars shared field
    (24.5, 27.0, 50.0, 53.5, "Qatar Gas Flares"),
]

def _is_probable_flare(lat: float, lon: float) -> tuple[bool, str]:
    """Return broad industrial-zone overlap, not a determination of gas flaring."""
    for lat_min, lat_max, lon_min, lon_max, label in GAS_FLARE_ZONES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True, label
    return False, ""

# ── In-memory cache for last poll results (exposed via API) ───────────────────
_last_hotspots: list[dict] = []           # filtered hotspot list from last poll
_last_poll_ts: str = ""                   # ISO timestamp of last successful poll
_last_poll_confirmed: int = 0             # legacy field remains zero
_last_poll_associated: int = 0
_last_fetch_status: str = "not_started"
_last_fetch_error: str = ""
_last_poll_attempt_ts: str = ""
_last_fetch_success_ts: str = ""
_last_processing_error: str = ""
_association_truncated: bool = False
_poll_in_progress: bool = False
_last_poll_new_events: int = 0            # new anomaly events in last cycle
_matched_hotspot_keys: set[str] = set()   # spatial-temporal associations only


# ── Utilities ─────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(max(0, min(1, a))), math.sqrt(max(0, 1 - a)))



def _hotspot_key(h: dict) -> str:
    return f"{h.get('satellite', '')}|{h.get('instrument', 'VIIRS')}|{h['lat']:.5f}|{h['lon']:.5f}|{h['ts'].isoformat()}"


def _parse_firms_csv(raw: str) -> list[dict]:
    """Parse observations; never invent coordinates, times, or confidence values."""
    reader = csv.DictReader(io.StringIO(raw))
    required = {"latitude", "longitude", "acq_date", "acq_time", "frp"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError("FIRMS response lacks required CSV columns")
    hotspots, invalid = [], 0
    confidence_names = {"l": "low", "low": "low", "n": "nominal", "nominal": "nominal",
                        "h": "high", "high": "high"}
    for row_index, row in enumerate(reader):
        if row_index >= MAX_CSV_ROWS:
            raise ValueError("FIRMS response exceeds row limit")
        try:
            lat, lon, frp = float(row["latitude"]), float(row["longitude"]), float(row["frp"])
            if not valid_coordinates(lat, lon) or not math.isfinite(frp) or frp < 0:
                raise ValueError("Invalid location or FRP")
            clock = row["acq_time"].strip().zfill(4)
            if len(clock) != 4 or not clock.isdigit():
                raise ValueError("Invalid acquisition time")
            ts = datetime.strptime(row["acq_date"].strip(), "%Y-%m-%d").replace(
                hour=int(clock[:2]), minute=int(clock[2:]), tzinfo=timezone.utc)
            raw_conf = (row.get("confidence") or "").strip().lower()
            label = confidence_names.get(raw_conf, "unknown")
            numeric = None
            if raw_conf and raw_conf not in confidence_names:
                try:
                    parsed = float(raw_conf)
                    if math.isfinite(parsed) and 0 <= parsed <= 100:
                        numeric, label = parsed, "numeric"
                except ValueError:
                    pass
            hotspots.append({"lat": lat, "lon": lon, "frp": frp, "ts": ts,
                             "conf": numeric, "confidence_label": label,
                             "confidence_raw": raw_conf,
                             "satellite": row.get("satellite", ""),
                             "instrument": row.get("instrument", "VIIRS"),
                             "scan_km": row.get("scan", ""), "track_km": row.get("track", ""),
                             "proximity_matches": [], "raw_row": dict(row)})
        except (ValueError, TypeError, KeyError):
            invalid += 1
    if invalid:
        logger.warning("FIRMS: rejected %d malformed observations", invalid)
    if invalid and not hotspots:
        raise ValueError("FIRMS response contains no valid observations")
    return hotspots



def _copernicus_url(lat: float, lon: float, ts: datetime) -> str:
    """Context map only: this link supplies no acquisition date or damage proof."""
    return f"https://www.google.com/maps/@{lat:.5f},{lon:.5f},17z/data=!3m1!1e3"


def _sentinel_wms_thumb(lat: float, lon: float, ts: datetime, instance_id: str) -> str:
    """
    Sentinel Hub WMS thumbnail URL — returns a direct JPEG image.
    Uses a 30-day lookback window so a clear Sentinel-2 scene is almost always
    available (Sentinel-2 revisits every 5 days; 30-day window = 6 passes).
    MAXCC=30 filters cloudy scenes. Usable directly in <img> tags.
    """
    if not instance_id:
        return ""
    to_date   = ts.strftime("%Y-%m-%d")
    from_date = (ts - timedelta(days=30)).strftime("%Y-%m-%d")
    pad = 0.05   # ~5km box for tight focus
    w = round(lon - pad, 4)
    s = round(lat - pad, 4)
    e = round(lon + pad, 4)
    n = round(lat + pad, 4)
    return (
        f"https://sh.dataspace.copernicus.eu/ogc/wms/{instance_id}"
        f"?SERVICE=WMS&REQUEST=GetMap&LAYERS=TRUE_COLOR"
        f"&BBOX={w},{s},{e},{n}&CRS=EPSG:4326"
        f"&WIDTH=320&HEIGHT=240&FORMAT=image/jpeg"
        f"&TIME={from_date}/{to_date}&MAXCC=30"
    )


def _copernicus_browser_url(lat: float, lon: float, ts: datetime) -> str:
    """
    NASA Worldview deep-link as the Copernicus secondary option.
    Shows VIIRS thermal anomaly layer + true-color base, verified working.
    """
    date_str = ts.strftime("%Y-%m-%d")
    pad = 0.12
    w = round(lon - pad, 4)
    s = round(lat - pad, 4)
    e = round(lon + pad, 4)
    n = round(lat + pad, 4)
    return (
        f"https://worldview.earthdata.nasa.gov/"
        f"?v={w},{s},{e},{n}&t={date_str}"
        f"&l=VIIRS_NOAA20_Thermal_Anomalies_375m_Night"
        f",VIIRS_NOAA20_CorrectedReflectance_TrueColor"
        f"&lg=false"
    )




def _gibs_thumb(lat: float, lon: float, ts: datetime,
                layer: str = "VIIRS_NOAA20_CorrectedReflectance_TrueColor") -> str:
    """
    NASA GIBS (Global Imagery Browse Services) WMS thumbnail — completely free,
    no API key required. VIIRS NOAA-20: daily 375m true-color polar pass.
    MODIS Terra: daily 250m true-color.
    Uses a 7-day rolling window (TIME=from/to) so GIBS returns the most recent
    available scene — daily polar satellites have 1-3 day NRT processing lag.
    """
    to_date   = ts.strftime("%Y-%m-%d")
    lookback  = 14 if "Landsat" in layer else 7
    from_date = (ts - timedelta(days=lookback)).strftime("%Y-%m-%d")
    pad = 0.10
    if "Landsat" in layer:
        pad = 0.05
    elif "MODIS" in layer:
        pad = 0.12
    w = round(lon - pad, 4)
    s = round(lat - pad, 4)
    e = round(lon + pad, 4)
    n = round(lat + pad, 4)
    return (
        f"https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
        f"?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&STYLES="
        f"&LAYERS={layer}"
        f"&BBOX={w},{s},{e},{n}&SRS=EPSG:4326"
        f"&WIDTH=320&HEIGHT=240&FORMAT=image/jpeg"
        f"&TIME={from_date}/{to_date}"
    )


def _eo_browser_url(lat: float, lon: float, ts: datetime) -> str:
    """
    Copernicus Browser — free replacement for deprecated EO Browser.
    Provides Sentinel-2 L2A, Sentinel-1 SAR, and other ESA datasets.
    EO Browser was shut down in 2025 and redirects here for public data access.
    """
    date_str = ts.strftime("%Y-%m-%d")
    from_dt = (ts - timedelta(days=30)).strftime("%Y-%m-%d")
    return (
        f"https://browser.dataspace.copernicus.eu/"
        f"?zoom=14&lat={lat:.4f}&lng={lon:.4f}"
        f"&themeId=DEFAULT-THEME&datasetId=S2L2A"
        f"&fromTime={from_dt}T00%3A00%3A00.000Z"
        f"&toTime={date_str}T23%3A59%3A59.999Z"
    )


def _landsatlook_url(lat: float, lon: float) -> str:
    """USGS LandsatLook — free Landsat 8/9 viewer, 30m resolution, ~8-day revisit."""
    return f"https://landsatlook.usgs.gov/explore?center={lon:.4f},{lat:.4f}&zoom=15"


def _planet_explorer_url(lat: float, lon: float) -> str:
    """
    Planet Labs Explorer — free public viewer. Users with free/paid accounts
    see recent 3-5m daily imagery. Education/Research accounts are free to apply for.
    Even without login, the viewer shows the location correctly.
    """
    return f"https://www.planet.com/explorer/#lat={lat:.4f}&lng={lon:.4f}&zoom=15"

# ── FIRMS fetch ───────────────────────────────────────────────────────────────


class _FirmsLogRedactor(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        record.msg = re.sub(r"(https://firms\.modaps\.eosdis\.nasa\.gov/api/(?:area|data_availability)/csv/)[^/\s]+",
                            r"\1[REDACTED]", message)
        record.args = ()
        return True


# HTTPX logs URL paths at INFO; this provider puts its key in that path.
if not getattr(logging.getLogger("httpx"), "_firms_redaction", False):
    logging.getLogger("httpx").addFilter(_FirmsLogRedactor())
    logging.getLogger("httpx")._firms_redaction = True


async def _fetch_firms_hotspots() -> list[dict] | None:
    global _last_fetch_status, _last_fetch_error, _last_poll_attempt_ts, _last_fetch_success_ts
    _last_poll_attempt_ts = datetime.now(timezone.utc).isoformat()
    key = settings.firms_map_key
    if not key:
        _last_fetch_status, _last_fetch_error = "disabled", "FIRMS credentials not configured"
        return None
    url = f"{FIRMS_BASE}/{key}/{FIRMS_SOURCE}/{ME_BBOX}/{DAY_RANGE}"
    try:
        async with asyncio.timeout(40), httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared and int(declared) > MAX_RESPONSE_BYTES:
                    raise ValueError("FIRMS response exceeds byte limit")
                content = bytearray()
                async for block in response.aiter_bytes():
                    content.extend(block)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise ValueError("FIRMS response exceeds byte limit")
        spots = await asyncio.to_thread(_parse_firms_csv, bytes(content).decode("utf-8-sig"))
        now = datetime.now(timezone.utc)
        if any(h["ts"] > now + timedelta(minutes=5) or h["ts"] < now - timedelta(days=DAY_RANGE + 2) for h in spots):
            raise ValueError("FIRMS response acquisition times do not match requested window")
        _last_fetch_status, _last_fetch_error = "ok", ""
        _last_fetch_success_ts = now.isoformat()
        return [h for h in spots if h["frp"] >= MIN_FRP]
    except Exception as exc:
        _last_fetch_status, _last_fetch_error = "error", type(exc).__name__
        logger.warning("FIRMS fetch failed (%s); prior successful observations retained", type(exc).__name__)
        return None


# ── Cross-reference ───────────────────────────────────────────────────────────


async def _cross_reference_events(hotspots: list[dict]) -> int:
    """Attach proximity candidates to observations; never mutate incident evidence."""
    global _matched_hotspot_keys, _association_truncated
    _matched_hotspot_keys = set()
    _association_truncated = False
    for hotspot in hotspots:
        hotspot["proximity_matches"] = []
    if not hotspots:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MATCH_WINDOW_HRS + DAY_RANGE * 24 + 1)
    async with async_session() as session:
        result = await session.execute(select(Event).where(
            Event.lat.isnot(None), Event.lon.isnot(None), Event.timestamp >= cutoff,
            Event.event_type != "thermal_anomaly", Event.report_count > 0,
        ).order_by(Event.timestamp.desc(), Event.id.desc()).limit(MAX_ASSOCIATION_EVENTS + 1))
        events = list(result.scalars().all())
    _association_truncated = len(events) > MAX_ASSOCIATION_EVENTS
    events = events[:MAX_ASSOCIATION_EVENTS]
    return await asyncio.to_thread(_associate_observations, hotspots, events)


def _associate_observations(hotspots, events):
    """CPU work runs outside the API loop; source reports are never mutated."""
    associated_ids = set()
    for hotspot in hotspots:
        for event in events:
            if not valid_coordinates(event.lat, event.lon) or not event.timestamp:
                continue
            stamp = event.timestamp
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            distance = _haversine_km(event.lat, event.lon, hotspot["lat"], hotspot["lon"])
            hours = abs((stamp - hotspot["ts"]).total_seconds()) / 3600
            if distance <= MATCH_RADIUS_KM and hours <= MATCH_WINDOW_HRS:
                hotspot["proximity_matches"].append({
                    "event_id": event.id, "distance_km": round(distance, 3),
                    "time_difference_hours": round(hours, 3), "causation": "unassessed",
                })
                associated_ids.add(event.id)
        hotspot["proximity_matches"].sort(key=lambda m: (m["distance_km"], m["event_id"]))
        hotspot["proximity_matches"] = hotspot["proximity_matches"][:20]
        if hotspot["proximity_matches"]:
            _matched_hotspot_keys.add(_hotspot_key(hotspot))
    return len(associated_ids)


# ── New anomaly ingestion ─────────────────────────────────────────────────────


async def _ingest_new_anomaly_events(hotspots: list[dict]) -> int:
    """Retain high-FRP observations as observations, including industrial overlap."""
    high_frp = [h for h in hotspots if h["frp"] >= NEW_EVENT_FRP]
    if not high_frp:
        return 0
    created = 0
    created_events = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=DAY_RANGE * 24 + 1)
    async with async_session() as session:
        result = await session.execute(select(Event).where(
            Event.source == "satellite_firms", Event.timestamp >= cutoff)
            .order_by(Event.timestamp.desc(), Event.id.desc()).limit(MAX_CSV_ROWS + 1))
        existing = list(result.scalars().all())
        if len(existing) > MAX_CSV_ROWS:
            raise ValueError("Thermal identity lookup exceeds qualified row budget")
        known = {r.get("message_id") for event in existing for r in (event.reports or [])}
        for hotspot in high_frp:
            identity = _hotspot_key(hotspot)
            if identity in known:
                continue
            label = hotspot["confidence_label"]
            raw = (f"FIRMS {FIRMS_SOURCE}: lat={hotspot['lat']}, lon={hotspot['lon']}, "
                   f"FRP={hotspot['frp']} MW; acquisition={hotspot['ts'].isoformat()}; "
                   f"detection confidence={hotspot['confidence_raw'] or 'unknown'}; "
                   f"satellite={hotspot['satellite']}; instrument={hotspot['instrument']}")
            summary = (f"NASA FIRMS thermal observation: FRP {hotspot['frp']:.1f} MW; "
                       f"detection confidence {label}. Cause and conflict relevance are unassessed.")
            source_url = _copernicus_browser_url(hotspot["lat"], hotspot["lon"], hotspot["ts"])
            report = make_report(source="satellite_firms", channel_name="NASA FIRMS VIIRS-NOAA20",
                                 message_id=identity, source_url=source_url, raw_text=raw,
                                summary=summary, timestamp=hotspot["ts"], classification_status="extracted")
            report["sensor_record"] = dict(hotspot.get("raw_row") or {})
            report["sensor_record_sha256"] = hashlib.sha256(json.dumps(report["sensor_record"], sort_keys=True).encode("utf-8")).hexdigest()
            report["sensor_record_encoding"] = "parsed_csv_fields"
            event = Event(
                source="satellite_firms", channel_name="NASA FIRMS VIIRS-NOAA20",
                raw_text=raw, summary=summary, event_type="thermal_anomaly", severity=0,
                lat=hotspot["lat"], lon=hotspot["lon"],
                geometry=from_shape(Point(hotspot["lon"], hotspot["lat"]), srid=4326),
                timestamp=hotspot["ts"], report_count=1, reporting_channels="satellite_firms",
                source_reliability=None, location_name="Satellite pixel centroid",
                source_url=source_url, confirmed_networks="", reports=[report],
                classification_status="extracted", geolocation_precision="sensor_pixel",
            )
            session.add(event)
            created_events.append(event)
            known.add(identity)
            created += 1
        if created:
            await session.commit()
            for event in created_events:
                await session.refresh(event)
                await broadcaster.broadcast(EventWS(type="new_event", event=EventRead.model_validate(event)).model_dump_json())
    return created


# ── Main poll cycle ───────────────────────────────────────────────────────────


async def poll_firms_once() -> None:
    """Preserve last-good cache on failed fetch or processing; never overlap polls."""
    global _last_hotspots, _last_poll_ts, _last_poll_confirmed, _last_poll_new_events, _last_poll_associated
    global _poll_in_progress, _last_processing_error
    if _poll_in_progress:
        return
    _poll_in_progress = True
    _last_processing_error = ""
    try:
        hotspots = await _fetch_firms_hotspots()
        if hotspots is None:
            return
        associated = await _cross_reference_events(hotspots)
        new_events = await _ingest_new_anomaly_events(hotspots)
        _last_hotspots, _last_poll_ts = hotspots, datetime.now(timezone.utc).isoformat()
        _last_poll_confirmed, _last_poll_associated, _last_poll_new_events = 0, associated, new_events
        logger.info("FIRMS: %d observations, %d nearby reports, %d new observation records; cause unassessed",
                    len(hotspots), associated, new_events)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        _last_processing_error = type(error).__name__
        logger.warning("FIRMS persistence/association failed (%s); prior published cache retained", type(error).__name__)
        raise
    finally:
        _poll_in_progress = False


def _age(stamp, now):
    try:
        return max(0., (now - datetime.fromisoformat(stamp)).total_seconds()) if stamp else None
    except (ValueError, TypeError):
        return None


def get_firms_status() -> dict:
    now = datetime.now(timezone.utc)
    age = _age(_last_poll_ts, now)
    latest = max((h["ts"] for h in _last_hotspots if isinstance(h.get("ts"), datetime)), default=None)
    observation_age = max(0., (now - latest).total_seconds()) if latest else None
    state = ("disabled" if not settings.live_ingestion_enabled or not settings.firms_map_key else
        "failed" if _last_fetch_status == "error" or _last_processing_error else
        "unavailable" if age is None else "stale" if age > POLL_INTERVAL_HRS * 7200 else
        "empty" if not _last_hotspots else "ok")
    return {"status": state, "source": FIRMS_SOURCE, "coverage_bbox": ME_BBOX,
        "poll_interval_seconds": POLL_INTERVAL_HRS * 3600, "poll_in_progress": _poll_in_progress,
        "last_attempt_at": _last_poll_attempt_ts or None, "last_fetch_success_at": _last_fetch_success_ts or None,
        "last_success_at": _last_poll_ts or None, "cache_age_seconds": age,
        "latest_observation_at": latest.isoformat() if latest else None, "observation_age_seconds": observation_age,
        "observations_stale": observation_age is not None and observation_age > DAY_RANGE * 86400,
        "observation_count": len(_last_hotspots), "error_type": _last_processing_error or _last_fetch_error or None,
        "association_truncated": _association_truncated, "association_event_limit": MAX_ASSOCIATION_EVENTS,
        "min_frp_display_mw": MIN_FRP, "published_event_min_frp_mw": NEW_EVENT_FRP,
        "limitations": ["Thermal detections do not establish a strike, cause, actor, casualties or event severity.",
                        "Clouds, overpass timing, resolution and display thresholds limit coverage; absence does not refute a report."]}


def get_last_hotspots() -> dict:
    """Return cached hotspot data from the last FIRMS poll for API exposure."""
    instance_id = settings.sentinel_hub_instance_id
    status = get_firms_status()
    return {
        "status": status,
        "hotspots": [
            {
                "lat": h["lat"],
                "lon": h["lon"],
                "frp": h["frp"],
                "conf": h["conf"],
                "confidence_label": h["confidence_label"],
                "confidence_raw": h["confidence_raw"],
                "proximity_matches": h.get("proximity_matches", []),
                "observation_id": _hotspot_key(h),
                "ts": h["ts"].isoformat(),
                "google_maps_url":   _copernicus_url(h["lat"], h["lon"], h["ts"]),
                "copernicus_url":    _copernicus_browser_url(h["lat"], h["lon"], h["ts"]),
                "wms_thumbnail":     _sentinel_wms_thumb(h["lat"], h["lon"], h["ts"], instance_id),
                "gibs_viirs_thumb":  _gibs_thumb(h["lat"], h["lon"], h["ts"], "VIIRS_NOAA20_CorrectedReflectance_TrueColor"),
                "gibs_modis_thumb":  _gibs_thumb(h["lat"], h["lon"], h["ts"], "MODIS_Terra_CorrectedReflectance_TrueColor"),
                "gibs_landsat_thumb":_gibs_thumb(h["lat"], h["lon"], h["ts"], "Landsat_8_OLI_Natural_Color"),
                "eo_browser_url":    _eo_browser_url(h["lat"], h["lon"], h["ts"]),
                "landsatlook_url":   _landsatlook_url(h["lat"], h["lon"]),
                "planet_url":        _planet_explorer_url(h["lat"], h["lon"]),
                **(lambda pf, pl: {"probable_flare": pf, "flare_zone": pl})(*_is_probable_flare(h["lat"], h["lon"])),
                "matched": False,  # legacy UI must not hide a detection as confirmed
                "associated": bool(h.get("proximity_matches")),
                "causation": "unassessed",
                "observation_age_seconds": max(0., (datetime.now(timezone.utc) - h["ts"]).total_seconds()),
                "stale": status["status"] in {"stale", "failed"} or
                    (datetime.now(timezone.utc) - h["ts"]).total_seconds() > DAY_RANGE * 86400,
            }
            for h in _last_hotspots
        ],
        "polled_at": _last_poll_ts,
        "confirmed_events": 0,
        "associated_events": _last_poll_associated,
        "fetch_status": _last_fetch_status,
        "last_attempt_at": _last_poll_attempt_ts,
        "fetch_error": _last_fetch_error,
        "new_events": _last_poll_new_events,
        "total_hotspots": len(_last_hotspots),
    }


async def start_firms_poller() -> None:
    """Background task: polls FIRMS on startup and every POLL_INTERVAL_HRS hours."""
    logger.info(
        "FIRMS satellite poller started (interval=%dh, source=%s, bbox=%s)",
        POLL_INTERVAL_HRS, FIRMS_SOURCE, ME_BBOX,
    )
    await asyncio.sleep(90)   # let backend fully warm up first
    while True:
        try:
            await poll_firms_once()
        except Exception as e:
            logger.warning("FIRMS poller error (%s)", type(e).__name__)
        await asyncio.sleep(POLL_INTERVAL_HRS * 3600)

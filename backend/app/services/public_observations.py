"""Separate, bounded NASA publication dataset. Never reads private reports.

Only this fixed source/product may enter the public thermal dataset. Immutable
batches retain their provider-byte digest and literal observation clocks. NASA
pixels describe thermal anomalies, never incident causes or strike severity.
"""
import asyncio
import csv
import hashlib
import io
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, select, text, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.db import async_session
from app.models import PublicObservationBatch

logger = logging.getLogger(__name__)
SOURCE = "nasa_firms_noaa20"
SOURCE_URL = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_24h.csv"
CITATION_URL = "https://www.earthdata.nasa.gov/data/projects/lance#ed-firms-citation"
DISCLAIMER_URL = "https://nrt4.modaps.eosdis.nasa.gov/api/v2/content/archives/FIRMS/README.pdf"
POLL_SECONDS = 3 * 3600
DB_RETRY_SECONDS = 30
STALE_SECONDS = 12 * 3600
DISPLAY_SECONDS = 48 * 3600
MAX_BYTES = 32_000_000
MAX_ROWS = 400_000
MAX_OBSERVATIONS = 10_000
MAX_PACKET_BYTES = 6_000_000
MAX_DISPLAY = 2000
BBOX = (25, 10, 65, 42)
MIN_FRP = 10.0
LOCK_ID = 56182843097261031


def utcnow():
    return datetime.now(timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pixel_key(lat, lon, stamp):
    """Semantic position/time identity; source-row bytes retain their own digest."""
    return float(lat), float(lon), stamp.astimezone(timezone.utc).isoformat()


class ThermalPixel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    lat: float = Field(ge=10, le=42, allow_inf_nan=False)
    lon: float = Field(ge=25, le=65, allow_inf_nan=False)
    frp: float = Field(ge=MIN_FRP, allow_inf_nan=False)
    ts: str
    confidence_label: Literal["low", "nominal", "high", "unknown"]
    satellite: Literal["NOAA-20"] = "NOAA-20"
    instrument: Literal["VIIRS"] = "VIIRS"
    scan_km: float = Field(ge=0, le=100, allow_inf_nan=False)
    track_km: float = Field(ge=0, le=100, allow_inf_nan=False)
    source_row_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("ts")
    @classmethod
    def timestamp(cls, value):
        if len(value) > 40 or datetime.fromisoformat(value).tzinfo is None:
            raise ValueError("Acquisition clock must include timezone")
        return value


class ThermalBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    source: Literal["nasa_firms_noaa20"] = SOURCE
    source_url: Literal[SOURCE_URL] = SOURCE_URL
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    received_at: str
    source_rows: int = Field(ge=0, le=MAX_ROWS)
    regional_rows: int = Field(ge=0, le=MAX_ROWS)
    duplicate_rows: int = Field(ge=0, le=MAX_ROWS)
    filtered_rows: int = Field(ge=0, le=MAX_ROWS)
    observations: list[ThermalPixel] = Field(max_length=MAX_OBSERVATIONS)

    _clock = field_validator("received_at")(ThermalPixel.timestamp.__func__)

    @model_validator(mode="after")
    def consistent_batch(self):
        if self.regional_rows > self.source_rows or self.regional_rows != self.filtered_rows + self.duplicate_rows + len(self.observations):
            raise ValueError("NASA publication counts do not reconcile")
        ids, positions = set(), set()
        for pixel in self.observations:
            key = pixel_key(pixel.lat, pixel.lon, datetime.fromisoformat(pixel.ts))
            if pixel.id in ids or key in positions:
                raise ValueError("Duplicate NASA publication identity or position/time")
            ids.add(pixel.id)
            positions.add(key)
        return self


def parse_nasa_csv(raw: bytes, now: datetime) -> dict:
    if len(raw) > MAX_BYTES:
        raise ValueError("Source byte bound exceeded")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    required = {"latitude", "longitude", "acq_date", "acq_time", "frp", "satellite", "scan", "track", "confidence"}
    if not required.issubset(set(reader.fieldnames or [])) or len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
        raise ValueError("Unexpected NASA schema")
    observations, seen = [], {}
    total = regional = duplicates = filtered = 0
    for row in reader:
        total += 1
        if total > MAX_ROWS or None in row or any(v is None or len(v) > 200 for v in row.values()):
            raise ValueError("Malformed or oversized NASA record")
        lat, lon, frp = float(row["latitude"]), float(row["longitude"]), float(row["frp"])
        if not all(math.isfinite(v) for v in (lat, lon, frp)) or not (-90 <= lat <= 90 and -180 <= lon <= 180 and frp >= 0):
            raise ValueError("Invalid NASA coordinates or power")
        clock = row["acq_time"].zfill(4)
        if len(clock) != 4 or not clock.isdigit() or row["satellite"] not in {"1", "J1", "N20", "NOAA-20"}:
            raise ValueError("Invalid NASA instrument or clock")
        ts = datetime.strptime(row["acq_date"], "%Y-%m-%d").replace(hour=int(clock[:2]), minute=int(clock[2:]), tzinfo=timezone.utc)
        if ts > now + timedelta(minutes=5):
            raise ValueError("Future NASA observation")
        if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
            continue
        regional += 1
        if ts < now - timedelta(seconds=DISPLAY_SECONDS) or frp < MIN_FRP:
            filtered += 1
            continue
        identity = digest([SOURCE, *pixel_key(lat, lon, ts)])
        row_hash = digest(row)
        if identity in seen:
            if seen[identity] != row_hash:
                raise ValueError("Conflicting NASA records require review")
            duplicates += 1
            continue
        seen[identity] = row_hash
        observations.append(ThermalPixel(id=identity, lat=lat, lon=lon, frp=frp, ts=ts.isoformat(),
            confidence_label={"l": "low", "n": "nominal", "h": "high", "low": "low", "nominal": "nominal", "high": "high"}.get(row["confidence"].lower(), "unknown"),
            scan_km=float(row["scan"]), track_km=float(row["track"]), source_row_sha256=row_hash))
        if len(observations) > MAX_OBSERVATIONS:
            raise ValueError("Regional publication bound exceeded")
    payload = ThermalBatch(response_sha256=hashlib.sha256(raw).hexdigest(), received_at=now.isoformat(),
        source_rows=total, regional_rows=regional, duplicate_rows=duplicates, filtered_rows=filtered,
        observations=observations).model_dump()
    if len(canonical(payload)) > MAX_PACKET_BYTES:
        raise ValueError("Publication packet bound exceeded")
    return payload


async def fetch_nasa() -> bytes:
    # Fixed URL, no credentials/cookies/redirects/proxy environment. Provider
    # changes require review; a 200 HTML login page cannot become an empty feed.
    async with asyncio.timeout(65), httpx.AsyncClient(timeout=45, follow_redirects=False, trust_env=False) as client:
        async with client.stream("GET", SOURCE_URL) as response:
            response.raise_for_status()
            if int(response.headers.get("content-length", "0")) > MAX_BYTES:
                raise ValueError("Source byte bound exceeded")
            raw = bytearray()
            async for block in response.aiter_bytes():
                raw.extend(block)
                if len(raw) > MAX_BYTES:
                    raise ValueError("Source byte bound exceeded")
    return bytes(raw)


async def publish_once():
    if settings.public_read_only or settings.demo_mode or not settings.live_ingestion_enabled or not settings.public_observation_publisher_enabled:
        raise ValueError("Private publication collector is disabled")
    # Transaction-level ownership prevents duplicate collectors. Readers observe
    # either the complete old batch or the complete new batch, never a partial one.
    async with async_session() as session:
        async with session.begin():
            if not (await session.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_ID})).scalar_one():
                return "already_running"
            now = utcnow()
            previous = (await session.execute(select(PublicObservationBatch.published_at).where(PublicObservationBatch.source == SOURCE)
                .order_by(PublicObservationBatch.published_at.desc()).limit(1))).scalar_one_or_none()
            if previous is not None and (now - previous).total_seconds() < POLL_SECONDS:
                return "not_due"
            try:
                raw = await fetch_nasa()
                payload = await asyncio.to_thread(parse_nasa_csv, raw, utcnow())
                state = "ok"
            except Exception as exc:
                logger.warning("Public NASA fetch failed (%s)", type(exc).__name__)
                payload, state = {}, "failed"
            now = utcnow()
            identity = digest({"source": SOURCE, "published_at": now.isoformat(), "status": state, "payload": payload})
            await session.execute(insert(PublicObservationBatch).values(id=identity, source=SOURCE,
                published_at=now, status=state, payload=payload).on_conflict_do_nothing(index_elements=["id"]))
            await session.execute(delete(PublicObservationBatch).where(PublicObservationBatch.source == SOURCE,
                PublicObservationBatch.published_at < now - timedelta(days=7)))
    return state


async def start_public_observation_publisher():
    while True:
        delay = POLL_SECONDS
        try:
            outcome = await publish_once()
            if outcome in {"not_due", "already_running"}:
                # Recheck skipped database work promptly. The stored due gate
                # still prevents provider requests before three hours elapse.
                delay = DB_RETRY_SECONDS
        except (SQLAlchemyError, OSError) as exc:
            # Retry database/connection availability promptly. Each attempt still
            # takes the advisory lock and checks the stored cadence before HTTP.
            # If a commit failed after fetching, an uncommitted attempt may fetch
            # again; a committed attempt is protected by that same due gate.
            logger.warning("Public observation database unavailable (%s)", type(exc).__name__)
            delay = DB_RETRY_SECONDS
        except Exception as exc:
            logger.warning("Public observation publication failed (%s)", type(exc).__name__)
        await asyncio.sleep(delay)


def describe_batch(latest, successful, now: datetime) -> dict:
    for row in {id(row): row for row in (latest, successful) if row is not None}.values():
        if row.source != SOURCE or row.status not in {"ok", "failed"} or row.published_at.tzinfo is None:
            raise ValueError("Unknown publication state")
        if row.status == "failed" and row.payload != {}:
            raise ValueError("Invalid failure envelope")
        if len(canonical(row.payload)) > MAX_PACKET_BYTES:
            raise ValueError("Publication packet bound exceeded")
        packet = {"source": SOURCE, "published_at": row.published_at.isoformat(), "status": row.status, "payload": row.payload}
        if row.id != digest(packet) or (now - row.published_at).total_seconds() < -300:
            raise ValueError("Publication integrity check failed")
    result = {"source": SOURCE, "source_url": SOURCE_URL, "citation_url": CITATION_URL,
        "disclaimer_url": DISCLAIMER_URL, "attribution": "NASA LANCE / FIRMS, NOAA-20 VIIRS Collection 2 near-real-time observations",
        "limitations": "Thermal pixels are observations, not strike detection. Cause unknown. Incomplete overpass/cloud coverage; not for life-safety decisions.",
        "region": {"west": 25, "south": 10, "east": 65, "north": 42}, "minimum_frp_mw": MIN_FRP,
        "observation_window_hours": 48, "stale_after_seconds": STALE_SECONDS, "display_limit": MAX_DISPLAY,
        "status": "awaiting_publication", "last_attempt_status": latest.status if latest else "not_started",
        "last_attempt_at": latest.published_at.isoformat() if latest else None,
        "published_at": None, "batch_id": None, "hotspots": [], "displayed_count": 0, "eligible_count": 0}
    if not successful:
        if latest:
            result["status"] = "failed"
        return result
    payload = ThermalBatch.model_validate(successful.payload).model_dump()
    expected = digest({"source": SOURCE, "published_at": successful.published_at.isoformat(), "status": "ok", "payload": payload})
    if successful.id != expected:
        raise ValueError("Publication integrity check failed")
    age = (now - successful.published_at).total_seconds()
    if age < -300:
        raise ValueError("Future publication clock")
    eligible = [p for p in payload["observations"] if now-timedelta(seconds=DISPLAY_SECONDS) <= datetime.fromisoformat(p["ts"]) <= now+timedelta(minutes=5)]
    eligible.sort(key=lambda p: (-p["frp"], p["id"]))
    result.update({"status": "stale" if age > STALE_SECONDS else "empty" if not eligible else "fresh",
        "published_at": successful.published_at.isoformat(), "batch_id": successful.id,
        "received_at": payload["received_at"], "response_sha256": payload["response_sha256"],
        "source_rows": payload["source_rows"], "regional_rows": payload["regional_rows"],
        "filtered_rows": payload["filtered_rows"], "duplicate_rows": payload["duplicate_rows"],
        "eligible_count": len(eligible), "displayed_count": min(len(eligible), MAX_DISPLAY),
        "display_order": "highest FRP first, stable observation ID tie-break; not severity",
        "hotspots": eligible[:MAX_DISPLAY]})
    return result


async def read_public_observations(download=False, batch_id=None):
    async with async_session() as session:
        # One statement gives a consistent snapshot of latest attempt + success.
        latest = select(PublicObservationBatch.id).where(PublicObservationBatch.source == SOURCE).order_by(
            PublicObservationBatch.published_at.desc(), PublicObservationBatch.id.desc()).limit(1).correlate(None).scalar_subquery()
        successful = select(PublicObservationBatch.id).where(PublicObservationBatch.source == SOURCE, PublicObservationBatch.status == "ok").order_by(
            PublicObservationBatch.published_at.desc(), PublicObservationBatch.id.desc()).limit(1).correlate(None).scalar_subquery()
        condition = PublicObservationBatch.id == batch_id if batch_id else or_(PublicObservationBatch.id == latest, PublicObservationBatch.id == successful)
        rows = (await session.execute(select(PublicObservationBatch).where(condition)
            .order_by(PublicObservationBatch.published_at.desc(), PublicObservationBatch.id.desc()))).scalars().all()
    if batch_id and (not rows or rows[0].published_at < utcnow()-timedelta(days=7)):
        return None
    successful = next((row for row in rows if row.status == "ok"), None)
    result = await asyncio.to_thread(describe_batch, rows[0] if rows else None, successful, utcnow())
    if download:
        return {"batch_id": result["batch_id"], "source": SOURCE,
            "published_at": successful.published_at.isoformat() if successful else None,
            "status": "ok" if successful else "unavailable", "payload": successful.payload if successful else None,
            "attribution": result["attribution"], "citation_url": CITATION_URL,
            "disclaimer_url": DISCLAIMER_URL, "current_display_status": result["status"]}
    result["download_url"] = f"/publication/observations/download/{successful.id}" if successful else None
    return result

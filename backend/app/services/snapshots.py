"""Tracking snapshot recorder — periodically saves aircraft, vessel, and
jamming zone positions to the database for historical replay.

Runs every 2 minutes. Stores compact JSONB snapshots.
Prunes snapshots older than 30 days on each cycle.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, func

from app.db import async_session
from app.models import TrackingSnapshot
from app.services.opensky import get_aircraft, get_jamming_zones
from app.services.maritime import get_vessels

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL = 120  # 2 minutes
RETENTION_DAYS = 30


def _compact_aircraft(aircraft: list[dict]) -> list[dict]:
    """Filter to non-civilian + interesting aircraft and strip to essential fields."""
    # Commercial airline prefixes to exclude
    AIRLINE_PREFIXES = {
        "AAL","UAL","DAL","SWA","BAW","AFR","DLH","KLM","UAE","QTR","THY","SVA",
        "ETH","MSR","RYR","EZY","IBE","TAP","AZA","SAS","FIN","LOT","CSN","CCA",
        "CES","CHH","AIC","JAL","ANA","KAL","AAR","MAS","SIA","THA","GFA","OMA",
        "ELY","ROT","BMS","PIA","IRA","IRM","IRB","FZA","MEA","GLL","RAM","TUN",
        "AMC","AMF","AMX","AXM","AEA","AVA","GLO","LAM","LNE","LPE","TAM","VRG",
        "EIA","FDB","FLY","JZR","NAS","PGT","RJA","TCX","TOM","TUI","WZZ","EXS",
    }
    result = []
    for ac in aircraft:
        if ac.get("on_ground"):
            continue
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            continue
        # Conflict bounding box
        if not (8 <= lat <= 42 and 28 <= lon <= 67):
            continue
        cat = ac.get("aircraft_category", "civilian")
        cs = (ac.get("callsign") or "").strip().upper()
        # Keep non-civilian, emergencies, and non-airline callsigns
        if cat == "civilian" and not ac.get("is_emergency"):
            if cs and cs[:3] in AIRLINE_PREFIXES:
                continue
        result.append({
            "i": ac.get("icao24", ""),
            "c": cs,
            "la": round(lat, 5),
            "lo": round(lon, 5),
            "a": ac.get("altitude"),
            "h": ac.get("heading"),
            "v": ac.get("velocity"),
            "t": ac.get("type", ""),
            "k": cat,
            "e": ac.get("is_emergency", False),
            "s": ac.get("squawk", ""),
        })
    return result


def _compact_vessels(vessels: list[dict]) -> list[dict]:
    """Strip vessels to essential fields for replay."""
    result = []
    for v in vessels:
        lat, lon = v.get("lat"), v.get("lon")
        if lat is None or lon is None:
            continue
        result.append({
            "m": v.get("mmsi", ""),             # mmsi
            "n": v.get("name", ""),             # name
            "la": round(lat, 5),                # lat
            "lo": round(lon, 5),                # lon
            "sp": v.get("speed", 0),            # speed
            "h": v.get("heading", 0),           # heading
            "k": v.get("vessel_category", ""),   # category
            "f": v.get("flag_code", ""),         # flag
            "st": v.get("ship_type_name", ""),   # ship type name
        })
    return result


def _compact_jamming(zones: list[dict]) -> list[dict]:
    """Jamming zones are already compact."""
    return [
        {
            "la": z.get("lat"),
            "lo": z.get("lon"),
            "r": z.get("radius_km"),
            "c": z.get("aircraft_count"),
            "i": z.get("intensity"),
        }
        for z in zones
        if z.get("lat") is not None
    ]


async def _record_snapshot():
    """Take one snapshot and write to DB."""
    now = datetime.now(timezone.utc)
    aircraft = _compact_aircraft(get_aircraft())
    vessels = _compact_vessels(get_vessels())
    jamming = _compact_jamming(get_jamming_zones())

    async with async_session() as session:
        snapshot = TrackingSnapshot(
            timestamp=now,
            aircraft=aircraft,
            vessels=vessels,
            jamming_zones=jamming,
        )
        session.add(snapshot)
        await session.commit()

    logger.info(
        "Snapshot recorded: %d aircraft, %d vessels, %d jamming zones",
        len(aircraft), len(vessels), len(jamming),
    )


async def _prune_old_snapshots():
    """Delete snapshots older than RETENTION_DAYS."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    async with async_session() as session:
        result = await session.execute(
            delete(TrackingSnapshot).where(TrackingSnapshot.timestamp < cutoff)
        )
        if result.rowcount > 0:
            await session.commit()
            logger.info("Pruned %d old snapshots (older than %d days)", result.rowcount, RETENTION_DAYS)


async def get_snapshots(start: datetime, end: datetime, max_points: int = 500) -> list[dict]:
    """Sample IDs in SQL before loading bounded JSONB payloads."""
    if not 1 <= max_points <= 500:
        raise ValueError("max_points must be between 1 and 500")
    async with async_session() as session:
        count = await session.execute(select(func.count()).select_from(TrackingSnapshot).where(
            TrackingSnapshot.timestamp.between(start, end)))
        total = count.scalar_one()
        if not total:
            return []
        step = max(1, (total + max_points - 1) // max_points)
        numbered = select(TrackingSnapshot.id,
            func.row_number().over(order_by=(TrackingSnapshot.timestamp, TrackingSnapshot.id)).label("rn")
        ).where(TrackingSnapshot.timestamp.between(start, end)).subquery()
        result = await session.execute(select(TrackingSnapshot).join(numbered,
            TrackingSnapshot.id == numbered.c.id).where(func.mod(numbered.c.rn - 1, step) == 0)
            .order_by(TrackingSnapshot.timestamp, TrackingSnapshot.id).limit(max_points))
        return [{"ts": row.timestamp.isoformat(), "aircraft": row.aircraft,
            "vessels": row.vessels, "jamming": row.jamming_zones}
            for row in result.scalars().all()]


async def start_snapshot_recorder():
    """Background task that records tracking snapshots periodically."""
    logger.info("Snapshot recorder started (interval: %ds, retention: %dd)", SNAPSHOT_INTERVAL, RETENTION_DAYS)
    # Wait for caches to populate
    await asyncio.sleep(30)
    while True:
        try:
            await _record_snapshot()
            await _prune_old_snapshots()
        except Exception as e:
            logger.error("Snapshot recorder error: %s", e)
        await asyncio.sleep(SNAPSHOT_INTERVAL)

from datetime import datetime

from fastapi import APIRouter, Query, HTTPException

from app.services.maritime import get_vessels
from app.services.opensky import get_aircraft, get_aircraft_track, get_jamming_zones
from app.services.satellites import get_tles
from app.services.snapshots import get_snapshots

router = APIRouter(prefix="/tracking", tags=["tracking"])


@router.get("/aircraft")
async def aircraft():
    """Return cached aircraft positions from OpenSky."""
    return get_aircraft()


@router.get("/aircraft/{icao24}/track")
async def aircraft_track(icao24: str):
    """Return position history (last ~15 min) for a single aircraft."""
    return get_aircraft_track(icao24)


@router.get("/tle")
async def tle():
    """Return cached TLE records from CelesTrak."""
    return get_tles()


@router.get("/jamming")
async def jamming():
    """Return navigation-quality anomaly candidates, not confirmed jamming."""
    return get_jamming_zones()


@router.get("/vessels")
async def vessels():
    """Return cached maritime vessel positions from AISStream."""
    return get_vessels()


@router.get("/snapshots")
async def snapshots(
    start: str = Query(..., description="ISO datetime start"),
    end: str = Query(..., description="ISO datetime end"),
):
    """Return tracking snapshots for replay. Downsampled for large windows."""
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        if start_dt.tzinfo is None or end_dt.tzinfo is None or end_dt <= start_dt:
            raise ValueError("UTC-aware ordered interval required")
        if (end_dt - start_dt).total_seconds() > 31 * 86400:
            raise ValueError("Maximum replay window is 31 days")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return await get_snapshots(start_dt, end_dt)

"""Independent ODbL snapshots of the existing adsb.lol collector cache.

No additional upstream requests, no OpenSky records, private reports, heuristic
ownership, emergency assessment or navigation inference enter this dataset.
Every displayed derivative snapshot is independently downloadable under ODbL.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.db import async_session
from app.models import PublicAircraftBatch
from app.services.public_observations import canonical, digest, utcnow

logger = logging.getLogger(__name__)
SOURCE = "adsb_lol"
LICENSE_URL = "https://opendatacommons.org/licenses/odbl/1-0/"
SOURCE_URL = "https://www.adsb.lol/docs/open-data/api"
ATTRIBUTION = "Contains information from adsb.lol, made available under the Open Database License (ODbL) 1.0. This independent derivative snapshot is offered under the same license."
POLL_SECONDS = 30
TTL = 120
MAX_ROWS = 5000
MAX_PACKET_BYTES = 3_000_000
LOCK_ID = 56182843097261032
REGIONS = [dict(id=k, lat=la, lon=lo, radius_nm=250) for k,la,lo in (
    ("levant",33,35),("gulf",25,54),("iran_iraq",33,48),("red_sea",18,41))]


class AircraftPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    icao24: str = Field(pattern=r"^~?[0-9a-f]{6}$")
    source: Literal["adsb.lol"] = "adsb.lol"
    callsign: str = Field(max_length=16)
    origin_country: Literal[""] = ""
    lat: float = Field(ge=-90,le=90,allow_inf_nan=False)
    lon: float = Field(ge=-180,le=180,allow_inf_nan=False)
    altitude: float | None = Field(ge=-1000,le=61000,allow_inf_nan=False)
    altitude_reference: Literal["geometric_reported","barometric_standard_pressure","unknown"]
    velocity: float | None = Field(ge=0,le=1600,allow_inf_nan=False)
    heading: float | None = Field(ge=0,lt=360,allow_inf_nan=False)
    heading_basis: Literal["course_over_ground","true_heading"] | None
    on_ground: bool
    position_source: int | None = Field(ge=0,le=3)
    nic: float | None = Field(ge=0,le=11,allow_inf_nan=False)
    nac_p: float | None = Field(ge=0,le=11,allow_inf_nan=False)
    type: str = Field(max_length=12)
    registration: str = Field(max_length=24)
    category: str = Field(max_length=8)
    observed_at: str
    received_at: str
    normalized_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("observed_at","received_at")
    @classmethod
    def clock(cls,value):
        if len(value)>40 or datetime.fromisoformat(value).tzinfo is None:
            raise ValueError("Timezone required")
        return value

    @field_validator("callsign","type","registration","category")
    @classmethod
    def printable(cls,value):
        if not value.isascii() or any(ord(c)<32 or ord(c)>126 for c in value):
            raise ValueError("Unexpected aircraft identifier")
        return value


class AircraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid",strict=True)
    schema_version: Literal[1] = 1
    source: Literal["adsb_lol"] = SOURCE
    source_url: Literal[SOURCE_URL] = SOURCE_URL
    license: Literal["ODbL-1.0"] = "ODbL-1.0"
    license_url: Literal[LICENSE_URL] = LICENSE_URL
    attribution: Literal[ATTRIBUTION] = ATTRIBUTION
    captured_at: str
    provider_snapshot_at: str
    source_records: int = Field(ge=0,le=MAX_ROWS)
    filtered_records: int = Field(ge=0,le=MAX_ROWS)
    aircraft: list[AircraftPosition] = Field(max_length=MAX_ROWS)
    _clock = field_validator("captured_at","provider_snapshot_at")(AircraftPosition.clock.__func__)

    @model_validator(mode="after")
    def consistent_batch(self):
        if self.filtered_records + len(self.aircraft) != self.source_records:
            raise ValueError("Aircraft publication counts do not reconcile")
        if len({position.icao24 for position in self.aircraft}) != len(self.aircraft):
            raise ValueError("Duplicate aircraft publication identity")
        return self


def prepare_snapshot(rows, status, now):
    if status.get("source") != "adsb.lol" or status.get("status") != "ok" or len(rows)>MAX_ROWS:
        raise ValueError("No fresh licensed provider cache")
    provider_stamp = datetime.fromisoformat(status["source_timestamp"])
    if provider_stamp.tzinfo is None or not -5 <= (now-provider_stamp).total_seconds() <= TTL:
        raise ValueError("Stale provider snapshot")
    output, seen = [], set()
    keys=set(AircraftPosition.model_fields)-{"normalized_record_sha256","origin_country"}
    filtered=0
    for row in rows:
        if row.get("source") != "adsb.lol":
            filtered+=1
            continue
        observed=datetime.fromisoformat(row["observed_at"])
        if observed.tzinfo is None or not 0 <= (now-observed).total_seconds() <= TTL:
            filtered+=1
            continue
        projected={k:row.get(k) for k in keys}
        projected["normalized_record_sha256"]=digest(projected)
        pixel=AircraftPosition.model_validate(projected)
        if pixel.icao24 in seen:
            raise ValueError("Duplicate aircraft identity")
        seen.add(pixel.icao24);output.append(pixel)
    output.sort(key=lambda p:p.icao24)
    packet=AircraftPayload(captured_at=now.isoformat(),provider_snapshot_at=status["source_timestamp"],source_records=len(rows),filtered_records=filtered,aircraft=output).model_dump()
    if len(canonical(packet))>MAX_PACKET_BYTES:
        raise ValueError("Aircraft publication bound exceeded")
    return packet


async def publish_once():
    if settings.public_read_only or settings.demo_mode or not settings.live_ingestion_enabled or not settings.public_aircraft_publisher_enabled:
        raise ValueError("Private aircraft publication is disabled")
    from app.services.opensky import get_aircraft,get_aircraft_status
    async with async_session() as session:
        async with session.begin():
            if not (await session.execute(text("SELECT pg_try_advisory_xact_lock(:key)"),{"key":LOCK_ID})).scalar_one():
                return "already_running"
            now=utcnow()
            previous=(await session.execute(select(PublicAircraftBatch.published_at).where(PublicAircraftBatch.source==SOURCE).order_by(PublicAircraftBatch.published_at.desc()).limit(1))).scalar_one_or_none()
            if previous is not None and (now-previous).total_seconds()<POLL_SECONDS:
                return "not_due"
            try:
                payload=prepare_snapshot(get_aircraft(now=now.timestamp()),get_aircraft_status(now=now.timestamp()),now)
                state="ok"
            except (ValueError,KeyError,TypeError):
                payload,state={},"failed"
            identity=digest({"source":SOURCE,"published_at":now.isoformat(),"status":state,"payload":payload})
            await session.execute(insert(PublicAircraftBatch).values(id=identity,source=SOURCE,published_at=now,status=state,payload=payload).on_conflict_do_nothing(index_elements=["id"]))
            await session.execute(delete(PublicAircraftBatch).where(PublicAircraftBatch.published_at<now-timedelta(hours=1)))
    return state


async def start_public_aircraft_publisher():
    while True:
        try:await publish_once()
        except Exception as exc:logger.warning("Public aircraft publication failed (%s)",type(exc).__name__)
        await asyncio.sleep(POLL_SECONDS)


def describe(row, now, download=False):
    result={"source":SOURCE,"source_url":SOURCE_URL,"license":"ODbL-1.0","license_url":LICENSE_URL,"attribution":ATTRIBUTION,
        "status":"awaiting_publication","batch_id":None,"published_at":None,"aircraft":[],"coverage":REGIONS,
        "position_expires_after_seconds":TTL,"packet_retention_seconds":3600,"download_url":None,
        "limitations":"Selected query regions, not global coverage. Reported positions and identifiers are unverified. Surface projections; no inferred motion, ownership, mission or intent."}
    if row is None:return result
    if row.source!=SOURCE or row.status not in {"ok","failed"} or row.published_at.tzinfo is None or (now-row.published_at).total_seconds() < -5:
        raise ValueError("Invalid publication envelope")
    packet={"source":SOURCE,"published_at":row.published_at.isoformat(),"status":row.status,"payload":row.payload}
    if len(canonical(row.payload))>MAX_PACKET_BYTES or digest(packet)!=row.id:
        raise ValueError("Publication integrity check failed")
    if row.status=="failed":
        if row.payload!={}:raise ValueError("Invalid failure payload")
        result.update(status="failed",published_at=row.published_at.isoformat())
        return result
    payload=AircraftPayload.model_validate(row.payload).model_dump()
    visible=[p for p in payload["aircraft"] if 0 <= (now-datetime.fromisoformat(p["observed_at"])).total_seconds()<=TTL]
    result.update(status="stale" if (now-row.published_at).total_seconds()>TTL else "fresh" if visible else "empty",
        batch_id=row.id,published_at=row.published_at.isoformat(),aircraft=visible,
        provider_snapshot_at=payload["provider_snapshot_at"],source_records=payload["source_records"],filtered_records=payload["filtered_records"],
        download_url=f"/publication/aircraft/download/{row.id}")
    if download:return {**packet,"batch_id":row.id,"license":"ODbL-1.0","license_url":LICENSE_URL,"attribution":ATTRIBUTION}
    return result


async def read_public_aircraft(batch_id=None):
    async with async_session() as session:
        query=select(PublicAircraftBatch).where(PublicAircraftBatch.source==SOURCE)
        query=query.where(PublicAircraftBatch.id==batch_id) if batch_id else query.order_by(PublicAircraftBatch.published_at.desc(),PublicAircraftBatch.id.desc()).limit(1)
        row=(await session.execute(query)).scalar_one_or_none()
    if batch_id and (row is None or row.published_at < utcnow()-timedelta(hours=1)):return None
    return await asyncio.to_thread(describe,row,utcnow(),batch_id is not None)

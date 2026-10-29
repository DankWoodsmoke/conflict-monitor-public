"""CelesTrak GP elements with explicit OMM format and observable freshness.

The historical /tracking/tle route remains, but new catalog identifiers no
longer fit in TLE. Consumers prefer ``omm`` and satellite.js json2satrec.
An orbit is propagation from its published epoch, not live sensor imagery.
"""

import asyncio
import copy
import json
import logging
import math
import re
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)
CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"
TLE_GROUPS = ["military"]  # Compatibility name; transport is OMM JSON.
REFRESH_INTERVAL = 6 * 3600
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 10_000
_tle_cache: list[dict] = []
_last_attempt_at: datetime | None = None
_last_success_at: datetime | None = None
_last_error: str | None = None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc(value: str) -> datetime:
    if (not isinstance(value, str) or len(value) > 64
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", value)):
        raise ValueError("missing orbit epoch")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # CelesTrak omits TIME_SYSTEM=UTC and EPOCH has no suffix by default.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_omm_records(payload, *, group: str, fetched_at: datetime) -> list[dict]:
    """Validate an entire provider snapshot before replacing cached data.

    Empty/malformed/duplicate-ID snapshots fail instead of becoming fresh empty
    coverage. No guessed positions, artificial TLEs or epochs are generated.
    """
    if not isinstance(payload, list) or not 0 < len(payload) <= MAX_RECORDS:
        raise ValueError("expected a nonempty bounded OMM array")
    records: list[dict] = []
    seen: set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("OMM record is not an object")
        raw_id = row.get("NORAD_CAT_ID")
        if isinstance(raw_id, bool) or not re.fullmatch(r"[1-9][0-9]{0,8}", str(raw_id)):
            raise ValueError("invalid NORAD catalog identifier")
        norad_id = str(raw_id)
        if norad_id in seen:
            raise ValueError("duplicate NORAD catalog identifier")
        seen.add(norad_id)
        epoch = _utc(row.get("EPOCH"))
        name = row.get("OBJECT_NAME")
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise ValueError("invalid satellite name")
        for key, expected in (("CENTER_NAME", "EARTH"), ("REF_FRAME", "TEME"),
                              ("TIME_SYSTEM", "UTC"), ("MEAN_ELEMENT_THEORY", "SGP4")):
            if row.get(key, expected) != expected:
                raise ValueError(f"unsupported OMM {key}")
        omm = {"OBJECT_NAME": name.strip(), "NORAD_CAT_ID": int(norad_id),
               "EPOCH": _iso(epoch)}
        object_id = row.get("OBJECT_ID", "")
        if not isinstance(object_id, str) or len(object_id) > 64:
            raise ValueError("invalid international designator")
        omm["OBJECT_ID"] = object_id
        for key in ("MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
                    "ARG_OF_PERICENTER", "MEAN_ANOMALY", "BSTAR", "MEAN_MOTION_DOT",
                    "MEAN_MOTION_DDOT"):
            raw = row.get(key)
            if isinstance(raw, bool) or raw is None:
                raise ValueError(f"missing or invalid OMM {key}")
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid OMM {key}") from exc
            if not math.isfinite(value):
                raise ValueError(f"nonfinite OMM {key}")
            omm[key] = value
        if omm["MEAN_MOTION"] <= 0 or not 0 <= omm["ECCENTRICITY"] < 1:
            raise ValueError("invalid mean motion or eccentricity")
        if not 0 <= omm["INCLINATION"] <= 180:
            raise ValueError("invalid inclination")
        if any(not 0 <= omm[key] < 360 for key in
               ("RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY")):
            raise ValueError("invalid orbital angle")
        for key in ("CLASSIFICATION_TYPE", "ELEMENT_SET_NO", "REV_AT_EPOCH", "EPHEMERIS_TYPE"):
            if key in row:
                raw = row[key]
                if key == "CLASSIFICATION_TYPE":
                    if raw not in ("U", "C", "S"):
                        raise ValueError("invalid classification type")
                elif isinstance(raw, bool) or not re.fullmatch(r"[0-9]{1,12}", str(raw)):
                    raise ValueError(f"invalid OMM {key}")
                omm[key] = raw
        line1, line2 = row.get("TLE_LINE1"), row.get("TLE_LINE2")
        if line1 is not None or line2 is not None:
            if (not isinstance(line1, str) or not isinstance(line2, str)
                    or not line1.startswith("1 ") or not line2.startswith("2 ")
                    or line1[2:7].strip() != norad_id or line2[2:7].strip() != norad_id):
                raise ValueError("TLE lines do not match the OMM identifier")
        records.append({
            "name": name.strip(), "line1": line1, "line2": line2, "omm": omm,
            "norad_id": norad_id, "epoch": _iso(epoch), "format": "OMM_JSON",
            "source": "CelesTrak", "source_group": group,
            "source_url": f"{CELESTRAK_URL}?GROUP={group}&FORMAT=JSON",
            "fetched_at": _iso(fetched_at),
        })
    return records


async def refresh_satellites(client: httpx.AsyncClient) -> bool:
    """Failed refreshes preserve the last good cohort and its original clock."""
    global _tle_cache, _last_attempt_at, _last_success_at, _last_error
    _last_attempt_at = datetime.now(timezone.utc)
    try:
        records: list[dict] = []
        for group in TLE_GROUPS:
            async with asyncio.timeout(65):
                async with client.stream("GET", CELESTRAK_URL,
                                         params={"GROUP": group, "FORMAT": "JSON"}) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise ValueError("CelesTrak response exceeds byte limit")
            records.extend(normalize_omm_records(json.loads(body), group=group,
                                                 fetched_at=_last_attempt_at))
        # Groups can overlap; retain the newest published epoch per object.
        by_id: dict[str, dict] = {}
        for row in records:
            previous = by_id.get(row["norad_id"])
            if previous is None or row["epoch"] > previous["epoch"]:
                by_id[row["norad_id"]] = row
        if not by_id:
            raise ValueError("no satellite groups produced records")
        _tle_cache = list(by_id.values())
        _last_success_at = _last_attempt_at
        _last_error = None
        logger.info("CelesTrak: cached %d validated OMM records", len(_tle_cache))
        return True
    except (httpx.HTTPError, ValueError, TypeError, TimeoutError, RecursionError) as exc:
        # No response bodies or arbitrary upstream text enter health output.
        _last_error = (f"upstream HTTP {exc.response.status_code}"
                       if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__)
        logger.warning("CelesTrak refresh failed (%s); retained %d records", _last_error, len(_tle_cache))
        return False


async def start_tle_fetcher():
    async with httpx.AsyncClient(timeout=60, follow_redirects=False,
                                headers={"User-Agent": "ConflictMonitor/1.0 (CelesTrak OMM)"}) as client:
        while True:
            await refresh_satellites(client)
            await asyncio.sleep(REFRESH_INTERVAL)


def get_tles(*, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    records = copy.deepcopy(_tle_cache)
    for row in records:
        row["epoch_age_hours"] = round((now - _utc(row["epoch"])).total_seconds() / 3600, 3)
    return records


def get_tle_status(*, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    age = (now - _last_success_at).total_seconds() if _last_success_at else None
    stale = age is not None and age > 2 * REFRESH_INTERVAL
    status = "failed" if _last_error else "unavailable" if age is None else "stale" if stale else "ok"
    return {
        "status": status, "source": "CelesTrak", "format": "OMM_JSON",
        "record_count": len(_tle_cache), "data_available": bool(_tle_cache),
        "last_attempt_at": _iso(_last_attempt_at) if _last_attempt_at else None,
        "last_success_at": _iso(_last_success_at) if _last_success_at else None,
        "data_age_seconds": round(max(0, age), 1) if age is not None else None,
        "data_stale": stale, "refresh_interval_seconds": REFRESH_INTERVAL,
        "error": _last_error,
        "interpretation": "SGP4 propagation from element epoch; not live imagery or measured current position",
    }

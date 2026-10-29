"""Aircraft tracking service.

Uses four explicitly bounded adsb.lol circles at the same one-request/15-second
budget, with a budgeted anonymous OpenSky fallback. Regional observations are
merged by identity and actual position time; failed regions never become empty
successes. Source clocks and expiry are separate from collection time. Navigation
quality and position-method clusters are unverified inspection aids.
"""

import asyncio
import logging
import copy
import re
import time
from collections import defaultdict, deque, OrderedDict

import httpx

from app.config import settings
from app.services.tracking_contract import bounded_json, coordinates, iso, number, source_epoch, text

logger = logging.getLogger(__name__)

# Compatibility defaults for a standalone adapter call. The live poller rotates
# the named circles below; no radius exceeds the public API's 250 NM maximum.
CENTRE_LAT = 30
CENTRE_LON = 45
RADIUS_NM = 250  # documented API maximum; coverage is this circle, not the whole region
AIRCRAFT_REGIONS = (
    {"id": "levant", "label": "Eastern Mediterranean", "lat": 33, "lon": 35},
    {"id": "gulf", "label": "Persian Gulf", "lat": 25, "lon": 54},
    {"id": "iran_iraq", "label": "Iran / Iraq", "lat": 33, "lon": 48},
    {"id": "red_sea", "label": "Red Sea", "lat": 18, "lon": 41},
)

POLL_INTERVAL = 15  # seconds

# Bound both distinct identities and history per aircraft.
TRACK_MAX_POINTS = 120
MAX_TRACKED_AIRCRAFT = 1000
MAX_AIRCRAFT = 5000
POSITION_TTL = 120
CACHE_TTL = 180
TRACK_TTL = 1800
FRESH_AGE = 45
OPENSKY_FALLBACK_INTERVAL = 900  # anonymous 400 credits/day, 4 credits for this bbox
_tracks: OrderedDict[str, deque] = OrderedDict()
_cache = {"states": [], "timestamp": 0, "jamming": [], "source": None,
          "last_attempt": None, "last_success": None, "source_time": None,
          "error": None, "rejected_records": 0}
_next_attempt = {"adsb.lol": 0.0, "opensky": 0.0}
_regional_snapshots: dict[str, dict] = {}
_regional_health: dict[str, dict] = {}
COVERAGE = {
    "adsb.lol": {"kind": "regional_circles", "radius_nm": RADIUS_NM,
                 "circles": [dict(region, radius_nm=RADIUS_NM) for region in AIRCRAFT_REGIONS],
                 "minimum_request_interval_seconds": POLL_INTERVAL,
                 "nominal_revisit_seconds": POLL_INTERVAL * len(AIRCRAFT_REGIONS)},
    "opensky": {"kind": "bounding_box", "south": 15, "north": 45, "west": 25, "east": 65},
}
UNITS = {"altitude": "m", "velocity": "m/s", "heading": "degrees", "climb_rate": "m/s"}


def _detect_jamming(states: list[dict]) -> list[dict]:
    """Aggregate low-quality or MLAT positions; neither signal proves jamming."""
    jammed = [
        s for s in states
        if not s.get("on_ground") and (
            s.get("position_source") == 2
            or (s.get("nac_p") == 0 and s.get("nic") == 0)
        )
        and all(v is not None for v in coordinates(s.get("lat"), s.get("lon")))
    ]
    if len(jammed) < 2:
        return []

    grid_size = 0.8  # degrees (~90 km)
    grid: dict[tuple[float, float], list[dict]] = defaultdict(list)
    grid_ids: dict[tuple[float, float], set[str]] = defaultdict(set)
    for ac in jammed:
        latitude, longitude = coordinates(ac["lat"], ac["lon"])
        key = (
            round(latitude / grid_size) * grid_size,
            round(longitude / grid_size) * grid_size,
        )
        identity = ac.get("icao24")
        if identity and identity in grid_ids[key]:
            continue
        if identity:
            grid_ids[key].add(identity)
        grid[key].append(ac)

    zones = []
    for (lat, lon), aircraft in grid.items():
        if len(aircraft) >= 2:
            zones.append({
                "lat": lat,
                "lon": lon,
                "radius_km": grid_size * 111 / 2,
                "aircraft_count": len(aircraft),
                "intensity": min(len(aircraft) / 8, 1.0),
                "assessment": "navigation_quality_anomaly",
                "jamming_confirmed": False,
                "mlat_position_count": sum(a.get("position_source") == 2 for a in aircraft),
                "low_accuracy_count": sum(a.get("nac_p") == 0 and a.get("nic") == 0 for a in aircraft),
                "limitations": ["MLAT and low accuracy alone do not establish interference or attribution.",
                                "This short-window heuristic is not GPSJAM methodology or a calibrated detector."],
            })
    return zones


# ── Aircraft classification ────────────────────────────────────────────────

# Military aircraft type codes
_MIL_FIGHTERS = {
    "F16", "F15", "F15E", "F18", "F35", "F22", "EF2K", "RFAL", "TYPH",
    "SU27", "SU30", "SU34", "SU35", "SU25", "SU24", "MIG29", "MIG31",
    "B1", "B2", "B52", "B52H", "A10", "HAWK", "M346", "T38",
    "JF17", "J10", "J16", "J20", "FA50", "GRIB", "TORN",
}
_MIL_TANKERS = {
    "KC10", "KC46", "KC35", "K35R", "KC30", "KC13", "A330MRTT",
    "IL78", "A400",
}
_MIL_CARGO = {
    "C17", "C5", "C5M", "C130", "C130J", "C2", "IL76", "AN12",
    "AN22", "AN24", "AN26", "AN32", "AN72", "AN74", "AN124", "AN225",
    "C160", "C27J", "A400M", "CN35",
}
_SURVEILLANCE = {
    "E3CF", "E3TF", "E6B", "E8C", "RC135", "RC12", "RC26", "P3",
    "P8", "P8A", "GLXE", "RQ4", "E2C", "E2D", "E737", "G550CAEW",
    "EP3", "EC130", "MC12", "U2",
}
_UAVS = {
    "HRON", "MQ9", "MQ1", "RQ4", "RQ7", "ANKA", "BAYRKTR", "MQ25",
    "HERMS", "RQ21", "BT2B",
}
_HELICOPTERS = {
    "AH64", "UH60", "CH47", "CH53", "MI24", "MI35", "MI8", "MI17",
    "KA52", "S70", "NH90", "AW139", "AW101", "V22", "MH60",
    "H60", "AS332", "EC725", "AH1Z", "UH1Y",
}

# US military ICAO hex ranges (AE/AF prefix = ~AE0000-AFFFFF)
_US_MIL_HEX_START = int("AE0000", 16)
_US_MIL_HEX_END = int("AFFFFF", 16)
# Israeli military range
_IL_MIL_HEX_START = int("738000", 16)
_IL_MIL_HEX_END = int("738FFF", 16)

# Military callsign prefixes
_MIL_CALLSIGN_PREFIXES = (
    "RCH", "REACH", "DUKE", "IRON", "VIPER", "COBRA", "TOPCAT", "HAVOC",
    "FORTE", "LAGR", "HOMER", "KNIFE", "DOOM", "REAPER", "HAWK", "BOLT",
    "RAGE", "SKULL", "PYTHON", "DAGGER", "SNTRY", "AWACS", "IAF", "RFR",
    "CNV", "CFC", "RRR", "EVAC", "SAM", "TITAN", "ATLAS", "GIANT",
    "NCHO", "PACK", "MOOSE", "GORDO", "TEAL", "GOLD",
)


def _classify_aircraft(ac: dict) -> tuple[str, bool]:
    """Classify aircraft and detect emergencies. Returns (category, is_emergency)."""
    squawk = ac.get("squawk", "")
    is_emergency = squawk in ("7700", "7600", "7500")

    ac_type = (ac.get("type") or "").upper().replace("-", "")
    callsign = (ac.get("callsign") or "").upper().strip()
    hex_code = ac.get("icao24", "")
    category = (ac.get("category") or "")

    # UAV by ADS-B category
    if category == "B2":
        return "uav", is_emergency

    # Rotorcraft by ADS-B category
    if category == "A7":
        return "helicopter", is_emergency

    # Type code matches (most specific)
    if ac_type in _UAVS:
        return "uav", is_emergency
    if ac_type in _SURVEILLANCE:
        return "surveillance", is_emergency
    if ac_type in _MIL_FIGHTERS:
        return "military", is_emergency
    if ac_type in _MIL_TANKERS:
        return "tanker", is_emergency
    if ac_type in _MIL_CARGO:
        return "cargo", is_emergency
    if ac_type in _HELICOPTERS:
        return "helicopter", is_emergency

    # ICAO hex range (US military, Israeli military)
    try:
        hex_int = int(hex_code, 16)
        if _US_MIL_HEX_START <= hex_int <= _US_MIL_HEX_END:
            return "military", is_emergency
        # A national allocation includes civilian registrations; it is not a military identifier.
    except (ValueError, TypeError):
        pass

    # Callsign pattern
    for prefix in _MIL_CALLSIGN_PREFIXES:
        if callsign.startswith(prefix):
            return "military", is_emergency

    return "civilian", is_emergency


def _finish_aircraft(row, *, observed, received, provider):
    row.update({"observed_at": iso(observed), "observed_timestamp": observed,
                "received_at": iso(received), "received_timestamp": received,
                "source": provider, "units": UNITS.copy(),
                "classification_status": "heuristic_unverified"})
    category, emergency = _classify_aircraft(row)
    row.update(aircraft_category=category, is_emergency=emergency)
    return row


def normalize_adsb(data, *, received):
    if not isinstance(data, dict) or not isinstance(data.get("ac"), list) or len(data["ac"]) > MAX_AIRCRAFT:
        raise ValueError("Invalid or oversized ADS-B snapshot")
    stamp = source_epoch(data.get("now"), now=received, milliseconds=True)
    if stamp is None or received - stamp > CACHE_TTL:
        raise ValueError("ADS-B snapshot clock is missing or stale")
    states = {}
    rejected = 0
    for item in data["ac"]:
        if not isinstance(item, dict):
            rejected += 1
            continue
        # Never promote receiver-derived rr_lat/rr_lon or lastPosition to current position.
        lat, lon = coordinates(item.get("lat"), item.get("lon"))
        identity = item.get("hex", "").lower() if isinstance(item.get("hex"), str) else ""
        age = number(item.get("seen_pos"), 0)
        if lat is None or lon is None or not re.fullmatch(r"~?[0-9a-f]{6}", identity) or age is None:
            rejected += 1
            continue
        observed = stamp - age
        if received - observed > POSITION_TTL:
            continue
        alt_source = "alt_geom" if item.get("alt_geom") is not None else "alt_baro"
        alt = item.get(alt_source)
        climb = item.get("baro_rate") if item.get("baro_rate") is not None else item.get("geom_rate")
        alt, speed, climb = number(alt, -2000, 200000), number(item.get("gs"), 0, 3000), number(climb, -60000, 60000)
        heading = number(item.get("track"), 0, 360)
        if heading is None:
            heading = number(item.get("true_heading"), 0, 360)
        row = {
            "icao24": identity, "callsign": text(item.get("flight"), 16), "origin_country": "",
            "lat": lat, "lon": lon, "altitude": alt * 0.3048 if alt is not None else None,
            "altitude_source": alt_source if alt is not None else None,
            "altitude_reference": ("geometric_reported" if alt_source == "alt_geom" else "barometric_standard_pressure") if alt is not None else "unknown",
            "velocity": speed * 0.5144444444444445 if speed is not None else None,
            "climb_rate": climb * 0.00508 if climb is not None else None, "heading": heading,
            "on_ground": item.get("alt_baro") == "ground",
            "position_source": 2 if isinstance(item.get("mlat"), list) and "lat" in item["mlat"] else 0,
            "nac_p": number(item.get("nac_p"), 0, 11), "nic": number(item.get("nic"), 0, 11),
            "type": text(item.get("t"), 12), "registration": text(item.get("r"), 24),
            "category": text(item.get("category"), 8), "squawk": text(item.get("squawk"), 4),
            "emergency": text(item.get("emergency"), 40),
        }
        prior = states.get(identity)
        if prior is None or observed > prior["observed_timestamp"]:
            states[identity] = _finish_aircraft(row, observed=observed, received=received, provider="adsb.lol")
    if data["ac"] and rejected == len(data["ac"]):
        raise ValueError("No usable ADS-B rows in nonempty snapshot")
    return {"states": list(states.values()), "source_time": stamp, "source": "adsb.lol", "rejected_records": rejected}


def normalize_opensky(data, *, received):
    if not isinstance(data, dict) or "states" not in data:
        raise ValueError("Invalid OpenSky response")
    rows = data["states"] if data["states"] is not None else []
    stamp = source_epoch(data.get("time"), now=received)
    if not isinstance(rows, list) or len(rows) > MAX_AIRCRAFT or stamp is None or received - stamp > CACHE_TTL:
        raise ValueError("Invalid or stale OpenSky snapshot")
    states = {}
    rejected = 0
    for item in rows:
        if not isinstance(item, list) or len(item) < 17:
            rejected += 1
            continue
        lat, lon = coordinates(item[6], item[5])
        identity = item[0].lower() if isinstance(item[0], str) else ""
        observed = source_epoch(item[3], now=received)
        if lat is None or lon is None or not re.fullmatch(r"[0-9a-f]{6}", identity) or observed is None:
            rejected += 1
            continue
        if received - observed > POSITION_TTL:
            continue
        if type(item[8]) is not bool:
            rejected += 1
            continue
        row = {"icao24": identity, "callsign": text(item[1], 16), "origin_country": text(item[2], 80),
               "lat": lat, "lon": lon, "altitude": number(item[13] if item[13] is not None else item[7], -1000, 61000),
               "altitude_source": "geo_altitude" if item[13] is not None else "baro_altitude",
               "altitude_reference": "geometric_reported" if item[13] is not None else "barometric_standard_pressure",
               "velocity": number(item[9], 0, 1600), "heading": number(item[10], 0, 360),
               "climb_rate": number(item[11], -305, 305), "on_ground": item[8],
               "position_source": int(item[16]) if number(item[16], 0, 3) is not None else None,
               "squawk": text(item[14], 4), "type": "", "registration": "", "category": ""}
        if row["altitude"] is None:
            row.update(altitude_source=None, altitude_reference="unknown")
        prior = states.get(identity)
        if prior is None or observed > prior["observed_timestamp"]:
            states[identity] = _finish_aircraft(row, observed=observed, received=received, provider="opensky")
    if rows and rejected == len(rows):
        raise ValueError("No usable OpenSky rows in nonempty snapshot")
    return {"states": list(states.values()), "source_time": stamp, "source": "opensky", "rejected_records": rejected}


def _provider_failure(provider, exc):
    now = time.time()
    error = type(exc).__name__
    delay = 30
    if isinstance(exc, httpx.HTTPStatusError):
        error = f"HTTP_{exc.response.status_code}"
        if exc.response.status_code in (401, 403):
            delay = 86400
        if exc.response.status_code == 429:
            delay = number(exc.response.headers.get("X-Rate-Limit-Retry-After-Seconds") or
                           exc.response.headers.get("Retry-After"), 1, 86400) or 900
    _next_attempt[provider] = max(_next_attempt[provider], now + delay)
    _cache["error"] = f"{provider}:{error}"
    logger.warning("Aircraft provider failed: %s", _cache["error"])


async def _poll_adsb_lol(client, *, region=None):
    if time.time() < _next_attempt["adsb.lol"]:
        return None
    _cache["last_attempt"] = time.time()
    try:
        async with asyncio.timeout(25):
            latitude = region["lat"] if region is not None else CENTRE_LAT
            longitude = region["lon"] if region is not None else CENTRE_LON
            data = await bounded_json(client, f"https://api.adsb.lol/v2/lat/{latitude}/lon/{longitude}/dist/{RADIUS_NM}")
        return normalize_adsb(data, received=time.time())
    except (httpx.HTTPError, ValueError, TypeError, TimeoutError, RecursionError) as exc:
        _provider_failure("adsb.lol", exc)
        return None


async def _poll_opensky(client, auth=None):
    # Basic auth was retired. Anonymous fallback is credit-budgeted; OAuth is a separate adapter.
    if time.time() < _next_attempt["opensky"]:
        return None
    now = time.time()
    _cache["last_attempt"] = now
    _next_attempt["opensky"] = now + OPENSKY_FALLBACK_INTERVAL
    try:
        async with asyncio.timeout(25):
            data = await bounded_json(client, "https://opensky-network.org/api/states/all",
                                      params={"lamin": 15, "lamax": 45, "lomin": 25, "lomax": 65})
        return normalize_opensky(data, received=time.time())
    except (httpx.HTTPError, ValueError, TypeError, TimeoutError, RecursionError) as exc:
        _provider_failure("opensky", exc)
        return None


def _prune_tracks(now):
    for identity in list(_tracks):
        points = _tracks[identity]
        while points and now - points[0]["ts"] > TRACK_TTL:
            points.popleft()
        if not points:
            del _tracks[identity]
    while len(_tracks) > MAX_TRACKED_AIRCRAFT:
        _tracks.popitem(last=False)


def _publish_snapshot(snapshot, *, now):
    _cache.update(snapshot, timestamp=now, last_success=now, error=None)
    _cache["jamming"] = _detect_jamming(snapshot["states"])
    for aircraft in snapshot["states"]:
        if aircraft.get("on_ground"):
            continue
        identity = aircraft["icao24"]
        points = _tracks.setdefault(identity, deque(maxlen=TRACK_MAX_POINTS))
        stamp = aircraft["observed_timestamp"]
        if not points or stamp > points[-1]["ts"]:
            points.append({"lat": aircraft["lat"], "lon": aircraft["lon"], "alt": aircraft.get("altitude"),
                           "ts": stamp, "source": aircraft["source"], "altitude_unit": "m"})
            _tracks.move_to_end(identity)
    _prune_tracks(now)


def _accept_region(region_id, snapshot, *, now):
    """Atomically retain a validated regional response; never mutate callers."""
    if region_id not in {region["id"] for region in AIRCRAFT_REGIONS}:
        raise ValueError("Unknown aircraft region")
    _regional_snapshots[region_id] = {"snapshot": copy.deepcopy(snapshot), "received_at": now}
    _regional_health[region_id] = {"last_attempt_at": now, "last_success_at": now, "error": None}


def _merged_regions(*, now):
    """Newest actual observation wins in overlaps, with bounded age and memory."""
    snapshots = [row["snapshot"] for row in _regional_snapshots.values()
                 if 0 <= now - row["received_at"] <= CACHE_TTL]
    if not snapshots:
        return None
    by_identity = {}
    for snapshot in snapshots:
        for row in snapshot["states"]:
            if not 0 <= now - row["observed_timestamp"] <= POSITION_TTL:
                continue
            prior = by_identity.get(row["icao24"])
            if prior is None or row["observed_timestamp"] > prior["observed_timestamp"]:
                by_identity[row["icao24"]] = row
    rows = sorted(by_identity.values(), key=lambda row: (-row["observed_timestamp"], row["icao24"]))[:MAX_AIRCRAFT]
    return {"states": copy.deepcopy(rows), "source_time": max(s["source_time"] for s in snapshots),
            "source": "adsb.lol", "rejected_records": sum(s["rejected_records"] for s in snapshots)}


def _region_status(*, now):
    result = []
    for region in AIRCRAFT_REGIONS:
        health = _regional_health.get(region["id"], {})
        success = health.get("last_success_at")
        age = max(0, now - success) if success is not None else None
        state = "failed" if health.get("error") else "not_collected" if success is None else "expired" if age > CACHE_TTL else "ok"
        result.append({**region, "radius_nm": RADIUS_NM, "status": state,
                       "last_attempt_at": iso(health.get("last_attempt_at")),
                       "last_success_at": iso(success), "cache_age_seconds": round(age, 1) if age is not None else None,
                       "error": health.get("error")})
    return result


async def start_opensky_poller():
    if settings.demo_mode or not settings.live_ingestion_enabled:
        return
    logger.info("Aircraft tracking: %d regional circles radius=%dnm, one request/%ds; anonymous OpenSky fallback", len(AIRCRAFT_REGIONS), RADIUS_NM, POLL_INTERVAL)
    region_index = 0
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        while True:
            region = AIRCRAFT_REGIONS[region_index]
            region_index = (region_index + 1) % len(AIRCRAFT_REGIONS)
            attempted_at = time.time()
            request_allowed = attempted_at >= _next_attempt["adsb.lol"]
            snapshot = await _poll_adsb_lol(client, region=region)
            now = time.time()
            if snapshot is not None:
                _accept_region(region["id"], snapshot, now=now)
                _publish_snapshot(_merged_regions(now=now), now=now)
            else:
                health = _regional_health.setdefault(region["id"], {})
                if request_allowed:
                    health["last_attempt_at"] = attempted_at
                health["error"] = _cache.get("error") or "provider_backoff"
                # Do not replace good regional coverage with a failure or refresh
                # its clock. Anonymous fallback remains separately credit-bound.
                if _merged_regions(now=now) is None:
                    fallback = await _poll_opensky(client)
                    if fallback is not None:
                        _publish_snapshot(fallback, now=time.time())
            _prune_tracks(time.time())
            await asyncio.sleep(POLL_INTERVAL)


def get_aircraft(*, now=None):
    now = time.time() if now is None else now
    if settings.demo_mode:
        return [{**copy.deepcopy(row), "source": "synthetic", "data_mode": "synthetic"} for row in _cache["states"]]
    success = _cache.get("last_success")
    if success is None or now - success > CACHE_TTL:
        return []
    return [{**copy.deepcopy(row), "age_seconds": max(0, round(now - row["observed_timestamp"], 1)),
             "stale": now - row["observed_timestamp"] > FRESH_AGE or now - success > FRESH_AGE}
            for row in _cache["states"] if now - row["observed_timestamp"] <= POSITION_TTL]


def get_aircraft_track(icao24, *, now=None):
    if not re.fullmatch(r"~?[0-9a-fA-F]{6}", icao24):
        return []
    _prune_tracks(time.time() if now is None else now)
    return copy.deepcopy(list(_tracks.get(icao24.lower(), [])))


def get_jamming_zones(*, now=None):
    if settings.demo_mode:
        return [{**copy.deepcopy(row), "data_mode": "synthetic", "jamming_confirmed": False} for row in _cache["jamming"]]
    return _detect_jamming(get_aircraft(now=now))


def get_aircraft_status(*, now=None):
    now = time.time() if now is None else now
    success = _cache.get("last_success")
    age = max(0, now - success) if success is not None else None
    data = get_aircraft(now=now)
    state = "synthetic" if settings.demo_mode else "disabled" if not settings.live_ingestion_enabled else (
        "unavailable" if success is None else "stale" if age > FRESH_AGE else "failed" if _cache.get("error") else "ok")
    return {"status": state, "source": "synthetic" if settings.demo_mode else _cache.get("source"),
            "count": len(data), "cached_count": len(_cache["states"]), "data_available": bool(data),
            "last_attempt_at": iso(_cache.get("last_attempt")), "last_success_at": iso(success),
            "source_timestamp": iso(_cache.get("source_time")), "cache_age_seconds": round(age, 1) if age is not None else None,
            "fresh_for_seconds": FRESH_AGE, "position_expires_after_seconds": POSITION_TTL,
            "error": _cache.get("error"), "rejected_records": _cache.get("rejected_records", 0),
            "coverage": copy.deepcopy(COVERAGE.get(_cache.get("source"), COVERAGE["adsb.lol"])),
            "regions": _region_status(now=now),
            "fallback": {"source": "opensky", "authentication": "anonymous", "minimum_interval_seconds": OPENSKY_FALLBACK_INTERVAL},
            "limitations": ["Selected regional circles, not global coverage; one ADS-B request every 15 seconds. A nominal full cycle takes at least 60 seconds plus network time.",
                            "Partial receiver/transponder coverage; no returned aircraft is not proof of no aircraft.",
                            "Geometric and barometric altitude references differ; no terrain/geoid correction has been established.",
                            "Aircraft type/category and emergency indication are reported or heuristic, not independently verified.",
                            "MLAT and low navigation accuracy do not establish jamming or attribution."]}



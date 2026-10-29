"""Maritime vessel tracking via AISStream.io WebSocket.

Connects to the AISStream WebSocket and maintains a cache of
vessel positions within the Middle East bounding box.
"""

import asyncio
import json
import logging
import time
import copy
import re
import random
from collections import OrderedDict
from datetime import datetime

from app.config import settings
from app.services.tracking_contract import coordinates, iso, number, source_epoch, text

logger = logging.getLogger(__name__)

# Conflict theater bounding boxes
# Box 1: Core conflict zone (Eastern Med / Red Sea / Persian Gulf / Hormuz)
# lon starts at 28 to exclude noisy Aegean/Greek shipping lanes
BOUNDING_BOXES = [
    [[8, 28], [42, 68]],  # Conflict theater: Eastern Med → Persian Gulf
]

MAX_VESSELS = 5000
MAX_MESSAGE_BYTES = 65536
POSITION_TTL = 600
STATIC_TTL = 1800
_cache = {"vessels": OrderedDict(), "last_update": None, "last_attempt": None,
          "last_message": None, "last_prune": 0, "connected": False, "error": None,
          "rejected_messages": 0, "evicted_records": 0, "compression_enabled": None}

# AIS ship type codes to human-readable categories
SHIP_TYPES = {
    range(20, 30): "Wing in Ground",
    range(40, 50): "High Speed Craft",
    range(60, 70): "Passenger",
    range(70, 80): "Cargo",
    range(80, 90): "Tanker",
    range(90, 100): "Other",
}


def _ship_type_name(code: int) -> str:
    # Individual codes are not ranges: 31 is towing, 36 sailing, 51 SAR.
    # https://www.navcen.uscg.gov/ais-class-a-static-voyage-message-5
    special = {30: "Fishing", 31: "Towing", 32: "Towing (large tow)",
               33: "Dredging or underwater operations", 34: "Diving operations",
               35: "Military or restricted operations (reported)", 36: "Sailing", 37: "Pleasure craft",
               50: "Pilot vessel", 51: "Search and rescue", 52: "Tug", 53: "Port tender",
               54: "Anti-pollution", 55: "Law enforcement", 58: "Medical transport",
               59: "Noncombatant ship (reported)"}
    if code in special:
        return special[code]
    for rng, name in SHIP_TYPES.items():
        if code in rng:
            return name
    return "Unknown"


# ── MMSI → Flag state (MID = Maritime Identification Digits, first 3 of MMSI)
# Source: ITU MID table. Only includes countries relevant to the conflict theater
# and major flag-of-convenience states.
# Registry allocation only, not current ownership/operator or military attribution.
# Corrected against https://www.itu.int/gladapp/Allocation/MIDs (2026-10-28).
_MID_FLAGS = {
    "209": "CY",
    "210": "CY",
    "211": "DE",
    "218": "DE",
    "224": "ES",
    "225": "ES",
    "226": "FR",
    "227": "FR",
    "228": "FR",
    "229": "MT",
    "230": "FI",
    "231": "FO",
    "232": "GB",
    "233": "GB",
    "234": "GB",
    "235": "GB",
    "236": "GI",
    "237": "GR",
    "239": "GR",
    "240": "GR",
    "241": "GR",
    "242": "MA",
    "244": "NL",
    "245": "NL",
    "246": "NL",
    "247": "IT",
    "248": "MT",
    "249": "MT",
    "255": "PT",
    "256": "MT",
    "271": "TR",
    "272": "UA",
    "273": "RU",
    "274": "MK",
    "275": "LV",
    "276": "EE",
    "277": "LT",
    "279": "RS",
    "303": "US",
    "309": "BS",
    "311": "BS",
    "312": "BZ",
    "314": "BB",
    "319": "KY",
    "338": "US",
    "341": "KN",
    "351": "PA",
    "352": "PA",
    "353": "PA",
    "354": "PA",
    "355": "PA",
    "356": "PA",
    "357": "PA",
    "366": "US",
    "367": "US",
    "368": "US",
    "369": "US",
    "370": "PA",
    "371": "PA",
    "372": "PA",
    "373": "PA",
    "374": "PA",
    "376": "VC",
    "377": "VC",
    "378": "VG",
    "403": "SA",
    "408": "BH",
    "413": "CN",
    "416": "TW",
    "422": "IR",
    "423": "AZ",
    "425": "IQ",
    "428": "IL",
    "431": "JP",
    "432": "JP",
    "436": "KZ",
    "437": "UZ",
    "438": "JO",
    "440": "KR",
    "441": "KR",
    "445": "KP",
    "447": "KW",
    "450": "LB",
    "461": "OM",
    "466": "QA",
    "468": "SY",
    "470": "AE",
    "471": "AE",
    "472": "TJ",
    "473": "YE",
    "475": "YE",
    "477": "HK",
    "533": "MY",
    "538": "MH",
    "548": "PH",
    "550": "TL",
    "564": "SG",
    "572": "TV",
    "574": "VN",
    "576": "VU",
    "577": "VU",
    "603": "AO",
    "605": "DZ",
    "622": "EG",
    "636": "LR",
    "637": "LR",
    "667": "SL",
    "674": "TZ",
    "677": "TZ"
}

# Flag labels for display
_FLAG_NAMES: dict[str, str] = {
    "SA": "Saudi Arabia", "BH": "Bahrain", "IR": "Iran", "IL": "Israel",
    "JO": "Jordan", "SY": "Syria", "LB": "Lebanon", "KW": "Kuwait",
    "IQ": "Iraq", "YE": "Yemen", "QA": "Qatar", "AE": "UAE", "OM": "Oman",
    "US": "United States", "GB": "United Kingdom", "FR": "France",
    "DE": "Germany", "IT": "Italy", "GR": "Greece", "TR": "Turkey",
    "RU": "Russia", "UA": "Ukraine", "EG": "Egypt", "ES": "Spain",
    "NL": "Netherlands", "PT": "Portugal", "MT": "Malta", "NO": "Norway",
    "PA": "Panama", "LR": "Liberia", "MH": "Marshall Islands",
    "BS": "Bahamas", "KY": "Cayman Islands", "SG": "Singapore",
    "MY": "Malaysia", "FI": "Finland", "MA": "Morocco", "GI": "Gibraltar",
    "VN": "Vietnam", "PH": "Philippines", "DZ": "Algeria", "TZ": "Tanzania",
    "EE": "Estonia", "LT": "Lithuania", "AZ": "Azerbaijan", "BE": "Belgium",
    "BZ": "Belize", "BB": "Barbados", "KN": "St Kitts", "JM": "Jamaica",
    "MX": "Mexico", "VC": "St Vincent", "VG": "BVI", "TW": "Taiwan",
    "TL": "Timor-Leste",
}


def _classify_vessel(vessel: dict) -> tuple[str, str, str]:
    """Classify a vessel. Returns (vessel_category, flag_code, flag_name)."""
    mmsi = vessel.get("mmsi", "")
    mid = mmsi[:3] if len(mmsi) >= 3 else ""
    ship_type = vessel.get("ship_type", 0) or 0
    name = (vessel.get("name") or "").upper()

    # MMSI allocation inferred from an unverified broadcast identity
    flag_code = _MID_FLAGS.get(mid, "")
    flag_name = _FLAG_NAMES.get(flag_code, "")

    # Naval detection: MMSI starting with 1-9 + MID pattern for warships
    # Military vessels often use specific type codes (35 = military ops, 55 = law enforcement)
    if ship_type == 35:
        return "naval", flag_code, flag_name

    # SAR (51) and anti-pollution (54) do not imply government ownership.
    if ship_type == 55:
        return "government", flag_code, flag_name

    if ship_type in (31, 32, 52):
        return "tug", flag_code, flag_name

    # Name-based category is heuristic, not verified naval ownership
    naval_keywords = (
        "WARSHIP", "NAVY", "NAVAL", "USS ", "HMS ", "ITS ", "TCG ", "FS ",
        "HNLMS ", "FRIGATE", "DESTROYER", "CORVETTE", "PATROL", "COAST GUARD",
        "COASTGUARD", " DDG", " FFG", " LHD", " LPD", " CG ",
    )
    for kw in naval_keywords:
        if kw in name or name.startswith(kw.strip()):
            return "naval", flag_code, flag_name

    # Standard AIS type classification
    if 80 <= ship_type <= 89:
        return "tanker", flag_code, flag_name
    if 70 <= ship_type <= 79:
        return "cargo", flag_code, flag_name
    if 60 <= ship_type <= 69:
        return "passenger", flag_code, flag_name
    if ship_type == 30:
        return "fishing", flag_code, flag_name
    if 40 <= ship_type <= 49:
        return "high_speed", flag_code, flag_name

    return "other", flag_code, flag_name



_FLAG_NAMES.update({"CY":"Cyprus", "FO":"Faroe Islands", "MK":"North Macedonia", "LV":"Latvia",
    "RS":"Serbia", "CN":"China", "JP":"Japan", "KZ":"Kazakhstan", "UZ":"Uzbekistan",
    "KR":"South Korea", "KP":"North Korea", "TJ":"Tajikistan", "HK":"Hong Kong",
    "TV":"Tuvalu", "VU":"Vanuatu", "AO":"Angola", "SL":"Sierra Leone"})


def _message_observed_at(meta, now):
    # AIS Timestamp is only seconds within a minute, not a complete UTC timestamp.
    # Do not fabricate an observation date from collection time.
    value = meta.get("time_utc")
    if not isinstance(value, str) or len(value) > 80:
        return None
    try:
        value = value.replace(" +0000 UTC", "+00:00").replace(" UTC", "+00:00")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return source_epoch(parsed.timestamp(), now=now)
    except (ValueError, OverflowError):
        return None


def _prune_vessels(now, *, force=False):
    if force or now - _cache["last_prune"] >= 30:
        for identity in list(_cache["vessels"]):
            row = _cache["vessels"][identity]
            stamp = row.get("last_seen", row.get("static_received_timestamp", 0))
            ttl = POSITION_TTL if row.get("lat") is not None else STATIC_TTL
            if now - stamp > ttl:
                del _cache["vessels"][identity]
        _cache["last_prune"] = now
    while len(_cache["vessels"]) > MAX_VESSELS:
        _cache["vessels"].pop(next(iter(_cache["vessels"])))
        _cache["evicted_records"] += 1


def _consume_message(raw, *, now=None):
    """Validate one frame; never expose provider text/errors or refresh old positions."""
    now = time.time() if now is None else now
    if not isinstance(raw, (str, bytes)) or len(raw.encode("utf-8") if isinstance(raw, str) else raw) > MAX_MESSAGE_BYTES:
        raise ValueError("Invalid or oversized AIS message")
    message = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite AIS JSON")))
    if not isinstance(message, dict):
        raise ValueError("AIS envelope must be an object")
    _cache["last_message"] = now
    if "error" in message or message.get("MessageType") == "Error":
        raise RuntimeError("AIS provider rejected the subscription")
    if message.get("MessageType") == "SubscriptionConfirmation":
        body = message.get("Message", {})
        _cache["compression_enabled"] = body.get("CompressionEnabled") is True if isinstance(body, dict) else False
        return
    kind = message.get("MessageType")
    if kind not in {"PositionReport", "ShipStaticData"}:
        return
    meta = message.get("MetaData") or message.get("Metadata") or message.get("metadata")
    body = message.get("Message")
    if not isinstance(meta, dict) or not isinstance(body, dict) or not isinstance(body.get(kind), dict):
        raise ValueError("Malformed AIS envelope")
    mmsi = str(meta.get("MMSI", ""))
    if not re.fullmatch(r"[2-7][0-9]{8}", mmsi):
        raise ValueError("Invalid ship MMSI")
    report = body[kind]
    if report.get("Valid") is False or (kind == "PositionReport" and report.get("Valid") is not True):
        raise ValueError("AIS provider marked this message invalid")
    if report.get("UserID") is not None and str(report["UserID"]) != mmsi:
        raise ValueError("AIS identity mismatch")
    _prune_vessels(now)
    vessel = dict(_cache["vessels"].get(mmsi, {}))
    vessel["mmsi"] = mmsi
    vessel["name"] = text(meta.get("ShipName") or vessel.get("name"), 120)
    if kind == "PositionReport":
        # Coordinates must be in the actual position report, not last-known metadata.
        lat, lon = coordinates(report.get("Latitude"), report.get("Longitude"))
        if lat is None or lon is None or not any(
            min(c[0][0], c[1][0]) <= lat <= max(c[0][0], c[1][0]) and
            min(c[0][1], c[1][1]) <= lon <= max(c[0][1], c[1][1]) for c in BOUNDING_BOXES
        ):
            raise ValueError("Invalid or out-of-coverage AIS position")
        observed = _message_observed_at(meta, now)
        if meta.get("time_utc") and observed is None:
            raise ValueError("Invalid AIS observation clock")
        if observed is not None and (now - observed > POSITION_TTL or
            (vessel.get("observed_timestamp") is not None and observed <= vessel["observed_timestamp"])):
            return
        course = number(report.get("Cog"), 0, 359.999)
        heading = number(report.get("TrueHeading"), 0, 359)
        vessel.update({"lat": lat, "lon": lon, "speed": number(report.get("Sog"), 0, 102.2),
            "heading": heading if heading is not None else course, "heading_basis": "true_heading" if heading is not None else "course_over_ground",
            "course": course, "nav_status": number(report.get("NavigationalStatus"), 0, 15),
            "last_seen": now, "received_at": iso(now), "observed_timestamp": observed, "observed_at": iso(observed),
            "observation_time_status": "provider_timestamp" if observed is not None else "unavailable",
            "position_accuracy": report.get("PositionAccuracy") if type(report.get("PositionAccuracy")) is bool else None,
            "source": "aisstream", "units": {"speed": "knots", "heading": "degrees", "course": "degrees"}})
        _cache["last_update"] = now
        _cache["error"] = None
    else:
        dimensions = report.get("Dimension") if isinstance(report.get("Dimension"), dict) else {}
        front, back = number(dimensions.get("A"), 0, 511), number(dimensions.get("B"), 0, 511)
        ship_type = number(report.get("Type"), 0, 99)
        vessel.update({"ship_type": int(ship_type) if ship_type is not None else None,
            "ship_type_name": _ship_type_name(int(ship_type)) if ship_type is not None else "Unknown",
            "destination": text(report.get("Destination"), 80), "callsign": text(report.get("CallSign"), 20),
            "length": front + back if front is not None and back is not None else None,
            "imo": number(report.get("ImoNumber"), 1, 9999999), "static_received_timestamp": now,
            "static_received_at": iso(now)})
    category, flag, flag_name = _classify_vessel(vessel)
    vessel.update(vessel_category=category, flag_code=flag, flag_name=flag_name,
                  classification_status="broadcast_metadata_heuristic_unverified", flag_basis="MMSI_allocation_not_ownership")
    _cache["vessels"].pop(mmsi, None)
    _cache["vessels"][mmsi] = vessel
    _prune_vessels(now)


async def start_maritime_poller():
    if settings.demo_mode or not settings.live_ingestion_enabled or not settings.aisstream_api_key:
        return
    failures = 0
    while True:
        _cache["last_attempt"] = time.time()
        try:
            await _run_websocket()
        except Exception as exc:
            _cache["error"] = type(exc).__name__
            logger.warning("AISStream connection failed (%s)", type(exc).__name__)
        finally:
            _cache["connected"] = False
        _prune_vessels(time.time(), force=True)
        failures = min(failures + 1, 6)
        await asyncio.sleep(min(300, 5 * 2 ** failures) + random.uniform(0, 3))


async def _run_websocket():
    import websockets
    subscription = json.dumps({"APIKey": settings.aisstream_api_key,
        "BoundingBoxes": BOUNDING_BOXES, "FilterMessageTypes": ["PositionReport", "ShipStaticData"]})
    async with websockets.connect("wss://stream.aisstream.io/v0/stream", open_timeout=20,
        ping_interval=20, ping_timeout=20, max_size=MAX_MESSAGE_BYTES, max_queue=16,
        compression="deflate", close_timeout=5) as websocket:
        await asyncio.wait_for(websocket.send(subscription), timeout=2)
        _cache["connected"] = True
        while True:
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=90)
                _consume_message(raw)
            except (ValueError, TypeError, RecursionError):
                _cache["rejected_messages"] += 1
                _cache["error"] = "invalid_message"


def get_vessels(*, now=None):
    now = time.time() if now is None else now
    _prune_vessels(now, force=True)
    result = []
    for vessel in _cache["vessels"].values():
        if vessel.get("lat") is None or now - vessel.get("last_seen", 0) > POSITION_TTL:
            continue
        observed = vessel.get("observed_timestamp")
        if observed is not None and now - observed > POSITION_TTL:
            continue
        row = copy.deepcopy(vessel)
        row.update({"age_seconds": round(max(0, now - observed), 1) if observed is not None else None,
            "received_age_seconds": round(max(0, now - vessel["last_seen"]), 1),
            "stale": now - observed > 120 if observed is not None else None})
        if settings.demo_mode:
            row.update(source="synthetic", data_mode="synthetic")
        result.append(row)
    return result


def get_maritime_status(*, now=None):
    now = time.time() if now is None else now
    vessels = get_vessels(now=now)
    last = _cache["last_update"]
    age = max(0, now - last) if last is not None else None
    state = "synthetic" if settings.demo_mode else "disabled" if not settings.live_ingestion_enabled or not settings.aisstream_api_key else (
        "unavailable" if last is None else "stale" if age > 120 else "failed" if _cache["error"] else "ok")
    return {"status": state, "source": "synthetic" if settings.demo_mode else "aisstream",
        "connected": _cache["connected"], "subscription_compression": _cache["compression_enabled"],
        "count": len(vessels), "cached_identities": len(_cache["vessels"]), "data_available": bool(vessels),
        "last_attempt_at": iso(_cache["last_attempt"]), "last_message_at": iso(_cache["last_message"]),
        "last_position_received_at": iso(last), "cache_age_seconds": round(age, 1) if age is not None else None,
        "positions_with_known_observation_time": sum(v.get("observed_at") is not None for v in vessels),
        "position_expires_after_seconds": POSITION_TTL, "coverage": copy.deepcopy(BOUNDING_BOXES),
        "error": _cache["error"], "rejected_messages": _cache["rejected_messages"], "evicted_records": _cache["evicted_records"],
        "limitations": ["Partial AIS receiver coverage; silence is not absence, and missing packets are not replayed.",
                        "AIS identity, flag allocation and vessel category are not independent ownership or military verification.",
                        "Receive time is not observation time; unknown provider timestamps stay unknown."]}

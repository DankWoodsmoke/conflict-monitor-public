"""Public evidence metadata. Counts describe coverage, never factual certainty.

This module has no database, model, network, configuration, or clock dependency.
Raw source text is preserved; extraction and interpretation do not become sources.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def value(record, key, default=None):
    return record.get(key, default) if isinstance(record, Mapping) else getattr(record, key, default)


def canonical_source(name: str) -> str:
    name = str(name or "").strip().lower().lstrip("@")
    aliases = {
        "nasa firms viirs-noaa20": "satellite_firms", "nasa firms": "satellite_firms",
        "x_ajebreaking": "aljazeera", "ajenews": "aljazeera",
        "x_haaretz": "haaretz", "haaretzcom": "haaretz",
    }
    name = aliases.get(name, name)
    return name.removeprefix("x_")


def parse_channels(channels: str) -> list[str]:
    """Comma-delimited names, including multi-word publishers, without substrings."""
    return sorted({canonical_source(c) for c in str(channels or "").split(",") if c.strip()})


def canonical_url(url: str) -> str:
    try:
        parts = urlsplit(str(url or "").strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            return ""
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))
    except ValueError:
        return ""


def make_report(record=None, **fields) -> dict:
    """Snapshot a source report from an Event, mapping, or keyword arguments.

    Identity is source-scoped for message IDs. Revisions of the same identity keep
    separate hashes so edits survive without inflating the report count.
    """
    def get(key, default=""):
        return fields.get(key, value(record, key, default))

    channel = str(get("channel_name") or get("source") or "")
    source = canonical_source(channel)
    raw = str(get("raw_text") or "")
    summary = str(get("summary") or "")
    url = canonical_url(get("source_url"))
    msg_id = get("telegram_message_id", None) or get("message_id", None)
    ts = get("timestamp", None) or get("published_at", None)
    published_at = ts.isoformat() if isinstance(ts, datetime) else (str(ts) if ts else None)
    content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if msg_id is not None:
        identity = [source, "message", str(msg_id)]
    elif url:
        identity = [source, "url", url]
    else:
        # Undated unaddressable text is retained, but cannot prove a new origin.
        identity = [source, "content", content_hash, published_at]
    report_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {
        "report_id": report_id, "source": str(get("source") or ""),
        "channel_name": channel, "source_identity": source,
        "message_id": str(msg_id) if msg_id is not None else None,
        "source_url": url, "raw_text": raw, "summary": summary,
        "published_at": published_at, "content_sha256": content_hash,
        "classification_status": str(get("classification_status") or "legacy_unknown"),
    }


def append_report(reports: list[dict], report: dict) -> list[dict]:
    """Preserve new evidence/revisions; a replay of identical bytes is idempotent."""
    key = (report.get("report_id"), report.get("content_sha256"))
    if any((r.get("report_id"), r.get("content_sha256")) == key for r in reports):
        return list(reports)
    return [*reports, report]


def report_count(reports: list[dict]) -> int:
    return len({r["report_id"] for r in reports if r.get("report_id")})


def valid_coordinates(lat, lon) -> bool:
    if isinstance(lat, bool) or isinstance(lon, bool):
        return False
    try:
        return (lat is not None and lon is not None and
                math.isfinite(float(lat)) and math.isfinite(float(lon)) and
                -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180 and
                (float(lat), float(lon)) != (-25.0, 80.0))
    except (TypeError, ValueError, OverflowError):
        return False


_POLARITY = re.compile(r"\b(no|not|never|deny|denies|denied|denial|false|hoax|unconfirmed|unverified|alleged|allegedly|reportedly|claims?|claimed)\b|n['’]t\b", re.I)


def polarity_markers(text: str) -> frozenset[str]:
    """Conservative English guard, not a multilingual semantic verifier."""
    groups = set()
    for match in _POLARITY.finditer(text or ""):
        token = match.group().lower()
        if token in {"no", "not", "never", "deny", "denies", "denied", "denial", "false", "hoax"} or token in {"n't", "n’t"}:
            groups.add("negation")
        else:
            groups.add("attribution_or_uncertainty")
    return frozenset(groups)


def compatible_claims(a: str, b: str) -> bool:
    """Reject known polarity/number mismatches; True does NOT establish agreement."""
    if polarity_markers(a) != polarity_markers(b):
        return False
    nums_a = set(re.findall(r"\b\d+(?:[.,]\d+)*\b", a or ""))
    nums_b = set(re.findall(r"\b\d+(?:[.,]\d+)*\b", b or ""))
    return not (nums_a and nums_b and nums_a != nums_b)


def assess_evidence(event) -> dict:
    from app.services.verification import compute_confirmed_networks
    reports = value(event, "reports", []) or []
    names = set(parse_channels(value(event, "reporting_channels", "")))
    primary = canonical_source(value(event, "channel_name", "") or value(event, "source", ""))
    if primary:
        names.add(primary)
    names.update(canonical_source(r.get("channel_name") or r.get("source", "")) for r in reports)
    names.discard("")
    satellite = value(event, "source", "") == "satellite_firms" or value(event, "event_type", "") == "thermal_anomaly"
    status = "sensor_observation" if satellite else "multiple_reports" if len(names) > 1 else "reported" if names else "unassessed"
    limitations = ["Source count and network diversity do not establish independent corroboration."]
    limitations.append("Report publication time may differ from the time the described event occurred.")
    if value(event, "source", "") in {"demo", "synthetic", "simulation"}:
        limitations.append("Synthetic demonstration data; not evidence of a real-world event.")
    if not reports:
        limitations.append("Legacy event: individual report provenance is incomplete.")
    if value(event, "classification_status", "legacy_unknown") != "extracted" and not satellite:
        limitations.append("Successful structured extraction has not been established for this event.")
    if not valid_coordinates(value(event, "lat"), value(event, "lon")):
        limitations.append("Location is unresolved; no precise event position is established.")
    elif value(event, "geolocation_precision", "unknown") == "unknown":
        limitations.append("A map coordinate is present, but event-location precision is unassessed.")
    if satellite:
        limitations.append("Thermal detection does not establish cause, a strike, actor, damage, or casualties.")
    return {
        "status": status, "unique_source_count": len(names),
        "source_networks": compute_confirmed_networks(", ".join(sorted(names))),
        "independent_origin_count": None, "independence_status": "unassessed",
        "verification_basis": "none", "limitations": limitations,
    }

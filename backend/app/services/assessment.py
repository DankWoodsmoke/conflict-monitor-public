"""Source-bound, unreviewed model impact metadata; never factual verification."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

CONTRACT_VERSION = "source-claim-extraction-v2"
RUBRIC_VERSION = "reported-impact-v2"
EVENT_TYPES = {"military", "diplomatic", "economic", "humanitarian", "cyber", "protest", "unclassified"}
SUBTYPES = {"airstrike", "missile", "drone", "naval", "artillery", "ground", "assassination",
            "explosion", "interception", "rocket", "mortar", "sabotage", ""}
STANCES = {"reported", "denied", "uncertain", "mixed", "unknown"}
SNAPSHOT_FIELDS = {"contract_version","rubric_version","source_sha256","model","prompt_sha256",
    "review_status","event_type","severity","military_subtype","actor","casualties","stance",
    "evidence_quote","start","end"}


def source_fidelity_error(snapshot, source_text):
    """Limited literal/English guards, not semantic or multilingual validation."""
    from app.services.evidence import polarity_markers
    quote=snapshot["evidence_quote"]
    if not polarity_markers(source_text).issubset(polarity_markers(quote)):
        return "source_qualifier_omitted"
    caution = re.compile(r"\b(denies|denied|deny|denial|unconfirmed|unverified|alleged|allegedly|hypothetical|might|could)\b|\bmay\b(?!\s+\d{1,4}\b)|\b(?:did|was|were|is|has|have)\s+not\b|[\"\u201c\u201d]",re.I)
    if caution.search(source_text) and snapshot["severity"] != 0:
        return "qualified_or_quoted_claim_requires_review"
    correction = re.compile(r"\b(correction|corrected|retracted|withdrawn|withdraws|debunked)\b",re.I)
    if correction.search(source_text) and (not correction.search(quote) or snapshot["severity"] != 0):
        return "correction_requires_unscored_review"
    if any(fragment and fragment not in source_text for fragment in (snapshot["actor"],snapshot["casualties"])):
        return "unsupported_actor_or_quantity"
    return None


def valid_extraction(snapshot, source_text, *, event_type=None, severity=None):
    if not isinstance(snapshot, dict) or not isinstance(source_text, str):
        return False
    if set(snapshot) != SNAPSHOT_FIELDS or any(not isinstance(snapshot[key],str)
            for key in SNAPSHOT_FIELDS-{"severity","start","end"}):
        return False
    if len(snapshot["actor"])>400 or len(snapshot["casualties"])>400:
        return False
    if snapshot.get("contract_version") != CONTRACT_VERSION or snapshot.get("rubric_version") != RUBRIC_VERSION:
        return False
    if (snapshot.get("source_sha256") != hashlib.sha256(source_text.encode()).hexdigest() or
        not isinstance(snapshot.get("model"), str) or not 1 <= len(snapshot["model"]) <= 160 or
        not re.fullmatch(r"[0-9a-f]{64}", str(snapshot.get("prompt_sha256", ""))) or
        snapshot.get("review_status") != "unreviewed" or snapshot.get("stance") not in STANCES):
        return False
    score = snapshot.get("severity")
    if type(score) is not int or not 0 <= score <= 10 or snapshot.get("event_type") not in EVENT_TYPES:
        return False
    if snapshot.get("stance") != "reported" and score != 0:
        return False
    if snapshot.get("event_type") == "unclassified" and score != 0:
        return False
    if snapshot.get("military_subtype", "") not in SUBTYPES:
        return False
    if snapshot.get("event_type") != "military" and snapshot.get("military_subtype"):
        return False
    quote, start, end = (snapshot.get(key) for key in ("evidence_quote", "start", "end"))
    if (not isinstance(quote, str) or not quote.strip() or len(quote) > 2000 or
        type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source_text) or
        source_text[start:end] != quote):
        return False
    if event_type is not None and snapshot["event_type"] != event_type:
        return False
    if severity is not None and snapshot["severity"] != severity:
        return False
    return source_fidelity_error(snapshot,source_text) is None


def valid_classification(result, source_text):
    return (isinstance(result,dict) and result.get("classification_status") == "extracted" and
        result.get("event_type") in EVENT_TYPES and type(result.get("severity")) is int and
        result.get("is_noise") is False and
        result.get("location_name") == "Unknown" and
        valid_extraction(result.get("extraction"),source_text,
            event_type=result["event_type"],severity=result["severity"]) and
        result.get("summary") == result["extraction"]["evidence_quote"])


def event_assessment(event):
    get = event.get if isinstance(event, Mapping) else lambda key, default=None:getattr(event,key,default)
    status = get("classification_status", "legacy_unknown")
    score, category = get("severity"), get("event_type")
    result = {"status":"legacy_unreviewed", "event_type":None, "severity":None,
        "severity_label":None, "basis":"legacy_metadata", "review_status":"unreviewed",
        "confirmed":False, "critical_alert_eligible":False, "model":None,
        "rubric_version":None, "source_sha256":None, "stance":"unknown",
        "limitations":["Impact, urgency and certainty are different; no verified event severity or alert is established."]}
    if get("source") == "satellite_firms" or category == "thermal_anomaly":
        result.update(status="sensor_not_applicable",basis="sensor_observation")
        result["limitations"].append("Thermal sensor measurements do not establish an attack, damage or impact severity.")
        return result
    if type(score) is not int or not 0 <= score <= 10:
        result.update(status="invalid",basis="invalid_metadata")
        return result
    if status == "not_requested" and score == 0 and category == "unclassified":
        result.update(status="unscored",basis="not_requested",severity_label="unscored")
        result["limitations"].append("Report collection intentionally did not request classification or impact scoring.")
        return result
    if status == "extracted":
        matches=[]
        for report in get("reports", []) or []:
            if not isinstance(report, dict):
                continue
            snapshot=report.get("extraction")
            if valid_extraction(snapshot, report.get("raw_text"),event_type=category,severity=score):
                # The classification belongs to this Event's original bytes,
                # not a later merged report or a corrected source revision.
                if snapshot["source_sha256"] == hashlib.sha256(str(get("raw_text", "")).encode()).hexdigest():
                    matches.append(snapshot)
        if matches and all(item == matches[0] for item in matches):
            selected=matches[0]
            result.update(status="model_estimate",basis="source_bound_model_extraction",event_type=category,
                severity=score if score else None, severity_label=("critical" if score>=9 else "high" if score>=6 else
                    "moderate" if score>=4 else "low" if score else "unscored"),model=selected["model"],
                rubric_version=selected["rubric_version"],source_sha256=selected["source_sha256"],stance=selected["stance"])
            result["limitations"].extend(["Source-bound model interpretation is unreviewed; literal citation does not validate its meaning.",
                "This rubric is an uncalibrated reported-impact scale, not a probability, current urgency or cross-rubric comparison."])
            return result
    if status in {"invalid", "unavailable", "filtered", "source_permission_required"}:
        result.update(status="invalid",basis="invalid_metadata")
    result["limitations"].append("Stored type/score lacks admissible source-bound model and rubric provenance; it is retained only as legacy metadata.")
    return result

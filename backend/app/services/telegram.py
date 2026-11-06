from __future__ import annotations
import asyncio
import logging
import hashlib
import re
from datetime import datetime, timezone, timedelta

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from telethon import TelegramClient as _TelethonClient, events, errors
from telethon.sessions import StringSession

from app.config import settings
from app.services.ingest_ledger import capture_report, finish_report, report_identity
from app.services.evidence import make_report
from app.db import async_session
from app.models import ChannelCheckpoint, Event, SourceReport
from app.schemas import EventRead, EventWS
from app.seed_channels import DEFAULT_CHANNELS, get_reliability
from app.services.anomaly import analyze_anomaly
from app.services.broadcaster import broadcaster
from app.services.classifier import classify_message
from app.services.assessment import valid_classification
from app.services.local_briefing import ensure_artifact_source_permission, SourcePermissionRequired
from app.services.dedup import check_duplicate, merge_duplicate
from app.services.geocoder import geocode

logger = logging.getLogger(__name__)

# ── CONSTANTS ────────────────────────────────────────────────────────────────

UNKNOWN_LAT = -25.0
UNKNOWN_LON = 80.0   # Indian Ocean parking for unresolvable locations

MIN_SEVERITY = 3

# ── Noise phrases: messages matching any of these are dropped immediately ──────
# These are commentary, reactions, social-media meta-posts, and other non-events.
# They MUST NOT include legitimate event keywords (strikes, missiles, etc.)
NOISE_PHRASES = [
    # Social meta / channel admin
    "so how's everyone",
    "well hello there",
    "better test this",
    "not forgotten about",
    "just sitting back",
    "balancing real life",
    "bsky.social",
    "bluesky social media",
    "there is some beautiful irony",
    "follow us on",
    "subscribe to our",
    "join our channel",
    "turn on notifications",
    "share this post",
    "repost if you",
    "like and subscribe",
    "don't forget to",
    "link in bio",
    "check out our",
    "support us on",
    "patreon",
    # Pure reactions / commentary (no event content)
    "wait i thought",
    "i thought the war",
    "you had won",
    "the war was over",
    "is he fucking",
    "is he serious?",
    "is she serious?",
    "are they serious?",
    "what a surprise",
    "can you believe",
    "hot take:",
    "unpopular opinion:",
    "genuine question:",
    "genuine question,",
    "anyone else notice",
    "anyone else feel",
    "thoughts on this",
    "what do you think",
    "comment below",
    "your thoughts?",
    "let me know",
    "does anyone know",
    "asking for a friend",
    "just asking",
    "no way this is real",
    "this is insane",
    "this is crazy",
    "oh wow",
    "lol ",
    " lmao",
    " lmfao",
    " smh",
    "ðŸ˜‚ðŸ˜‚",
    "ðŸ¤£ðŸ¤£",
    # Raw URLs with no context (link dumps)
    "https://t.me/joinchat",
    "https://t.me/+",
    "t.me/joinchat",
    # Test / placeholder messages
    "this is a test",
    "testing 1 2 3",
    "hello world",
]

# Minimum word count for a message to be processed (filters very short reactions)
MIN_WORD_COUNT = 8

# Phrases that indicate a message is a reaction/commentary question with no event data
COMMENTARY_STARTERS = (
    "wait",
    "is he",
    "is she",
    "is this",
    "are they",
    "can you",
    "do you",
    "does anyone",
    "lol",
    "omg",
    "wow,",
    "wtf",
    "smh",
)


def _get_channels() -> list[str]:
    chosen = list(dict.fromkeys(c.strip().lstrip("@").lower() for c in settings.telegram_channels.split(",") if c.strip()))
    if settings.telegram_processing_mode == "reports":
        if len(chosen) > 5 or any(not re.fullmatch(r"[a-zA-Z0-9_]{5,32}", c) for c in chosen):
            raise ValueError("Select at most five public channel usernames")
        return chosen
    return chosen or DEFAULT_CHANNELS


def _get_conflict_cutoff() -> datetime:
    """Parse CONFLICT_START_DATE from settings and return as UTC datetime."""
    try:
        d = datetime.strptime(settings.conflict_start_date, "%Y-%m-%d")
        return d.replace(tzinfo=timezone.utc)
    except Exception:
        # Fallback: 30 days ago
        return datetime.now(timezone.utc) - timedelta(days=30)


def _is_noise(text: str, severity: int) -> bool:
    """Return True if this message should be dropped as noise/commentary."""
    # Short multilingual incident reports are valid. Semantic noise is assessed
    # by the bounded classifier; token count and a substring are not evidence.
    return not text.strip() or severity < MIN_SEVERITY


def _build_source_url(channel_name: str, message_id: int) -> str:
    if not channel_name or not message_id:
        return ""
    return f"https://t.me/{channel_name.lstrip('@')}/{message_id}"


# ── Checkpoint helpers ────────────────────────────────────────────────────────

async def _get_checkpoint(channel_name: str) -> int:
    """Return the last saved message_id for this channel (0 if none)."""
    async with async_session() as session:
        result = await session.execute(
            select(ChannelCheckpoint).where(ChannelCheckpoint.channel_name == channel_name)
        )
        cp = result.scalar_one_or_none()
        return cp.last_message_id if cp else 0


async def _save_checkpoint(channel_name: str, message_id: int):
    """Atomically advance a channel cursor; concurrent delivery cannot regress it."""
    async with async_session() as session:
        await session.execute(pg_insert(ChannelCheckpoint).values(channel_name=channel_name,
            last_message_id=message_id,last_processed_at=_stamp()).on_conflict_do_update(
                index_elements=[ChannelCheckpoint.channel_name],set_={
                    "last_message_id":func.greatest(ChannelCheckpoint.last_message_id,message_id),
                    "last_processed_at":func.now()}))
        await session.commit()


async def _message_already_saved(session, message_id: int, channel_name: str) -> bool:
    result = await session.execute(
        select(Event.id).where(Event.telegram_message_id == message_id, Event.channel_name == channel_name, Event.source == "telegram").limit(1)
    )
    return result.scalar_one_or_none() is not None


# ── Core message processor ────────────────────────────────────────────────────

async def _process_model_message(
    raw_text: str,
    channel_name: str,
    message_date: datetime,
    message_id: int,
):
    if not raw_text or not raw_text.strip():
        return

    # Drop messages before the conflict start date
    conflict_cutoff = _get_conflict_cutoff()
    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=timezone.utc)
    if message_date < conflict_cutoff:
        logger.debug(
            "Skipping pre-conflict message from %s (date=%s)", channel_name,
            message_date.strftime("%Y-%m-%d")
        )
        return

    report = {"source": "telegram", "channel_name": channel_name,
              "telegram_message_id": message_id, "source_url": _build_source_url(channel_name, message_id),
              "raw_text": raw_text, "timestamp": message_date.isoformat(),
              "time_basis": "source_publication_time"}
    receipt = await capture_report(report)
    if receipt is None:
        return
    try:
        ensure_artifact_source_permission({"source_platform":"telegram","source_url":report["source_url"]})
    except SourcePermissionRequired:
        await finish_report(receipt,"source_permission_required")
        return "source_permission_required"
    async with async_session() as session:
        if await _message_already_saved(session, message_id, channel_name):
            await finish_report(receipt, "source_revision_needs_review")
            return

    # Pre-filter using local noise rules (fast, no API call)
    # Run a quick severity-5 check first so we don't waste tokens on obvious noise
    if _is_noise(raw_text, 5):
        await finish_report(receipt, "noise")
        logger.debug("Pre-filter noise: %s", raw_text[:60])
        return

    # Classify
    result = await classify_message(raw_text)
    if result.get("classification_status", "invalid") != "extracted":
        await finish_report(receipt, result.get("classification_status", "invalid"))
        return
    if not valid_classification(result,raw_text):
        await finish_report(receipt,"invalid")
        return "invalid"
    report["summary"] = result.get("summary", "")
    report["classification_status"] = "extracted"
    report["extraction"] = result["extraction"]
    severity = result["severity"]

    # Classifier returned [NOISE] tag or severity=1 — drop immediately
    if result.get("is_noise"):
        await finish_report(receipt, "noise")
        logger.debug("Skipping noise (sev=%d): %s", severity, raw_text[:60])
        return

    # Geocode
    location_name = "Unknown"
    coords = None  # Model classification cannot authorize an incident position.

    if coords:
        lat, lon = coords
        is_geolocated = True
    else:
        lat, lon = None, None
        is_geolocated = False
        logger.info("No supported coordinates for '%s'; position unresolved (msg_id=%d)", location_name, message_id)

    geometry = from_shape(Point(lon, lat), srid=4326) if coords else None
    source_url = _build_source_url(channel_name, message_id)

    async with async_session() as session:
        existing = await check_duplicate(
            session,
            result.get("summary", ""),
            result["event_type"],
            lat, lon,
            message_date, source_name=channel_name, report=report,
        )
        if existing:
            await merge_duplicate(session, existing, channel_name, severity, lat, lon, report=report)
            await finish_report(receipt, "extracted", existing.id)
            await _save_checkpoint(channel_name, message_id)
            ws_payload = EventWS(type="new_event", event=EventRead.model_validate(existing))
            await broadcaster.broadcast(ws_payload.model_dump_json())
            return

        # Run anomaly detection for severity 5+ events
        anomaly_score = 0
        anomaly_analysis = ""
        if severity >= 5:
            try:
                anomaly = await analyze_anomaly(
                    summary=result.get("summary", ""),
                    event_type=result["event_type"],
                    severity=severity,
                    location_name=location_name,
                    raw_text=raw_text,
                )
                anomaly_score = anomaly.get("anomaly_score", 0)
                anomaly_analysis = anomaly.get("analysis", "")
            except Exception as e:
                logger.warning("Anomaly analysis failed for msg_id=%d: %s", message_id, e)

        db_event = Event(
            source="telegram",
            channel_name=channel_name,
            raw_text=raw_text,
            summary=result.get("summary", raw_text[:200]),
            event_type=result["event_type"],
            severity=severity,
            lat=lat,
            lon=lon,
            geometry=geometry,
            timestamp=message_date,
            source_reliability=get_reliability(channel_name),
            location_name=location_name,
            telegram_message_id=message_id,
            source_url=source_url,
            reporting_channels=channel_name,
            classification_status="extracted",
            geolocation_precision="unknown",
            reports=[make_report(report)],
            anomaly_score=anomaly_score,
            anomaly_analysis=anomaly_analysis,
        )
        session.add(db_event)
        await session.commit()
        await session.refresh(db_event)
        await finish_report(receipt, "extracted", db_event.id)

        ws_payload = EventWS(type="new_event", event=EventRead.model_validate(db_event))
        await broadcaster.broadcast(ws_payload.model_dump_json())
        logger.info(
            "Event #%d saved | sev=%d | loc='%s' -> (%s,%s) | geo=%s | anomaly=%d | %s",
            db_event.id, severity, location_name, lat, lon, is_geolocated, anomaly_score, source_url,
        )

    # Update checkpoint so next restart won't re-process this message
    await _save_checkpoint(channel_name, message_id)


# ── Free report preservation and observable state ─────────────────────────────
_state = {"status": "disabled", "error_type": None, "channels": {},
          "last_attempt_at": None, "last_success_at": None, "last_published_at": None}
_report_locks: dict[str, asyncio.Lock] = {}
_catchup_locks: dict[str, asyncio.Lock] = {}
_MAX_PENDING_REVISIONS = 20
REPORT_TERMINAL_OUTCOMES = frozenset({"reported", "duplicate", "source_revision_needs_review",
    "input_too_large", "invalid_source_metadata", "undated_source", "future_source_time",
    "before_configured_start", "no_text_or_caption"})
_LEGACY_TERMINAL_RECEIPTS = frozenset({"extracted", "noise", "source_permission_required"})


def _stamp():
    return datetime.now(timezone.utc)


def get_telegram_status():
    if settings.telegram_transport == "bot":
        from app.services.telegram_bot import get_bot_status
        return get_bot_status()
    if settings.telegram_transport != "session":
        return {"enabled": False, "status": "disabled", "transport": "disabled",
                "selected_channels": [], "channels": {}, "checkpoint_policy": "none",
                "coverage_limitation": "Telegram collection is disabled. Previously retained reports remain available."}
    checkpoint_policy = "ordered_provider_page" if settings.telegram_processing_mode == "reports" else "legacy_model"
    try:
        channels = _get_channels()
    except ValueError:
        return {"enabled":False,"status":"failed","transport":"session","error_type":"InvalidChannelSelection","selected_channels":[],
            "checkpoint_policy":checkpoint_policy}
    configured = bool(settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_session and channels)
    status = _state["status"] if settings.live_ingestion_enabled and configured else "disabled"
    now = _stamp()
    success, publication = _state.get("last_success_at"), _state.get("last_published_at")
    return {"enabled": bool(settings.live_ingestion_enabled and configured), "status": status,
        "mode": settings.telegram_processing_mode, "transport": "session", "selected_channels": channels,
        "checkpoint_policy": checkpoint_policy,
        "startup_limit_per_channel": settings.telegram_startup_max_messages,
        "error_type": _state.get("error_type"), "channels": dict(_state["channels"]),
        "reconnect_attempts": _state.get("reconnect_attempts", 0),
        "retry_delay_seconds": _state.get("retry_delay_seconds"),
        "next_retry_at": _state["next_retry_at"].isoformat() if _state.get("next_retry_at") else None,
        "cleanup_confirmed": _state.get("cleanup_confirmed"),
        "last_attempt_at": _state["last_attempt_at"].isoformat() if _state.get("last_attempt_at") else None,
        "last_success_at": success.isoformat() if success else None,
        "last_published_at": publication.isoformat() if publication else None,
        "cache_age_seconds": (now-success).total_seconds() if success else None,
        "publication_age_seconds": (now-publication).total_seconds() if publication else None,
        "publication_stale": bool(publication and (now-publication).total_seconds() > 86400),
        "coverage_limitation": "Selected public channels; bounded startup and incremental polling. Publication time is not event time."}


def _report_payload(raw_text, channel_name, message_date, message_id):
    report = {"source": "telegram", "channel_name": channel_name, "telegram_message_id": message_id,
        "source_url": _build_source_url(channel_name, message_id), "raw_text": str(raw_text or ""),
        "timestamp": message_date.isoformat() if isinstance(message_date, datetime) else None,
        "time_basis": "source_publication_time" if message_date else "unknown",
        "classification_status": "not_requested", "processing_mode": "publisher_metadata"}
    if len(report["raw_text"]) > 12000:
        report["original_text_sha256"] = hashlib.sha256(report["raw_text"].encode("utf-8")).hexdigest()
        report["raw_text"] = report["raw_text"][:12000]
        report["raw_text_truncated"] = True
    return report


async def _complete_report_receipt(receipt, report):
    channel_name = report["channel_name"]
    message_id = report["telegram_message_id"]
    raw_text = report["raw_text"]
    try:
        message_date = datetime.fromisoformat(report["timestamp"]) if report.get("timestamp") else None
    except (TypeError, ValueError):
        message_date = None

    async def retained(status, event_id=None):
        await finish_report(receipt, status, event_id)
        return status

    if not raw_text.strip():
        return await retained("invalid_source_metadata")
    if report.get("raw_text_truncated"):
        return await retained("input_too_large")
    if not isinstance(message_date, datetime) or message_date.tzinfo is None:
        return await retained("undated_source")
    if message_date > _stamp()+timedelta(minutes=5):
        return await retained("future_source_time")
    if message_date < _get_conflict_cutoff():
        return await retained("before_configured_start")
    summary = re.sub(r"\s+", " ", raw_text).strip()[:500]
    async with async_session() as session:
        existing = await session.execute(select(Event).where(Event.source == "telegram",
            Event.channel_name == channel_name, Event.telegram_message_id == message_id).limit(1))
        event = existing.scalar_one_or_none()
        if event is not None:
            if (event.raw_text != raw_text or event.timestamp != message_date or event.source_url != report["source_url"]
                    or event.classification_status != "not_requested"):
                return await retained("source_revision_needs_review", event.id)
        else:
            source_evidence = make_report({**report, "summary": summary})
            if report.get("collection_method") == "telegram_bot_api":
                source_evidence["collection_method"] = "telegram_bot_api"
            event = Event(source="telegram", channel_name=channel_name, raw_text=raw_text, summary=summary,
                event_type="unclassified", severity=0, lat=None, lon=None, geometry=None,
                timestamp=message_date, telegram_message_id=message_id, source_url=report["source_url"],
                source_reliability=get_reliability(channel_name), location_name="", report_count=1,
                reporting_channels=channel_name, confirmed_networks="", classification_status="not_requested",
                geolocation_precision="unknown", reports=[source_evidence],
                anomaly_score=0, anomaly_analysis="")
            session.add(event)
            await session.commit()
            await session.refresh(event)
    await finish_report(receipt, "reported", event.id)
    await broadcaster.broadcast(EventWS(type="new_event",event=EventRead.model_validate(event)).model_dump_json())
    return "reported"


async def _process_report_message(raw_text, channel_name, message_date, message_id, *, collection_method=None):
    """Process a provider-visible version and resume older unfinished versions first."""
    channel_name = str(channel_name or "").lstrip("@").lower()
    if not channel_name or type(message_id) is not int or message_id <= 0:
        return "invalid_source_metadata"
    report = _report_payload(raw_text, channel_name, message_date, message_id)
    if collection_method is not None:
        report["collection_method"] = collection_method
    identity = report_identity(report)[0]
    key = _report_lock_key(channel_name, message_id)
    # One worker per channel avoids exhausting the pool with lock-holding
    # transactions when Telegram dispatches a burst of updates concurrently.
    async with _report_locks.setdefault(channel_name, asyncio.Lock()):
        async with async_session() as session, session.begin():
            acquired = (await session.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key})).scalar_one()
            if not acquired:
                return "pending_receipt"
            pending = (await session.execute(select(SourceReport).where(
                SourceReport.status == "received", SourceReport.report["source"].astext == "telegram",
                SourceReport.report["channel_name"].astext == channel_name,
                SourceReport.report["telegram_message_id"].astext == str(message_id),
            ).order_by(SourceReport.received_at, SourceReport.identity).limit(_MAX_PENDING_REVISIONS + 1))).scalars().all()
            if len(pending) > _MAX_PENDING_REVISIONS:
                return "pending_receipt"
            resumed = None
            for row in pending:
                if report_identity(row.report) != (row.identity, row.content_hash):
                    raise ValueError("Stored Telegram receipt source identity is invalid")
                outcome = await _complete_report_receipt(row.identity, row.report)
                if row.identity == identity:
                    resumed = outcome
            if resumed is not None:
                return resumed
            if not report["raw_text"].strip():
                return "no_text_or_caption"
            receipt = await capture_report(report)
            if receipt is None:
                prior = await session.get(SourceReport, identity)
                if prior is not None and prior.status in REPORT_TERMINAL_OUTCOMES | _LEGACY_TERMINAL_RECEIPTS:
                    return "duplicate"
                return "pending_receipt"
            return await _complete_report_receipt(receipt, report)


def _report_lock_key(channel_name, message_id):
    return int.from_bytes(hashlib.sha256(f"telegram:{channel_name}:{message_id}".encode()).digest()[:8],
        byteorder="big", signed=True)


async def _process_message(raw_text, channel_name, message_date, message_id):
    if settings.telegram_processing_mode == "model":
        return await _process_model_message(raw_text,channel_name,message_date,message_id)
    return await _process_report_message(raw_text,channel_name,message_date,message_id)


async def _backfill_reports(client, entity, conflict_cutoff):
    channel = (getattr(entity,"username","") or "").lower()
    if not channel:
        raise ValueError("Only public username-addressed channels are supported")
    async with _catchup_locks.setdefault(channel, asyncio.Lock()):
        return await _backfill_report_page(client, entity, channel)


async def _backfill_report_page(client, entity, channel):
    budget = settings.telegram_startup_max_messages
    state = {"status":"checking", "processed":0, "history_complete":False,
        "startup_or_cycle_limit":budget, "checkpoint_message_id":None,
        "provider_page_last_message_id":None, "blocked_message_id":None}
    _state["channels"][channel] = state
    last_id = await _get_checkpoint(channel)
    state["checkpoint_message_id"] = last_id
    options = {"limit": budget}
    if last_id:
        options.update(min_id=last_id,reverse=True)
    messages = []
    async for message in client.iter_messages(entity,**options):
        messages.append(message)
        if len(messages) >= budget:
            break
    if not last_id:
        messages.reverse()
    ids = [message.id for message in messages]
    if any(type(message_id) is not int or message_id <= prior
           for prior, message_id in zip([last_id, *ids], ids)):
        raise ValueError("Telegram provider page is outside forward ID order")
    state["provider_page_last_message_id"] = ids[-1] if ids else None
    for message in messages:
        state["blocked_message_id"] = message.id
        if isinstance(message.date,datetime) and message.date.tzinfo is not None and message.date <= _stamp()+timedelta(minutes=5):
            if _state.get("last_published_at") is None or message.date > _state["last_published_at"]:
                _state["last_published_at"] = message.date
        outcome = await _process_report_message(message.text or "",channel,message.date,message.id)
        if outcome not in REPORT_TERMINAL_OUTCOMES:
            state["status"] = "pending_receipt"
            return state["processed"]
        # Only a provider-ordered page can certify that its prefix was examined.
        await _save_checkpoint(channel,message.id)
        state.update(checkpoint_message_id=message.id, blocked_message_id=None)
        if outcome != "no_text_or_caption":
            state["processed"] += 1
    state.update(status="ok", last_check_at=_stamp().isoformat())
    _state["last_success_at"] = _stamp()
    return state["processed"]


# ── Backfill helper — date-paginated, no fixed message count limit ─────────────

async def _backfill_entity(client: TelegramClient, entity, conflict_cutoff: datetime):
    """Fetch ALL messages for one channel since conflict_cutoff, oldest-first.

    Strategy:
    - If checkpoint exists: incremental — only messages with id > checkpoint
    - If no checkpoint: full historical sweep from conflict_cutoff to now
    Both approaches stop at the conflict_cutoff date, not at a message count.
    """
    if settings.telegram_processing_mode == "reports":
        return await _backfill_reports(client,entity,conflict_cutoff)
    # The legacy model path must not initiate an unbounded historical scan or
    # send Telegram content through a classifier/cache without source permission.
    ensure_artifact_source_permission({"source_platform":"telegram"})
    channel_name = getattr(entity, "username", "") or getattr(entity, "title", "")
    last_id = await _get_checkpoint(channel_name)

    if last_id > 0:
        logger.info("Backfill %s: incremental from message_id > %d", channel_name, last_id)
        # Incremental: only new messages since last checkpoint
        iter_kwargs = dict(min_id=last_id, reverse=True)
    else:
        logger.info(
            "Backfill %s: full sweep from conflict start %s",
            channel_name, conflict_cutoff.strftime("%Y-%m-%d"),
        )
        # Full sweep: oldest-first from conflict_cutoff
        # reverse=True + offset_date = start from that date going forward
        iter_kwargs = dict(reverse=True, offset_date=conflict_cutoff)

    count = 0
    try:
        async for message in client.iter_messages(entity, **iter_kwargs):
            if not message.date:
                continue
            msg_date = message.date
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            if msg_date < conflict_cutoff:
                continue  # shouldn't happen with offset_date, but safety
            if not message.text:
                continue
            await _process_message(
                raw_text=message.text,
                channel_name=channel_name,
                message_date=msg_date,
                message_id=message.id,
            )
            count += 1
            if count % 100 == 0:
                logger.info("Backfill %s: %d messages processed so far...", channel_name, count)
        logger.info("Backfill done for %s: %d total messages processed", channel_name, count)
    except Exception as e:
        logger.exception("Backfill error for %s: %s", channel_name, e)


# Shared client reference for on-demand backfill
_shared_client: TelegramClient | None = None


async def trigger_backfill() -> dict:
    task = asyncio.current_task()
    client = _shared_client
    if client is None:
        return {"status": "error", "message": "Telegram client unavailable"}
    _manual_backfills[task] = client
    try:
        return await _trigger_backfill_for_client(client)
    finally:
        _manual_backfills.pop(task, None)


async def _trigger_backfill_for_client(client) -> dict:
    """Run the configured forward catch-up; this does not recover older gaps."""
    if _shared_client is not client:
        return {"status": "error", "message": "Telegram client not yet initialised — wait for startup"}

    conflict_cutoff = _get_conflict_cutoff()
    channels = _get_channels()
    results = {}

    for ch in channels:
        try:
            if _shared_client is not client:
                raise ConnectionError("Client changed")
            entity = await client.get_entity(ch)
            if _shared_client is not client:
                raise ConnectionError("Client changed")
            _validate_public_entity(entity, ch)
            await _backfill_entity(client, entity, conflict_cutoff)
            results[ch] = _state["channels"].get(ch, {}).get("status", "ok")
        except Exception as e:
            results[ch] = "failed"
            _state["channels"].setdefault(ch, {}).update(status="failed", error_type=type(e).__name__)
            logger.warning("On-demand backfill failed for %s: %s", ch, type(e).__name__)

    return {"status": "complete" if all(status == "ok" for status in results.values()) else "partial",
            "channels": results, "scope": "forward_catchup",
            "history_complete": False, "historical_jobs": "/history/backfill/jobs"}


# ── Main listener ─────────────────────────────────────────────────────────────

_listener_owner = None
_listener_cleanup_unconfirmed = False
_manual_backfills = {}
_CLEANUP_TIMEOUT = 10
_RETRY_BASE = 5
_RETRY_CAP = 300
_STABLE_SECONDS = 300


class TelegramClient(_TelethonClient):
    """Coalesce all disconnect callers, including Telethon's internal finally.

    The pinned Telethon version shields its own disconnect task. Retain one completion future
    per client so a timeout cannot be mistaken for finished cleanup.
    """
    _owned_disconnect = None

    def disconnect(self):
        if self._owned_disconnect is None:
            original_disconnect = super().disconnect
            async def close():
                await original_disconnect()
            self._owned_disconnect = asyncio.create_task(close(), name="telegram_disconnect")
            self._owned_disconnect.add_done_callback(_consume_task_result)
        return asyncio.shield(self._owned_disconnect)


def _retry_delay(failures):
    return min(_RETRY_CAP, _RETRY_BASE * 2 ** min(max(failures - 1, 0), 6))


async def _retry_sleep(delay):
    await asyncio.sleep(delay)


def _transport_failure(exc):
    # Deliberately exclude RPC/auth/flood, sqlite, validation and arbitrary bugs.
    return isinstance(exc, (ConnectionError, TimeoutError))


def _terminal_provider_failure(exc):
    return isinstance(exc, (errors.UnauthorizedError, errors.AuthKeyError,
        errors.AuthKeyNotFound, errors.FloodError, SourcePermissionRequired))


def _validate_public_entity(entity, name):
    if (getattr(entity, "broadcast", False) is not True or
            not isinstance(getattr(entity, "username", None), str) or
            entity.username.lower() != name.lower()):
        raise ValueError("Selected entity must match the selected public broadcast channel")


class _CleanupUnconfirmed(RuntimeError):
    pass


def _consume_task_result(task):
    # A quarantined timed-out teardown may finish later; retrieve its exception
    # without treating that delayed completion as permission to reconnect.
    if not task.cancelled():
        task.exception()


async def _cleanup_attempt(client, tasks):
    """No successor client until owned workers and disconnect have completed."""
    for task in tasks:
        if task is not None:
            task.add_done_callback(_consume_task_result)
        if task is not None and not task.done():
            task.cancel()
    pending = [task for task in tasks if task is not None]
    if pending:
        done, still_running = await asyncio.wait(pending, timeout=_CLEANUP_TIMEOUT)
        for task in done:
            if not task.cancelled():
                task.exception()
    else:
        still_running = set()
    if client is not None:
        try:
            await asyncio.wait_for(client.disconnect(), timeout=_CLEANUP_TIMEOUT)
            if client.is_connected():
                raise _CleanupUnconfirmed("StillConnected")
        except _CleanupUnconfirmed:
            raise
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise _CleanupUnconfirmed("Disconnect" + type(exc).__name__) from None
    if still_running:
        # Still close the coalesced client transport even when an owned worker
        # ignores cancellation. Quarantine remains mandatory until process exit.
        raise _CleanupUnconfirmed("WorkerCleanupTimeout")


async def _join_cleanup(task):
    """Repeated shutdown cancellation must not abandon owned cleanup."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    # Retrieve cleanup failure before propagating cancellation to the owner.
    task.result()
    return cancelled


async def _listen_once(channels):
    global _shared_client, _listener_cleanup_unconfirmed
    client = None
    periodic_task = None
    disconnected_task = None
    retry = False
    cancelled = False
    _state["connected_since_monotonic"] = None
    try:
        client = TelegramClient(StringSession(settings.telegram_session), settings.telegram_api_id, settings.telegram_api_hash,
            auto_reconnect=True, connection_retries=2, request_retries=1, timeout=15,
            raise_last_call_error=True, flood_sleep_threshold=0)
        await asyncio.wait_for(client.connect(), timeout=20)
        if not await asyncio.wait_for(client.is_user_authorized(), timeout=15):
            _state.update(status="failed", error_type="UnauthorizedSession")
            return False
        resolved = []
        for name in channels:
            try:
                entity = await asyncio.wait_for(client.get_entity(name), timeout=15)
                _validate_public_entity(entity, name)
                resolved.append(entity)
                _state["channels"].setdefault(name, {}).update(status="resolved", error_type=None)
            except Exception as exc:
                _state["channels"].setdefault(name, {}).update(status="failed", error_type=type(exc).__name__)
                if _transport_failure(exc) or _terminal_provider_failure(exc):
                    raise
        if not resolved:
            _state.update(status="failed", error_type="NoPublicChannelsResolved")
            return False
        _shared_client = client
        @client.on(events.NewMessage(chats=resolved))
        @client.on(events.MessageEdited(chats=resolved))
        async def handler(event):
            if _shared_client is not client:
                return
            name = ""
            try:
                name = (getattr(event.chat, "username", "") or "").lower()
                await _process_message(event.message.text or "", name, event.message.date, event.message.id)
            except Exception as exc:
                if name and _shared_client is client:
                    _state["channels"].setdefault(name, {})["last_push_error_type"] = type(exc).__name__
        cutoff = _get_conflict_cutoff()
        async def catch_up():
            for entity in resolved:
                try:
                    await _backfill_entity(client, entity, cutoff)
                except Exception as exc:
                    name = (getattr(entity, "username", "") or "").lower()
                    _state["channels"].setdefault(name, {}).update(status="failed", error_type=type(exc).__name__)
                    if _transport_failure(exc) or _terminal_provider_failure(exc):
                        raise
        await catch_up()
        _state.update(status="ok", error_type=None, connected_at=_stamp(),
            connected_since_monotonic=asyncio.get_running_loop().time())
        async def poll():
            try:
                while True:
                    await asyncio.sleep(300)
                    await catch_up()
            except Exception as exc:
                # Provider failure belongs to the Telegram supervisor/status,
                # not core DB/HTTP readiness via Runtime.failures.
                return exc
        from app.services.runtime import runtime
        periodic_task = runtime.start("telegram_periodic", poll())
        disconnected_task = asyncio.create_task(client.run_until_disconnected(), name="telegram_disconnected")
        done, _ = await asyncio.wait((periodic_task, disconnected_task), return_when=asyncio.FIRST_COMPLETED)
        if periodic_task in done:
            error = periodic_task.result()
            if isinstance(error, Exception):
                raise error
            raise RuntimeError("UnexpectedPeriodicExit")
        disconnected_task.result()
        _state.update(status="retrying", error_type="Disconnected")
        retry = True
    except asyncio.CancelledError:
        cancelled = True
    except Exception as exc:
        retry = _transport_failure(exc)
        _state.update(status="retrying" if retry else "failed", error_type=type(exc).__name__)
    finally:
        if _shared_client is client:
            _shared_client = None
        manuals = tuple(task for task, owner in _manual_backfills.items() if owner is client)
        cleanup = asyncio.create_task(_cleanup_attempt(client, (periodic_task, disconnected_task, *manuals)), name="telegram_cleanup")
        try:
            cancelled = await _join_cleanup(cleanup) or cancelled
        except asyncio.CancelledError:
            _listener_cleanup_unconfirmed = True
            _state.update(status="failed", error_type="CleanupCancelled", cleanup_confirmed=False)
            cancelled = True
            retry = False
        except Exception as exc:
            _listener_cleanup_unconfirmed = True
            reason = str(exc) if isinstance(exc, _CleanupUnconfirmed) else "Cleanup" + type(exc).__name__
            _state.update(status="failed", error_type=reason, cleanup_confirmed=False)
            retry = False
        else:
            _state["cleanup_confirmed"] = True
        # Cancellation while cleanup was running must survive a simultaneous
        # teardown failure; _join_cleanup may raise before returning its flag.
        cancelled = cancelled or asyncio.current_task().cancelling() > 0
        if cancelled:
            if not _listener_cleanup_unconfirmed:
                _state.update(status="disabled", error_type="Stopped")
            raise asyncio.CancelledError
    return retry


async def start_telegram_listener():
    """One supervised public-channel reader; no login, joins or sending."""
    global _listener_owner
    if settings.telegram_transport != "session" or not settings.live_ingestion_enabled or settings.demo_mode:
        return
    if _listener_owner is not None and not _listener_owner.done():
        return
    if _listener_cleanup_unconfirmed:
        _state.update(status="failed", error_type="CleanupUnconfirmed", cleanup_confirmed=False)
        return
    _listener_owner = asyncio.current_task()
    failures = 0
    _state.update(reconnect_attempts=0, next_retry_at=None, retry_delay_seconds=None)
    _state.setdefault("channels", {})
    try:
        while True:
            _state.update(status="connecting", error_type=None, last_attempt_at=_stamp())
            if settings.telegram_processing_mode == "model":
                try:
                    ensure_artifact_source_permission({"source_platform": "telegram"})
                except SourcePermissionRequired:
                    _state.update(status="blocked", error_type="SourcePermissionRequired")
                    return
            try:
                channels = _get_channels()
            except ValueError:
                _state.update(status="failed", error_type="InvalidChannelSelection")
                return
            if not channels or not (settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_session):
                _state.update(status="disabled", error_type="MissingCredentialsOrChannelSelection")
                return
            if not await _listen_once(channels):
                return
            connected_since = _state.get("connected_since_monotonic")
            elapsed = 0 if connected_since is None else asyncio.get_running_loop().time() - connected_since
            failures = 1 if elapsed >= _STABLE_SECONDS else failures + 1
            delay = _retry_delay(failures)
            _state.update(status="retrying", reconnect_attempts=_state["reconnect_attempts"] + 1,
                retry_delay_seconds=delay, next_retry_at=_stamp() + timedelta(seconds=delay))
            await _retry_sleep(delay)
            _state.update(next_retry_at=None, retry_delay_seconds=None)
    except asyncio.CancelledError:
        if not _listener_cleanup_unconfirmed:
            _state.update(status="disabled", error_type="Stopped", next_retry_at=None, retry_delay_seconds=None)
        raise
    finally:
        if _listener_owner is asyncio.current_task():
            _listener_owner = None

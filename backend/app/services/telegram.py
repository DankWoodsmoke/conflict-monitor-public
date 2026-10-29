import asyncio
import logging
import hashlib
import re
from datetime import datetime, timezone, timedelta

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from telethon import TelegramClient, events
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
    report["summary"] = result.get("summary", "")
    report["classification_status"] = "extracted"
    severity = result.get("severity", 5)

    # Classifier returned [NOISE] tag or severity=1 — drop immediately
    if result.get("is_noise") or _is_noise(raw_text, severity):
        await finish_report(receipt, "noise")
        logger.debug("Skipping noise (sev=%d): %s", severity, raw_text[:60])
        return

    # Geocode
    location_name = result.get("location_name", "Unknown")
    coords = await geocode(location_name)

    if coords:
        lat, lon = coords
        is_geolocated = True
    else:
        lat, lon = None, None
        is_geolocated = False
        logger.info("No coords for '%s' — parking at Indian Ocean (msg_id=%d)", location_name, message_id)

    geometry = from_shape(Point(lon, lat), srid=4326) if coords else None
    source_url = _build_source_url(channel_name, message_id)

    async with async_session() as session:
        existing = await check_duplicate(
            session,
            result.get("summary", ""),
            result.get("event_type", "military"),
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
                    event_type=result.get("event_type", "military"),
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
            event_type=result.get("event_type", "military"),
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


def _stamp():
    return datetime.now(timezone.utc)


def get_telegram_status():
    try:
        channels = _get_channels()
    except ValueError:
        return {"enabled":False,"status":"failed","error_type":"InvalidChannelSelection","selected_channels":[]}
    configured = bool(settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_session and channels)
    status = _state["status"] if settings.live_ingestion_enabled and configured else "disabled"
    now = _stamp()
    success, publication = _state.get("last_success_at"), _state.get("last_published_at")
    return {"enabled": bool(settings.live_ingestion_enabled and configured), "status": status,
        "mode": settings.telegram_processing_mode, "selected_channels": channels,
        "startup_limit_per_channel": settings.telegram_startup_max_messages,
        "error_type": _state.get("error_type"), "channels": dict(_state["channels"]),
        "last_attempt_at": _state["last_attempt_at"].isoformat() if _state.get("last_attempt_at") else None,
        "last_success_at": success.isoformat() if success else None,
        "last_published_at": publication.isoformat() if publication else None,
        "cache_age_seconds": (now-success).total_seconds() if success else None,
        "publication_age_seconds": (now-publication).total_seconds() if publication else None,
        "publication_stale": bool(publication and (now-publication).total_seconds() > 86400),
        "coverage_limitation": "Selected public channels; bounded startup and incremental polling. Publication time is not event time."}


async def _process_report_message(raw_text, channel_name, message_date, message_id):
    channel_name = str(channel_name or "").lstrip("@").lower()
    report = {"source": "telegram", "channel_name": channel_name, "telegram_message_id": message_id,
        "source_url": _build_source_url(channel_name, message_id), "raw_text": str(raw_text or ""),
        "timestamp": message_date.isoformat() if isinstance(message_date, datetime) else None,
        "time_basis": "source_publication_time" if message_date else "unknown",
        "classification_status": "not_requested", "processing_mode": "publisher_metadata"}
    if len(report["raw_text"]) > 12000:
        report["original_text_sha256"] = hashlib.sha256(report["raw_text"].encode("utf-8")).hexdigest()
        report["raw_text"] = report["raw_text"][:12000]
        report["raw_text_truncated"] = True
    receipt = await capture_report(report)
    if receipt is None:
        identity = report_identity(report)[0]
        async with async_session() as session:
            prior = await session.get(SourceReport, identity)
        if prior is None or prior.status == "received":
            return "pending_receipt"
        # A terminal retained receipt can advance a checkpoint after a crash;
        # an incomplete receipt cannot silently authorize skipping source work.
        await _save_checkpoint(channel_name, message_id)
        return "duplicate"
    async def retained(status, event_id=None):
        await finish_report(receipt, status, event_id)
        if channel_name and isinstance(message_id,int) and message_id > 0:
            await _save_checkpoint(channel_name, message_id)
        return status
    if not raw_text or not str(raw_text).strip() or not channel_name or not isinstance(message_id, int) or message_id <= 0:
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
    report["summary"] = summary
    async with async_session() as session:
        existing = await session.execute(select(Event.id).where(Event.source == "telegram",
            Event.channel_name == channel_name, Event.telegram_message_id == message_id).limit(1))
        prior_id = existing.scalar_one_or_none()
        if prior_id is not None:
            return await retained("source_revision_needs_review", prior_id)
        event = Event(source="telegram", channel_name=channel_name, raw_text=raw_text, summary=summary,
            event_type="unclassified", severity=0, lat=None, lon=None, geometry=None,
            timestamp=message_date, telegram_message_id=message_id, source_url=report["source_url"],
            source_reliability=get_reliability(channel_name), location_name="", report_count=1,
            reporting_channels=channel_name, confirmed_networks="", classification_status="not_requested",
            geolocation_precision="unknown", reports=[make_report(report)], anomaly_score=0, anomaly_analysis="")
        session.add(event)
        await session.commit()
        await session.refresh(event)
        await finish_report(receipt, "reported", event.id)
        await _save_checkpoint(channel_name, message_id)
        await broadcaster.broadcast(EventWS(type="new_event",event=EventRead.model_validate(event)).model_dump_json())
    if _state.get("last_published_at") is None or message_date > _state["last_published_at"]:
        _state["last_published_at"] = message_date
    _state["last_success_at"] = _stamp()
    return "reported"


async def _process_message(raw_text, channel_name, message_date, message_id):
    if settings.telegram_processing_mode == "model":
        return await _process_model_message(raw_text,channel_name,message_date,message_id)
    return await _process_report_message(raw_text,channel_name,message_date,message_id)


async def _backfill_reports(client, entity, conflict_cutoff):
    channel = (getattr(entity,"username","") or "").lower()
    if not channel:
        raise ValueError("Only public username-addressed channels are supported")
    last_id = await _get_checkpoint(channel)
    budget = settings.telegram_startup_max_messages
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
    count = 0
    for message in messages:
        if isinstance(message.date,datetime) and message.date.tzinfo is not None and message.date <= _stamp()+timedelta(minutes=5):
            if _state.get("last_published_at") is None or message.date > _state["last_published_at"]:
                _state["last_published_at"] = message.date
        if not message.text:
            # No text/caption is not a text report; do not download media.
            await _save_checkpoint(channel,message.id)
            continue
        outcome = await _process_message(message.text,channel,message.date,message.id)
        if outcome == "pending_receipt":
            _state["channels"][channel] = {"status":"pending_receipt", "processed":count}
            return count
        count += 1
    _state["channels"][channel] = {"status":"ok", "processed":count, "last_check_at":_stamp().isoformat(),
        "history_complete":False,"startup_or_cycle_limit":budget}
    _state["last_success_at"] = _stamp()
    return count


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
    """Trigger a full re-backfill from conflict start using the live client.
    Called by the admin API endpoint — does not restart the listener.
    """
    if _shared_client is None:
        return {"status": "error", "message": "Telegram client not yet initialised — wait for startup"}

    conflict_cutoff = _get_conflict_cutoff()
    channels = _get_channels()
    results = {}

    for ch in channels:
        try:
            entity = await _shared_client.get_entity(ch)
            await _backfill_entity(_shared_client, entity, conflict_cutoff)
            results[ch] = "ok"
        except Exception as e:
            results[ch] = f"error: {e}"
            logger.warning("On-demand backfill failed for %s: %s", ch, e)

    return {"status": "complete", "channels": results}


# ── Main listener ─────────────────────────────────────────────────────────────

async def start_telegram_listener():
    """Read selected public channels without joining, sending or prompting."""
    global _shared_client
    _state.update(status="connecting",error_type=None,last_attempt_at=_stamp(),channels={})
    try:
        channels = _get_channels()
    except ValueError:
        _state.update(status="failed",error_type="InvalidChannelSelection")
        return
    if not channels or not (settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_session):
        _state.update(status="disabled",error_type="MissingCredentialsOrChannelSelection")
        return
    client = None
    periodic_task = None
    try:
        client = TelegramClient(StringSession(settings.telegram_session), settings.telegram_api_id, settings.telegram_api_hash,
            auto_reconnect=True, connection_retries=2, request_retries=1, timeout=15)
        await asyncio.wait_for(client.connect(),timeout=20)
        if not await asyncio.wait_for(client.is_user_authorized(),timeout=15):
            _state.update(status="failed",error_type="UnauthorizedSession")
            return
        _shared_client = client
        resolved = []
        for name in channels:
            try:
                entity = await asyncio.wait_for(client.get_entity(name),timeout=15)
                if not getattr(entity,"username",None) or not getattr(entity,"broadcast",False):
                    raise ValueError("Selected entity must be a public broadcast channel")
                resolved.append(entity)
                _state["channels"][name] = {"status":"resolved"}
            except Exception as exc:
                _state["channels"][name] = {"status":"failed","error_type":type(exc).__name__}
        if not resolved:
            _state.update(status="failed",error_type="NoPublicChannelsResolved")
            return
        @client.on(events.NewMessage(chats=resolved))
        @client.on(events.MessageEdited(chats=resolved))
        async def handler(event):
            try:
                name = (getattr(event.chat,"username","") or "").lower()
                await _process_message(event.message.text or "",name,event.message.date,event.message.id)
            except Exception as exc:
                _state["channels"][name] = {"status":"failed","error_type":type(exc).__name__}
        cutoff = _get_conflict_cutoff()
        for entity in resolved:
            await _backfill_entity(client,entity,cutoff)
        _state.update(status="ok",last_success_at=_stamp())
        async def poll():
            while True:
                await asyncio.sleep(300)
                for entity in resolved:
                    try:
                        await _backfill_entity(client,entity,cutoff)
                    except Exception as exc:
                        name=(getattr(entity,"username","") or "").lower()
                        _state["channels"][name]={"status":"failed","error_type":type(exc).__name__}
        from app.services.runtime import runtime
        periodic_task = runtime.start("telegram_periodic",poll())
        await client.run_until_disconnected()
        _state.update(status="failed",error_type="Disconnected")
    except asyncio.CancelledError:
        _state.update(status="disabled",error_type="Stopped")
        raise
    except Exception as exc:
        _state.update(status="failed",error_type=type(exc).__name__)
    finally:
        if _shared_client is client:
            _shared_client = None
        if periodic_task is not None and not periodic_task.done():
            periodic_task.cancel()
            await asyncio.gather(periodic_task,return_exceptions=True)
        if client is not None:
            try:
                await asyncio.wait_for(client.disconnect(),timeout=5)
            except Exception as exc:
                _state.update(status="failed",error_type="Disconnect"+type(exc).__name__)

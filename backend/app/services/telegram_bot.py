"""Receive publisher-authorized channel posts through Telegram's official Bot API."""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from time import monotonic

import httpx
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.services import telegram


_POLL_SECONDS = 20
_EMPTY_POLL_FLOOR_SECONDS = 2
_BATCH_LIMIT = 20
_MAX_RESPONSE_BYTES = 2_000_000
_RETENTION_HOURS = 24
_OWNER = None
_STATE = {}
_BOT_URL_TOKEN = re.compile(r"(/bot)[1-9][0-9]{0,15}(?::|%3a)[A-Za-z0-9_-]{20,100}(?=/getUpdates\b)", re.I)
_COVERAGE = ("Publisher-authorized public channels that added this deployment bot. "
             "Forward delivery only from Telegram's 24-hour update queue. "
             "A successful poll does not establish channel membership or complete history.")


class BotProtocolError(Exception):
    """An unexpected or terminal provider response. Raw provider details stay private."""


class BotRetry(Exception):
    def __init__(self, reason, delay=0):
        super().__init__(reason)
        self.reason = reason
        self.delay = delay


class _BotTokenLogFilter(logging.Filter):
    def filter(self, record):
        original = record.getMessage()
        redacted = _BOT_URL_TOKEN.sub(r"\1[redacted]", original)
        if redacted != original:
            record.msg, record.args = redacted, ()
        return True


def _configuration():
    token = settings.telegram_bot_token.get_secret_value()
    if (settings.telegram_processing_mode != "reports"
            or not re.fullmatch(r"[1-9][0-9]{0,15}:[A-Za-z0-9_-]{20,100}", token)):
        raise ValueError("A deployment token and reports mode are required")
    channels = {}
    for item in settings.telegram_bot_channels.split(","):
        match = re.fullmatch(r"([a-zA-Z0-9_]{5,32}):(-100[0-9]{3,12})", item.strip())
        if not match:
            raise ValueError("Select authorized public channel handle and ID pairs")
        name, chat_id = match[1].lower(), int(match[2])
        if name in channels or chat_id in channels.values():
            raise ValueError("Duplicate channel handle or ID")
        channels[name] = chat_id
    if not 1 <= len(channels) <= 5:
        raise ValueError("Select one to five authorized channels")
    return token, channels


def get_bot_status():
    active = settings.live_ingestion_enabled and not settings.demo_mode
    result = {"enabled": False, "status": "disabled", "transport": "bot", "mode": "reports",
              "checkpoint_policy": "bot_update_queue", "retention_hours": _RETENTION_HOURS,
              "selected_channels": [], "channels": {}, "coverage_limitation": _COVERAGE}
    if not active:
        return result
    try:
        _, channels = _configuration()
    except ValueError:
        return {**result, "status": "failed", "error_type": "InvalidBotConfiguration"}
    now = datetime.now(timezone.utc)
    last_success = _STATE.get("last_success_at")
    publication = _STATE.get("last_published_at")
    return {**result, **_STATE, "enabled": True, "selected_channels": list(channels),
            "channels": {name: dict(_STATE.get("channels", {}).get(name, {})) for name in channels},
            "cache_age_seconds": (now - last_success).total_seconds() if last_success else None,
            "publication_age_seconds": (now - publication).total_seconds() if publication else None,
            "publication_stale": bool(publication and (now - publication).total_seconds() > 86400)}


async def _response_body(response):
    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise BotProtocolError("UnexpectedBotEncoding")
    body = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=65536):
        if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
            raise BotProtocolError("BotResponseTooLarge")
        body.extend(chunk)
    try:
        value = json.loads(body)
    except (ValueError, RecursionError):
        raise BotProtocolError("InvalidBotJSON") from None
    if not isinstance(value, dict):
        raise BotProtocolError("InvalidBotResponse")
    return value


async def _get_updates(client, token, offset):
    params = {"limit": _BATCH_LIMIT, "timeout": _POLL_SECONDS,
              "allowed_updates": ["channel_post", "edited_channel_post"]}
    if offset is not None:
        params["offset"] = offset
    try:
        async with asyncio.timeout(30), client.stream(
                "POST", f"https://api.telegram.org/bot{token}/getUpdates", json=params) as response:
            if response.status_code == 429:
                value = await _response_body(response)
                error_params = value.get("parameters")
                wait = error_params.get("retry_after") if isinstance(error_params, dict) else None
                if type(wait) is not int or not 1 <= wait <= 604800:
                    raise BotProtocolError("InvalidBotRateLimit")
                raise BotRetry("BotRateLimited", wait)
            if 500 <= response.status_code <= 599:
                raise BotRetry("BotServerUnavailable")
            if response.status_code != 200:
                # 401/403 need operator action. 409 can mean another receiver or a configured webhook.
                raise BotProtocolError(f"BotHTTP{response.status_code}")
            value = await _response_body(response)
    except (httpx.TransportError, TimeoutError):
        raise BotRetry("BotTransportUnavailable") from None
    result = value.get("result")
    if value.get("ok") is not True or not isinstance(result, list) or len(result) > _BATCH_LIMIT:
        raise BotProtocolError("InvalidBotUpdatePage")
    last = 0 if offset is None else offset - 1
    for update in result:
        update_id = update.get("update_id") if isinstance(update, dict) else None
        if type(update_id) is not int or not last < update_id < (1 << 63) - 1:
            raise BotProtocolError("UnorderedBotUpdatePage")
        last = update_id
    return result


def _authorized_post(update, channels):
    post = update.get("channel_post", update.get("edited_channel_post"))
    chat = post.get("chat") if isinstance(post, dict) else None
    username = chat.get("username") if isinstance(chat, dict) else None
    if (not isinstance(username, str) or chat.get("type") != "channel"
            or type(chat.get("id")) is not int or chat["id"] != channels.get(username.lower())):
        return None
    if (post.get("has_protected_content") is True or post.get("is_paid_post") is True or "forward_origin" in post
            or post.get("is_automatic_forward") is True):
        return None
    text = post.get("text", post.get("caption"))
    if text is None:
        return None
    message_id, published = post.get("message_id"), post.get("date")
    if (not isinstance(text, str) or type(message_id) is not int or not 0 < message_id < 1 << 31
            or type(published) is not int or not 0 < published < 253402300800):
        raise BotProtocolError("InvalidAuthorizedBotPost")
    clock = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=published)
    return username.lower(), message_id, clock, text


async def _persist_post(update, channels):
    post = _authorized_post(update, channels)
    if post is None:
        return
    channel, message_id, published, text = post
    try:
        async with asyncio.timeout(45):
            result = await telegram._process_report_message(
                text, channel, published, message_id, collection_method="telegram_bot_api")
    except (SQLAlchemyError, TimeoutError, OSError):
        raise BotRetry("BotStorageUnavailable") from None
    if result not in telegram.REPORT_TERMINAL_OUTCOMES:
        raise BotRetry("BotReceiptPending")
    now = datetime.now(timezone.utc)
    channel_state = _STATE["channels"][channel]
    channel_state.update(status="observed", last_check_at=now, processed=channel_state["processed"] + 1)
    prior = _STATE.get("last_published_at")
    if published <= now and result not in {"future_source_time", "undated_source"} and (prior is None or published > prior):
        _STATE["last_published_at"] = published


async def start_bot_listener():
    global _OWNER
    if _OWNER is not None or settings.telegram_transport != "bot" or not settings.live_ingestion_enabled or settings.demo_mode:
        return
    try:
        token, channels = _configuration()
    except ValueError:
        _STATE.update(status="failed", error_type="InvalidBotConfiguration")
        return
    _OWNER = asyncio.current_task()
    _STATE.clear()
    _STATE.update(status="connecting", channels={name: {"status": "awaiting_updates",
                                                       "processed": 0, "history_complete": False}
                                                for name in channels})
    loop = asyncio.get_running_loop()
    last_nonempty = monotonic()
    offset = None
    failures = 0
    http_logger = logging.getLogger("httpx")
    token_filter = _BotTokenLogFilter()
    http_logger.addFilter(token_filter)
    try:
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                timeout=httpx.Timeout(25, connect=5), headers={"Accept-Encoding": "identity"}) as client:
            while True:
                # Telegram may pick a random update ID after a quiet week. Discard a stale
                # memory-only hint before it could acknowledge a newer, lower provider ID.
                if monotonic() - last_nonempty >= _RETENTION_HOURS * 3600:
                    offset = None
                _STATE["last_attempt_at"] = datetime.now(timezone.utc)
                poll_start = loop.time()
                try:
                    page = await _get_updates(client, token, offset)
                    if offset is not None:
                        _STATE["last_acknowledged_at"] = datetime.now(timezone.utc)
                    if not page:
                        offset = None
                    else:
                        last_nonempty = monotonic()
                    for update in page:
                        await _persist_post(update, channels)
                        # Telegram durably confirms only on a subsequent request. If the
                        # process exits first, its queue replays this idempotent receipt.
                        offset = update["update_id"] + 1
                    failures = 0
                    _STATE.update(status="ok", error_type=None, reconnect_attempts=0,
                                  retry_delay_seconds=None, next_retry_at=None, last_success_at=datetime.now(timezone.utc))
                    if not page and (pause := _EMPTY_POLL_FLOOR_SECONDS - (loop.time() - poll_start)) > 0:
                        await asyncio.sleep(pause)
                except BotRetry as exc:
                    failures += 1
                    delay = max(exc.delay, min(300, 5 * 2 ** min(failures - 1, 6)))
                    _STATE.update(status="retrying", error_type=exc.reason, reconnect_attempts=failures,
                                  retry_delay_seconds=delay, next_retry_at=datetime.now(timezone.utc) + timedelta(seconds=delay))
                    await asyncio.sleep(delay)
    except asyncio.CancelledError:
        _STATE.update(status="disabled", error_type="Stopped", retry_delay_seconds=None, next_retry_at=None)
        raise
    except BotProtocolError as exc:
        _STATE.update(status="failed", error_type=str(exc), retry_delay_seconds=None, next_retry_at=None)
    except Exception as exc:
        _STATE.update(status="failed", error_type=type(exc).__name__, retry_delay_seconds=None, next_retry_at=None)
    finally:
        http_logger.removeFilter(token_filter)
        _OWNER = None

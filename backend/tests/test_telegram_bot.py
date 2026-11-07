"""Official receive-only Bot API tests. All network responses are authored."""

import asyncio
import json
import logging
import socket
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
from pydantic import SecretStr
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services import telegram
from app.services import telegram_bot as bot


_CHAT_ID = -1001234567890
_TOKEN = f"{42}:{'a' * 32}"
_PUBLISHED = 1760000000


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(bot.settings, "telegram_transport", "bot")
    monkeypatch.setattr(bot.settings, "telegram_bot_token", SecretStr(_TOKEN))
    monkeypatch.setattr(bot.settings, "telegram_bot_channels", f"publisher_one:{_CHAT_ID}")
    monkeypatch.setattr(bot.settings, "telegram_processing_mode", "reports")
    monkeypatch.setattr(bot.settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(bot.settings, "demo_mode", False)
    monkeypatch.setattr(bot.settings, "telegram_api_id", 0)
    monkeypatch.setattr(bot.settings, "telegram_api_hash", "")
    monkeypatch.setattr(bot.settings, "telegram_session", "")
    monkeypatch.setattr(bot.settings, "telegram_phone", "")
    monkeypatch.setattr(bot, "_OWNER", None)
    monkeypatch.setattr(bot, "_STATE", {})
    return {"publisher_one": _CHAT_ID}


def update(update_id, message_id, *, edited=False, **changes):
    post = {"chat": {"type": "channel", "username": "Publisher_One", "id": _CHAT_ID},
            "text": "Preserve this original source text.", "message_id": message_id, "date": _PUBLISHED}
    post.update(changes)
    return {"update_id": update_id, "edited_channel_post" if edited else "channel_post": post}


def intercept_http(monkeypatch, handler):
    real_client = httpx.AsyncClient
    def client(**options):
        assert options["trust_env"] is False
        assert options["follow_redirects"] is False
        assert options["headers"]["Accept-Encoding"] == "identity"
        return real_client(transport=httpx.MockTransport(handler), **options)
    monkeypatch.setattr(bot.httpx, "AsyncClient", client)


def response(*rows):
    return httpx.Response(200, json={"ok": True, "result": list(rows)})


def request_offset(request):
    assert request.method == "POST"
    assert request.url == f"https://api.telegram.org/bot{_TOKEN}/getUpdates"
    params = json.loads(request.content)
    assert params["allowed_updates"] == ["channel_post", "edited_channel_post"]
    assert params["timeout"] == 20 and params["limit"] == 20
    return params.get("offset")


@pytest.mark.asyncio
async def test_only_durably_processed_prefix_is_confirmed_and_empty_poll_resets_hint(configured, monkeypatch):
    ignored = {"update_id": 5, "message": {"text": "unrequested private content"}}
    first, second = update(7, 13), update(9, 14, edited=True)
    offsets, failures = [], []
    async def provider(request):
        offsets.append(request_offset(request))
        if offsets == [None]:
            return response(ignored, first, second)
        if offsets == [None, 8]:
            return response(second)
        if offsets == [None, 8, 10]:
            return response()
        raise asyncio.CancelledError
    async def sleep(delay):
        failures.append((delay, bot.get_bot_status()["error_type"]))
    intercept_http(monkeypatch, provider)
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)
    persist = AsyncMock(side_effect=["reported", "pending_receipt", "source_revision_needs_review"])
    monkeypatch.setattr(telegram, "_process_report_message", persist)
    monkeypatch.setattr(telegram, "_save_checkpoint", AsyncMock(side_effect=AssertionError("MTProto checkpoint changed")))
    with pytest.raises(asyncio.CancelledError):
        await bot.start_bot_listener()
    assert offsets == [None, 8, 10, None]
    assert failures[0] == (5, "BotReceiptPending")
    assert len(failures) == 2 and 0 < failures[1][0] <= 2 and failures[1][1] is None
    assert [call.args[3] for call in persist.await_args_list] == [13, 14, 14]
    assert all(call.kwargs == {"collection_method": "telegram_bot_api"} for call in persist.await_args_list)
    assert bot.get_bot_status()["last_acknowledged_at"] is not None
    assert bot._OWNER is None


@pytest.mark.parametrize("failure", [
    socket.gaierror("private database hostname"),
    ConnectionRefusedError("private database address"),
    ConnectionResetError("private connection details"),
    SQLAlchemyError("private SQL"),
    TimeoutError("private timeout details"),
], ids=["dns", "refused", "reset", "sqlalchemy", "timeout"])
@pytest.mark.asyncio
async def test_storage_outage_retains_confirmed_prefix_until_failed_post_is_durable(
        configured, monkeypatch, failure):
    first, second = update(7, 13), update(9, 14)
    offsets, transitions = [], []

    async def provider(request):
        offsets.append(request_offset(request))
        if len(offsets) == 1:
            return response(first, second)
        if len(offsets) == 2:
            return response(second)
        transitions.append((bot._STATE["status"], bot._STATE["error_type"],
                            bot._STATE["channels"]["publisher_one"]["processed"]))
        raise asyncio.CancelledError

    async def sleep(delay):
        transitions.append((bot._STATE["status"], bot._STATE["error_type"],
                            bot._STATE["channels"]["publisher_one"]["processed"]))
        assert delay == 5
        assert "private" not in repr(bot.get_bot_status())

    intercept_http(monkeypatch, provider)
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)
    persist = AsyncMock(side_effect=["reported", failure, "reported"])
    monkeypatch.setattr(telegram, "_process_report_message", persist)
    with pytest.raises(asyncio.CancelledError):
        await bot.start_bot_listener()
    assert offsets == [None, 8, 10]
    assert transitions == [("retrying", "BotStorageUnavailable", 1), ("ok", None, 2)]
    assert [call.args[3] for call in persist.await_args_list] == [13, 14, 14]
    assert bot._OWNER is None


@pytest.mark.asyncio
async def test_cancel_during_storage_retry_does_not_acknowledge_failed_post(configured, monkeypatch):
    offsets = []

    async def provider(request):
        offsets.append(request_offset(request))
        return response(update(7, 13))

    async def sleep(delay):
        assert delay == 5 and bot._STATE["status"] == "retrying"
        raise asyncio.CancelledError

    intercept_http(monkeypatch, provider)
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)
    monkeypatch.setattr(telegram, "_process_report_message", AsyncMock(side_effect=ConnectionResetError()))
    with pytest.raises(asyncio.CancelledError):
        await bot.start_bot_listener()
    assert offsets == [None]
    assert bot._STATE["channels"]["publisher_one"]["processed"] == 0
    assert bot._STATE.get("last_acknowledged_at") is None
    assert bot._STATE["status"] == "disabled" and bot._OWNER is None


@pytest.mark.asyncio
async def test_storage_invariant_failure_still_fails_closed_without_retry(configured, monkeypatch):
    offsets = []

    async def provider(request):
        offsets.append(request_offset(request))
        return response(update(7, 13))

    intercept_http(monkeypatch, provider)
    sleep = AsyncMock(side_effect=AssertionError("Fatal invariant must not retry"))
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)
    monkeypatch.setattr(telegram, "_process_report_message", AsyncMock(side_effect=ValueError("private invariant")))
    await bot.start_bot_listener()
    sleep.assert_not_awaited()
    assert offsets == [None]
    assert bot._STATE["status"] == "failed" and bot._STATE["error_type"] == "ValueError"
    assert bot._STATE["channels"]["publisher_one"]["processed"] == 0
    assert bot._OWNER is None


@pytest.mark.asyncio
async def test_restart_replays_unconfirmed_committed_item_without_acknowledging_early(configured, monkeypatch):
    committed, calls = set(), []
    first, later = update(20, 15), update(21, 16)
    async def provider(request):
        calls.append(request_offset(request))
        if calls == [None]:
            return response(first, later)
        if calls == [None, None]:
            return response(first, later)
        if calls == [None, None, 22]:
            return response()
        raise asyncio.CancelledError
    async def persist(_text, _channel, _date, message_id, **_):
        if message_id not in committed:
            committed.add(message_id)
            if message_id == 15:
                raise asyncio.CancelledError
            return "reported"
        return "duplicate"
    intercept_http(monkeypatch, provider)
    monkeypatch.setattr(telegram, "_process_report_message", persist)
    for _ in range(2):
        with pytest.raises(asyncio.CancelledError):
            await bot.start_bot_listener()
    assert calls == [None, None, 22, None] and committed == {15, 16}


@pytest.mark.asyncio
async def test_transport_flood_delay_and_duplicate_owner_are_bounded(configured, monkeypatch):
    calls, delays = [], []
    async def provider(request):
        calls.append(request_offset(request))
        if len(calls) == 1:
            raise httpx.ConnectError("Sensitive provider path", request=request)
        if len(calls) == 2:
            return httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 361}})
        if len(calls) == 3:
            return httpx.Response(502)
        return httpx.Response(409, json={"description": "Sensitive service token or webhook"})
    async def sleep(delay):
        delays.append(delay)
        await bot.start_bot_listener()  # same owner holds it; another receive loop never starts
    intercept_http(monkeypatch, provider)
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)
    await bot.start_bot_listener()
    assert calls == [None] * 4 and delays == [5, 361, 20]
    status = telegram.get_telegram_status()
    assert status["error_type"] == "BotHTTP409" and status["status"] == "failed"
    assert status["transport"] == "bot" and status["checkpoint_policy"] == "bot_update_queue"
    assert _TOKEN not in repr(status) and "Sensitive" not in repr(status)


@pytest.mark.asyncio
async def test_long_outage_discards_old_offset_before_provider_reuses_lower_ids(configured, monkeypatch):
    clock, offsets = [0], []
    async def provider(request):
        offsets.append(request_offset(request))
        if offsets == [None]:
            return response(update(9000, 10))
        if offsets == [None, 9001]:
            raise httpx.ConnectError("Offline", request=request)
        if offsets == [None, 9001, None]:
            return response(update(6, 20))
        return httpx.Response(409)
    async def sleep(delay):
        assert delay == 5
        clock[0] += 8 * 86400
    intercept_http(monkeypatch, provider)
    monkeypatch.setattr(bot, "monotonic", lambda: clock[0])
    monkeypatch.setattr(bot.asyncio, "sleep", sleep)
    persist = AsyncMock(return_value="reported")
    monkeypatch.setattr(telegram, "_process_report_message", persist)
    await bot.start_bot_listener()
    assert offsets == [None, 9001, None, 7]
    assert [call.args[3] for call in persist.await_args_list] == [10, 20]


@pytest.mark.asyncio
async def test_forced_httpx_info_never_logs_bot_token(configured, monkeypatch, caplog):
    intercept_http(monkeypatch, lambda request: httpx.Response(
        403, json={"ok": False, "description": f"Untrusted response {_TOKEN}"}))
    with caplog.at_level(logging.INFO, logger="httpx"):
        await bot.start_bot_listener()
    assert "https://api.telegram.org/bot[redacted]/getUpdates" in caplog.text
    assert _TOKEN not in caplog.text and "Untrusted response" not in caplog.text
    assert bot.get_bot_status()["error_type"] == "BotHTTP403"


@pytest.mark.parametrize("rows", [
    [update(2, 2), update(1, 1)], [update(1, 2), update(1, 1)],
    [{"update_id": True}], [{"update_id": 1 << 63}], [None],
])
@pytest.mark.asyncio
async def test_malformed_or_unordered_update_page_cannot_confirm_next_prefix(rows):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response(*rows))) as client:
        with pytest.raises(bot.BotProtocolError, match="UnorderedBotUpdatePage"):
            await bot._get_updates(client, _TOKEN, None)


@pytest.mark.parametrize("payload,headers,message", [
    (b"{}", {"Content-Encoding": "gzip"}, "UnexpectedBotEncoding"),
    (b"not-json", {}, "InvalidBotJSON"),
    (b"0" * 101, {}, "BotResponseTooLarge"),
    (b'{"ok":true,"result":{}}', {}, "InvalidBotUpdatePage"),
])
@pytest.mark.asyncio
async def test_response_boundary(monkeypatch, payload, headers, message):
    monkeypatch.setattr(bot, "_MAX_RESPONSE_BYTES", 100)
    # Deliberately use an unread streaming transport for the encoded-body rejection.
    class Raw(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield payload
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=Raw(), headers=headers))) as client:
        with pytest.raises(bot.BotProtocolError, match=message):
            await bot._get_updates(client, _TOKEN, None)


@pytest.mark.parametrize("changes", [
    {"has_protected_content": True}, {"forward_origin": {}}, {"is_automatic_forward": True},
    {"chat": {"type": "group", "username": "publisher_one", "id": _CHAT_ID}},
    {"chat": {"type": "channel", "username": "publisher_one", "id": _CHAT_ID - 1}},
    {"chat": {"type": "channel", "username": "other_publisher", "id": _CHAT_ID}},
    {"chat": {"type": "channel", "username": "publisher_one", "id": str(_CHAT_ID)}},
    {"text": None},
])
def test_unauthorized_protected_and_forwarded_posts_are_ignored(configured, changes):
    assert bot._authorized_post(update(1, 1, **changes), configured) is None


def test_captions_preserve_provider_publication_clock_and_exact_bytes(configured):
    post = update(1, 2, edited=True, caption="Café — العربية", edit_date=_PUBLISHED + 900)
    post["edited_channel_post"].pop("text")
    assert bot._authorized_post(post, configured) == (
        "publisher_one", 2, datetime.fromtimestamp(_PUBLISHED, timezone.utc), "Café — العربية")


@pytest.mark.parametrize("changes", [{"date": True}, {"date": -1}, {"date": 253402300800},
                                      {"message_id": 1 << 31}, {"message_id": 0}, {"text": 1}])
def test_malformed_selected_post_fails_closed(configured, changes):
    post = update(1, 2)
    post["channel_post"].update(changes)
    with pytest.raises(bot.BotProtocolError, match="InvalidAuthorizedBotPost"):
        bot._authorized_post(post, configured)


@pytest.mark.parametrize("bad_channels", ["", "publisher_one", "https://t.me/publisher_one",
                                         f"publisher_one:{_CHAT_ID},publisher_one:{_CHAT_ID - 1}",
                                         f"publisher_one:{_CHAT_ID},publisher_two:{_CHAT_ID}"])
@pytest.mark.asyncio
async def test_invalid_channel_permissions_make_no_provider_calls(configured, monkeypatch, bad_channels):
    monkeypatch.setattr(bot.settings, "telegram_bot_channels", bad_channels)
    monkeypatch.setattr(bot.httpx, "AsyncClient", lambda **_: pytest.fail("Provider called without permission"))
    await bot.start_bot_listener()
    state = telegram.get_telegram_status()
    assert state["enabled"] is False and state["error_type"] == "InvalidBotConfiguration"


@pytest.mark.asyncio
async def test_bot_cannot_enable_telegram_model_ingestion(configured, monkeypatch):
    monkeypatch.setattr(bot.settings, "telegram_processing_mode", "model")
    monkeypatch.setattr(bot.httpx, "AsyncClient", lambda **_: pytest.fail("Provider called in model mode"))
    await bot.start_bot_listener()
    assert telegram.get_telegram_status()["error_type"] == "InvalidBotConfiguration"

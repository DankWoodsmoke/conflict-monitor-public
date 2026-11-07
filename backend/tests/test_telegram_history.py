import asyncio
import copy
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.services import telegram as tg
from app.services import telegram_history as history
from test_free_telegram import free, RAW, STAMP

UTC = timezone.utc
IDENTITY = "a9a7b50b-9078-4f71-b0a8-9d613fc66cc9"


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(history.settings, "live_ingestion_enabled", True)
    monkeypatch.setattr(history.settings, "telegram_transport", "session")
    monkeypatch.setattr(history.settings, "demo_mode", False)
    monkeypatch.setattr(history.settings, "telegram_processing_mode", "reports")
    monkeypatch.setattr(history.settings, "telegram_channels", "fixture_public")
    monkeypatch.setattr(tg, "_get_conflict_cutoff", lambda: STAMP-timedelta(days=2))
    monkeypatch.setattr(history, "PAGE_LIMIT", 2)


def request(**changes):
    return dict(request_id=IDENTITY, channel_name="fixture_public",
                start_at=STAMP, end_at=STAMP+timedelta(hours=1), max_messages=20, **changes)


def job(**changes):
    result = dict(id=IDENTITY, channel_name="fixture_public", start_at=STAMP,
        end_at=STAMP+timedelta(hours=1), max_messages=20, status="queued",
        cursor_message_id=0, upper_message_id=None, source_entity_id=None,
        processed_messages=0, outcomes={}, last_error_type=None, blocked_message_id=None, completed_at=None)
    result.update(changes)
    return result


def msg(i, **changes):
    value = dict(id=i, text=RAW+str(i), date=STAMP+timedelta(seconds=i))
    value.update(changes)
    return SimpleNamespace(**value)


class Provider:
    def __init__(self, messages):
        self.messages = list(messages)
        self.calls = []
        self.entity = SimpleNamespace(id=12345, username="fixture_public", broadcast=True)

    async def get_entity(self, channel):
        assert channel == "fixture_public"
        return self.entity

    async def iter_messages(self, entity, **options):
        self.calls.append(copy.deepcopy(options))
        assert entity is self.entity
        reverse = options.get("reverse", False)
        rows = sorted(self.messages, key=lambda m:m.id, reverse=not reverse)
        rows = [m for m in rows if options.get("min_id", 0) < m.id < options.get("max_id", 2**63)]
        if "offset_date" in options:
            rows = [m for m in rows if (m.date > options["offset_date"] if reverse else m.date < options["offset_date"])]
        for row in rows[:options["limit"]]:
            yield row


class Store:
    def __init__(self):
        self.items = []
        self.saved = None

    async def persist(self, value, item=None, *, status_only=False):
        if status_only:
            assert not item and self.saved is not None
            for key in ("status", "last_error_type", "blocked_message_id", "completed_at"):
                self.saved[key] = copy.deepcopy(value[key])
            value.update(copy.deepcopy(self.saved))
            return
        if item:
            assert item["message_id"] == value["cursor_message_id"]
            assert all(i["message_id"] != item["message_id"] for i in self.items)
            self.items.append(copy.deepcopy(item))
        self.saved = copy.deepcopy(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [asyncio.CancelledError, OSError])
async def test_lost_commit_ack_never_regresses_durable_progress(enabled,free,error):
    class LostAck(Store):
        failed=False
        async def persist(self,value,item=None,*,status_only=False):
            await super().persist(value,item,status_only=status_only)
            if item is not None and not self.failed:
                self.failed=True
                raise error("fixture lost commit acknowledgement")
    value=job();store=LostAck();provider=Provider([msg(1),msg(2),msg(3)])
    if error is asyncio.CancelledError:
        with pytest.raises(asyncio.CancelledError):
            await history.run_page(value,provider,store.persist)
    else:
        await history.run_page(value,provider,store.persist)
    assert value["status"]==store.saved["status"]=="paused"
    assert value["cursor_message_id"]==store.saved["cursor_message_id"]==1
    assert value["processed_messages"]==1 and value["outcomes"]=={"reported":1}
    assert value["upper_message_id"]==3 and len(store.items)==1
    await history.run_page(value,provider,store.persist)
    assert value["status"]=="completed" and value["cursor_message_id"]==3
    assert [i["message_id"] for i in store.items]==[1,2,3]
    assert len(free.store.events)==3


@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_abandon_connection_cleanup():
    entered=asyncio.Event();release=asyncio.Event();order=[]
    async def cleanup():
        entered.set();await release.wait();order.append("cleanup_finished")
    async def owner():
        try:await history._finish_cleanup(cleanup())
        finally:order.append("connection_context_exited")
    task=asyncio.create_task(owner());await entered.wait()
    task.cancel();await asyncio.sleep(0);task.cancel();await asyncio.sleep(0)
    assert not task.done() and not order
    release.set()
    with pytest.raises(asyncio.CancelledError):await task
    assert order==["cleanup_finished","connection_context_exited"]


@pytest.mark.parametrize("field,value", [("start_at", STAMP.replace(tzinfo=None)),
    ("end_at", STAMP.replace(microsecond=1)), ("max_messages", True), ("max_messages", 0),
    ("max_messages", 5001), ("max_messages", "200"), ("channel_name", "https://t.me/fixture_public")])
def test_request_schema_refuses_ambiguous_or_unbounded_inputs(enabled,field,value):
    data=request(); data[field]=value
    with pytest.raises(ValidationError):history.HistoryRequest(**data)


@pytest.mark.parametrize("change", [{"start_at":STAMP+timedelta(hours=2)},
    {"end_at":STAMP+timedelta(days=32)}, {"start_at":STAMP-timedelta(days=3)},
    {"end_at":STAMP+timedelta(days=10)}, {"channel_name":"not_selected"}])
def test_request_policy_bounds(enabled,change):
    data=request();data.update(change)
    with pytest.raises(HTTPException):
        history.request_values(history.HistoryRequest(**data), now=STAMP+timedelta(days=1))


def test_request_normalizes_source_and_utc_without_changing_window(enabled):
    data=request();data["channel_name"]="@Fixture_Public"
    values=history.request_values(history.HistoryRequest(**data),now=STAMP+timedelta(days=1))
    assert values["channel_name"]=="fixture_public" and values["start_at"]==STAMP
    assert len(values["request_hash"])==64 and values["cursor_message_id"]==0


@pytest.mark.asyncio
async def test_resume_keeps_frozen_fence_and_separate_live_checkpoint(enabled,free):
    provider=Provider([msg(i) for i in range(1,6)]); store=Store(); value=job()
    before=copy.deepcopy(tg._state)
    await history.run_page(value,provider,store.persist)
    assert value["status"]=="paused" and value["cursor_message_id"]==2 and value["upper_message_id"]==5
    provider.messages.append(msg(6))
    await history.run_page(value,provider,store.persist)
    await history.run_page(value,provider,store.persist)
    assert value["status"]=="completed" and value["cursor_message_id"]==5
    assert len(free.store.events)==5 and [i["message_id"] for i in store.items]==[1,2,3,4,5]
    assert len([x for x in provider.calls if not x.get("reverse")])==1
    assert provider.calls[1]["offset_date"]==STAMP-timedelta(seconds=1)
    assert all(x.get("max_id")==6 for x in provider.calls if x.get("reverse"))
    assert tg._state==before
    free.checkpoint.assert_not_awaited();free.forbidden.assert_not_awaited()


@pytest.mark.asyncio
async def test_budget_exhaustion_is_partial_even_if_page_is_successful(enabled,free):
    value=job(max_messages=2); provider=Provider([msg(i) for i in range(1,5)]); store=Store()
    await history.run_page(value,provider,store.persist)
    assert value["status"]=="budget_exhausted" and not history.public_job(value)["requested_window_complete"]
    calls=len(provider.calls)
    await history.run_page(value,provider,store.persist)
    assert len(provider.calls)==calls and value["processed_messages"]==2


@pytest.mark.asyncio
async def test_pending_receipt_never_advances_over_blocked_message(enabled,free,monkeypatch):
    actual=tg._process_report_message; pending=True
    async def process(raw,channel,stamp,i,**kwargs):
        if i==2 and pending:return "pending_receipt"
        return await actual(raw,channel,stamp,i,**kwargs)
    monkeypatch.setattr(tg,"_process_report_message",process)
    value=job();provider=Provider([msg(1),msg(2),msg(3)]);store=Store()
    await history.run_page(value,provider,store.persist)
    assert value["status"]=="paused" and value["cursor_message_id"]==1 and value["blocked_message_id"]==2
    pending=False
    await history.run_page(value,provider,store.persist)
    assert value["status"]=="completed" and [x["message_id"] for x in store.items]==[1,2,3]
    free.checkpoint.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_failure_preserves_last_committed_progress(enabled,free):
    class Broken(Provider):
        async def iter_messages(self, entity, **kwargs):
            if kwargs.get("reverse"):
                yield msg(1)
                raise RuntimeError("private source or credential must not appear")
            async for item in super().iter_messages(entity,**kwargs):yield item
    value=job();store=Store()
    await history.run_page(value,Broken([msg(1),msg(2)]),store.persist)
    assert value["cursor_message_id"]==1 and value["status"]=="paused"
    assert value["last_error_type"]=="RuntimeError" and len(store.items)==1


@pytest.mark.asyncio
async def test_cancellation_keeps_last_committed_cursor(enabled,free,monkeypatch):
    actual=tg._process_report_message
    async def process(raw,ch,stamp,i,**kwargs):
        if i==2:raise asyncio.CancelledError()
        return await actual(raw,ch,stamp,i,**kwargs)
    monkeypatch.setattr(tg,"_process_report_message",process)
    value=job();store=Store()
    with pytest.raises(asyncio.CancelledError):
        await history.run_page(value,Provider([msg(1),msg(2)]),store.persist)
    assert store.saved["status"]=="paused" and store.saved["last_error_type"]=="Cancelled"
    assert store.saved["cursor_message_id"]==1 and len(store.items)==1
    free.checkpoint.assert_not_awaited()


@pytest.mark.asyncio
async def test_timeout_is_partial_not_success(enabled,free,monkeypatch):
    monkeypatch.setattr(history,"BATCH_SECONDS",.01)
    client=Provider([msg(1)])
    async def slow(_):await asyncio.sleep(1)
    client.get_entity=slow
    value=job();store=Store()
    await history.run_page(value,client,store.persist)
    assert value["status"]=="paused" and value["last_error_type"]=="TimeoutError"
    assert value["cursor_message_id"]==0 and not store.items


@pytest.mark.asyncio
async def test_duplicate_and_correction_preserve_original_evidence_without_live_cursor(enabled,free):
    await tg._process_report_message(RAW+"1","fixture_public",msg(1).date,1)
    await tg._process_report_message(RAW+"2","fixture_public",msg(2).date,2)
    before=[(e.raw_text,e.reports) for e in free.store.events]
    free.checkpoint.reset_mock()
    provider=Provider([msg(1),msg(2,text=RAW+" amended")]);store=Store();value=job()
    await history.run_page(value,provider,store.persist)
    assert value["status"]=="completed"
    assert value["outcomes"]=={"duplicate":1,"source_revision_needs_review":1}
    assert [(e.raw_text,e.reports) for e in free.store.events]==before
    assert len(free.ledger.records)==3 and all(i["source_report_identity"] in free.ledger.records for i in store.items)
    free.checkpoint.assert_not_awaited();free.forbidden.assert_not_awaited()


@pytest.mark.asyncio
async def test_unicode_and_oversized_identity_matches_preserved_ledger(enabled,free):
    provider=Provider([msg(1,text="\u0645"*13000)]);value=job();store=Store()
    await history.run_page(value,provider,store.persist)
    item=store.items[0]
    assert item["outcome"]=="input_too_large" and not free.store.events
    assert item["source_report_identity"] in free.ledger.records
    assert item["content_sha256"]==hashlib.sha256(("\u0645"*13000).encode()).hexdigest()
    free.checkpoint.assert_not_awaited()


@pytest.mark.asyncio
async def test_frozen_public_entity_change_stops_before_more_source_reads(enabled,free):
    value=job(source_entity_id=999);provider=Provider([msg(1)]);store=Store()
    await history.run_page(value,provider,store.persist)
    assert value["last_error_type"]=="PublicChannelIdentityChanged" and not provider.calls and not store.items


@pytest.mark.asyncio
async def test_public_username_does_not_authorize_private_chat_or_user_history(enabled,free):
    value=job();provider=Provider([msg(1)]);provider.entity.broadcast=False;store=Store()
    await history.run_page(value,provider,store.persist)
    assert value["last_error_type"]=="PublicChannelIdentityMismatch" and not provider.calls and not store.items


@pytest.mark.asyncio
async def test_provider_cannot_escape_id_fence_or_order(enabled,free):
    class Wrong(Provider):
        async def iter_messages(self,entity,**kwargs):
            if kwargs.get("reverse"):
                yield msg(3)
            else:
                yield msg(2)
    value=job();store=Store()
    await history.run_page(value,Wrong([]),store.persist)
    assert value["status"]=="paused" and value["last_error_type"]=="MessageOutsideFrozenIdOrder"
    assert not store.items and not free.store.events


@pytest.mark.asyncio
async def test_empty_provider_completes_only_frozen_requested_window(enabled,free):
    value=job();store=Store();provider=Provider([])
    await history.run_page(value,provider,store.persist)
    assert value["status"]=="completed" and value["upper_message_id"]==0
    assert not history.public_job(value)["history_complete"] and not free.store.events


@pytest.mark.asyncio
async def test_no_text_is_receipted_without_download_or_event(enabled,free):
    value=job();store=Store()
    await history.run_page(value,Provider([msg(1,text="")]),store.persist)
    assert store.items[0]["outcome"]=="no_text_or_caption" and not free.store.events and not free.ledger.records
    free.checkpoint.assert_not_awaited()


def test_history_api_is_admin_only_and_unknown_job_id_is_rejected(enabled,monkeypatch):
    monkeypatch.setattr(history.settings,"admin_api_key","fixture-admin")
    monkeypatch.setattr(history,"create_job",AsyncMock(side_effect=AssertionError("must not execute")))
    client=TestClient(app)
    data={**request(),"start_at":STAMP.isoformat(),"end_at":(STAMP+timedelta(hours=1)).isoformat()}
    assert client.post('/history/backfill/jobs',json=data).status_code==403
    assert client.get('/history/backfill/jobs').status_code==403
    assert client.post('/history/backfill/jobs/not-a-uuid/run',headers={'X-Admin-Key':'fixture-admin'}).status_code==422


def test_forward_report_catchup_does_not_require_paid_provider(enabled,monkeypatch):
    from app.routes import events
    monkeypatch.setattr(history.settings,"admin_api_key","fixture-admin")
    monkeypatch.setattr(history.settings,"anthropic_api_key","")
    monkeypatch.setattr(tg,"_shared_client",SimpleNamespace(is_connected=lambda:True))
    starter=Mock();monkeypatch.setattr(events,"_start_admin_review",starter)
    response=TestClient(app).post('/events/admin/backfill',headers={'X-Admin-Key':'fixture-admin'})
    assert response.status_code==200 and response.json()['scope']=='forward_catchup'
    assert response.json()['history_complete'] is False
    starter.assert_called_once()

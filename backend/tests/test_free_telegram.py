from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.models import SourceReport
from app.services import telegram as tg
from test_ingestion_integration import EventStore, Ledger

STAMP = datetime(2026,10,28,12,tzinfo=timezone.utc)
RAW = "وصول المساعدات — publisher-authored report without automated classification"


@pytest.fixture
def free(monkeypatch):
    order=[]
    store=EventStore()
    ledger=Ledger(order)
    async def get(model, identity):
        assert model is SourceReport
        row=ledger.records.get(identity)
        return SimpleNamespace(**row) if row else None
    store.get=get
    monkeypatch.setattr(tg.settings,"telegram_processing_mode","reports")
    monkeypatch.setattr(tg.settings,"telegram_channels","fixture_public")
    monkeypatch.setattr(tg.settings,"telegram_startup_max_messages",3)
    monkeypatch.setattr(tg,"capture_report",ledger.capture)
    monkeypatch.setattr(tg,"finish_report",ledger.finish)
    monkeypatch.setattr(tg,"async_session",store.session)
    monkeypatch.setattr(tg,"_stamp",lambda:STAMP+timedelta(hours=1))
    monkeypatch.setattr(tg,"_get_conflict_cutoff",lambda:STAMP-timedelta(days=1))
    monkeypatch.setattr(tg,"_state",{"status":"disabled","channels":{},"last_success_at":None,"last_published_at":None})
    forbidden=AsyncMock(side_effect=AssertionError("Free Telegram must not call a model/geocoder/anomaly"))
    monkeypatch.setattr(tg,"classify_message",forbidden)
    monkeypatch.setattr(tg,"geocode",forbidden)
    monkeypatch.setattr(tg,"analyze_anomaly",forbidden)
    checkpoint=AsyncMock()
    monkeypatch.setattr(tg,"_save_checkpoint",checkpoint)
    broadcast=AsyncMock()
    monkeypatch.setattr(tg.broadcaster,"broadcast",broadcast)
    return SimpleNamespace(store=store,ledger=ledger,forbidden=forbidden,checkpoint=checkpoint,broadcast=broadcast)


async def ingest(text=RAW,channel="Fixture_Public",stamp=STAMP,message_id=42):
    return await tg._process_message(text,channel,stamp,message_id)


@pytest.mark.asyncio
async def test_free_telegram_preserves_unicode_unscored_and_null_location(free):
    assert await ingest()=="reported"
    event=free.store.events[0]
    assert event.source=="telegram" and event.channel_name=="fixture_public"
    assert event.raw_text==RAW
    assert event.event_type=="unclassified" and event.severity==0
    assert event.classification_status=="not_requested"
    assert event.lat is event.lon is event.geometry is None
    assert event.source_url=="https://t.me/fixture_public/42"
    free.forbidden.assert_not_awaited()
    free.checkpoint.assert_awaited_once_with("fixture_public",42)
    assert free.broadcast.await_count==1


@pytest.mark.asyncio
async def test_replay_and_source_edit_never_inflate_or_overwrite(free):
    assert await ingest()=="reported"
    assert await ingest()=="duplicate"
    assert await ingest(text=RAW+" Source correction.")=="source_revision_needs_review"
    assert len(free.store.events)==1 and len(free.ledger.records)==2
    assert free.store.events[0].raw_text==RAW
    assert free.broadcast.await_count==1


@pytest.mark.asyncio
async def test_same_message_id_across_public_channels_is_distinct(free):
    assert await ingest(channel="first_public")=="reported"
    assert await ingest(channel="second_public")=="reported"
    assert len(free.store.events)==2


@pytest.mark.asyncio
async def test_incomplete_receipt_cannot_advance_checkpoint(free):
    report={"source":"telegram","channel_name":"fixture_public","telegram_message_id":42,
        "source_url":"https://t.me/fixture_public/42","raw_text":RAW,"timestamp":STAMP.isoformat()}
    await free.ledger.capture(report)
    assert await ingest()=="pending_receipt"
    free.checkpoint.assert_not_awaited()
    assert not free.store.events


@pytest.mark.asyncio
@pytest.mark.parametrize("stamp,status",[(None,"undated_source"),(STAMP.replace(tzinfo=None),"undated_source"),
    (STAMP+timedelta(days=1),"future_source_time")])
async def test_invalid_clocks_retain_receipt_without_fabricated_event(free,stamp,status):
    assert await ingest(stamp=stamp)==status
    assert not free.store.events and free.ledger.records
    assert next(iter(free.ledger.records.values()))["status"]==status


@pytest.mark.asyncio
async def test_large_report_is_explicitly_retained_not_published(free):
    assert await ingest(text="x"*13000)=="input_too_large"
    receipt=next(iter(free.ledger.records.values()))
    assert receipt["report"]["raw_text_truncated"] is True
    assert len(receipt["report"]["raw_text"])==12000
    assert not free.store.events


def test_reports_mode_never_expands_to_all_inherited_channels(monkeypatch):
    monkeypatch.setattr(tg.settings,"telegram_processing_mode","reports")
    monkeypatch.setattr(tg.settings,"telegram_channels","")
    assert tg._get_channels()==[]
    monkeypatch.setattr(tg.settings,"telegram_channels",",".join("public_"+str(i) for i in range(6)))
    with pytest.raises(ValueError):tg._get_channels()
    monkeypatch.setattr(tg.settings,"telegram_channels","https://t.me/private")
    with pytest.raises(ValueError):tg._get_channels()


@pytest.mark.asyncio
async def test_initial_backfill_is_bounded_and_chronological(free,monkeypatch):
    monkeypatch.setattr(tg,"_get_checkpoint",AsyncMock(return_value=0))
    client=MagicMock()
    requested=[]
    async def messages(entity,**kwargs):
        requested.append(kwargs)
        for i in (8,7,6,5,4):yield SimpleNamespace(id=i,text=RAW+str(i),date=STAMP)
    client.iter_messages=messages
    assert await tg._backfill_reports(client,SimpleNamespace(username="fixture_public"),STAMP)==3
    assert requested==[{"limit":3}]
    assert [row.telegram_message_id for row in free.store.events]==[6,7,8]


@pytest.mark.asyncio
async def test_incremental_backfill_uses_cursor_and_hard_budget(free,monkeypatch):
    monkeypatch.setattr(tg,"_get_checkpoint",AsyncMock(return_value=50))
    requested=[]
    async def messages(entity,**kwargs):
        requested.append(kwargs)
        for i in range(51,100):yield SimpleNamespace(id=i,text=RAW+str(i),date=STAMP)
    client=SimpleNamespace(iter_messages=messages)
    assert await tg._backfill_reports(client,SimpleNamespace(username="fixture_public"),STAMP)==3
    assert requested==[{"limit":3,"min_id":50,"reverse":True}]
    assert [row.telegram_message_id for row in free.store.events]==[51,52,53]

"""FIRMS resource/freshness boundaries with synthetic CSV and HTTP responses."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import satellite_firms as firms


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(firms.settings,"firms_map_key","fixture-nasa-key")
    monkeypatch.setattr(firms.settings,"live_ingestion_enabled",True)
    for name,value in {"_last_hotspots":[],"_last_poll_ts":"","_last_fetch_status":"not_started",
        "_last_fetch_error":"","_last_poll_attempt_ts":"","_last_fetch_success_ts":"",
        "_last_processing_error":"","_association_truncated":False,"_poll_in_progress":False}.items():
        monkeypatch.setattr(firms,name,value)


def csv(stamp=None, rows=1):
    stamp=stamp or datetime.now(timezone.utc)-timedelta(hours=1)
    header="latitude,longitude,acq_date,acq_time,frp,confidence,satellite,instrument\n"
    return header + "".join(f"35,50,{stamp:%Y-%m-%d},{stamp:%H%M},90,n,N20,VIIRS\n" for _ in range(rows))


def mock_http(monkeypatch, handler):
    original=httpx.AsyncClient
    monkeypatch.setattr(firms.httpx,"AsyncClient",lambda **kw:original(transport=httpx.MockTransport(handler),**kw))


@pytest.mark.asyncio
async def test_disabled_key_never_requests_provider(state, monkeypatch):
    monkeypatch.setattr(firms.settings,"firms_map_key","")
    forbidden=AsyncMock(side_effect=AssertionError("unconfigured network call"))
    monkeypatch.setattr(firms.httpx,"AsyncClient",forbidden)
    assert await firms._fetch_firms_hotspots() is None
    assert firms.get_firms_status()["status"] == "disabled"
    forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_firms_http_info_logs_redact_key_path(state, monkeypatch, caplog):
    caplog.set_level(logging.INFO,logger="httpx")
    mock_http(monkeypatch,lambda request:httpx.Response(200,text=csv()))
    rows=await firms._fetch_firms_hotspots()
    assert len(rows)==1
    assert "fixture-nasa-key" not in caplog.text
    assert "[REDACTED]" in caplog.text
    assert firms._last_fetch_status == "ok" and firms._last_fetch_success_ts
    assert rows[0]["raw_row"]["confidence"] == "n"


@pytest.mark.asyncio
@pytest.mark.parametrize("body,headers", [("x"*2048,{}),(csv(),{"content-length":"5000"})])
async def test_response_byte_limit_fails_without_replacing_cache(state, monkeypatch, body, headers):
    monkeypatch.setattr(firms,"MAX_RESPONSE_BYTES",1024)
    firms._last_poll_ts="2026-10-28T12:00:00+00:00"
    mock_http(monkeypatch,lambda request:httpx.Response(200,text=body,headers=headers))
    assert await firms._fetch_firms_hotspots() is None
    assert firms._last_fetch_error == "ValueError"
    assert firms._last_poll_ts == "2026-10-28T12:00:00+00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize("delta", [timedelta(days=1),timedelta(days=-30)])
async def test_out_of_window_sensor_clock_fails(state, monkeypatch, delta):
    mock_http(monkeypatch,lambda request:httpx.Response(200,text=csv(datetime.now(timezone.utc)+delta)))
    assert await firms._fetch_firms_hotspots() is None
    assert firms._last_fetch_status == "error"


def test_csv_row_budget_fails_whole_snapshot(state, monkeypatch):
    monkeypatch.setattr(firms,"MAX_CSV_ROWS",1)
    with pytest.raises(ValueError,match="row limit"):
        firms._parse_firms_csv(csv(rows=2))


@pytest.mark.asyncio
async def test_processing_failure_retains_cache_and_reports_failure(state, monkeypatch):
    firms._last_poll_ts="2026-10-28T12:00:00+00:00"
    firms._last_hotspots=[{"ts":datetime(2026,10,28,12,tzinfo=timezone.utc)}]
    monkeypatch.setattr(firms,"_fetch_firms_hotspots",AsyncMock(return_value=[]))
    monkeypatch.setattr(firms,"_cross_reference_events",AsyncMock(side_effect=RuntimeError("database unavailable")))
    with pytest.raises(RuntimeError):
        await firms.poll_firms_once()
    assert firms._last_poll_ts == "2026-10-28T12:00:00+00:00"
    assert len(firms._last_hotspots) == 1
    assert firms.get_firms_status()["status"] == "failed"
    assert firms.get_firms_status()["error_type"] == "RuntimeError"
    assert firms._poll_in_progress is False


@pytest.mark.asyncio
async def test_overlapping_poll_does_not_duplicate_provider_work(state, monkeypatch):
    entered=asyncio.Event()
    release=asyncio.Event()
    async def fetch():
        entered.set()
        await release.wait()
        return []
    provider=AsyncMock(side_effect=fetch)
    monkeypatch.setattr(firms,"_fetch_firms_hotspots",provider)
    first=asyncio.create_task(firms.poll_firms_once())
    await entered.wait()
    await firms.poll_firms_once()
    assert provider.await_count==1
    release.set()
    await first
    assert firms._poll_in_progress is False


def test_freshness_keeps_sensor_and_cache_clock_distinct(state):
    now=datetime.now(timezone.utc)
    firms._last_poll_ts=now.isoformat()
    firms._last_hotspots=[{"ts":now-timedelta(days=3)}]
    current=firms.get_firms_status()
    assert current["status"]=="ok" and current["cache_age_seconds"]<1
    assert current["observations_stale"] is True
    assert current["observation_age_seconds"]>=3*86400
    firms._last_fetch_status="error"
    firms._last_fetch_error="HTTPStatusError"
    assert firms.get_firms_status()["status"]=="failed"


@pytest.mark.asyncio
async def test_thermal_observation_persists_unscored_and_delivers_once(state, monkeypatch):
    from test_ingestion_integration import EventStore
    store=EventStore()
    delivery=AsyncMock()
    monkeypatch.setattr(firms,"async_session",store.session)
    monkeypatch.setattr(firms.broadcaster,"broadcast",delivery)
    rows=firms._parse_firms_csv(csv())
    assert await firms._ingest_new_anomaly_events(rows)==1
    assert len(store.events)==1
    event=store.events[0]
    assert event.severity==0 and event.event_type=="thermal_anomaly"
    assert event.source_reliability is None and event.confirmed_networks==""
    assert event.reports[0]["sensor_record"]["instrument"] == "VIIRS"
    assert len(event.reports[0]["sensor_record_sha256"]) == 64
    assert '"status":"sensor_observation"' in delivery.await_args.args[0]
    assert '"severity":0' in delivery.await_args.args[0]
    assert await firms._ingest_new_anomaly_events(rows)==0
    assert delivery.await_count==1

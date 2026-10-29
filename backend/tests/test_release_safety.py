import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from app.config import Settings, settings
from app.main import app
from app.models import Event, SourceReport, Base
from app.services.ingest_ledger import report_identity
from app.services.opensky import _classify_aircraft, _detect_jamming
from app.services.runtime import Runtime
from app.services import geocoder


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "live_ingestion_enabled", False)
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "admin_api_key", "")
    # No lifespan: database is intentionally not available in these API boundary tests.
    return TestClient(app)


def test_admin_write_routes_fail_closed(client):
    for path, method in [('/sitreps/generate', 'post'), ('/satellite/poll', 'post'),
                         ('/events/admin/purge-old', 'delete'), ('/events/admin/dedup', 'delete'),
                         ('/events/admin/backfill', 'post'), ('/events/admin/fix-null-coords', 'post'),
                         ('/events/admin/import-osint-dataset', 'post')]:
        response = getattr(client, method)(path)
        assert response.status_code == 503, (path, response.text)


def test_admin_wrong_key_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "fixture-only-not-a-real-secret")
    for key in ['', 'incorrect']:
        response = client.post('/sitreps/generate', headers={'X-Admin-Key': key})
        assert response.status_code == 403


def test_correct_key_does_not_enable_paid_calls(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "fixture-only")
    monkeypatch.setattr(settings, "enable_sitrep_generation", False)
    response = client.post('/sitreps/generate', headers={'X-Admin-Key': 'fixture-only'})
    assert response.status_code == 503


def test_public_config_does_not_serialize_secrets(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "not-public")
    response = client.get('/config')
    assert response.status_code == 200
    assert 'not-public' not in response.text
    assert 'api_key' not in response.text
    assert response.json()['live_ingestion_enabled'] is False


def test_replay_interval_validation_without_database(client):
    cases = [('bad', 'bad'), ('2026-01-01', '2026-01-02'),
             ('2026-01-02T00:00:00Z', '2026-01-01T00:00:00Z'),
             ('2026-01-01T00:00:00Z', '2026-03-01T00:00:00Z')]
    for start, end in cases:
        assert client.get('/tracking/snapshots', params={'start': start, 'end': end}).status_code == 422


def test_source_identity_scopes_channel_and_content_revision():
    original = {'source':'telegram', 'channel_name':'a', 'telegram_message_id':42, 'raw_text':'source text'}
    assert report_identity(original) == report_identity(dict(original))
    assert report_identity(original)[0] != report_identity({**original, 'channel_name':'b'})[0]
    assert report_identity(original)[0] != report_identity({**original, 'raw_text':'correction'})[0]


def test_schema_keeps_channel_scoped_message_ids():
    from sqlalchemy.schema import CreateTable
    ddl = str(CreateTable(Event.__table__).compile(dialect=postgresql.dialect()))
    assert 'UNIQUE (source, channel_name, telegram_message_id)' in ddl
    assert 'UNIQUE (telegram_message_id)' not in ddl
    assert {'source_reports', 'usage_log', 'cost_config'} <= set(Base.metadata.tables)
    assert SourceReport.__table__.c.report.nullable is False


def test_national_icao_block_is_not_military_proof():
    category, _ = _classify_aircraft({'icao24':'738123', 'callsign':'CIVIL', 'type':'A320'})
    assert category != 'military'


def test_navigation_anomaly_never_claims_cause():
    states = [{'lat':30.1, 'lon':44.1, 'position_source':2},
              {'lat':30.12, 'lon':44.12, 'position_source':2}]
    result = _detect_jamming(states)
    assert result
    assert all(r['jamming_confirmed'] is False for r in result)


@pytest.mark.asyncio
async def test_geocoder_unknown_stays_unknown_and_no_default_network(monkeypatch):
    monkeypatch.setattr(settings, 'nominatim_url', '')
    assert await geocoder.geocode('Unknown') is None
    assert await geocoder.geocode('unresolvable-fixture-locality-123456') is None
    # "Iran" must not match inside a different word.
    assert await geocoder.geocode('Miranda-fixture-locality') is None


@pytest.mark.asyncio
async def test_worker_failure_is_not_healthy_and_does_not_leak_error_text():
    rt = Runtime()
    async def fail():
        raise ValueError('private provider URL or token')
    rt.start('fixture', fail())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    snapshot = rt.snapshot()
    assert snapshot['workers']['fixture']['state'] == 'failed'
    assert 'private provider' not in str(snapshot)
    await rt.stop()


def test_all_declared_admin_operations_have_security_dependency():
    spec = app.openapi()
    for path, operations in spec['paths'].items():
        for method, operation in operations.items():
            if method in {'post','delete','put','patch'}:
                assert any(p.get('in') == 'header' and p['name'].lower() == 'x-admin-key'
                           for p in operation.get('parameters', [])), (path, method)


def test_event_cursor_rejects_ambiguous_dates_before_database(client):
    for params in ({"before_id":42}, {"after":"2026-10-01T00:00:00"},
                   {"after":"2026-10-02T00:00:00Z", "before":"2026-10-01T00:00:00Z"}):
        assert client.get("/events",params=params).status_code == 422


def test_server_maps_key_is_hidden_unless_explicitly_enabled(client, monkeypatch):
    monkeypatch.setattr(settings,"google_maps_browser_key","fixture_browser_key")
    monkeypatch.setattr(settings,"google_earth_enabled",False)
    result=client.get("/config").json()
    assert result["google_earth_enabled"] is False and result["google_maps_browser_key"] == ""


def test_explicit_public_maps_key_never_exposes_backend_credentials(client, monkeypatch):
    monkeypatch.setattr(settings,"google_maps_browser_key","fixture_browser_key")
    monkeypatch.setattr(settings,"google_earth_enabled",True)
    monkeypatch.setattr(settings,"anthropic_api_key","fixture_private_model_credential")
    monkeypatch.setattr(settings,"telegram_session","fixture_private_session_credential")
    monkeypatch.setattr(settings,"admin_api_key","fixture_private_admin_credential")
    response=client.get("/config")
    assert response.json()["google_maps_browser_key"] == "fixture_browser_key"
    assert response.json()["google_earth_enabled"] is True
    for value in (settings.anthropic_api_key,settings.telegram_session,settings.admin_api_key):
        assert value not in response.text


def test_enabled_maps_without_key_stays_unconfigured(client, monkeypatch):
    monkeypatch.setattr(settings,"google_maps_browser_key","")
    monkeypatch.setattr(settings,"google_earth_enabled",True)
    assert client.get("/config").json()["google_earth_enabled"] is False

import asyncio
import socket
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import main
from app.config import settings
from app.services import public_observations as pub

NOW = datetime(2026, 11, 6, 2, tzinfo=timezone.utc)
HEADER = 'latitude,longitude,acq_date,acq_time,frp,satellite,scan,track,confidence\n'
ROW = '29,44,2026-11-05,1900,25,N20,0.4,0.5,nominal\n'


def batch(raw=None, stamp=NOW):
    payload = pub.parse_nasa_csv(raw or (HEADER + ROW).encode(), stamp)
    identity = pub.digest({'source':pub.SOURCE,'published_at':stamp.isoformat(),'status':'ok','payload':payload})
    return SimpleNamespace(id=identity, source=pub.SOURCE, published_at=stamp, status='ok', payload=payload)


def test_source_pixels_retain_clocks_coordinates_provenance_without_private_fields():
    receipt = batch()
    output = pub.describe_batch(receipt, receipt, NOW)
    assert output['status'] == 'fresh' and output['batch_id'] == receipt.id
    pixel = output['hotspots'][0]
    assert (pixel['lat'], pixel['lon'], pixel['frp'], pixel['ts']) == (29,44,25,'2026-11-05T19:00:00+00:00')
    assert pixel['confidence_label'] == 'nominal'
    assert len(pixel['source_row_sha256']) == 64
    assert not {'raw_text','summary','proximity_matches','actor','severity','confirmed_networks'}.intersection(pixel)
    assert output['citation_url'].startswith('https://www.earthdata.nasa.gov/')


def test_acquisition_window_region_threshold_dedup_counts_are_explicit():
    raw = HEADER + ROW + ROW + '0,0,2026-11-05,1900,50,N20,0.4,0.5,high\n' + '29,44,2026-11-05,1800,2,N20,0.4,0.5,low\n' + '29,44,2026-11-02,1800,40,N20,0.4,0.5,high\n'
    payload = pub.parse_nasa_csv(raw.encode(),NOW)
    assert (payload['source_rows'],payload['regional_rows'],payload['duplicate_rows'],payload['filtered_rows']) == (5,4,1,2)
    assert len(payload['observations']) == 1


@pytest.mark.parametrize('row',[
    ROW.replace('29,','nan,',1), ROW.replace('44,','181,',1), ROW.replace(',25,',',-1,'),
    ROW.replace('1900','2500'), ROW.replace('N20','N21'), ROW.replace('2026-11-05','2026-11-07'),
    ROW.replace('0.4','nan'), ROW.replace('0.5','-1'), ROW.rstrip()+',extra\n',
])
def test_invalid_source_records_fail_the_batch_instead_of_fake_empty(row):
    with pytest.raises(ValueError): pub.parse_nasa_csv((HEADER+row).encode(),NOW)


def test_html_or_wrong_schema_is_not_a_successful_empty_source():
    with pytest.raises(ValueError): pub.parse_nasa_csv(b'<html>Unavailable</html>',NOW)
    empty = batch(HEADER.encode())
    assert pub.describe_batch(empty,empty,NOW)['status'] == 'empty'


def test_awaiting_failure_stale_and_expired_are_distinct():
    assert pub.describe_batch(None,None,NOW)['status'] == 'awaiting_publication'
    failed = SimpleNamespace(source=pub.SOURCE,status='failed',published_at=NOW,payload={})
    failed.id=pub.digest({'source':pub.SOURCE,'published_at':NOW.isoformat(),'status':'failed','payload':{}})
    assert pub.describe_batch(failed,None,NOW)['status'] == 'failed'
    good = batch()
    stale = pub.describe_batch(failed,good,NOW+timedelta(hours=13))
    assert stale['status']=='stale' and len(stale['hotspots'])==1 and stale['last_attempt_status']=='failed'
    expired = pub.describe_batch(failed,good,NOW+timedelta(hours=50))
    assert expired['status']=='stale' and expired['hotspots']==[]


def test_corrupt_digest_and_unapproved_fields_are_rejected():
    good = batch();good.payload['observations'][0]['lat']=30.0
    with pytest.raises(ValueError,match='integrity'): pub.describe_batch(good,good,NOW)
    good=batch();good.payload['private_report']='do not publish'
    with pytest.raises(ValueError): pub.describe_batch(good,good,NOW)


def test_conflicting_duplicate_pixel_fails_instead_of_first_wins():
    with pytest.raises(ValueError,match='Conflicting'):
        pub.parse_nasa_csv((HEADER+ROW+ROW.replace(',25,',',30,')).encode(),NOW)


def test_alternate_coordinate_format_cannot_hide_conflicting_pixel():
    alternate = ROW.replace('29,44,', '29.0,44.00,').replace(',25,', ',30,')
    with pytest.raises(ValueError, match='Conflicting'):
        pub.parse_nasa_csv((HEADER + ROW + alternate).encode(), NOW)
    original = pub.parse_nasa_csv((HEADER + ROW).encode(), NOW)['observations'][0]
    equivalent = pub.parse_nasa_csv((HEADER + ROW.replace('29,44,', '29.0,44.00,')).encode(), NOW)['observations'][0]
    assert original['id'] == equivalent['id']
    assert original['source_row_sha256'] != equivalent['source_row_sha256']
    distinct = batch((HEADER + ROW + ROW.replace('29,44,', '29.1,44,')).encode())
    assert len(pub.describe_batch(distinct, distinct, NOW)['hotspots']) == 2


@pytest.mark.parametrize('defect', ['spatial_time', 'id', 'counts'])
def test_digest_valid_older_writer_batch_still_requires_unique_consistent_pixels(defect):
    import copy
    row = batch()
    if defect == 'counts':
        row.payload['regional_rows'] += 1
    else:
        pixel = copy.deepcopy(row.payload['observations'][0])
        if defect == 'spatial_time':
            pixel['id'] = '0' * 64
            pixel['ts'] = '2026-11-05T14:00:00-05:00'
            pixel['frp'] = 30.0
        else:
            pixel['lat'] = 29.1
        row.payload['observations'].append(pixel)
        row.payload['regional_rows'] += 1
        row.payload['source_rows'] += 1
    row.id = pub.digest({'source':row.source,'published_at':row.published_at.isoformat(),'status':row.status,'payload':row.payload})
    with pytest.raises(ValueError, match='Duplicate|reconcile'):
        pub.describe_batch(row, row, NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize('name,value',[('public_read_only',True),('demo_mode',True),('live_ingestion_enabled',False),('public_observation_publisher_enabled',False)])
async def test_only_explicit_private_collector_can_publish(monkeypatch,name,value):
    for key,val in [('public_read_only',False),('demo_mode',False),('live_ingestion_enabled',True),('public_observation_publisher_enabled',True)]:monkeypatch.setattr(settings,key,val)
    monkeypatch.setattr(settings,name,value)
    fetch=AsyncMock();monkeypatch.setattr(pub,'fetch_nasa',fetch)
    with pytest.raises(ValueError): await pub.publish_once()
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_endpoint_is_separate_from_private_reports_even_when_legacy_switch_true(monkeypatch):
    monkeypatch.setattr(settings,'public_read_only',True);monkeypatch.setattr(settings,'public_reports_enabled',True);monkeypatch.setattr(settings,'demo_mode',False)
    read=AsyncMock(return_value={'status':'awaiting_publication','hotspots':[]});monkeypatch.setattr(pub,'read_public_observations',read)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://fixture') as client:
        assert (await client.get('/events')).status_code==503
        assert (await client.get('/publication/observations')).json()['status']=='awaiting_publication'
        head=await client.head('/publication/observations')
        assert head.status_code==200 and head.content==b''
        assert (await client.get('/publication/observations?source=private')).status_code==400
        response=await client.get('/publication/observations/download')
        assert response.status_code==200 and 'attachment' in response.headers['content-disposition']
    read.assert_awaited_with(download=True, batch_id=None)


def test_publication_openapi_operation_ids_are_unique_and_head_is_not_duplicated(monkeypatch):
    monkeypatch.setattr(main.app, 'openapi_schema', None)
    schema=main.app.openapi()
    ids=[operation['operationId'] for path in schema['paths'].values() for operation in path.values()
         if isinstance(operation,dict) and 'operationId' in operation]
    assert len(ids)==len(set(ids))
    for path,operations in schema['paths'].items():
        if path.startswith('/publication/'):
            assert 'get' in operations and 'head' not in operations


def publication_session(previous=None, *, locked=True, connection_error=None, commit_error=None):
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    transaction = AsyncMock()
    transaction.__aexit__.return_value = False
    transaction.__aexit__.side_effect = commit_error
    session.begin = Mock(return_value=transaction)
    session.execute.side_effect = connection_error or [
        SimpleNamespace(scalar_one=lambda: locked),
        SimpleNamespace(scalar_one_or_none=lambda: previous),
        None, None,
    ]
    return session, transaction


def configure_publisher(monkeypatch, sessions, *, fetch_error=None, sleeps=1):
    for name, value in [('public_read_only', False), ('demo_mode', False),
                        ('live_ingestion_enabled', True), ('public_observation_publisher_enabled', True)]:
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(pub, 'utcnow', lambda: NOW)
    factory = Mock(side_effect=sessions)
    fetch = AsyncMock(return_value=(HEADER + ROW).encode(), side_effect=fetch_error)
    sleep = AsyncMock(side_effect=[None] * (sleeps - 1) + [asyncio.CancelledError()])
    monkeypatch.setattr(pub, 'async_session', factory)
    monkeypatch.setattr(pub, 'fetch_nasa', fetch)
    monkeypatch.setattr(pub.asyncio, 'sleep', sleep)
    return factory, fetch, sleep


@pytest.mark.asyncio
@pytest.mark.parametrize('error_type', [SQLAlchemyError, socket.gaierror])
@pytest.mark.parametrize('previous', [None, NOW])
async def test_database_recovery_is_prompt_and_stored_due_gate_prevents_refetch(monkeypatch, error_type, previous):
    failed, failed_transaction = publication_session(connection_error=error_type('fixture database unavailable'))
    recovered, recovered_transaction = publication_session(previous=previous)
    factory, fetch, sleep = configure_publisher(monkeypatch, [failed, recovered], sleeps=2)
    with pytest.raises(asyncio.CancelledError):
        await pub.start_public_observation_publisher()
    assert sleep.await_args_list == [call(30), call(30 if previous is not None else 3 * 3600)]
    assert factory.call_count == 2
    failed_transaction.__aexit__.assert_awaited_once()
    recovered_transaction.__aexit__.assert_awaited_once()
    assert failed.execute.await_count == 1
    assert recovered.execute.await_count == (4 if previous is None else 2)
    assert fetch.await_count == (1 if previous is None else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('commit_visible', [True, False])
async def test_uncertain_commit_rechecks_persisted_cadence_before_another_fetch(monkeypatch, commit_visible):
    first, transaction = publication_session(commit_error=SQLAlchemyError('fixture commit outcome unknown'))
    recovered, _ = publication_session(previous=NOW if commit_visible else None)
    factory, fetch, sleep = configure_publisher(monkeypatch, [first, recovered], sleeps=2)
    with pytest.raises(asyncio.CancelledError):
        await pub.start_public_observation_publisher()
    transaction.__aexit__.assert_awaited_once_with(None, None, None)
    assert first.execute.await_count == 4 and factory.call_count == 2
    assert sleep.await_args_list == [call(30), call(30 if commit_visible else 3 * 3600)]
    # A lost commit response may already have persisted the attempt. A rollback
    # has no persisted due marker, so the bounded fetch can legitimately repeat.
    assert fetch.await_count == (1 if commit_visible else 2)


@pytest.mark.asyncio
@pytest.mark.parametrize('fetch_error', [httpx.ConnectError('fixture source unavailable'), OSError('fixture source socket')])
async def test_recorded_provider_failure_keeps_normal_three_hour_cadence(monkeypatch, fetch_error):
    session, transaction = publication_session()
    _, fetch, sleep = configure_publisher(monkeypatch, [session], fetch_error=fetch_error)
    with pytest.raises(asyncio.CancelledError):
        await pub.start_public_observation_publisher()
    fetch.assert_awaited_once()
    sleep.assert_awaited_once_with(3 * 3600)
    transaction.__aexit__.assert_awaited_once_with(None, None, None)
    recorded = session.execute.await_args_list[2].args[0].compile().params
    assert recorded['status'] == 'failed' and recorded['payload'] == {}


@pytest.mark.asyncio
async def test_advisory_ownership_contention_rechecks_without_fetching(monkeypatch):
    session, transaction = publication_session(locked=False)
    _, fetch, sleep = configure_publisher(monkeypatch, [session])
    with pytest.raises(asyncio.CancelledError):
        await pub.start_public_observation_publisher()
    assert session.execute.await_count == 1
    fetch.assert_not_awaited()
    sleep.assert_awaited_once_with(30)
    transaction.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_during', ['database', 'fetch'])
async def test_publisher_cancellation_unwinds_transaction_without_sleep_or_failure_record(monkeypatch, cancel_during):
    session, transaction = publication_session(
        connection_error=asyncio.CancelledError() if cancel_during == 'database' else None)
    _, fetch, sleep = configure_publisher(monkeypatch, [session],
        fetch_error=asyncio.CancelledError() if cancel_during == 'fetch' else None)
    with pytest.raises(asyncio.CancelledError):
        await pub.start_public_observation_publisher()
    sleep.assert_not_awaited()
    assert fetch.await_count == (cancel_during == 'fetch')
    assert session.execute.await_count == (2 if cancel_during == 'fetch' else 1)
    assert transaction.__aexit__.await_args.args[0] is asyncio.CancelledError
    assert session.__aexit__.await_args.args[0] is asyncio.CancelledError


@pytest.mark.asyncio
async def test_unexpected_publisher_error_keeps_existing_normal_delay(monkeypatch):
    _, _, sleep = configure_publisher(monkeypatch, [])
    attempt = AsyncMock(side_effect=ValueError('fixture unexpected publisher error'))
    monkeypatch.setattr(pub, 'publish_once', attempt)
    with pytest.raises(asyncio.CancelledError):
        await pub.start_public_observation_publisher()
    attempt.assert_awaited_once()
    sleep.assert_awaited_once_with(3 * 3600)


@pytest.mark.asyncio
@pytest.mark.parametrize('remaining_seconds', [0.1, 29.9])
async def test_near_due_attempt_rechecks_and_fetches_after_stored_deadline(monkeypatch, remaining_seconds):
    previous = NOW - timedelta(seconds=pub.POLL_SECONDS - remaining_seconds)
    early, early_transaction = publication_session(previous=previous)
    due, due_transaction = publication_session(previous=previous)
    _, fetch, _ = configure_publisher(monkeypatch, [early, due])
    current = [NOW]
    waits = []
    monkeypatch.setattr(pub, 'utcnow', lambda: current[0])

    async def advance_or_stop(seconds):
        waits.append(seconds)
        if len(waits) == 1:
            # The real stored due check executes again against this changed clock.
            assert early.execute.await_count == 2
            fetch.assert_not_awaited()
            current[0] += timedelta(seconds=seconds)
            return
        raise asyncio.CancelledError()

    monkeypatch.setattr(pub.asyncio, 'sleep', advance_or_stop)
    with pytest.raises(asyncio.CancelledError):
        await pub.start_public_observation_publisher()
    assert waits == [30, 3 * 3600]
    assert (current[0] - previous).total_seconds() >= pub.POLL_SECONDS
    fetch.assert_awaited_once()
    assert early.execute.await_count == 2 and due.execute.await_count == 4
    early_transaction.__aexit__.assert_awaited_once_with(None, None, None)
    due_transaction.__aexit__.assert_awaited_once_with(None, None, None)
    recorded = due.execute.await_args_list[2].args[0].compile().params
    assert recorded['status'] == 'ok' and recorded['published_at'] == current[0]


@pytest.mark.asyncio
async def test_recent_committed_attempt_rechecks_without_early_provider_requests(monkeypatch):
    first, _ = publication_session(previous=NOW)
    second, _ = publication_session(previous=NOW)
    _, fetch, _ = configure_publisher(monkeypatch, [first, second])
    current = [NOW]
    waits = []
    monkeypatch.setattr(pub, 'utcnow', lambda: current[0])

    async def advance_or_stop(seconds):
        waits.append(seconds)
        if len(waits) == 1:
            current[0] += timedelta(seconds=seconds)
            return
        raise asyncio.CancelledError()

    monkeypatch.setattr(pub.asyncio, 'sleep', advance_or_stop)
    with pytest.raises(asyncio.CancelledError):
        await pub.start_public_observation_publisher()
    assert waits == [30, 30]
    assert first.execute.await_count == second.execute.await_count == 2
    fetch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('holder_committed', [True, False])
async def test_contended_owner_recheck_reads_committed_cadence_before_fetch(monkeypatch, holder_committed):
    locked, transaction = publication_session(locked=False)
    acquired, _ = publication_session(previous=NOW if holder_committed else None)
    _, fetch, sleep = configure_publisher(monkeypatch, [locked, acquired], sleeps=2)
    with pytest.raises(asyncio.CancelledError):
        await pub.start_public_observation_publisher()
    assert sleep.await_args_list == [call(30), call(30 if holder_committed else 3 * 3600)]
    assert locked.execute.await_count == 1
    assert acquired.execute.await_count == (2 if holder_committed else 4)
    assert fetch.await_count == (0 if holder_committed else 1)
    transaction.__aexit__.assert_awaited_once_with(None, None, None)

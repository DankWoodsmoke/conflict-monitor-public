"""Independent observation must fail for tampering, stale data or private fields."""
import copy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('publication_observer', Path(__file__).resolve().parents[2] / 'tools/observe_publication.py')
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)

NOW = datetime(2026, 11, 6, 2, 40, tzinfo=timezone.utc)


def thermal():
    return {'source': 'nasa_firms_noaa20', 'status': 'fresh', 'batch_id': 'a' * 64,
            'citation_url': 'https://www.earthdata.nasa.gov/', 'disclaimer_url': 'https://nrt4.modaps.eosdis.nasa.gov/',
            'displayed_count': 1, 'hotspots': [{'id': 'b' * 64, 'lat': 25.0, 'lon': 50.0, 'frp': 12,
                'ts': NOW.isoformat(), 'satellite': 'NOAA-20', 'instrument': 'VIIRS'}]}


def aircraft():
    return {'source': 'adsb_lol', 'status': 'fresh', 'batch_id': 'c' * 64, 'coverage': [1, 2, 3, 4],
            'license': 'ODbL-1.0', 'attribution': 'Attributed fixture',
            'aircraft': [{'icao24': '123abc', 'lat': 25.0, 'lon': 50.0, 'source': 'adsb.lol',
                'origin_country': '', 'observed_at': NOW.isoformat()}]}


@pytest.mark.parametrize('kind,fixture', [('observations', thermal), ('aircraft', aircraft)])
def test_current_bounded_attributed_dataset_is_observable(kind, fixture):
    value = fixture()
    assert subject.validate_display(kind, value, NOW) == (value['batch_id'], 1)


@pytest.mark.parametrize('defect', ['nan', 'bool_coordinate', 'old_clock', 'wrong_source', 'private_text', 'duplicate', 'stale_status'])
@pytest.mark.parametrize('kind,fixture,key,clock_field', [('observations', thermal, 'hotspots', 'ts'), ('aircraft', aircraft, 'aircraft', 'observed_at')])
def test_invalid_positions_or_publication_boundaries_cannot_qualify(kind, fixture, key, clock_field, defect):
    value = fixture()
    row = value[key][0]
    if defect == 'nan':
        row['lat'] = float('nan')
    elif defect == 'bool_coordinate':
        row['lon'] = True
    elif defect == 'old_clock':
        row[clock_field] = (NOW - timedelta(days=3)).isoformat()
    elif defect == 'wrong_source':
        value['source'] = 'telegram'
    elif defect == 'private_text':
        row['raw_text'] = 'private fixture'
    elif defect == 'duplicate':
        value[key].append(copy.deepcopy(row))
    else:
        value['status'] = 'stale'
    with pytest.raises(ValueError):
        subject.validate_display(kind, value, NOW)


def test_download_is_bound_to_exact_displayed_identity_and_content():
    core = {'source': 'adsb_lol', 'published_at': NOW.isoformat(), 'status': 'ok', 'payload': {'aircraft': []}}
    identifier = sha256(subject.canonical(core)).hexdigest()
    value = {**core, 'batch_id': identifier}
    assert subject.verify_download(value, identifier, 'adsb_lol') == core
    for damaged in [{**value, 'batch_id': '0' * 64}, {**value, 'source': 'other_source'},
                    {**value, 'payload': {'aircraft': ['changed']}}, {**value, 'status': 'failed'}]:
        with pytest.raises(ValueError):
            subject.verify_download(damaged, identifier, 'adsb_lol')


def test_naive_clock_cannot_be_treated_as_a_known_observation_time():
    with pytest.raises(ValueError, match='Timezone'):
        subject.clock('2026-11-06T02:40:00')


def test_different_public_ids_cannot_hide_equivalent_thermal_position_time():
    value=thermal()
    value['hotspots'].append({**value['hotspots'][0], 'id':'d'*64, 'ts':'2026-11-05T21:40:00-05:00', 'frp':30})
    value['displayed_count']=2
    with pytest.raises(ValueError, match='position/time'):
        subject.validate_display('observations',value,NOW)


def test_repeated_edge_and_app_no_store_headers_must_remain_consistent():
    from httpx import Headers
    assert subject.no_store_headers(Headers({'cache-control': 'no-store'}))
    assert subject.no_store_headers(Headers([('cache-control', 'no-store'), ('Cache-Control', 'no-store')]))
    for headers in (Headers(), Headers({'cache-control': 'public'}),
                    Headers([('cache-control', 'no-store'), ('cache-control', 'max-age=60')]),
                    Headers({'cache-control': 'no-store, public'})):
        assert not subject.no_store_headers(headers)


def projection(kind):
    value = thermal() if kind == 'observations' else aircraft()
    value['published_at'] = NOW.isoformat()
    rows = copy.deepcopy(value['hotspots' if kind == 'observations' else 'aircraft'])
    if kind == 'observations':
        payload = {'observations': rows, 'source_rows': 5, 'regional_rows': 1,
                   'filtered_rows': 0, 'duplicate_rows': 0, 'response_sha256': 'd' * 64,
                   'received_at': NOW.isoformat()}
        value.update({key: item for key, item in payload.items() if key != 'observations'}, eligible_count=1)
    else:
        payload = {'aircraft': rows, 'source_records': 1, 'filtered_records': 0,
                   'provider_snapshot_at': NOW.isoformat()}
        value.update({key: item for key, item in payload.items() if key != 'aircraft'})
    return value, {'source': value['source'], 'published_at': NOW.isoformat(), 'status': 'ok', 'payload': payload}


@pytest.mark.parametrize('kind', ['observations', 'aircraft'])
def test_every_displayed_record_is_bound_to_its_downloaded_packet(kind):
    value, core = projection(kind)
    subject.verify_display_projection(kind, value, core, NOW, NOW + timedelta(milliseconds=50))
    rows = 'hotspots' if kind == 'observations' else 'aircraft'
    value[rows][0]['lat'] += 0.01  # Still valid geography; same source and batch ID.
    subject.validate_display(kind, value, NOW)
    with pytest.raises(ValueError, match='differs from immutable packet'):
        subject.verify_display_projection(kind, value, core, NOW, NOW)


@pytest.mark.parametrize('kind', ['observations', 'aircraft'])
@pytest.mark.parametrize('defect', ['omitted_row', 'changed_provenance', 'changed_publication_time'])
def test_valid_looking_incomplete_or_misattributed_projection_cannot_pass(kind, defect):
    value, core = projection(kind)
    if defect == 'omitted_row':
        value['hotspots' if kind == 'observations' else 'aircraft'] = []
        if kind == 'observations':
            value.update(displayed_count=0, eligible_count=0)
    elif defect == 'changed_provenance':
        value['source_rows' if kind == 'observations' else 'source_records'] += 1
    else:
        value['published_at'] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):
        subject.verify_display_projection(kind, value, core, NOW, NOW)


def test_thermal_selection_must_use_declared_order_and_count():
    value, core = projection('observations')
    second = {**core['payload']['observations'][0], 'id': 'e' * 64, 'frp': 20}
    core['payload']['observations'].append(second)
    value.update(eligible_count=2, displayed_count=2)
    value['hotspots'].append(copy.deepcopy(second))
    with pytest.raises(ValueError, match='timed projection'):
        subject.verify_display_projection('observations', value, core, NOW, NOW)
    value['hotspots'].reverse()
    subject.verify_display_projection('observations', value, core, NOW, NOW)


def test_position_expiring_during_request_has_a_valid_bounded_projection():
    value, core = projection('aircraft')
    stamp = (NOW - timedelta(seconds=119.9)).isoformat()
    value['aircraft'][0]['observed_at'] = stamp
    core['payload']['aircraft'][0]['observed_at'] = stamp
    subject.verify_display_projection('aircraft', value, core, NOW, NOW + timedelta(seconds=.2))
    value['aircraft'] = []
    value['status'] = 'empty'
    subject.verify_display_projection('aircraft', value, core, NOW, NOW + timedelta(seconds=.2))
    with pytest.raises(ValueError, match='clock window'):
        subject.verify_display_projection('aircraft', value, core, NOW, NOW + timedelta(seconds=31))


def test_final_delay_cannot_escape_gap_check_when_loop_has_ended():
    assert subject.final_sample_gap(14400.05, 14370.0) == pytest.approx(30.05)
    for elapsed, previous in [(14430, 14300), (14400, None), (1, 2)]:
        with pytest.raises(ValueError, match='Final observation gap'):
            subject.final_sample_gap(elapsed, previous)

"""Guard the exported reader gate against silently re-admitting old surfaces."""
import gzip
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('public_reader_gate', ROOT / 'tools/verify_public_readers.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def config():
    return {'public_read_only': True, 'public_observations_enabled': True, 'public_aircraft_enabled': True,
            **{key: False for key in ('public_reports_enabled', 'public_tracking_enabled', 'public_media_enabled',
                'generation_enabled', 'video_generation_enabled', 'local_ai_enabled')}}


def test_closed_public_capabilities_are_accepted():
    gate.capabilities(config())


@pytest.mark.parametrize('key', ['public_reports_enabled', 'public_tracking_enabled', 'public_media_enabled',
                                'generation_enabled', 'video_generation_enabled', 'local_ai_enabled'])
def test_retired_flags_and_private_controls_fail_gate(key):
    value = config()
    value[key] = True
    with pytest.raises(ValueError):
        gate.capabilities(value)


def test_missing_closed_flag_is_not_equivalent_to_false():
    value = config()
    del value['public_reports_enabled']
    with pytest.raises(ValueError):
        gate.capabilities(value)


def test_gzip_roundtrip_and_expansion_bound(monkeypatch):
    body = b'authored public JSON ' * 40
    assert gate.decode_body(gzip.compress(body), 'gzip') == body
    assert gate.decode_body(body, 'identity') == body
    monkeypatch.setattr(gate, 'MAX_BYTES', 64)
    with pytest.raises(ValueError):
        gate.decode_body(gzip.compress(b'a'*1000), 'gzip')


def test_unrecognized_encoding_fails_instead_of_skipping_check():
    with pytest.raises(ValueError):
        gate.decode_body(b'anything', 'br')


@pytest.mark.parametrize('headers', [
    {'Cache-Control': 'public,max-age=60', 'X-Content-Type-Options': 'nosniff'},
    {'Cache-Control': 'no-store'},
    {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Set-Cookie': 'unexpected'},
])
def test_public_cache_credential_and_security_policy(headers):
    import httpx
    with pytest.raises(ValueError):
        gate.public_headers(httpx.Headers(headers))


def test_identical_app_and_nginx_headers_are_accepted_but_conflicts_rejected():
    import httpx
    headers = httpx.Headers([('cache-control','no-store'),('cache-control','no-store'),
                            ('x-content-type-options','nosniff'),('x-content-type-options','nosniff')])
    gate.public_headers(headers)
    headers['x-content-type-options'] = 'nosniff, unsafe'
    with pytest.raises(ValueError):
        gate.public_headers(headers)


def fixture_tool():
    spec = importlib.util.spec_from_file_location('public_profile_fixture', ROOT / 'tools/verify_public_profile_ci.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_config():
    project = 'cm-public-ci-' + 'a'*16
    return project, {'volumes': {'pgdata17_36_alpine': {'name':project+'_pgdata17_36_alpine'}},
        'services': {'db': {'volumes': [{'type':'volume','source':'pgdata17_36_alpine','target':'/var/lib/postgresql/data'}]}}}


def test_fixture_values_override_host_secrets_ports_and_project():
    module = fixture_tool()
    inherited = {'POSTGRES_PASSWORD':'private', 'POSTGRES_APP_PASSWORD':'private2',
                 'POSTGRES_PUBLIC_PASSWORD':'private3', 'PUBLIC_FRONTEND_PORT':'443', 'COMPOSE_PROJECT_NAME':'production', 'PATH':'retain'}
    fixture = {key:'authored_fixture' for key in inherited if key != 'PATH'}
    actual = module.fixture_environment(fixture, inherited)
    assert all(actual[key] == value for key,value in fixture.items())
    assert actual['PATH'] == 'retain' and inherited['POSTGRES_PASSWORD'] == 'private'


@pytest.mark.parametrize('mutation', ['external','explicit_name','driver_bind','anonymous','bind_database'])
def test_unowned_resolved_volumes_rejected_before_start_or_cleanup(mutation):
    module = fixture_tool();project,value=fixture_config()
    volume=value['volumes']['pgdata17_36_alpine'];mount=value['services']['db']['volumes'][0]
    if mutation=='external':volume['external']=True
    elif mutation=='explicit_name':volume['name']='production-database'
    elif mutation=='driver_bind':volume['driver_opts']={'device':'/existing/data'}
    elif mutation=='anonymous':mount.pop('source')
    else:mount.update(type='bind',source='/existing/data')
    with pytest.raises(ValueError):module.admit_volumes(value,project)


@pytest.mark.parametrize('mutation', ['wrong_label','foreign_mount','wrong_database_mount'])
def test_runtime_volume_mismatch_refuses_cleanup(mutation):
    module=fixture_tool();project,value=fixture_config();allowed=module.admit_volumes(value,project)
    name=project+'_pgdata17_36_alpine'
    volumes=[{'Name':name,'Labels':{'com.docker.compose.project':project,'com.docker.compose.volume':'pgdata17_36_alpine'}}]
    containers=[{'Config':{'Labels':{'com.docker.compose.project':project,'com.docker.compose.service':'db'}},
        'Mounts':[{'Type':'volume','Name':name,'Destination':'/var/lib/postgresql/data'}]}]
    module.admit_runtime_mounts(containers,volumes,project,allowed)
    if mutation=='wrong_label':volumes[0]['Labels']['com.docker.compose.project']='production'
    elif mutation=='foreign_mount':containers[0]['Mounts'][0]['Name']='production-volume'
    else:containers[0]['Mounts'][0].update(Type='bind',Source='/production')
    with pytest.raises(ValueError):module.admit_runtime_mounts(containers,volumes,project,allowed)


def test_recovery_allows_only_database_restart_not_changed_app_identity():
    module=fixture_tool()
    before={name:{'Id':name+'-id','Image':name+'-image','State':{'StartedAt':'before','Running':True}}
            for name in ['db','backend','reader','frontend','publicfrontend']}
    after=copy.deepcopy(before);after['db']['State']['StartedAt']='after'
    assert module.recovery_identity_unchanged(before,after)
    for service in ['backend','reader','frontend','publicfrontend']:
        changed=copy.deepcopy(after);changed[service]['State']['StartedAt']='after'
        assert not module.recovery_identity_unchanged(before,changed)
    for field in ['Id','Image']:
        changed=copy.deepcopy(after);changed['db'][field]='replacement'
        assert not module.recovery_identity_unchanged(before,changed)


def test_old_success_cannot_prove_post_restart_publication_recovery():
    module=fixture_tool();restart=datetime(2026,11,6,3,tzinfo=timezone.utc)
    row={'operator':{'http':200,'status':'healthy','database':'connected'},
         'reader':{'http':200,'status':'healthy'},'worker':{'state':'running'},
         'delivery':{'status':'ok','last_success_at':(restart-timedelta(microseconds=1)).isoformat()}}
    assert not module.publication_recovered(row,restart.isoformat())
    row['delivery']['last_success_at']=(restart+timedelta(microseconds=1)).isoformat()
    assert module.publication_recovered(row,restart.isoformat())
    row['worker']['state']='failed'
    assert not module.publication_recovered(row,restart.isoformat())
    row['worker']['state']='running';row['reader']['http']=503
    assert not module.publication_recovered(row,restart.isoformat())

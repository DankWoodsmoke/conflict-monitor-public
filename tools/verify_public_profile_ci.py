"""Disposable authored-publication Compose gate; never calls a live provider.

Uses the shipped publisher topology with collection explicitly disabled, seeds
authored records through the restricted writer, then tests the actual public
reader role and nginx boundary. No Google key, source credential or tunnel.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]


async def seed():
    from app.config import settings
    from app.db import async_session, engine
    from app.models import PublicAircraftBatch, PublicObservationBatch
    from app.services import public_aircraft as aircraft, public_observations as thermal
    from app.services.opensky import normalize_adsb
    parsed = urlsplit(os.environ.get('DATABASE_URL', ''))
    if (parsed.username != 'monitor' or parsed.hostname != 'db' or parsed.path != '/conflict_monitor_test'
            or settings.live_ingestion_enabled or settings.demo_mode or settings.public_read_only
            or settings.public_observation_publisher_enabled or settings.public_aircraft_publisher_enabled):
        raise ValueError('Authored seed requires the isolated non-collecting writer fixture')
    now = datetime.now(timezone.utc)
    observed = now - timedelta(minutes=1)
    header = 'latitude,longitude,acq_date,acq_time,frp,satellite,scan,track,confidence\n'
    raw = header + ''.join(f'{29+i/1000},{44+i/1000},{observed:%Y-%m-%d},{observed:%H%M},25,N20,0.4,0.5,nominal\n' for i in range(32))
    payload = thermal.parse_nasa_csv(raw.encode(), now)
    rows = normalize_adsb({'now': now.timestamp()*1000, 'ac': [
        {'hex': f'{0xabc100+i:06x}', 'lat': 29+i/1000, 'lon': 44+i/1000, 'seen_pos': 10,
         'flight': 'CI FIXTURE', 'alt_baro': 10000, 'gs': 300, 'track': 0, 'category': 'A3'}
        for i in range(32)]}, received=now.timestamp())['states']
    planes = aircraft.prepare_snapshot(rows, {'source': 'adsb.lol', 'status': 'ok', 'source_timestamp': now.isoformat()}, now)
    identities = {}
    try:
        async with async_session() as session:
            async with session.begin():
                for kind, model, source, value in (
                    ('observations', PublicObservationBatch, thermal.SOURCE, payload),
                    ('aircraft', PublicAircraftBatch, aircraft.SOURCE, planes),
                ):
                    identity = thermal.digest({'source': source, 'published_at': now.isoformat(), 'status': 'ok', 'payload': value})
                    session.add(model(id=identity, source=source, published_at=now, status='ok', payload=value))
                    identities[kind] = identity
        print(json.dumps({'status': 'PASS', 'authored_fixture': True, 'provider_requests': 0, 'batch_ids': identities}))
    finally:
        await engine.dispose()


def run(command, *, timeout=90, env=None):
    result = subprocess.run(command, capture_output=True, timeout=timeout, env=env)
    if result.returncode:
        raise RuntimeError('Fixture operation failed; credentials and arbitrary subprocess output withheld')
    return result.stdout.decode('utf8').strip()


def fixture_environment(values, inherited=None):
    # --env-file alone does not override shell variables in Compose expansion.
    return {**(os.environ if inherited is None else inherited), **values}


def admit_volumes(config, project):
    if not re.fullmatch(r'cm-public-ci-[0-9a-f]{16}', project):
        raise ValueError('Unexpected fixture project identity')
    allowed = {}
    for key, value in config.get('volumes', {}).items():
        if (key not in {'pgdata17_36_alpine', 'briefing_data'} or value.get('external')
                or value.get('name') != project+'_'+key or value.get('driver_opts')):
            raise ValueError('Resolved volume is not exclusively owned by this fixture')
        allowed[project+'_'+key] = key
    if project+'_pgdata17_36_alpine' not in allowed:
        raise ValueError('Missing owned database volume')
    for service, value in config['services'].items():
        for mount in value.get('volumes', []):
            if mount['type'] == 'volume' and mount.get('source') not in allowed.values():
                raise ValueError('Unowned or anonymous service volume')
            if service == 'db' and mount['target'] == '/var/lib/postgresql/data':
                if mount['type'] != 'volume' or mount.get('source') != 'pgdata17_36_alpine':
                    raise ValueError('Database does not use the owned fixture volume')
    return allowed


def admit_runtime_mounts(containers, volumes, project, allowed):
    by_name = {row['Name']: row for row in volumes}
    if not set(by_name) <= set(allowed):
        raise ValueError('Unexpected project volume')
    for name, row in by_name.items():
        labels = row.get('Labels') or {}
        if (labels.get('com.docker.compose.project') != project
                or labels.get('com.docker.compose.volume') != allowed[name]):
            raise ValueError('Actual volume ownership differs from the admitted plan')
    for row in containers:
        labels = row['Config'].get('Labels') or {}
        if labels.get('com.docker.compose.project') != project:
            raise ValueError('Actual container ownership differs')
        for mount in row.get('Mounts', []):
            if mount['Type'] == 'volume' and mount.get('Name') not in by_name:
                raise ValueError('Container mounts a volume outside the owned fixture')
            if labels.get('com.docker.compose.service') == 'db' and mount['Destination'] == '/var/lib/postgresql/data':
                if mount['Type'] != 'volume' or mount.get('Name') != project+'_pgdata17_36_alpine':
                    raise ValueError('Actual database mount differs from admitted fixture')


def verify_cleanup_ownership(project, allowed, inputs):
    if any(sha256(path.read_bytes()).hexdigest() != digest for path, digest in inputs.items()):
        raise ValueError('Cleanup refused because an admitted Compose input changed')
    ids = run(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project]).split()
    names = run(['docker','volume','ls','-q','--filter','label=com.docker.compose.project='+project]).split()
    containers = json.loads(run(['docker','inspect',*ids])) if ids else []
    volumes = json.loads(run(['docker','volume','inspect',*names])) if names else []
    admit_runtime_mounts(containers, volumes, project, allowed)


def recovery_identity_unchanged(before, after):
    if set(before) != set(after):
        return False
    return all(row['Id'] == after[name]['Id'] and row['Image'] == after[name]['Image']
        and after[name]['State']['Running'] is True
        and (name == 'db' or row['State']['StartedAt'] == after[name]['State']['StartedAt'])
        for name, row in before.items())


def publication_recovered(sample, restart_at):
    if not (sample['operator']['http'] == sample['reader']['http'] == 200
            and sample['operator']['status'] == sample['reader']['status'] == 'healthy'
            and sample['operator']['database'] == 'connected'
            and sample['worker'].get('state') == 'running'
            and sample['delivery'].get('status') == 'ok'):
        return False
    success = sample['delivery'].get('last_success_at')
    if not isinstance(success, str):
        return False
    stamp = datetime.fromisoformat(success)
    return stamp.tzinfo is not None and stamp >= datetime.fromisoformat(restart_at)


def verify_database_recovery(by_service, compose_run):
    """Restart only this admitted fixture DB; app containers must stay running."""
    from verify_http_headers import local_origin
    origins = {name:local_origin('http://'+compose_run(['port',service,'80']))
               for name,service in [('operator','frontend'),('reader','publicfrontend')]}
    result = {'status':'running', 'scope':'Actual local DB transport outage; no app restart or provider call', 'samples':[]}
    stage = 'before_outage'
    def read(client, url):
        with client.stream('GET',url) as response:
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body)>262144:
                    raise ValueError('Recovery status response exceeds bound')
            return response.status_code,json.loads(body)
    def sample(client):
        row={'at':datetime.now(timezone.utc).isoformat()}
        for name,origin in origins.items():
            status,value=read(client,origin+'/api/health')
            row[name]={'http':status,'status':value.get('status'),'database':value.get('database')}
        code,state=read(client,origins['operator']+'/api/status')
        if code!=200:
            raise ValueError('Operator diagnostic route unavailable')
        row['worker']=(state.get('workers') or {}).get('event_delivery',{})
        row['delivery']={key:(state.get('event_delivery') or {}).get(key)
                         for key in ('status','error_type','last_success_at','last_published_at')}
        return row
    try:
        with httpx.Client(trust_env=False,follow_redirects=False,timeout=12) as client:
            result['before']=sample(client)
            assert all(result['before'][name]['http']==200 and result['before'][name]['status']=='healthy' for name in origins)
            stage='database_outage'
            run(['docker','stop','--time','10',by_service['db']['Id']])
            time.sleep(5)
            result['during']=sample(client)
            assert all(result['during'][name]['http']==503 for name in origins)
            run(['docker','start',by_service['db']['Id']])
            result['restarted_at']=datetime.now(timezone.utc).isoformat()
            stage='database_recovery'
            deadline=time.monotonic()+150; consecutive=0
            while time.monotonic()<deadline:
                row=sample(client);result['samples'].append(row)
                consecutive=consecutive+1 if publication_recovered(row,result['restarted_at']) else 0
                if consecutive==3:
                    break
                time.sleep(2)
            else:
                raise RuntimeError('Database recovery did not restore both health and event publication')
        current=json.loads(run(['docker','inspect',*[row['Id'] for row in by_service.values()]]))
        after={row['Config']['Labels']['com.docker.compose.service']:row for row in current}
        result['checks']={'app_ids_images_and_start_times_unchanged':recovery_identity_unchanged(by_service,after),
            'database_same_id_and_image_with_intentional_restart':by_service['db']['Id']==after['db']['Id']
                and by_service['db']['Image']==after['db']['Image']
                and by_service['db']['State']['StartedAt']!=after['db']['State']['StartedAt'],
            'new_successful_delivery_after_restart':publication_recovered(result['samples'][-1],result['restarted_at'])}
        result['status']='PASS' if all(result['checks'].values()) else 'FAIL'
    except Exception as error:
        result.update(status='FAIL/INCOMPLETE',failed_stage=stage,error_type=type(error).__name__)
    return result


def qualify(root, images):
    root = root.resolve()
    required = ['docker-compose.yml', 'compose.publisher.yml', 'compose.public.yml']
    if not all((root/name).is_file() for name in required):
        raise ValueError('Expected a complete shipped Compose source tree')
    identities = {}
    for role, image in images.items():
        identity = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image])
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', identity):
            raise ValueError('Local immutable image identity required')
        identities[role] = identity
    project = 'cm-public-ci-' + secrets.token_hex(8)
    helper_hash = sha256(Path(__file__).read_bytes()).hexdigest()
    report = {'status': 'running', 'scope': 'Authored fixtures through actual Compose writer, two-table reader, HTTP and SQL',
        'project': project, 'images': identities, 'provider_requests': 0, 'tunnel_started': False,
        'helper_sha256': helper_hash,
        'source_sha256': {name: sha256((root/name).read_bytes()).hexdigest() for name in required},
        'checks': {}, 'limitations': ['Not live source access, source truth, Google imagery, public TLS or audience capacity proof.']}
    compose = None
    stage = 'ownership'
    try:
        # No resource with this project label may predate our ownership.
        for kind in ('container', 'network', 'volume'):
            command = ['docker', 'ps', '-aq'] if kind == 'container' else ['docker', kind, 'ls', '-q']
            if run(command + ['--filter', 'label=com.docker.compose.project=' + project]):
                raise ValueError('Fixture identity already exists')
        with tempfile.TemporaryDirectory(prefix=project+'-') as temporary:
            folder = Path(temporary)
            values = {}
            for key in ('POSTGRES_PASSWORD', 'POSTGRES_APP_PASSWORD', 'POSTGRES_PUBLIC_PASSWORD'):
                values[key] = secrets.token_hex(32)
            values.update({'CONFLICT_ENV_FILE': str(folder/'fixture.env'),
                'PIPER_VOICE_DIR': str(folder/'empty-voice'), 'FRONTEND_PORT': '0', 'PUBLIC_FRONTEND_PORT': '0',
                'BACKEND_PORT': '0', 'GOOGLE_EARTH_ENABLED': 'false', 'GOOGLE_MAPS_BROWSER_KEY': ''})
            (folder/'empty-voice').mkdir()
            descriptor = os.open(folder/'fixture.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf8') as stream:
                stream.write(''.join(k+'='+v+'\n' for k,v in values.items()))
            common = {'PYTHONPATH': '/app', 'PYTHONDONTWRITEBYTECODE': '1',
                      'GOOGLE_EARTH_ENABLED': 'false', 'GOOGLE_MAPS_BROWSER_KEY': ''}
            mount = {'type': 'bind', 'source': str(root/'tools'), 'target': '/qualification/tools', 'read_only': True}
            seed_mount = {'type': 'bind', 'source': str(Path(__file__).resolve()), 'target': '/qualification/authored-fixture.py', 'read_only': True}
            override = {'services': {
                'db': {'image': identities['database'], 'pull_policy': 'never', 'environment': {'POSTGRES_DB': 'conflict_monitor_test'},
                    'healthcheck': {'test': ['CMD-SHELL','pg_isready -h 127.0.0.1 -U monitor_admin -d conflict_monitor_test']}},
                'migrate': {'image': identities['backend'], 'environment': {'DATABASE_URL': 'postgresql+asyncpg://monitor_admin:${POSTGRES_PASSWORD}@db:5432/conflict_monitor_test'}},
                'backend': {'image': identities['backend'], 'environment': {**common,
                    'DATABASE_URL': 'postgresql+asyncpg://monitor:${POSTGRES_APP_PASSWORD}@db:5432/conflict_monitor_test',
                    'LIVE_INGESTION_ENABLED': 'false', 'PUBLIC_OBSERVATION_PUBLISHER_ENABLED': 'false', 'PUBLIC_AIRCRAFT_PUBLISHER_ENABLED': 'false'},
                    'volumes': [mount, seed_mount]},
                'reader': {'image': identities['backend'], 'environment': {**common,
                    'DATABASE_URL': 'postgresql+asyncpg://monitor_public:${POSTGRES_PUBLIC_PASSWORD}@db:5432/conflict_monitor_test'}, 'volumes': [mount]},
                'frontend': {'image': identities['operator'], 'networks': ['default', 'ci_operator_ingress']},
                'publicfrontend': {'image': identities['public']},
            }, 'networks': {'default': {'internal': True}, 'ci_operator_ingress': {}}}
            override_path = folder/'compose.override.json'
            override_path.write_text(json.dumps(override), encoding='utf8')
            compose = ['docker', 'compose', '--project-name', project, '--env-file', str(folder/'fixture.env'),
                '-f', str(root/'docker-compose.yml'), '-f', str(root/'compose.publisher.yml'), '-f', str(override_path)]
            fixture_env = fixture_environment({**values, 'COMPOSE_PROJECT_NAME': project})
            def compose_run(arguments, timeout=90):
                return run(compose+arguments, timeout=timeout, env=fixture_env)
            resolved = json.loads(compose_run(['config', '--format', 'json']))
            allowed_volumes = admit_volumes(resolved, project)
            inputs = {path:sha256(path.read_bytes()).hexdigest() for path in
                      [*(root/name for name in required), override_path, folder/'fixture.env']}
            try:
                assert resolved['networks']['default']['internal'] is True and resolved['networks']['public_reader']['internal'] is True
                for name in ('backend', 'reader'):
                    env = resolved['services'][name]['environment']
                    assert all(env[key] == 'false' for key in ('LIVE_INGESTION_ENABLED', 'DEMO_MODE', 'PUBLIC_OBSERVATION_PUBLISHER_ENABLED', 'PUBLIC_AIRCRAFT_PUBLISHER_ENABLED'))
                report['checks']['application_networks_internal_and_collection_disabled_before_start'] = True
                stage = 'compose_start'
                compose_run(['up','-d','--no-build','--wait','--wait-timeout','180'], timeout=230)
                verify_cleanup_ownership(project, allowed_volumes, inputs)
                report['checks']['actual_volume_ownership_admitted_before_sql'] = True
                profile = json.loads(run(['docker','inspect',*[project+'-'+name+'-1' for name in ('db','backend','reader','frontend','publicfrontend')]]))
                by_service = {row['Config']['Labels']['com.docker.compose.service']: row for row in profile}
                report['checks']['reader_and_writer_networks_disjoint'] = not (set(by_service['reader']['NetworkSettings']['Networks']) & set(by_service['backend']['NetworkSettings']['Networks']))
                report['checks']['db_api_reader_have_no_host_ports'] = all(not any(by_service[name]['NetworkSettings']['Ports'].values()) for name in ('db','backend','reader'))
                report['checks']['public_nginx_shares_reader_and_own_ingress_only'] = set(by_service['publicfrontend']['NetworkSettings']['Networks']) == set(by_service['reader']['NetworkSettings']['Networks']) | {project+'_public_ingress'}
                report['checks']['only_frontends_have_ingress_networks'] = all(not any(name.endswith(('_public_ingress','_ci_operator_ingress')) for name in by_service[service]['NetworkSettings']['Networks']) for service in ('db','backend','reader'))
                if not all(report['checks'].values()):
                    raise ValueError('Actual network or port isolation failed before seeding')
                stage = 'authored_seed'
                seeded = json.loads(compose_run(['exec','-T','backend','python','-B','/qualification/authored-fixture.py','--seed-authored-packets']))
                assert seeded['status'] == 'PASS' and seeded['authored_fixture'] is True
                report['authored_batches'] = seeded['batch_ids']
                # Existing tool probes actual TCP role permissions and ASGI paths;
                # it also verifies retired flags cannot reopen private events.
                stage = 'reader_sql'
                role = json.loads(compose_run(['exec','-T','reader','python','-B','/qualification/tools/verify_public_database_role.py']))
                assert role['status'] == 'PASS' and all(role['checks'].values())
                report['reader_sql'] = role
                stage = 'public_http_origin'
                from verify_public_readers import verify
                port = compose_run(['port','publicfrontend','80'])
                report['public_binding'] = port if re.fullmatch(r'127\.0\.0\.1:[0-9]+',port) else 'unexpected_binding'
                stage = 'public_http'
                report['public_http'] = asyncio.run(verify('http://'+port, require_published=True))
                assert report['public_http']['status'] == 'pass' and report['public_http']['published_data_checked']
                for name, row in by_service.items():
                    actual = json.loads(run(['docker','inspect',row['Id']]))[0]
                    assert actual['Id'] == row['Id'] and actual['Image'] == row['Image'] and actual['State']['StartedAt'] == row['State']['StartedAt']
                report['checks']['images_and_start_identities_unchanged'] = True
                # Keep the pre-outage all-five identity gate above intact. The
                # following regression permits only its explicit DB restart.
                stage = 'actual_database_recovery'
                report['database_recovery'] = verify_database_recovery(by_service, compose_run)
                assert report['database_recovery']['status'] == 'PASS'
                report['checks']['helper_unchanged'] = sha256(Path(__file__).read_bytes()).hexdigest() == helper_hash
                report['status'] = 'PASS' if all(report['checks'].values()) else 'FAIL'
            finally:
                verify_cleanup_ownership(project, allowed_volumes, inputs)
                compose_run(['down','--volumes','--remove-orphans'], timeout=90)
                compose = None
                for kind in ('container', 'network', 'volume'):
                    command = ['docker','ps','-aq'] if kind == 'container' else ['docker',kind,'ls','-q']
                    if run(command+['--filter','label=com.docker.compose.project='+project]):
                        raise RuntimeError('Owned fixture cleanup incomplete')
                report['cleanup_verified'] = True
    except Exception as error:
        report.update(status='FAIL/INCOMPLETE', error_type=type(error).__name__, failed_stage=stage)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-authored-packets', action='store_true')
    parser.add_argument('--source-root', type=Path, default=ROOT)
    for role in ('backend', 'database', 'operator', 'public'):
        parser.add_argument('--'+role+'-image')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.seed_authored_packets:
        asyncio.run(seed())
    else:
        if args.output is None or not all(getattr(args,role+'_image') for role in ('backend','database','operator','public')):
            parser.error('All four images and an output path are required')
        result = qualify(args.source_root, {role:getattr(args,role+'_image') for role in ('backend','database','operator','public')})
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
        print(json.dumps(result))
        raise SystemExit(0 if result['status']=='PASS' else 2)

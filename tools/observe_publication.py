"""Read-only, bounded public HTTP/SQL publication observation.

Only metadata and hashes are recorded. This does not grant source rights or
verify the factual accuracy of reported coordinates. It makes no provider calls.
"""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

import httpx

DATASETS = {
    'observations': {'source': 'nasa_firms_noaa20', 'table': 'public_observation_batches', 'rows': 'hotspots', 'limit': 2000},
    'aircraft': {'source': 'adsb_lol', 'table': 'public_aircraft_batches', 'rows': 'aircraft', 'limit': 5000},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def utcnow():
    return datetime.now(timezone.utc)


def no_store_headers(headers):
    # Both the application and edge enforce this policy. Repeated identical
    # directives are valid; any missing/conflicting directive is a finding.
    values = headers.get_list('cache-control')
    return bool(values) and all(token.strip().lower() == 'no-store' for value in values for token in value.split(','))


def clock(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Timezone missing')
    return parsed


def validate_display(kind, value, now):
    expected = DATASETS[kind]
    if value.get('source') != expected['source'] or value.get('status') not in {'fresh', 'empty'}:
        raise ValueError('Public dataset is not available and current')
    rows = value.get(expected['rows'])
    if not isinstance(rows, list) or len(rows) > expected['limit']:
        raise ValueError('Unexpected publication size')
    identifier = value.get('batch_id')
    if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{64}', identifier):
        raise ValueError('Missing immutable publication identity')
    identities, thermal_positions = [], []
    for row in rows:
        lat, lon = row.get('lat'), row.get('lon')
        if not all(type(v) in {int, float} and math.isfinite(v) for v in [lat, lon]) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Invalid public position')
        if any(key in row for key in ['raw_text', 'summary', 'event_id', 'event_ids', 'severity', 'military', 'operator', 'emergency']):
            raise ValueError('Private or inferred fields in public position')
        if kind == 'observations':
            age = (now - clock(row['ts'])).total_seconds()
            if not (-300 <= age <= 172805 and 25 <= lon <= 65 and 10 <= lat <= 42):
                raise ValueError('Thermal position outside declared clock/coverage')
            if type(row['frp']) not in {int, float} or not math.isfinite(row['frp']) or row['frp'] < 10:
                raise ValueError('Thermal filter differs from declaration')
            if row.get('satellite') != 'NOAA-20' or row.get('instrument') != 'VIIRS':
                raise ValueError('Undeclared thermal source')
            identities.append(row['id'])
            thermal_positions.append((lat, lon, clock(row['ts']).astimezone(timezone.utc)))
        else:
            age = (now - clock(row['observed_at'])).total_seconds()
            if not -5 <= age <= 125 or row.get('source') != 'adsb.lol' or row.get('origin_country') != '':
                raise ValueError('Aircraft clock/source or heuristic boundary failed')
            identities.append(row['icao24'])
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate public identity')
    if len(thermal_positions) != len(set(thermal_positions)):
        raise ValueError('Duplicate thermal position/time')
    if kind == 'aircraft' and (value.get('license') != 'ODbL-1.0' or not value.get('attribution') or len(value.get('coverage', [])) != 4):
        raise ValueError('Aircraft attribution or coverage absent')
    if kind == 'observations' and (not value.get('citation_url') or not value.get('disclaimer_url') or value.get('displayed_count') != len(rows)):
        raise ValueError('NASA attribution or counts absent')
    return identifier, len(rows)


def verify_download(value, expected_id, expected_source):
    core = {key: value[key] for key in ['source', 'published_at', 'status', 'payload']}
    if value.get('batch_id') != expected_id or core['source'] != expected_source or core['status'] != 'ok':
        raise ValueError('Download identity/status differs from displayed publication')
    if sha256(canonical(core)).hexdigest() != expected_id:
        raise ValueError('Canonical download digest mismatch')
    return core


def verify_display_projection(kind, value, core, requested_at, received_at):
    """Bind every displayed field to one valid projection of the exact packet.

    Local host/container clocks receive a declared one-second allowance. Only
    clock cutoffs inside that bounded request window can change the projection;
    a download fetched later must not retroactively age the earlier response.
    """
    if not 0 <= (received_at - requested_at).total_seconds() <= 30:
        raise ValueError('Publication request clock window exceeded')
    if value.get('source') != core['source'] or clock(value['published_at']) != clock(core['published_at']):
        raise ValueError('Display envelope differs from immutable packet')
    nasa = kind == 'observations'
    rows = core['payload']['observations' if nasa else 'aircraft']
    displayed = value['hotspots' if nasa else 'aircraft']
    if value['status'] != ('fresh' if displayed else 'empty'):
        raise ValueError('Display availability contradicts its visible selection')
    identity, timestamp = ('id', 'ts') if nasa else ('icao24', 'observed_at')
    by_id = {row[identity]: row for row in rows}
    if len(by_id) != len(rows) or any(row != by_id.get(row[identity]) for row in displayed):
        raise ValueError('Displayed position or metadata differs from immutable packet')
    for field in (('source_rows', 'regional_rows', 'filtered_rows', 'duplicate_rows', 'response_sha256', 'received_at')
                  if nasa else ('source_records', 'filtered_records', 'provider_snapshot_at')):
        if value.get(field) != core['payload'][field]:
            raise ValueError('Display provenance differs from immutable packet')
    lower, upper = requested_at - timedelta(seconds=1), received_at + timedelta(seconds=1)
    clocks = [clock(row[timestamp]) for row in rows]
    lifetime, future = (172800, 300) if nasa else (120, 0)
    candidates = {lower, upper}
    for stamp in clocks:
        for boundary in (stamp - timedelta(seconds=future), stamp + timedelta(seconds=lifetime, microseconds=1)):
            if lower < boundary < upper:
                candidates.add(boundary)
    if len(candidates) > 256:
        raise ValueError('Too many ambiguous clock transitions in one publication read')
    # Most reads have no intervening clock transition. Worst-case work remains
    # bounded by the source row caps and 256 candidate timestamps.
    for at in sorted(candidates):
        if not (-300 if nasa else -5) <= (at - clock(core['published_at'])).total_seconds() <= (43200 if nasa else 120):
            continue
        eligible = [row for row, stamp in zip(rows, clocks) if -future <= (at - stamp).total_seconds() <= lifetime]
        if nasa:
            eligible.sort(key=lambda row: (-row['frp'], row['id']))
            if value['eligible_count'] != len(eligible) or value['displayed_count'] != min(len(eligible), 2000):
                continue
        if displayed == (eligible[:2000] if nasa else eligible):
            return
    raise ValueError('Displayed selection is not a valid timed projection of its packet')


def final_sample_gap(elapsed_seconds, previous_sample):
    if previous_sample is None or not 0 <= elapsed_seconds - previous_sample <= 90:
        raise ValueError('Final observation gap exceeded90seconds')
    return elapsed_seconds - previous_sample


def inspect_profile(names):
    fmt = '{"name":{{json .Name}},"image":{{json .Image}},"started_at":{{json .State.StartedAt}}}'
    result = subprocess.check_output(['docker', 'inspect', '--format', fmt, *names], text=True, timeout=15)
    rows = [json.loads(line) for line in result.splitlines() if line]
    for row in rows:
        row['name'] = row['name'].lstrip('/')
    if len(rows) != len(names) or {r['name'] for r in rows} != set(names):
        raise ValueError('Deployment identity unavailable')
    return sorted(rows, key=lambda row: row['name'])


def verify_sql(args, kind, identifier, core):
    if not re.fullmatch('[0-9a-f]{64}', identifier):
        raise ValueError('Unexpected publication ID')
    table = DATASETS[kind]['table']
    sql = ("SELECT json_build_object('role',current_user,'database',current_database(),'source',source,"
           "'published_at',published_at,'status',status,'payload',payload) FROM public."
           + table + " WHERE id='" + identifier + "';")
    output = subprocess.check_output(['docker', 'exec', args.database_container, 'psql', '-XqAt',
        '-v', 'ON_ERROR_STOP=1', '-U', 'monitor_public', '-d', args.database_name, '-c', sql], text=True, timeout=15)
    row = json.loads(output)
    if row.pop('role') != 'monitor_public' or row.pop('database') != args.database_name:
        raise ValueError('Unexpected reader database identity')
    row['published_at'] = clock(row['published_at']).isoformat()
    if row != core:
        raise ValueError('Immutable HTTP/SQL publication mismatch')


def observe(args):
    parsed = urlsplit(args.base_url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}:
        raise ValueError('Use a literal loopback qualification origin')
    if not 60 <= args.seconds <= 14400:
        raise ValueError('Use a bounded one-minute to four-hour observation')
    folder = Path(args.output)
    folder.mkdir(exist_ok=False)
    expected = json.loads(Path(args.profile).read_bytes())
    names = [row['name'] for row in expected]
    if inspect_profile(names) != expected:
        raise ValueError('Wrong initial deployment profile')
    started = time.monotonic()
    elapsed = lambda: time.monotonic() - started
    report = {'status': 'running', 'started_at': utcnow().isoformat(), 'requested_seconds': args.seconds,
              'samples': 0, 'findings': [], 'datasets': {kind: {'samples': 0, 'max_rows': 0, 'batch_ids': []} for kind in DATASETS},
              'resource_samples': 0,
              'profile': expected, 'observer_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Local public HTTP, exact per-batch downloads, SELECT-only SQL and unchanged image/start identities',
              'limits': ['No provider requests or generated traffic.', 'No source truth, physical device or internet-capacity claim.']}
    verified = {kind: set() for kind in DATASETS}
    current_packets = {}  # Only one complete packet per source, never the entire soak history.
    previous = None
    def save():
        temporary = folder / 'summary.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
        for attempt in range(6):
            try:
                temporary.replace(folder / 'summary.json')
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(.02 * (attempt + 1))
    try:
        with httpx.Client(base_url=args.base_url, timeout=20, trust_env=False, follow_redirects=False) as client:
            while elapsed() < args.seconds:
                tick = elapsed()
                row = {'at': utcnow().isoformat(), 'elapsed_seconds': round(tick, 3), 'datasets': {}}
                stage = 'deployment_identity'
                try:
                    if previous is not None and tick - previous > 90:
                        raise ValueError('Observation gap exceeded90seconds')
                    previous = tick
                    if inspect_profile(names) != expected:
                        raise ValueError('Deployment identity changed')
                    if report['samples'] % 2 == 0:
                        stage = 'container_resources'
                        raw = subprocess.check_output(['docker', 'stats', '--no-stream', '--format', '{{json .}}', *names], text=True, timeout=20)
                        metrics = [json.loads(line) for line in raw.splitlines() if line]
                        if len(metrics) != len(names) or {item.get('Name') for item in metrics} != set(names):
                            raise ValueError('Incomplete service resource observation')
                        row['container_resources'] = [{key: item[key] for key in ('Name', 'CPUPerc', 'MemUsage', 'MemPerc', 'PIDs')} for item in metrics]
                        report['resource_samples'] += 1
                    stage = 'public_health'
                    health = client.get('/api/health').raise_for_status().json()
                    if health != {'status': 'healthy'}:
                        raise ValueError('Public database health failed')
                    for kind, spec in DATASETS.items():
                        stage = kind + '_display'
                        requested_at = utcnow()
                        response = client.get('/api/publication/' + kind).raise_for_status()
                        if not no_store_headers(response.headers):
                            raise ValueError('Publication cache policy changed')
                        value = response.json()
                        received_at = utcnow()
                        identifier, count = validate_display(kind, value, received_at)
                        if current_packets.get(kind, (None,))[0] != identifier:
                            stage = kind + '_download'
                            path = '/api/publication/' + kind + '/download/' + identifier
                            download = client.get(path).raise_for_status()
                            if not no_store_headers(download.headers):
                                raise ValueError('Download cache policy changed')
                            packet = download.json()
                            core = verify_download(packet, identifier, spec['source'])
                            stage = kind + '_sql'
                            verify_sql(args, kind, identifier, core)
                            verified[kind].add(identifier)
                            current_packets[kind] = (identifier, core)
                        stage = kind + '_display_projection'
                        verify_display_projection(kind, value, current_packets[kind][1], requested_at, received_at)
                        report['datasets'][kind]['samples'] += 1
                        report['datasets'][kind]['max_rows'] = max(count, report['datasets'][kind]['max_rows'])
                        report['datasets'][kind]['batch_ids'] = sorted(verified[kind])
                        row['datasets'][kind] = {'batch_id': identifier, 'visible_rows': count, 'status': value['status']}
                except (ValueError, TypeError, KeyError, httpx.HTTPError, subprocess.SubprocessError) as error:
                    row['finding'] = type(error).__name__
                    row['finding_stage'] = stage
                    report['findings'].append({'sample': report['samples'], 'stage': stage, 'type': type(error).__name__})
                report['samples'] += 1
                report['elapsed_seconds'] = elapsed()
                with (folder / 'samples.jsonl').open('a', encoding='utf8') as stream:
                    stream.write(json.dumps(row) + '\n')
                save()
                time.sleep(max(0, min(tick + 30, args.seconds) - elapsed()))
        required_batches = 2 if args.seconds >= 12600 else 1
        report['final_sample_gap_seconds'] = final_sample_gap(elapsed(), previous)
        report['projection_clock_allowance_seconds'] = 1
        good = (elapsed() >= args.seconds and report['samples'] >= 2 and not report['findings']
                and report['resource_samples'] == (report['samples'] + 1) // 2
                and inspect_profile(names) == expected
                and all(len(verified[kind]) >= required_batches and report['datasets'][kind]['max_rows'] > 0 for kind in DATASETS))
        report['required_distinct_batches_per_dataset'] = required_batches
        report['status'] = 'qualified_sample' if good else 'incomplete_or_findings'
    except (ValueError, TypeError, KeyError, httpx.HTTPError, subprocess.SubprocessError) as error:
        report['status'] = 'incomplete_or_findings'
        report['findings'].append({'type': type(error).__name__})
    finally:
        report.update(ended_at=utcnow().isoformat(), elapsed_seconds=elapsed())
        save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--seconds', type=int, required=True)
    parser.add_argument('--database-container', required=True)
    parser.add_argument('--database-name', choices=['conflict_monitor_test'], required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--output', required=True)
    result = observe(parser.parse_args())
    print(json.dumps(result))
    raise SystemExit(0 if result['status'] == 'qualified_sample' else 1)

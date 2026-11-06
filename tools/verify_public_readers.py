"""Bounded read-only qualification of a disposable loopback public profile.

Only dedicated public publication packets are admitted; private reports and
WebSockets are always closed. This workload is not internet capacity proof.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import statistics
import time

import httpx

from observe_publication import DATASETS, no_store_headers, validate_display, verify_display_projection, verify_download
from verify_http_headers import local_origin

MAX_BYTES = 8_000_000
PRIVATE_PATHS = (
    '/api/events', '/api/events/delivery/baseline', '/api/events/delivery/changes',
    '/api/events/time-range', '/api/tracking/aircraft', '/api/tracking/vessels',
    '/api/satellite/hotspots', '/api/costs/summary', '/api/briefing/status',
    '/api/media/feed', '/api/docs', '/api/openapi.json', '/api/channels', '/api/sitreps',
)


def decode_body(raw, encoding):
    if len(raw) > MAX_BYTES:
        raise ValueError('Compressed response exceeds bound')
    if encoding == 'gzip':
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            body = stream.read(MAX_BYTES + 1)
    elif encoding in {'', 'identity'}:
        body = raw
    else:
        raise ValueError('Unexpected content encoding')
    if len(body) > MAX_BYTES:
        raise ValueError('Decoded response exceeds bound')
    return body


async def fetch(client, path, *, method='GET', encoding='gzip', headers=None):
    started = time.perf_counter()
    async with client.stream(method, path, headers={'Accept-Encoding': encoding, **(headers or {})}) as response:
        raw = bytearray()
        async for chunk in response.aiter_raw():
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise ValueError('HTTP response exceeds bound')
        body = decode_body(bytes(raw), response.headers.get('content-encoding', '')) if method != 'HEAD' else b''
        return response.status_code, response.headers, body, {
            'status': response.status_code, 'wire_bytes': len(raw), 'decoded_bytes': len(body),
            'gzip': response.headers.get('content-encoding') == 'gzip',
            'milliseconds': round((time.perf_counter() - started) * 1000, 3),
        }


def public_headers(headers):
    nosniff = headers.get_list('x-content-type-options')
    if not no_store_headers(headers) or not nosniff or any(token.strip().lower() != 'nosniff' for value in nosniff for token in value.split(',')):
        raise ValueError('Public cache/security policy changed')
    if 'set-cookie' in headers:
        raise ValueError('Public response issued a credential')


def capabilities(value):
    if (value.get('public_read_only') is not True or value.get('public_observations_enabled') is not True
            or value.get('public_aircraft_enabled') is not True):
        raise ValueError('Not the dedicated public publication profile')
    for key in ('public_reports_enabled', 'public_tracking_enabled', 'public_media_enabled',
                'generation_enabled', 'video_generation_enabled', 'local_ai_enabled'):
        if value.get(key) is not False:
            raise ValueError('Private/operator capability reopened')


async def verify(origin, require_published=False):
    origin = local_origin(origin)
    result = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Isolated public profile; one loopback peer; bounded local workload',
        'checks': [], 'datasets': {}, 'published_data_checked': False,
        'limitations': ['No public DNS, TLS, CDN, physical device or audience capacity is tested.',
                       'Authored fixtures do not qualify live provider access or source truth.']}
    stage = 'config'
    try:
        async with httpx.AsyncClient(base_url=origin, trust_env=False, timeout=25,
                follow_redirects=False, limits=httpx.Limits(max_connections=16)) as client:
            status, headers, body, _ = await fetch(client, '/api/config')
            assert status == 200
            stage = 'config_headers'
            public_headers(headers)
            stage = 'config_capabilities'
            capabilities(json.loads(body))
            result['checks'].append('dedicated_public_capabilities_private_controls_disabled')
            stage = 'private_boundaries'
            for path in PRIVATE_PATHS:
                status, headers, _, _ = await fetch(client, path, headers={
                    'X-Admin-Key': 'fixture-cannot-authorize-public', 'Cookie': 'session=fixture'})
                assert status == 404, path
                public_headers(headers)
            for method in ('POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'):
                assert (await fetch(client, '/api/publication/observations', method=method))[0] == 405
            status, _, _, _ = await fetch(client, '/api/ws/events', headers={
                'Connection': 'Upgrade', 'Upgrade': 'websocket', 'Origin': origin,
                'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ=='})
            assert status == 404
            result['checks'].append('private_api_and_websocket_always_closed_despite_credentials')
            stage = 'publication_contract'
            for kind, spec in DATASETS.items():
                path = '/api/publication/' + kind
                requested_at = datetime.now(timezone.utc)
                status, headers, body, metric = await fetch(client, path)
                received_at = datetime.now(timezone.utc)
                assert status == 200
                public_headers(headers)
                value = json.loads(body)
                assert value.get('source') == spec['source']
                state = value.get('status')
                assert state in {'fresh', 'empty', 'awaiting_publication', 'failed', 'stale'}
                dataset = {'status': state, 'display': metric, 'exact_download_checked': False}
                if state in {'fresh', 'empty'}:
                    identifier, count = validate_display(kind, value, datetime.now(timezone.utc))
                    status, headers, packet, download_metric = await fetch(client, path + '/download/' + identifier)
                    assert status == 200
                    public_headers(headers)
                    core = verify_download(json.loads(packet), identifier, spec['source'])
                    verify_display_projection(kind, value, core, requested_at, received_at)
                    if len(packet) >= 1024:
                        assert download_metric['gzip'] and 'accept-encoding' in headers.get('vary', '').lower()
                    dataset.update(batch_id=identifier, rows=count, exact_download_checked=True,
                                   download=download_metric, decoded_sha256=sha256(packet).hexdigest())
                elif require_published:
                    raise ValueError('Fresh publication required but unavailable')
                elif state in {'awaiting_publication', 'failed'}:
                    assert value.get(spec['rows']) == []
                result['datasets'][kind] = dataset
                # Query denial is part of the explicit ingress contract.
                assert (await fetch(client, path + '?provider=private'))[0] == 404
            result['published_data_checked'] = all(v['exact_download_checked'] for v in result['datasets'].values())
            result['checks'].append('truthful_dedicated_dataset_states_and_exact_packet_digests')
            stage = 'steady_health'
            timings = []
            for _ in range(24):
                status, headers, body, metric = await fetch(client, '/api/health')
                assert status == 200 and json.loads(body) == {'status': 'healthy'}
                public_headers(headers)
                timings.append(metric['milliseconds'])
                await asyncio.sleep(.3)
            result['steady'] = {'responses': len(timings), 'latency_ms_median': round(statistics.median(timings), 2),
                                'latency_ms_max': max(timings)}
            result['checks'].append('steady_actual_database_health_requests_succeed')
            stage = 'burst_recovery'
            statuses = Counter(row[0] for row in await asyncio.gather(*(fetch(client, '/api/config',
                headers={'X-Forwarded-For': '203.0.113.18'}) for _ in range(96))))
            assert set(statuses) <= {200, 429} and statuses[200] > 0 and statuses[429] > 0
            result['burst'] = dict(statuses)
            await asyncio.sleep(10)
            assert (await fetch(client, '/api/health'))[0] == 200
            result['checks'].append('bounded_burst_returns_429_not_5xx_and_recovers')
        result['status'] = 'pass'
    except Exception as error:
        result.update(status='fail', error_type=type(error).__name__, failed_stage=stage)
    result['finished_at'] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--require-published', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(verify(args.base_url, args.require_published))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result))
    raise SystemExit(0 if result['status'] == 'pass' else 1)

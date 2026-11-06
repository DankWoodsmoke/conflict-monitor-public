"""Fail-closed source acquisition and reviewed-patch binding for native builds."""
import hashlib
import importlib.util
import io
import json
from collections import Counter
from pathlib import Path
import re
import socket
import ssl
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def native(monkeypatch):
    folder = Path(__file__).resolve().parents[1] / 'container'
    monkeypatch.syspath_prepend(str(folder))
    import native_build
    return native_build


def test_cached_native_archive_must_match_before_reuse(native, tmp_path, monkeypatch):
    (tmp_path / 'source.tar.gz').write_bytes(b'changed archive')
    monkeypatch.setattr(native.urllib.request, 'build_opener', lambda *args: None)
    with pytest.raises(ValueError, match='checksum mismatch'):
        native.fetch_sources({'source.tar.gz': {'url': 'https://github.com/example/source',
                              'sha256': hashlib.sha256(b'expected archive').hexdigest()}}, tmp_path)


@pytest.mark.parametrize('status,attempts', [(403, 1), (404, 1), (503, 3)])
def test_native_source_retry_preserves_permanent_and_exhausted_errors(native, tmp_path, monkeypatch, status, attempts):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, status, 'fixture', {}, None)
    monkeypatch.setattr(native.urllib.request, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(native.time, 'sleep', lambda seconds: None)
    with pytest.raises(urllib.error.HTTPError):
        native.fetch_sources({'source.tar.gz': {'url': 'https://github.com/example/source', 'sha256': '0'*64}}, tmp_path)
    assert len(calls) == attempts


@pytest.mark.parametrize('target', ['http://github.com/source', 'https://attacker.example/source',
                                  'https://user:fixture-password@github.com/source', 'https://github.com:444/source'])
def test_native_source_redirect_cannot_change_trust_boundary(native, target):
    with pytest.raises(ValueError, match='redirect'):
        native.SourceRedirect().redirect_request(urllib.request.Request('https://github.com/source'),
                                                  None, 302, 'Found', {}, target)


def test_native_source_size_cap_precedes_archive_processing(native, tmp_path, monkeypatch):
    class Response(io.BytesIO):
        pass
    class Opener:
        def open(self, request, timeout):
            return Response(b'oversized')
    monkeypatch.setattr(native.urllib.request, 'build_opener', lambda *args: Opener())
    with pytest.raises(ValueError, match='budget'):
        native.fetch_sources({'source.tar.gz': {'url': 'https://github.com/example/source',
                              'sha256': hashlib.sha256(b'oversized').hexdigest(), 'max_bytes': 3}}, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('reason,retries', [
    (ConnectionRefusedError(111, 'fixture refused'), 3),
    (ConnectionResetError(104, 'fixture reset'), 3),
    (TimeoutError('fixture timeout'), 3),
    (socket.gaierror(socket.EAI_AGAIN, 'fixture temporary DNS failure'), 3),
    (socket.gaierror(socket.EAI_NONAME, 'fixture permanent DNS failure'), 1),
    (ssl.SSLCertVerificationError('fixture invalid certificate'), 1),
    ('fixture unsupported URL error', 1),
])
def test_native_wrapped_transport_retry_is_bounded_and_narrow(native, tmp_path, monkeypatch, reason, retries):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise urllib.error.URLError(reason)
    monkeypatch.setattr(native.urllib.request, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(native.time, 'sleep', lambda seconds: None)
    with pytest.raises(urllib.error.URLError):
        native.fetch_sources({'source.tar.gz': {'url': 'https://github.com/example/source', 'sha256': '0'*64}}, tmp_path)
    assert len(calls) == retries
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('exhausted', [False, True])
def test_native_partial_transfer_never_becomes_cached_archive(native, tmp_path, monkeypatch, exhausted):
    payload = b'complete verified archive'
    calls = []
    class BrokenResponse(io.BytesIO):
        def read1(self, size):
            if self.tell():
                raise ConnectionResetError('fixture reset after partial body')
            return self.read(5)
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            assert not (tmp_path / 'source.tar.gz').exists()
            assert list(tmp_path.iterdir()) == []
            return BrokenResponse(payload) if exhausted or len(calls) < 3 else io.BytesIO(payload)
    monkeypatch.setattr(native.urllib.request, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(native.time, 'sleep', lambda seconds: None)
    entries = {'source.tar.gz': {'url': 'https://github.com/example/source',
                               'sha256': hashlib.sha256(payload).hexdigest()}}
    if exhausted:
        with pytest.raises(ConnectionResetError):
            native.fetch_sources(entries, tmp_path)
        assert list(tmp_path.iterdir()) == []
    else:
        native.fetch_sources(entries, tmp_path)
        assert (tmp_path / 'source.tar.gz').read_bytes() == payload
        assert len(list(tmp_path.iterdir())) == 1
    assert len(calls) == 3


def test_native_download_checksum_failure_is_not_retried_or_cached(native, tmp_path, monkeypatch):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            return io.BytesIO(b'unexpected archive')
    monkeypatch.setattr(native.urllib.request, 'build_opener', lambda *args: Opener())
    with pytest.raises(ValueError, match='checksum mismatch'):
        native.fetch_sources({'source.tar.gz': {'url': 'https://github.com/example/source', 'sha256': '0'*64}}, tmp_path)
    assert len(calls) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('name', ['build_glibc_patch', 'build_curl_patch'])
def test_every_native_backport_file_matches_its_reviewed_pin(native, name):
    folder = Path(__file__).resolve().parents[1] / 'container'
    spec = importlib.util.spec_from_file_location(name, folder / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for patch, digest in {**module.PATCHES, **getattr(module, 'UPSTREAM_INPUTS', {}),
                          **getattr(module, 'NGHTTP2_HARDENING_INPUTS', {})}.items():
        native.checked(folder / patch, digest)


@pytest.mark.parametrize('stem', ['boringssl-crl-tests', 'boringssl-CVE-2026-35189'])
def test_boringssl_context_adaptation_preserves_every_executable_change(stem):
    folder = Path(__file__).resolve().parents[1] / 'container'
    def executable_changes(path):
        return [line for line in path.read_text().splitlines()
                if line.startswith(('+', '-')) and not line.startswith(('+++ ', '--- '))
                and not line[1:].lstrip().startswith('//')]
    assert executable_changes(folder / (stem + '.patch')) == executable_changes(folder / (stem + '.upstream.patch'))


def test_nghttp2_adaptation_retains_all_upstream_executable_additions_and_applicable_removals():
    folder = Path(__file__).resolve().parents[1] / 'container'
    manifest = json.loads((folder / 'nghttp2-client-hardening.json').read_text())
    def changes(text):
        result = {'+': Counter(), '-': Counter()}
        path = ''
        for line in text.splitlines():
            if line.startswith('+++ b/'):
                path = line[6:]
                continue
            if not path.startswith('lib/') or not line or line[0] not in '+-' or line.startswith(('+++', '---')):
                continue
            code = line[1:].strip()
            if not code or code.startswith(('/*', '*', '//')):
                continue
            result[line[0]].update(re.findall(r'[A-Za-z_]\w*|[0-9]+|[^\s]', code))
        return result
    upstream = changes('\n'.join((folder / row['input']).read_text() for row in manifest['upstream_changes']))
    adapted = changes((folder / manifest['patch']).read_text())
    # Both older DATA payload handlers lack this upstream-deleted block.
    # Exact original/applied file hashes separately bind the reviewed context.
    absent_original = Counter(re.findall(r'[A-Za-z_]\w*|[0-9]+|[^\s]',
        'if (iframe->state == NGHTTP2_IB_IGN_ALL) { return (nghttp2_ssize)inlen; }'))
    # Follow-up corrections intentionally remove earlier additions (including
    # counter placement/defaults); compare signed net changes, retaining zeros
    # and negative counts. This is supplemental conservation evidence, not a
    # semantic proof: exact source hashes and ordinary upstream suites gate it.
    upstream_net = upstream['+'].copy()
    upstream_net.subtract(upstream['-'])
    adapted_net = adapted['+'].copy()
    adapted_net.subtract(adapted['-'])
    adapted_net.subtract(absent_original)
    adapted_net.subtract(absent_original)
    assert dict(sorted((k, v) for k, v in upstream_net.items() if v)) == dict(
        sorted((k, v) for k, v in adapted_net.items() if v))
    assert len(manifest['source_files']) == 11
    assert manifest['source_files']['lib/nghttp2_session.c']['before'] == '78969d777e6f221bcbaf06e1827a3afd71b68dc545d08443b6082162957c5b52'
    assert {row['pull_request'] for row in manifest['upstream_changes']} == {
        2826, 2829, 2926, 2931, 2934, 2945,
        2485, 2488, 2508, 2509, 2510, 2598, 2599, 2607, 2856,
    }


@pytest.mark.parametrize('damage', [None, 'required_missing', 'skipped', 'aggregate_only', 'error'])
def test_nghttp2_unit_gate_requires_actual_named_successes_and_zero_skips(native, damage):
    import build_curl_patch as build
    names = sorted(build.NGHTTP2_REQUIRED_TESTS)
    names += ['test_nghttp2_fixture_' + str(i) for i in range(217 - len(names))]
    text = '\n'.join(name + '[ OK    ]' for name in names)
    text += '\n217 of 217 (100%) tests successful, 0 (0%) test skipped.\nTest Passed.\n'
    if damage == 'required_missing':
        text = text.replace(names[0], 'test_nghttp2_other_fixture')
    elif damage == 'skipped':
        text = text.replace('0 (0%) test skipped.', '1 (1%) test skipped.')
    elif damage == 'aggregate_only':
        text = text[text.index('217 of 217'):]
    elif damage == 'error':
        text += '[ ERROR ]'
    if damage:
        with pytest.raises(RuntimeError):
            build.validate_nghttp2_unit_log(text)
    else:
        assert build.validate_nghttp2_unit_log(text)['tests'] == 217

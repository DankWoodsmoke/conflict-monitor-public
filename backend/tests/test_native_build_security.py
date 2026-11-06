"""Fail-closed source acquisition and reviewed-patch binding for native builds."""
import hashlib
import importlib.util
import io
from pathlib import Path
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
    for patch, digest in {**module.PATCHES, **getattr(module, 'UPSTREAM_INPUTS', {})}.items():
        native.checked(folder / patch, digest)


@pytest.mark.parametrize('stem', ['boringssl-crl-tests', 'boringssl-CVE-2026-35189'])
def test_boringssl_context_adaptation_preserves_every_executable_change(stem):
    folder = Path(__file__).resolve().parents[1] / 'container'
    def executable_changes(path):
        return [line for line in path.read_text().splitlines()
                if line.startswith(('+', '-')) and not line.startswith(('+++ ', '--- '))
                and not line[1:].lstrip().startswith('//')]
    assert executable_changes(folder / (stem + '.patch')) == executable_changes(folder / (stem + '.upstream.patch'))

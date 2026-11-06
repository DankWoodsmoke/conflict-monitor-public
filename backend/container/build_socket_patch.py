"""Build the pending upstream CPython 3.12 getaddrinfo security backport.

The distributor's interpreter and package version stay intact. Only the native
socket extension is rebuilt from the distributor's exact source revision. All
downloaded bytes, the upstream patch and the original socket source are pinned.
The build and regression phase runs with Docker networking disabled.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import time
import urllib.error
import urllib.request

BASE = Path('/build/socket-security')
OUTPUT = Path('/opt/socket-security')
SOURCE_COMMIT = '3d6d2a63a23ee4d340ed8df6de0bd70ef175c4cf'
BACKPORT_COMMIT = '14815082af8f3c21bd50800030faed37c76296cb'
ARCHIVE_URL = 'https://codeload.github.com/python/cpython/tar.gz/' + SOURCE_COMMIT
ARCHIVE_SHA256 = 'ae7468643ec51e7878835db2746d5d22eec2c32dd36ecac034d6c263eefdecc7'
PATCH_SHA256 = 'a204a8d3071f8a768d213ebfee64c93b0dc872957e6220c0489ba226045d4af1'
BEFORE_SHA256 = 'd0089780e209ce9f0297d54cf9ec488e90f6b84f98d6bbf48310ba3da4c49314'
AFTER_SHA256 = '88d874b97250e66ec590c99ad3918de862e7e1561cb84dc79d4b8f7db20be236'
PATCH = Path(__file__).with_name('CVE-2026-116566.patch')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Unexpected CPython source redirect')


def fetch():
    BASE.mkdir(parents=True, exist_ok=True)
    archive = BASE / 'cpython.tar.gz'
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
    for attempt in range(3):
        started = time.monotonic()
        try:
            request = urllib.request.Request(ARCHIVE_URL, headers={'User-Agent': 'ConflictMonitor-native-security-build'})
            with opener.open(request, timeout=30) as response, archive.open('wb') as target:
                if response.geturl() != ARCHIVE_URL:
                    raise ValueError('Unexpected CPython source URL')
                declared = response.headers.get('Content-Length')
                if declared is not None and int(declared) > 60_000_000:
                    raise ValueError('CPython source exceeds download size budget')
                size = 0
                while chunk := response.read1(1024 * 1024):
                    size += len(chunk)
                    if size > 60_000_000 or time.monotonic() - started > 180:
                        raise ValueError('CPython source exceeds download budget')
                    target.write(chunk)
            if sha(archive) != ARCHIVE_SHA256:
                raise ValueError('CPython source checksum mismatch')
            return
        except urllib.error.HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise
        except (TimeoutError, ConnectionError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)
    raise RuntimeError('CPython source download did not complete')


def build():
    if sys.version_info[:3] != (3, 12, 16):
        raise RuntimeError('Requalify socket backport before changing Python version')
    archive = BASE / 'cpython.tar.gz'
    if sha(archive) != ARCHIVE_SHA256 or sha(PATCH) != PATCH_SHA256:
        raise ValueError('Native security input checksum mismatch')
    with tarfile.open(archive) as bundle:
        bundle.extractall(BASE, filter='data')
    source = BASE / ('cpython-' + SOURCE_COMMIT)
    socket_source = source / 'Modules/socketmodule.c'
    if sha(socket_source) != BEFORE_SHA256:
        raise ValueError('Distributor socket source changed')
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(PATCH)], cwd=source, check=True)
    if sha(socket_source) != AFTER_SHA256:
        raise ValueError('Patched socket source differs from reviewed upstream backport')
    native, provenance = OUTPUT / 'lib', OUTPUT / 'provenance'
    native.mkdir(parents=True)
    provenance.mkdir()
    extension = '_socket' + sysconfig.get_config_var('EXT_SUFFIX')
    target = native / extension
    original = Path(sysconfig.get_config_var('DESTSHARED')) / extension
    if not original.is_file():
        raise RuntimeError('Original distributor socket extension is missing')
    command = (shlex.split(sysconfig.get_config_var('LDSHARED'))
               + shlex.split(sysconfig.get_config_var('CFLAGS'))
               + ['-fPIC', '-fstack-protector-strong', '-D_FORTIFY_SOURCE=3',
                  '-Wl,-z,relro,-z,now', '-I' + sysconfig.get_path('include'),
                  '-I' + str(Path(sysconfig.get_path('include')) / 'internal'),
                  '-I' + str(source / 'Modules'), str(socket_source), '-o', str(target)])
    subprocess.run(command, check=True)
    subprocess.run(['strip', '--strip-debug', str(target)], check=True)
    environment = dict(os.environ, PYTHONPATH=str(native) + ':' + str(source / 'Lib'),
                       PYTHONDONTWRITEBYTECODE='1')
    regression = [sys.executable, '-m', 'unittest', '-v',
                  'test.test_socket.GeneralModuleTests.test_getaddrinfo_null_bytes']
    with (provenance / 'upstream-regression.log').open('wb') as output:
        subprocess.run(regression, env=environment, cwd=BASE, stdout=output,
                       stderr=subprocess.STDOUT, timeout=60, check=True)
    # Pin the actually imported module and check a normal numeric lookup too.
    check = ('import _socket, pathlib, socket; '
             'assert pathlib.Path(_socket.__file__).resolve() == pathlib.Path(' + repr(str(target)) + ').resolve(); '
             'assert socket.getaddrinfo("127.0.0.1", 80, socket.AF_INET, socket.SOCK_STREAM, '
             'socket.IPPROTO_TCP, socket.AI_NUMERICHOST | socket.AI_NUMERICSERV)[0][4] == ("127.0.0.1", 80)')
    subprocess.run([sys.executable, '-c', check], env=environment, cwd=BASE, timeout=20, check=True)
    shutil.copyfile(PATCH, provenance / PATCH.name)
    shutil.copyfile(socket_source, provenance / 'socketmodule.c')
    shutil.copyfile(source / 'LICENSE', provenance / 'CPython-LICENSE')
    receipt = {
        'cve': 'CVE-2026-116566', 'status': 'NATIVE_BACKPORT_BUILT_UPSTREAM_REGRESSION_PASSED',
        'source_commit': SOURCE_COMMIT, 'source_url': ARCHIVE_URL, 'source_archive_sha256': ARCHIVE_SHA256,
        'upstream_main_fix': '131a3a66c5f400b588f9fd2732a5ed4e89623ee3',
        'backport_commit': BACKPORT_COMMIT, 'backport_pr': 'https://github.com/python/cpython/pull/160975',
        'backport_status_at_review': 'Open upstream PR; local backport, not an upstream released fix',
        'patch_sha256': PATCH_SHA256, 'source_sha256_before': BEFORE_SHA256, 'source_sha256_after': AFTER_SHA256,
        'original_extension_sha256': sha(original), 'extension': extension, 'extension_sha256': sha(target),
        'python_version': sys.version, 'soabi': sysconfig.get_config_var('SOABI'),
        'build_command': command, 'regression_command': regression,
        'regression_log_sha256': sha(provenance / 'upstream-regression.log'),
        'package_version_changed': False,
        'limits': ['Only the named native socket flaw is backported.',
                   'Nominal package scan findings remain visible; no ignore rule or version override.',
                   'Final image application, full socket suite and network pipeline qualification are separate.'],
    }
    (provenance / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'extension_sha256': receipt['extension_sha256']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['fetch', 'build'])
    arguments = parser.parse_args()
    (fetch if arguments.phase == 'fetch' else build)()

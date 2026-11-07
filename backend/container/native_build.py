"""Bounded, checksum-pinned source retrieval for offline native security builds."""
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def checked(path, expected):
    if sha(path) != expected:
        raise ValueError(f'Native input checksum mismatch: {Path(path).name}')


class SourceRedirect(urllib.request.HTTPRedirectHandler):
    ALLOWED = {'github.com', 'codeload.github.com', 'release-assets.githubusercontent.com',
               'objects.githubusercontent.com', 'gitlab.com', 'ftp.gnu.org'}

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if (target.scheme != 'https' or target.hostname not in self.ALLOWED
                or target.username or target.password or target.port not in (None, 443)):
            raise ValueError('Unexpected native source redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_sources(entries, folder):
    folder.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(SourceRedirect(), urllib.request.ProxyHandler({}))
    for name, spec in entries.items():
        target = folder / name
        if target.exists():
            checked(target, spec['sha256'])
            continue
        for attempt in range(3):
            partial = None
            try:
                started = time.monotonic()
                req = urllib.request.Request(spec['url'], headers={'User-Agent': 'ConflictMonitor-native-security-build'})
                with opener.open(req, timeout=30) as response, tempfile.NamedTemporaryFile(
                        mode='wb', dir=folder, prefix='.' + target.name + '.', suffix='.part', delete=False) as output:
                    partial = Path(output.name)
                    count = 0
                    while chunk := response.read1(1024 * 1024):
                        count += len(chunk)
                        if count > spec.get('max_bytes', 80_000_000) or time.monotonic() - started > 180:
                            raise ValueError('Native source download exceeds budget')
                        output.write(chunk)
                checked(partial, spec['sha256'])
                partial.replace(target)
                break
            except urllib.error.HTTPError as error:
                if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                    raise
            except urllib.error.URLError as error:
                # urllib wraps socket failures; certificate errors and permanent
                # DNS failures must not be treated as transient transport faults.
                reason = error.reason
                temporary_dns = isinstance(reason, socket.gaierror) and reason.errno == socket.EAI_AGAIN
                if not (isinstance(reason, (TimeoutError, ConnectionError)) or temporary_dns) or attempt == 2:
                    raise
            except (TimeoutError, ConnectionError):
                if attempt == 2:
                    raise
            finally:
                if partial is not None:
                    partial.unlink(missing_ok=True)
            print(f'Retrying native source {name}: attempt {attempt + 2}/3', flush=True)
            time.sleep(attempt + 1)


def extract(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(destination, filter='data')


def run(command, *, cwd, log=None, env=None, timeout=1800, check=True):
    environment = dict(os.environ, LC_ALL='C', TZ='UTC')
    if env:
        environment.update(env)
    if log is None:
        return subprocess.run(command, cwd=cwd, env=environment, timeout=timeout, check=check)
    with Path(log).open('wb') as output:
        return subprocess.run(command, cwd=cwd, env=environment, timeout=timeout,
                              stdout=output, stderr=subprocess.STDOUT, check=check)


def dynamic_symbols(path):
    output = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(path)], text=True)
    symbols = {}
    for line in output.splitlines():
        columns = line.split()
        if len(columns) < 8 or not columns[0].rstrip(':').isdigit() or columns[6] == 'UND':
            continue
        name = columns[7]
        symbols[name] = {'type': columns[3], 'binding': columns[4], 'visibility': columns[5],
                         'object_size': columns[2] if columns[3] in {'OBJECT', 'TLS'} else None}
    return symbols

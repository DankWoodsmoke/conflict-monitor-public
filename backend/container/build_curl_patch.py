"""Rebuild curl_cffi's native library with an nghttp2 backport and released zlib 1.4.

The Python distribution and nghttp2 nominal version remain unchanged. Sources are
downloaded in a bounded fetch phase; compilation, regression and linking are offline.
"""
import argparse
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET

from native_build import checked, dynamic_symbols, extract, fetch_sources, run, sha

BASE = Path('/build/curl-security')
OUTPUT = Path('/opt/curl-security')
INPUT = Path(__file__).parent
DOWNLOADS = BASE / 'sources'
IMPERSONATE_COMMIT = '98de20ee6b6ca6f755d59bc502f819079a3c94ac'
CFFI_COMMIT = 'ae03f3702678b76a2500746e1a5a7ccd1d7f6302'
SOURCES = {
    'curl-impersonate.tar.gz': ('https://codeload.github.com/lexiforest/curl-impersonate/tar.gz/' + IMPERSONATE_COMMIT, '3a159228fcde3925e6266373460b294d00b6ee9c7709b02d024a81ec1f41ebaf'),
    'curl-cffi.tar.gz': ('https://codeload.github.com/lexiforest/curl_cffi/tar.gz/' + CFFI_COMMIT, '318b852eda579c36eb58868c55f0dba6964f0121cbaabbcf03cf8e0bc972c750'),
    'brotli.tar.gz': ('https://github.com/google/brotli/archive/refs/tags/v1.2.1.tar.gz', '98d35d11a78dc453aebb7d10c3748f3f73ff78c8267c0dc697b8631f67bf7e8f'),
    'boringssl.zip': ('https://github.com/google/boringssl/archive/156c7b75ae9b8c3b3f847acf264f17594c3859fb.zip', '450e169b284697c6eafe523cb7679f4221fbe1a0993f773a566c33b188762844'),
    'nghttp2.tar.bz2': ('https://github.com/nghttp2/nghttp2/releases/download/v1.63.0/nghttp2-1.63.0.tar.bz2', '607b174554d22a828bc532d1d734fe0f729b5d5ed207f2f12e96a62e83f29c55'),
    'ngtcp2.tar.bz2': ('https://github.com/ngtcp2/ngtcp2/releases/download/v1.20.0/ngtcp2-1.20.0.tar.bz2', '871ec97ad86803cf312901b0c393b0ee70163e25a87c9b2894d1234341ce4e97'),
    'nghttp3.tar.bz2': ('https://github.com/ngtcp2/nghttp3/releases/download/v1.15.0/nghttp3-1.15.0.tar.bz2', 'c6c491a52804814098e446630e6efc459afc0d3da7952ffe6cbdc0b3f99b2b62'),
    'zlib.tar.gz': ('https://github.com/madler/zlib/releases/download/v1.4/zlib-1.4.tar.gz', '02dd159783677a749c04adbdd02b55b8a2bcc7e054f51b76b549199a916ad584'),
    'zstd.tar.gz': ('https://github.com/facebook/zstd/releases/download/v1.5.7/zstd-1.5.7.tar.gz', 'eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3'),
    'cares.tar.gz': ('https://github.com/c-ares/c-ares/releases/download/v1.34.9/c-ares-1.34.9.tar.gz', '9364b70a12eb59a06830fb488d9357f90100dff0d98b23ea3593a183d43e6f2f'),
    'curl.tar.gz': ('https://github.com/curl/curl/archive/curl-8_23_0.tar.gz', 'd0605d5883124ef5ae64c6d2b307e1417c482b362583b57491fdf37d9a99a792'),
    'libidn2-2.3.7.tar.gz': ('https://ftp.gnu.org/gnu/libidn/libidn2-2.3.7.tar.gz', '4c21a791b610b9519b9d0e12b8097bf2f359b12f8dd92647611a929e6bfd7d64'),
}
SOURCES = {name: {'url': url, 'sha256': digest} for name, (url, digest) in SOURCES.items()}
SOURCES['boringssl.zip']['max_bytes'] = 90_000_000
NGHTTP2_PATCHES = {
    'nghttp2-prerequisite.patch': 'abd281a460e9a37b78678e8dcb3acd17c25a53ba5e3b48cd7cee69fd3b78bc76',
    'nghttp2-altsvc.patch': '08892a36793baedaf255745f7e6ce00fa32434cbfbfdd8ae35a9a95408c86327',
    'CVE-2026-27135.patch': 'e3381d25b36c3db69ccc8fb482fbd1f5cd9ff26eb9867c2440d5c506f7545785',
    'nghttp2-state-tests.patch': '20d230e33b53c216198600c3ce129b49bd7eaee7997006c0e483e1e62ed471ba',
}
BORINGSSL_PATCHES = {
    'boringssl-test-deleters.patch': '798f08abe3007c84db401e6854c38bd8604208c873c266a5c8eb679176af7acb',
    'boringssl-crl-tests.patch': '51a00fabff865541d7ef4d69178c22e4ec59c246db286acf8d96949e0fe8b808',
    'boringssl-CVE-2026-35189.patch': '72dffc4128f63fdfe5a7b1cdf15db4273ed1a7fe66b6d44a34b5d4651fe7cffd',
    'boringssl-rng-thread-local.patch': '11fdd8aa9fd3ec217e0e3752efb9a9515309331abd81e98d9e989036c45667d2',
}
UPSTREAM_INPUTS = {
    'boringssl-crl-tests.upstream.patch': '5ff5e8a420bc8eb26ffec072e8430948f5948a406e4acf6596f0652dcfb1615b',
    'boringssl-CVE-2026-35189.upstream.patch': 'c58eb56d800d78f5f9ca77b4a3aefa743edf9fd0f1ed298c931e140cec952033',
}
PATCHES = {**NGHTTP2_PATCHES, **BORINGSSL_PATCHES}
BORINGSSL_SOURCE_BEFORE = {
    'crypto/x509/x509_test.cc': '8ef8e1fa3560779ec52879681ce1cd2ba81c56b6c207423c7a56d1f72873162b',
    'crypto/x509/x509_vfy.cc': '8a2fa3f8cff682ba844bc14e7d69876bd56621ffb0fc446a4b9f8c0a6cd8ea8b',
    'crypto/x509/internal.h': '155758473be9dcd73e1e2aec917fb90d5be53fcdb4b0b5d84b5a518abb882ccb',
    'crypto/x509/v3_crld.cc': 'ef3fe139c435643106414310fb4b6fbd96ac30be40afa6f5235c0f11dd81c3bb',
    'crypto/x509/v3_purp.cc': '986d0c64b92ee24987d88da1d291e247214ee4c76cb2c3aa40204c0f0b94d0a6',
    'crypto/x509/x_crl.cc': '590b05eae2e2731d71cc32e199ccd81371e772077fdfb03a44456082c9fffc02',
    'include/openssl/x509.h': 'd586f8a76bf2491b8d8f485bfded3a2ee277b3455c957947a0a5e98d43a557da',
    'crypto/fipsmodule/rand/rand.cc.inc': '5d2ed85ad4f9cd253b04ee1bad2aefbbeb5c82cf67d32ce4f55ad1fa186b5fee',
}
BORINGSSL_SOURCE_AFTER = {
    'crypto/x509/x509_test.cc': 'd71ae3ea9214eaea3336d6c9f09413018545bfc932aedd91d19f43b19ad31b4a',
    'crypto/x509/x509_vfy.cc': 'ce7c4f038be965b2d8acc001cab3142fe5eaa5c6b8e82732a19d29196c1808fb',
    'crypto/x509/internal.h': 'f183f22e1c20532cc1abe72c8d3290b188ce985d3eab180adbe60f66b92673dd',
    'crypto/x509/v3_crld.cc': '0c0c2d3e3e10ec83bb19fe19bab8939de9fa5f3bdbcb4b7efe56fa1fccc4f43c',
    'crypto/x509/v3_purp.cc': 'bb335b72ed0114524955813f48af88d5d7ba30d214c8819167b4a61374130000',
    'crypto/x509/x_crl.cc': '718fa60a617995dae563ff6d7e627323ac16ec9ce326b0a92de51a18e3a3c84e',
    'include/openssl/x509.h': 'f527abd219d923187b0f859b0a7ccad217b8859ba6fae413caa9f2251396f03a',
    'crypto/fipsmodule/rand/rand.cc.inc': '6460d5ae056c7fbbf8beeeed53253cb034368a9e3dae0a704cb04fc57175fb28',
}


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Upstream curl build recipe changed: ' + before)
    return text.replace(before, after)


def patch_nghttp2():
    for name, digest in NGHTTP2_PATCHES.items():
        checked(INPUT / name, digest)
        run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(INPUT / name)], cwd=Path.cwd())


def patch_boringssl():
    source = Path.cwd()
    for name, digest in {**BORINGSSL_PATCHES, **UPSTREAM_INPUTS}.items():
        checked(INPUT / name, digest)
    for name, digest in BORINGSSL_SOURCE_BEFORE.items():
        checked(source / name, digest)
    for name in BORINGSSL_PATCHES:
        run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(INPUT / name)], cwd=source)
    for name, digest in BORINGSSL_SOURCE_AFTER.items():
        checked(source / name, digest)


def check_boringssl(work, evidence):
    source, build = work / 'deps/src/boringssl', work / 'deps/build/boringssl'
    libraries = {name: sha(build / ('lib' + name + '.a')) for name in ['crypto', 'ssl']}
    run(['cmake', '-S', str(source), '-B', str(build), '-DBUILD_TESTING=ON'],
        cwd=work, log=evidence / 'boringssl-test-configure.log')
    run(['cmake', '--build', str(build), '--target', 'crypto_test', '--parallel', '4'],
        cwd=work, log=evidence / 'boringssl-test-build.log')
    # Test configuration must not substitute differently compiled runtime libraries.
    for name, digest in libraries.items():
        checked(build / ('lib' + name + '.a'), digest)
        checked(work / ('deps/install/lib/lib' + name + '.a'), digest)
    xml = evidence / 'boringssl-crypto-tests.xml'
    run([str(build / 'crypto_test'), '--gtest_filter=X509Test.*:RandTest.*',
         '--gtest_output=xml:' + str(xml)], cwd=source,
        log=evidence / 'boringssl-crypto-tests.log', timeout=300)
    results = ET.parse(xml).getroot()
    cases = {c.attrib['classname'] + '.' + c.attrib['name']: c
             for c in results.iter('testcase')}
    required = {'X509Test.' + name for name in ['CRLScope', 'CRLScopeNameRelativeToCRLIssuer',
                'CRLScopeTwoCRLs', 'CRLScopeNoIDP', 'CRLScopeNoCRLDistributionPoints',
                'CRLScopeReasons', 'CRLScopeOnlyUserOrCA']}
    required.update({'RandTest.NotObviouslyBroken', 'RandTest.Threads'})
    if len(cases) < 100 or not required <= cases.keys():
        raise RuntimeError('Required ordinary BoringSSL certificate/RNG tests did not execute')
    for name in required:
        if cases[name].find('failure') is not None or cases[name].find('skipped') is not None:
            raise RuntimeError('Required BoringSSL test failed or skipped: ' + name)
    return {'selected_tests': len(cases), 'failures': int(results.attrib.get('failures', 0)),
            'disabled': int(results.attrib.get('disabled', 0)),
            'skipped': [name for name, case in cases.items() if case.find('skipped') is not None],
            'required_tests': sorted(required), 'runtime_archive_sha256': libraries,
            'scope': 'Ordinary upstream certificate and RNG suites; no attack reproduction or failure injection'}


def http_regression():
    from curl_cffi import requests
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/gzip')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            body = gzip.compress(json.dumps({'message': 'native regression', 'path': self.path}).encode())
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for browser in ['chrome', 'safari', 'firefox']:
            with requests.Session(impersonate=browser) as client:
                reply = client.get(f'http://127.0.0.1:{server.server_port}/redirect', timeout=5)
                if reply.status_code != 200 or reply.json() != {'message': 'native regression', 'path': '/gzip'}:
                    raise RuntimeError('Native HTTP/decompression regression failed: ' + browser)
                print(browser + ': gzip/redirect/session PASS')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def build():
    import importlib.metadata
    if importlib.metadata.version('curl_cffi') != '0.17.0':
        raise RuntimeError('Requalify native binding before changing curl_cffi Python code')
    for name, spec in SOURCES.items():
        checked(DOWNLOADS / name, spec['sha256'])
    for name, digest in {**PATCHES, **UPSTREAM_INPUTS}.items():
        checked(INPUT / name, digest)
    extract(DOWNLOADS / 'curl-impersonate.tar.gz', BASE)
    source = BASE / ('curl-impersonate-' + IMPERSONATE_COMMIT)
    cmake = source / 'CMakeLists.txt'
    checked(cmake, 'dc1992ff7577938225e1a5719a095a069bc23f0c43467a6a6da0532570c11be7')
    text = cmake.read_text()
    text = replace_once(text, 'set(ZLIB_VERSION "1.3.1")', 'set(ZLIB_VERSION "1.4")')
    text = replace_once(text, '9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23', SOURCES['zlib.tar.gz']['sha256'])
    for variable, filename in [('BROTLI', 'brotli.tar.gz'), ('BORINGSSL', 'boringssl.zip'),
                               ('NGHTTP2', 'nghttp2.tar.bz2'), ('NGTCP2', 'ngtcp2.tar.bz2'),
                               ('NGHTTP3', 'nghttp3.tar.bz2'), ('ZLIB', 'zlib.tar.gz'),
                               ('ZSTD', 'zstd.tar.gz'), ('CARES', 'cares.tar.gz'), ('CURL', 'curl.tar.gz')]:
        text, count = re.subn(r'^set\(' + variable + r'_URL "[^\n]+"\)$',
                              f'set({variable}_URL "{DOWNLOADS / filename}")', text, flags=re.M)
        if count != 1:
            raise ValueError('Dependency source URL changed: ' + variable)
    text = replace_once(text, '  CMAKE_ARGS ${_boringssl_cmake_args}',
                        '  CMAKE_ARGS ${_boringssl_cmake_args}\n    -DCMAKE_C_COMPILER=/usr/bin/clang\n    -DCMAKE_CXX_COMPILER=/usr/bin/clang++')
    text = replace_once(text, '  PATCH_COMMAND ${PATCH_EXE} -p1 -i "${_boringssl_patch_file}"',
                        '  PATCH_COMMAND ${PATCH_EXE} -p1 -i "${_boringssl_patch_file}"\n'
                        '    COMMAND /opt/monitor/bin/python ' + str(INPUT / 'build_curl_patch.py') + ' patch-boringssl')
    start = text.index('ExternalProject_Add(nghttp2\n')
    end = text.index('\n# nghttp3', start)
    chunk = replace_once(text[start:end], 'ExternalProject_Add(nghttp2\n',
                         'ExternalProject_Add(nghttp2\n  PATCH_COMMAND /opt/monitor/bin/python ' + str(INPUT / 'build_curl_patch.py') + ' patch-nghttp2\n')
    chunk = replace_once(chunk, '-DBUILD_TESTING=OFF', '-DBUILD_TESTING=ON\n    -DCMAKE_C_STANDARD=11')
    text = text[:start] + chunk + text[end:]
    text = replace_once(text, '-DZLIB_BUILD_EXAMPLES=OFF', '-DZLIB_BUILD_TESTING=ON')
    cmake.write_text(text)
    evidence = OUTPUT / 'provenance'
    native = OUTPUT / 'lib'
    evidence.mkdir(parents=True)
    native.mkdir()
    work = source / 'build'
    idn_download = work / 'deps/downloads'
    idn_download.mkdir(parents=True)
    shutil.copyfile(DOWNLOADS / 'libidn2-2.3.7.tar.gz', idn_download / 'libidn2-2.3.7.tar.gz')
    run(['make', 'prepare-libidn2', 'JOBS=4'], cwd=source, log=evidence / 'libidn2-build.log')
    install = BASE / 'install'
    configure = ['cmake', '-S', '.', '-B', 'build', '-DSUBJOBS=4', '-DCMAKE_BUILD_TYPE=Release',
                 '-DCMAKE_INSTALL_PREFIX=' + str(install), '-DCMAKE_INSTALL_LIBDIR=lib',
                 '-DCURL_IMPERSONATE_VERSION=2.3.1-local-security']
    run(configure, cwd=source, log=evidence / 'configure.log')
    run(['cmake', '--build', 'build', '--parallel', '2'], cwd=source, log=evidence / 'build.log')
    boringssl_tests = check_boringssl(work, evidence)
    ngbuild = work / 'deps/build/nghttp2'
    ngsource = work / 'deps/src/nghttp2'
    test_command = ['cmake', '--build', str(ngbuild), '--target', 'check', '--parallel', '4']
    run(test_command, cwd=source, log=evidence / 'nghttp2-suite.log', env={'CTEST_OUTPUT_ON_FAILURE': '1'})
    shutil.copyfile(ngbuild / 'Testing/Temporary/LastTest.log', evidence / 'nghttp2-LastTest.log')
    run(['patch', '-R', '--batch', '--fuzz=0', '-p1', '-i', str(INPUT / 'CVE-2026-27135.patch')],
        cwd=ngsource, log=evidence / 'negative-patch-reversal.log')
    bad = run(test_command, cwd=source, log=evidence / 'nghttp2-negative-control.log',
              env={'CTEST_OUTPUT_ON_FAILURE': '1'}, check=False)
    negative_log = (ngbuild / 'Testing/Temporary/LastTest.log').read_text()
    if bad.returncode == 0 or 'test_nghttp2_session_verify_iframe_state[ ERROR ]' not in negative_log:
        raise RuntimeError('Original nghttp2 did not reproduce the targeted regression')
    shutil.copyfile(ngbuild / 'Testing/Temporary/LastTest.log', evidence / 'nghttp2-negative-LastTest.log')
    run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(INPUT / 'CVE-2026-27135.patch')],
        cwd=ngsource, log=evidence / 'restore-security-patch.log')
    run(test_command, cwd=source, log=evidence / 'nghttp2-restored-suite.log')
    run(['cmake', '--build', str(ngbuild), '--target', 'install', '--parallel', '4'],
        cwd=source, log=evidence / 'nghttp2-install.log')
    run(['ctest', '--test-dir', str(work / 'deps/build/zlib'), '--output-on-failure'],
        cwd=source, log=evidence / 'zlib-suite.log')
    if '100% tests passed' not in (evidence / 'zlib-suite.log').read_text():
        raise RuntimeError('zlib suite did not execute successfully')
    shared_zlib = work / 'deps/build/zlib/libz.so.1.4'
    original_zlib = Path('/usr/lib/libz.so.1').resolve()
    old_symbols, new_symbols = dynamic_symbols(original_zlib), dynamic_symbols(shared_zlib)
    if old_symbols != new_symbols or len(new_symbols) < 100:
        raise RuntimeError('Released zlib exported symbol contract differs from runtime')
    shared_output = OUTPUT / 'zlib'
    shared_output.mkdir()
    shutil.copyfile(shared_zlib, shared_output / 'libz.so.1.4')
    run(['/opt/monitor/bin/python', '-c',
         'import zlib,gzip; assert zlib.ZLIB_RUNTIME_VERSION=="1.4"; '
         'p=b"native zlib regression"*30000; assert zlib.decompress(zlib.compress(p))==p; '
         'assert gzip.decompress(gzip.compress(p))==p; print(zlib.ZLIB_VERSION,zlib.ZLIB_RUNTIME_VERSION,"PASS")'],
        cwd=BASE, env={'LD_LIBRARY_PATH': str(shared_zlib.parent)}, log=evidence / 'shared-zlib-python.log')
    (evidence / 'shared-zlib-provenance.json').write_text(json.dumps({
        'source': SOURCES['zlib.tar.gz'], 'version': '1.4', 'original_library': str(original_zlib),
        'original_sha256': sha(original_zlib), 'library_sha256': sha(shared_output / 'libz.so.1.4'),
        'exported_symbol_contract_equal': True, 'exported_symbol_count': len(new_symbols),
        'package_metadata_changed': False, 'type': 'Released upstream shared-library overlay',
        'limits': 'Symbol contract and upstream/runtime checks do not prove every ABI or input path.'}, indent=2)+'\n')
    run(['cmake', '--build', str(work / 'deps/build/curl'), '--parallel', '4'],
        cwd=source, log=evidence / 'curl-final-link.log')
    run(['cmake', '--build', 'build', '--target', 'install-all', '--parallel', '2'],
        cwd=source, log=evidence / 'install.log')
    run(['make', 'checkbuild'], cwd=source, log=evidence / 'native-version.log')
    combined = BASE / 'combined'
    combined.mkdir()
    archives = [install / 'lib/libcurl-impersonate.a'] + [work / ('deps/install/lib/lib' + name + '.a')
        for name in ['z', 'zstd', 'brotlidec', 'brotlicommon', 'brotlienc', 'nghttp2', 'nghttp3',
                     'ngtcp2', 'ngtcp2_crypto_boringssl', 'ssl', 'crypto', 'cares', 'idn2']]
    run(['gcc', '-r', '-o', str(combined / 'full.o'), '-Wl,--whole-archive'] + list(map(str, archives)) + ['-Wl,--no-whole-archive'], cwd=source, log=evidence / 'merge.log')
    run(['ar', 'rcs', str(combined / 'libcurl-impersonate.a'), str(combined / 'full.o')], cwd=source)
    shutil.copytree(install / 'include', combined / 'include')
    extract(DOWNLOADS / 'curl-cffi.tar.gz', BASE)
    binding = BASE / ('curl_cffi-' + CFFI_COMMIT)
    run(['/opt/monitor/bin/python', 'setup.py', 'build_ext', '--inplace'], cwd=binding,
        env={'IMPERSONATE_BUILD_DIR': str(combined), 'IMPERSONATE_LINK_TYPE': 'static',
             'LDSHARED': 'g++ -shared -Wl,-z,relro,-z,now'}, log=evidence / 'wrapper-build.log')
    wrappers = list((binding / 'curl_cffi').glob('_wrapper*.so'))
    if len(wrappers) != 1:
        raise RuntimeError('Expected one native curl_cffi extension')
    shutil.copyfile(wrappers[0], native / wrappers[0].name)
    probe_env = {'PYTHONPATH': str(binding), 'PYTHONDONTWRITEBYTECODE': '1'}
    run(['/opt/monitor/bin/python', str(INPUT / 'build_curl_patch.py'), 'http-regression'],
        cwd=BASE, env=probe_env, log=evidence / 'offline-http-regression.log')
    run(['/opt/monitor/bin/python', '-c', 'from curl_cffi import Curl; c=Curl(); v=c.version(); print(v.decode()); assert b"zlib/1.4" in v; c.close()'], cwd=BASE, env=probe_env, log=evidence / 'wrapper-version.log')
    run(['/usr/lib/ld-linux-x86-64.so.2', '--list', str(wrappers[0])], cwd=BASE, log=evidence / 'wrapper-linked-libraries.log')
    run(['cmake', '-P', 'build/CollectLicenses.cmake'], cwd=source, log=evidence / 'collect-licenses.log')
    shutil.copytree(work / 'licenses', evidence / 'licenses')
    # Include exact corresponding source and relink/build instructions for static LGPL parts.
    shutil.copytree(DOWNLOADS, evidence / 'sources')
    for name in ['native_build.py', 'build_curl_patch.py'] + list(PATCHES) + list(UPSTREAM_INPUTS):
        shutil.copyfile(INPUT / name, evidence / name)
    shutil.copyfile(cmake, evidence / 'CMakeLists.patched.txt')
    shutil.copyfile(ngsource / 'lib/nghttp2_session.c', evidence / 'nghttp2_session.c')
    receipt = {'status': 'NATIVE_NGHTTP2_BACKPORT_AND_ZLIB_RELEASE_BUILT_REGRESSIONS_PASSED',
               'cve': 'CVE-2026-27135', 'source': SOURCES, 'patches': PATCHES,
               'upstream_fix': '5c7df8fa815ac1004d9ecb9d1f7595c4d37f46e1',
               'upstream_tests': 'c619c7be0737ac78051b1cacf4b1ce5467eb838d',
               'test_backport_adjustments': 'Registration/header context and explicit RFC 9218 priority setup for two cases; assertions retained.',
               'nghttp2_version': '1.63.0', 'curl_cffi_version': '0.17.0', 'zlib_version': '1.4',
               'boringssl': {
                   'source_commit': '156c7b75ae9b8c3b3f847acf264f17594c3859fb',
                   'fix_commits': ['9b639f5b3b086508c03f6a4a1792e4a6043777ac', 'bee44385a528bba66abe1af553113ed9a703bf0a'],
                   'test_prerequisites': ['1ac6cdd31d02523a9aac6fe4ac35b83d7b5da202', '29af437ac41551d4276a368d9444d3d6d651b95c'],
                   'upstream_input_hashes': UPSTREAM_INPUTS,
                   'source_before': BORINGSSL_SOURCE_BEFORE, 'source_after': BORINGSSL_SOURCE_AFTER,
                   'context_adaptations': ['Two removed TODO comment spellings in test prerequisite.',
                                           'One unchanged supported-extension context line before MTC support.'],
                   'production_hunks': 'Complete upstream executable additions/removals retained; RNG patch unmodified.',
                   'ordinary_tests': boringssl_tests,
                   'coverage_limit': 'Source/advisory applicability and normal unit/compatibility tests; no exploit or failure-injection reproduction.'},
               'original_negative_exit': bad.returncode, 'wrapper': wrappers[0].name,
               'wrapper_sha256': sha(native / wrappers[0].name), 'configure': configure,
               'linkage': 'Native static components; existing distributor libstdc++ remains dynamically linked',
               'raw_scanner_record': 'Nominal nghttp2 record retained; no ignore or gate change'}
    (evidence / 'provenance.json').write_text(json.dumps(receipt, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['fetch', 'build', 'patch-nghttp2', 'patch-boringssl', 'http-regression'])
    phase = parser.parse_args().phase
    if phase == 'fetch':
        fetch_sources(SOURCES, DOWNLOADS)
    elif phase == 'build':
        build()
    elif phase == 'patch-nghttp2':
        patch_nghttp2()
    elif phase == 'patch-boringssl':
        patch_boringssl()
    else:
        http_regression()

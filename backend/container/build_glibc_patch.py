"""Exact-source local glibc backport; retain the distributor loader and APK version."""
import argparse
import json
import platform
from pathlib import Path
import shutil
import subprocess

from native_build import checked, dynamic_symbols, extract, fetch_sources, run, sha

BASE = Path('/build/glibc-security')
OUTPUT = Path('/opt/glibc-security')
INPUT = Path(__file__).parent
COMMIT = '21442dba0d0be00d8b875349ba9fc71daa1639ce'
SOURCES = {'glibc.tar.gz': {
    'url': f'https://gitlab.com/gnutools/glibc/-/archive/{COMMIT}/glibc-{COMMIT}.tar.gz',
    'sha256': '7f109affb6576a78514a7869c9a08f9ec212feef9bf1f255071f502f15445dcf'}}
PATCHES = {
    'glibc-wolfi-startup.patch': '4fb8772021dcd5f24941b4d031d10b30f81b48d885f71889c669933e5a51d142',
    'glibc-wolfi-fdo.patch': 'a187de88cb3143c440b33488793ba6dcae5aeb9710d081c587defaba0abb06b4',
    'glibc-wolfi-test-matcher.patch': 'd6a7c6a1affc812ce7f0439645bf4311d26572c73284740baeaa6e0c486bb6f3',
    'CVE-2026-84243.patch': 'ce8488c15ca46365ca76cc80ab79b742dfd6c18aeb250d3b6dfc6b03eb4b3a96',
}


def build():
    if platform.machine() != 'x86_64':
        raise RuntimeError('The glibc local backport is qualified only on Linux amd64')
    package = 'glibc-2.44-2.44-r13'
    subprocess.run(['apk', 'info', '-e', 'glibc-2.44=2.44-r13'], check=True)
    archive = BASE / 'glibc.tar.gz'
    checked(archive, SOURCES['glibc.tar.gz']['sha256'])
    for name, digest in PATCHES.items():
        checked(INPUT / name, digest)
    extract(archive, BASE)
    source = BASE / ('glibc-' + COMMIT)
    checked(source / 'intl/dcigettext.c', '91b365a3fe833bb1c2792e8376d12243e4ac334c0ad270cf599b40a36b0217cd')
    native = OUTPUT / 'lib'
    evidence = OUTPUT / 'provenance'
    native.mkdir(parents=True)
    evidence.mkdir()
    for name in PATCHES:
        run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(INPUT / name)], cwd=source,
            log=evidence / (name + '.log'))
        shutil.copyfile(INPUT / name, evidence / name)
    checked(source / 'intl/dcigettext.c', '2a3eeebf23ad689feb1b4217ca8065f9f468a6696f0a1adf818b29ded8ef54f1')
    work = source / 'build'
    work.mkdir()
    config = ('user-defined-trusted-dirs=/usr/local/lib:/usr/local/lib64:/usr/lib:/usr/lib64:/lib:/lib64\n'
              'slibdir=/usr/lib\nlibdir=/usr/lib\nrootsbindir=/usr/bin\nrtlddir=/lib64\n')
    (work / 'configparms').write_text('build-programs=no\n' + config)
    configure = ['../configure', '--prefix=/usr', '--libdir=/usr/lib', '--datadir=/usr/share',
                 '--includedir=/usr/include', '--sbindir=/usr/bin', '--host=x86_64-pc-linux-gnu',
                 '--build=x86_64-pc-linux-gnu', '--enable-bind-now', '--enable-fortify-source',
                 '--enable-stackguard-randomization', '--enable-stack-protector=strong', '--enable-cet',
                 '--with-pkgversion=glibc-2.44-r13-local-CVE-2026-84243',
                 '--disable-werror', '--disable-crypt', '--enable-kernel=4.9']
    run(configure, cwd=work, log=evidence / 'configure.log')
    run(['make', '-j4'], cwd=work, log=evidence / 'build-library.log')
    (work / 'configparms').write_text('build-programs=yes\n' + config)
    run(['make', '-j4'], cwd=work, log=evidence / 'build-programs.log')
    run(['make', '-j4', 'subdirs=intl', 'check'], cwd=work, log=evidence / 'intl-suite.log')
    result = (work / 'intl/tst-gettext-path-traversal.test-result').read_text()
    if not result.startswith('PASS:'):
        raise RuntimeError('Upstream glibc path traversal regression did not pass')
    original = Path('/usr/lib/libc.so.6')
    patched = work / 'libc.so'
    before, after = dynamic_symbols(original), dynamic_symbols(patched)
    if before != after or len(after) < 3000:
        raise RuntimeError('Rebuilt glibc exported symbol contract differs from distributor')
    (evidence / 'symbol-contract.json').write_text(json.dumps({
        'status': 'DYNAMIC_SYMBOL_CONTRACT_EQUAL', 'count': len(after),
        'limits': 'Export names/versions/type/binding/visibility/object size only; not full ABI proof.'}, indent=2)+'\n')
    env = {'GCONV_PATH': str(work / 'iconvdata'), 'LOCPATH': str(work / 'localedata')}
    probe = str(work / 'intl/tst-gettext-path-traversal')
    loader = '/usr/lib/ld-linux-x86-64.so.2'
    bad = run([loader, '--library-path', '/usr/lib', probe], cwd=work, env=env,
              log=evidence / 'original-negative-control.log', check=False, timeout=30)
    if bad.returncode != 1:
        raise RuntimeError('Original glibc did not reproduce upstream failure')
    run([loader, '--library-path', str(work) + ':/usr/lib', probe], cwd=work, env=env,
        log=evidence / 'patched-distro-loader-regression.log', timeout=30)
    shutil.copyfile(patched, native / 'libc.so.6')
    # Ship corresponding exact source, patches and build scripts with the LGPL library.
    shutil.copyfile(archive, evidence / 'glibc-source.tar.gz')
    for name in ['COPYING.LIB', 'LICENSES']:
        if (source / name).is_file():
            shutil.copyfile(source / name, evidence / name)
    for name in ['build_glibc_patch.py', 'native_build.py']:
        shutil.copyfile(INPUT / name, evidence / name)
    shutil.copyfile(source / 'intl/dcigettext.c', evidence / 'dcigettext.c')
    shutil.copyfile(source / 'intl/tst-gettext-path-traversal.c', evidence / 'upstream-regression.c')
    receipt = {'cve': 'CVE-2026-84243', 'status': 'LOCAL_BACKPORT_BUILT_UPSTREAM_REGRESSION_PASSED',
               'source_commit': COMMIT, 'source': SOURCES, 'patches': PATCHES,
               'vendor_recipe_commit': '00176b83171bc6602733ee01d708d39ffbd260da',
               'upstream_patch': 'https://inbox.sourceware.org/libc-alpha/20261012112453.47383-1-avinal.xlvii@gmail.com/raw',
               'review': 'https://sourceware.org/pipermail/libc-alpha/2026-November/181723.html',
               'review_status': 'Maintainer Reviewed-by; not yet an upstream release at review',
               'original_library_sha256': sha(original), 'library_sha256': sha(native / 'libc.so.6'),
               'retained_distributor_loader_sha256': sha(Path(loader).resolve()),
               'package_version': package, 'package_version_changed': False,
               'configure': configure, 'symbol_count': len(after), 'original_negative_exit': bad.returncode,
               'installed_scope': 'libc.so.6 only; distributor loader and other libraries retained',
               'raw_scanner_record': 'Retained; local backport does not change nominal version or gate'}
    (evidence / 'provenance.json').write_text(json.dumps(receipt, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['fetch', 'build'])
    if parser.parse_args().phase == 'fetch':
        fetch_sources(SOURCES, BASE)
    else:
        build()

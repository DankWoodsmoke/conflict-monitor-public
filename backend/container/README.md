# Restricted local media build

The backend compiles FFmpeg 9.0.2 from the original provider archive. The archive SHA-256, official RSA release-signing fingerprint and build options are fixed in `build_ffmpeg.sh`. Both archive-hash and signature verification must succeed before extraction. Build tools do not enter the final stage.

Each original HTTPS fetch has at most three attempts for named transient transport/HTTP failures, with a 15-second connection timeout and per-attempt time and size caps. Redirects stay HTTPS and stop after three hops. Backoff is one then two seconds. Certificate verification and permanent HTTP failures fail immediately. Maximum transfer/backoff budgets are 363 seconds for the archive and 93 seconds each for signature and key.

An offline build can supply the identical provider files in `container/ffmpeg-source/` in a private copy of the backend build context. Supply `ffmpeg-9.0.2.tar.xz`, `ffmpeg.tar.xz.asc`, and `ffmpeg-devel.asc` together. The builder verifies the same size bounds, pinned digest and signing fingerprint using a dedicated verification keyring. Partial bundles fail the build. The [earlier fetch gate](../../docs/qualification/2026-10-30-rc2-build-fetch-retry.json) records the RC.2 transport cases.

The worker needs local PNG and PCM/WAV inputs, libx264/AAC MP4 output, safe local concatenation, stream probing and complete H.264/AAC decoding. The build includes those components, including the concatenation-required `h264_mp4toannexb` bitstream filter. Only the `file` and `pipe` protocols are built; no network protocol is available. This component reduction does not establish that every included parser is free of vulnerabilities.

`tools/verify_container_media.py` exercises the actual source-card renderer and media worker subprocess bounds. Run it in the candidate image with no network, two CPUs, 2 GiB memory, all capabilities dropped and no new privileges. Mount `tools/` read only, an empty writable output directory, and optionally an already installed Piper voice read only. It generates authored synthetic material, not a real publisher briefing or incident footage. It verifies actual speech/audio when `--voice` is supplied, encodes two segments, concatenates, probes, fully decodes and checks rejection of HTTPS/HLS inputs. It also verifies the nonroot UID and absence of `/usr` SUID/SGID files. It never downloads a voice or uses a model service.

FFmpeg is GPL in this configuration because libx264 is enabled. Its original signed source archive, signature, signer key, build configuration and license files are retained under `/usr/local/share/ffmpeg/` in the built image. The backend uses the separately packaged Wolfi x264 runtime. Its package metadata and source recipe are separate from the application license. Anyone distributing built images must satisfy the corresponding-source and notice obligations for the included dependencies.

The image scan does not reliably identify this custom FFmpeg binary. Security qualification therefore includes an explicit version/CPE component inventory and supplemental scan, retaining all resulting advisories. See [the scoped OS review](../../docs/OS_SECURITY_REVIEW.md).

## Native Python socket security backport

The separate `socket-security-build` stage rebuilds only CPython's `_socket`
extension to reject embedded NUL characters in `getaddrinfo` host and service
arguments (CVE-2026-116566). It uses the distributor's exact CPython source
revision `3d6d2a63a23ee4d340ed8df6de0bd70ef175c4cf` and the unmodified upstream
3.12 backport `14815082af8f3c21bd50800030faed37c76296cb` from
[PR160975](https://github.com/python/cpython/pull/160975). That PR was open at
review time; this is a local backport, not a claimed upstream release.

The helper pins the archive, patch and socket source hashes before and after
patching, uses matching versioned Python headers, and runs the upstream malformed
input regression with Docker networking disabled. A normal numeric lookup and
the loaded module's path are checked too. Only the extension and its source,
license, patch and build receipt enter the final image; compilers and test files
stay in the build stage. Provenance is under
`/usr/local/share/cpython-security/CVE-2026-116566/`.

Python's reported version and APK metadata stay unchanged. Raw security matches
remain visible, and final-image application/pipeline qualification is still
required. This patch does not address the separate SQLite or glibc findings.

## Native C library security backport

`glibc-security-build` compiles the distributor's exact glibc source revision
`21442dba0d0be00d8b875349ba9fc71daa1639ce`, retains its three vendor build
patches and adds the reviewed upstream LANGUAGE path-traversal repair for
CVE-2026-84243. The [upstream review](https://sourceware.org/pipermail/libc-alpha/2026-November/181723.html)
accepted the patch; it was not an upstream released fix at review time.
The build copies only `libc.so.6`, preserving the distributor loader, other
runtime libraries and APK metadata. It enforces the upstream regression,
failure of the original library on that same input, success with the retained
loader, and equality of exported symbol names, versions, types, bindings,
visibility and object sizes. That symbol comparison is not a full ABI proof.
This recipe currently rejects architectures other than Linux amd64.

The exact source archive, patches, LGPL text, build scripts, logs and native
hash receipt are included in `/usr/local/share/glibc-security/CVE-2026-84243/`.
The source-stage qualification separately exercised 1057 broader tests and
24 internationalization tests; 79 explicit platform/resource skips remain.
Final-image application, database and long-session checks are separate gates.

## curl and zlib native security build

`curl-security-build` retains curl_cffi 0.17.0's Python code and rebuilds its
native extension from the pinned curl-impersonate 2.3.1 source. The nghttp2
1.63 priority interface is required by that implementation. The build applies
the [upstream CVE-2026-27135 fix](https://github.com/nghttp2/nghttp2/commit/5c7df8fa815ac1004d9ecb9d1f7595c4d37f46e1)
and its prerequisites instead of inventing a higher version. The upstream
regression is adapted only for 1.63 test registration and explicit priority
setup. All 214 primary and five allocation-failure cases must pass; removing
the security patch must make its regression fail before the patch is restored.

The bundled and shared zlib libraries are built from the official
[1.4 release](https://github.com/madler/zlib/releases/tag/v1.4). Its 18 upstream
tests, the shared-library symbol contract and a Python compression roundtrip
run offline. The runtime replaces the old shared-library file and verifies
`ZLIB_RUNTIME_VERSION == "1.4"`. Wolfi's original APK record remains unchanged;
the explicit native-overlay receipt reports the actual new bytes and version.
The rebuilt binding uses the existing distributor `libstdc++` dynamically.
Chrome, Safari and Firefox profile HTTP redirects, sessions and gzip responses
are exercised against a local test server. This is not an Internet-provider
availability test or proof of every TLS/HTTP input.

All dependency downloads are hash pinned and bounded. The build/test phase
runs with networking disabled. Original component versions, patches, full
corresponding source archives, licenses and build/relink instructions remain
under `/usr/local/share/curl-security/`, including the static LGPL components.
Raw package and supplemental vulnerability records remain independently
visible; local fixes do not rewrite scanner results.

The BoringSSL source remains pinned to `156c7b75ae9b8c3b3f847acf264f17594c3859fb`.
Two official upstream repairs are applied: [CVE-2026-35189](https://boringssl.googlesource.com/boringssl/+/refs/heads/main/docs/advisories/2026-09-29.md)
removes relative CRL distribution-point expansion during certificate processing,
and [the RNG fix](https://github.com/google/boringssl/commit/bee44385a528bba66abe1af553113ed9a703bf0a)
removes a duplicate free after thread-local setup failure. The latter has no
invented CVE or severity. The preceding upstream CRL test addition and its two
C++ ownership-helper declarations are retained.
Only two old TODO-comment spellings and one unchanged pre-MTC context line
are adapted to the pinned source; all executable additions/removals remain.
Original upstream patches accompany the adapted inputs, with exact before/after
hashes for all eight affected files and zero-fuzz patch application.

The build runs ordinary upstream `X509Test` and `RandTest` cases, explicitly
requiring all seven added CRL tests and the normal RNG/thread tests. The test
configuration must leave the installed crypto/SSL archives byte-identical.
Test results and any skips enter the native provenance. No exploit, attack-input
or RNG failure-injection reproduction is performed for these repairs; source
ancestry, the official advisory, ordinary unit tests and normal TLS compatibility
provide separate evidence. Commit-only inventory matching cannot establish
complete BoringSSL vulnerability coverage.

## FFmpeg source backports

The restricted 9.0.2 build also applies the official HDR serializer,
empty-string replacement and encryption-list/MOV repairs for
CVE-2026-107676, CVE-2026-107677 and CVE-2026-107678. The full MOV repair
includes iterative list freeing, serialized side-data append and linear-time
`pssh` collection. Only the development-branch API-change note and version
bump are excluded from the append backport; implementation and upstream test
changes remain intact. Nominal FFmpeg and library versions are unchanged.

Build-time probes check all three repaired behaviors, including a deep list
under a bounded stack, and run the upstream encryption-info test. Original
negative controls and an actual MP4 with 12,000 `pssh` records were separately
qualified. Patches, applied-source hashes, probe source and build evidence
are retained under `/usr/local/share/ffmpeg/security/`. No network or additional
media format is enabled by these repairs. RTSP and libssh remain excluded
components; that is a separate applicability finding, not a code-patch claim.

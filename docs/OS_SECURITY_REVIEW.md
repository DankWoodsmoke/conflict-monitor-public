# Scoped container OS security review

## Candidate 17 review - November 6, 2026

**RC.5 source release candidate; public hosting is not approved.** Independent candidate 17 component and post-soak official-source refresh reviews are complete; the scoped four-hour checks completed. The exact five-image build passed against 545 frozen source files. Relative to candidate 16, only the NASA public-observation scheduler and its tests changed. Candidate 17 receipt SHA-256: `9a4e12bb8d52cba94f38174bb8291c51a89a3d7fb5697d519fa5974167883649`.

All five candidate 17 immutable images and three measured native inventories were freshly scanned with verified Grype 0.121.2 and the retained checksummed official DB built `2026-11-06T06:21:59Z`. There were no ignore rules, VEX filters, version substitutions or threshold changes. These eight image/inventory scans executed before the soak; the later official metadata and advisory reads refreshed their applicability after completion. The subsequent 39-source official fetch and late database recheck completed after the long runs; independent root review accepted their scoped findings. The official database tuple was unchanged, so these eight scan executions were retained rather than rerun or relabeled.

| Exact image role | Raw package-match records | Scoped component assessment |
| --- | --- | --- |
| Backend `872cb9a8c9a3` | 2 High, 1 Medium, 1 Low | Standalone SQLite recovery shell/code absent; exact-source glibc local repair; socket Medium locally repaired. Python `http.client` Low remains affected. |
| Database `6ab01325b27c` | 1 High, 3 Medium | Standalone SQLite recovery shell/code absent. Three Medium package aliases refer to one affected BusyBox advisory. |
| Operator `129c0ce54b9a` | 3 Medium | One affected BusyBox advisory across three package matches. |
| Public `c3f87024649f` | 3 Medium | One affected BusyBox advisory across three package matches. |
| Tunnel `bfb6f3c1f3f5` | 0 records | Scanner result only; no unknown-flaw or live-tunnel clearance. |

| Separate measured native inventory | Raw records |
| --- | --- |
| Restricted FFmpeg | 1 High, 10 Medium |
| curl extension/static components | 1 High, 1 Medium |
| PostgreSQL/PostGIS native components | 2 High, 1 Medium |

The eight reports retain **30 raw records, 24 product/CVE rows and 21 distinct CVEs: 8 locally fixed rows, 12 affected-code-absent rows and 4 affected residual rows**. Every finding and its vulnerability/advisory metadata matches the earlier candidate 16 scan under this database. Backend/database and all three supplement scans still return raw High-threshold exit2. The scoped repair/absence evidence addresses the reviewed named High conditions; it does not erase scanner records. Backend Python Low `CVE-2026-103995` and database/operator/public BusyBox Medium `CVE-2025-60876` remain affected. No zero-vulnerability claim is made.

Fresh installed candidate 17 native/source/archive/provenance measurements, complete SQLite shell/code absence and ordinary positive lookup/SELECT/media-linkage checks passed. Every measured native field equals candidate 16. Four roles have complete newly inspected RootFS, Config, OS and architecture equality to16. **The backend RootFS differs.** Its Config/OS/architecture are unchanged, while the changed application is independently measured before and after the packaged UID10001 test suite. The market/yfinance client caller, native build/dependency inputs and actual installed wrapper/library bytes match; the NASA module AST outside its scheduler function is unchanged. Dependency-layer equality is supplemental evidence, not a claim that the whole backend is identical.

The fresh **candidate 17 installed TLS 32** execution passed 25 genuine HTTP/2 exchanges, six strict certificate/hostname rejection cases and one offline yfinance constructor check, without a PYTHONPATH override. The two synthetic fixture containers used an internal-only network with no host ports or external provider calls; exact owned cleanup passed. Receipt SHA-256: `500f49fa6db4e92da13067ba04a5b6029ba6ba7b634abf00f67a7a929b5cde8e`. This is a new candidate 17 execution, unlike the historical TLS 15 execution transferred for16.

A separate fresh candidate 17 packaged suite passed **1,254 tests plus 29 subtests, zero skipped**, with actual process/kernel UID and GID10001 recorded at pytest entry and completion. It used the immutable image, network isolation, read-only root and temporary test tooling; all loaded application modules resolved to packaged `/app/app` files, source bytes matched before/after, and owned cleanup passed. The 27 test-only wheels reused their original verified provenance; no fresh wheel download is implied. Receipt SHA-256: `1f28bdf60ae34444e13cca677390e8d3c6d477a4f3c4f9f739b1402b3d097788`. Candidate 16's earlier root and nonroot suites remain historical separate executions.

The 217 ordinary nghttp2, 117 BoringSSL certificate/RNG and 18 zlib stage cases remain **historical executions transferred by exact native/source/provenance identity**, not new candidate 17 runs. The ordinary nghttp2/BoringSSL suites had no skips. Historical socket/glibc/FFmpeg evidence retains its original scope: 62 socket platform/resource skips and glibc unsupported cases are not erased by the new application's zero skips. No new crafted-input or failure-injection tests were executed for this transition.

The client retains nominal nghttp2 1.63.0 and RFC 7540 priority processing with 15 reviewed official backports. Complete CONNECT/glitch series 2485/2488/2508/2509/2510/2598/2599/2607/2856 is present. Protocol handling intentionally rejects invalid client CONNECT HEADERS/PUSH_PROMISE and uses the generic glitch counter, including frequent received PRIORITY frames, with a 10,000 burst/330-per-second default. This is not full 1.71 equivalence. The normal direct TLS 32 fixture does not establish end-to-end HTTP/2 forward-proxy behavior.

PR 2943 remains scoped to the selected curl client: the actual final receive parser checks `!session->server` and rejects PRIORITY_UPDATE before payload handling. This is more than a server assertion that release compilation could omit. The new candidate 17 binding combines the retained root semantic review with the identical parser manifest/native wrapper and independently measured selected app caller; independent root candidate 17 review confirmed this exact binding, preserving the server and protocol limitations. Server APIs remain compiled and unpatched for that separate scope. Optional BoringSSL DTLS hardening 7017746 also remains separately scoped and unpatched; it is not claimed absent or repaired. The official certificate-validation and RNG backports remain installed. Static subsets and commit-only dependencies retain scanner-coverage limitations.

Six FFmpeg Medium findings concern IMF, G2M, PCX, Sun Raster, CDXL and Huffyuv code excluded from the restricted build. Retained source/configuration/object/symbol evidence and ordinary positive MOV/PNG controls bind to newly measured equal ffmpeg/ffprobe bytes. Shipping retained source for licensing is not compiled-code presence. SQLite recovery-shell absence is likewise a specific applicability finding, not a blanket SQLite security claim.

New matrix validation checked **155 referenced evidence files and every record from all eight raw scans**. Matrix SHA-256: `1b33c780058500029c84e0a1d44db61d20c474925c93b2099c96fe8aed11f0fc`; validation: `898c65b8a4656fe36987cd7d0bddcf4adb349500dec8c8c2b771be2bf22bcf3e`. Independent root review rechecked **155 matrix references and 1,239 total evidence/source entries**, including the frozen and working source hashes, all eight raw scan records and fresh runtime identity measurements. It confirmed four complete role identities, the explicit changed backend, actual installed app/native/caller proof and fresh TLS 32. Review SHA-256: `32c557afe42b265bac3148e341b68d6aa9b0ea213a532422bdd4f77b938080f9`. These are local, scoped reviews rather than vendor attestations, a successful raw High gate or public-site approval. Initial private17 projection labels were corrected in a separately retained v2; original outputs and scan evidence were preserved.

Candidate 16's main and supplemental long runs were invalidated after the expected second NASA refresh was absent. A separately reproduced skipped-work scheduling defect justified the17 fix; its responsibility for that particular live symptom remains **UNVERIFIED**. Partial candidate 16 observations do not qualify a four-hour run, and no post-candidate16 freshness fetch was executed. Candidate 16 finite Google 21/Media results and their explicit exceptions remain historical; they cannot establish new candidate 17 long-session success. Earlier pre-raster browser matrices establish only their recorded control/network assertions.

**COMPLETED, SCOPED FOUR-HOUR CHECKS:** candidate 17's five main observers and two separate operator/public composed-raster observers each completed at least 14,400 seconds with 480 samples. Both parents and all seven observers exited zero; the later parent cleanup ended at **2026-11-06T17:10:31.949267Z**, following the 13:10:01Z start. Independent review verified unchanged source/helper and five-service identities, natural second NASA publication, Google session renewal, successful tile requests begun after three hours, and the applicable HTTP/download/SQL/rendered-scene checks. The offline proof projectors accepted these completed records. This is a bounded local execution, not provider uptime, location truth, memory-leak freedom, fresh AI/video generation or public-host approval. Rehearsals and interrupted candidate 16 observations supplied no elapsed-time credit.

Independent candidate 17 component-security review checked **155 matrix references and 1,239 total evidence/source entries**. The later post-soak official-source review independently rehashed **1,363 references**. Its 39-source fetch began at **2026-11-06T17:15:42.110772Z**, after both completed-run parent cleanups; semantic review ended at **17:34:12.501576Z**. The late official database recheck completed at **17:31:46.547865Z** with the same verified tuple, so the eight earlier exact-image/native scans were retained, not relabeled as new executions. They retain 30 raw records and 24 role/CVE rows across 21 CVEs: 8 fixed, 12 affected-code-absent and 4 affected residual rows. Raw High-threshold exit2 findings remain alongside exact repair/absence evidence; BusyBox Medium and Python Low remain affected. The reviewed image/native High conditions are addressed within their stated scope; separate host Critical/High issues remain unresolved. This is not a zero-vulnerability or public-host approval claim.

**Release evidence boundary:** final packaging requires independently admitted six-proof evidence, unchanged runtime identity, reviewed source/export and the exact-source hosted CI jobs. The release workflow enforces the later publication and asset-verification steps; their actual result belongs to the exact GitHub release/verification receipt. These local records do not assert a future CI result, published tag, asset checksum or authenticated/anonymous download success. Public hosting remains unapproved. No matrix or draft OpenVEX was passed to Grype as a suppression file. New advisories or changed client/server/DTLS conditions require renewed review. Independent post-soak review SHA-256: `4d78214101bb401559dfe90221e9c7dfa83d77c7340fd08d7317508bbbaf3636`.

## Separate Windows host-security deployment blocker

**This measured Windows PC is not admitted for public hosting.** The November 6 read-only host inventory measured Docker Desktop 4.63.0, Engine 29.2.1, WSL 2.6.3.0 and the running amd64 WSL kernel 6.6.87.2. Docker's CNA places these product/platform versions in scope for CVE-2026-112917 (Critical 9.2, WSL isolation), CVE-2026-17106 (High 7.1, archive extraction) and CVE-2026-114409 (Medium 5.7, credential logging). Actual credential exposure, exploitation and compromise were not established; no credential logs or secrets were inspected. [Docker release notes](https://docs.docker.com/desktop/release-notes/), [WSL issue](https://www.cve.org/CVERecord?id=CVE-2026-112917), [archive advisory](https://github.com/moby/go-archive/security/advisories/GHSA-hfg8-hc9c-6c3h), [logging CNA](https://www.cve.org/CVERecord?id=CVE-2026-114409).

The corresponding Microsoft kernel source also lacks the checksum-start guard associated with CVE-2026-99999 (Linux CNA Critical 9.3). This is source/version applicability evidence; exact installed kernel binary provenance and current attack reachability remain unverified. The cited path concerns a local/guest virtual-device boundary, not a demonstrated direct Internet receive path. Upstream fixed branches include 6.6.159 and 6.18.57. **Docker Desktop 4.98.0 plus WSL 3.0.3 is the joint minimum for the AF_VSOCK issue, but is not established as sufficient for all four issues:** WSL 3.0.3 depends on Microsoft kernel 6.18.54.1, whose reviewed source still lacks the separate kernel guard. A supported patched kernel/runtime or a separately qualified patched Linux host is required before public-host admission; no custom kernel backport has been built or qualified. [Linux CNA](https://www.cve.org/CVERecord?id=CVE-2026-99999), [Microsoft WSL 3.0.3](https://github.com/microsoft/WSL/releases/tag/3.0.3), [Microsoft kernel dependency](https://github.com/microsoft/WSL2-Linux-Kernel/releases/tag/linux-msft-wsl-6.18.54.1).

A vendor prerelease path is available: WSL 3.0.5 release notes name kernel 6.18.58.1-1, and the retained review found the checksum-start guard in Microsoft kernel 6.18.58.1 source. This package/kernel was not installed or locally qualified. Availability of a source fix is separate from exact installed binary provenance and attack reachability; stable WSL 3.0.3 remains insufficient for the separate checksum issue. A selected supported patched runtime or independently qualified Linux host remains a deployment requirement. [Microsoft WSL 3.0.5 prerelease](https://github.com/microsoft/WSL/releases/tag/3.0.5), [Microsoft kernel source release](https://github.com/microsoft/WSL2-Linux-Kernel/releases/tag/linux-msft-wsl-6.18.58.1).

These four host issues are separate from the application's **24 role/CVE rows and 30 raw image/native scanner records**. Successful application tests or a source prerelease do not repair the host or approve deployment. This bounded four-advisory review is not an exhaustive Windows, Docker, containerd or runc assessment. The host inspection changed no runtime or service; the five candidate 17 identities remained unchanged during that inspection. The main/raster scoped checks and independent later 39-source review have completed; final source/release admission remains separate from host deployment approval.

The retained read-only installer inventory identifies EXE-managed Docker Desktop registration: the uninstall executable is Docker Desktop Installer.exe, with no WindowsInstaller flag or product GUID recorded. The vendor MSI upgrade warning remains conditional; it is not proof that this installed EXE-managed deployment follows the affected MSI path. The inventory and maintenance proposal authorize no uninstall, update or restart. Preserve and restore-test protected data before a separately reviewed maintenance window; completed application checks do not qualify host maintenance or recovery.

## Historical security evidence and stage-specific status

Historical browser matrices executed before the composed-raster guard qualify only their recorded control, layout, transport and provider/network assertions. They do not retrospectively establish visible photographic output. A blank candidate 14 WebKit capture exposed that coverage gap and prompted the current guard. Historical candidate 16 finite pixel/raster evidence and its explicit binding addendum remain separate; older uses of "Google pass" must not be read as photographic-render qualification.

The following archive describes earlier source/stage/image states. Earlier "pending", "blocked", "final" or "fixed" text is historical, and its image hashes remain authoritative for those executions only. Candidate 17's current applicability and unfinished release gates are stated above; candidate 16's incomplete long runs do not qualify candidate 17; earlier CONNECT or raw-version-only blockers are not silently carried forward as current flaws, and prior successful suites are not new executions.

### Additional native repairs prepared on November 6

The source now includes real local repairs for glibc CVE-2026-84243,
nghttp2 CVE-2026-27135 and FFmpeg CVE-2026-107676/107677/107678, plus the
official zlib 1.4 release for the backend's bundled and shared library.
These changes preserve original package/version records where a native
overlay or backport is used. They do not edit scanner output or relax a gate.
The [source recipes and provenance](../backend/container/README.md) describe
the exact inputs, original negative controls and corresponding-source files.

The glibc source stage passed its 24 internationalization tests and a separate
broader run with 1057 passes, 79 explicit unsupported cases and zero failures.
Two unsupported IDN cases require a shared libidn2 not installed in that stage.
The original runtime fails the upstream traversal regression; the rebuilt
library passes with the original distributor loader. All 3169 exported-symbol
contracts match, with the documented limits of that comparison. The
[maintainer review](https://sourceware.org/pipermail/libc-alpha/2026-November/181723.html)
supports the local patch; it is not represented as a released vendor update.

The nghttp2 backport passes 214 primary tests and five allocation-failure
tests. Reversing only its security patch makes the new state-machine case
fail; restoring it passes again. zlib 1.4 passes 18 upstream tests and the
shared-library contract comparison. The [official release](https://github.com/madler/zlib/releases/tag/v1.4)
also addresses invalid-window/reset and other memory defects beyond the
previously cataloged compression finding. Actual final TLS/HTTP2 and media
linkage checks remain separate from these source-stage results.

The explicit BoringSSL source review identified two additional repairs missing
from the July 8 pin: the official CVE-2026-35189 CRL-distribution-point fix and
the upstream RNG thread-local cleanup fix. The former applies to ordinary
TLS clients verifying server certificates, according to the
[BoringSSL advisory](https://boringssl.googlesource.com/boringssl/+/refs/heads/main/docs/advisories/2026-09-29.md).
The source recipe now retains both complete upstream fixes, their exact source
and patch hashes, and the ordinary upstream certificate/RNG test prerequisite.
Context adaptations affect comments or unchanged surrounding lines only.
No BoringSSL attack reproduction or failure-injection result is claimed.
The patched source stage passes 117 ordinary certificate/RNG tests with zero
failures or skips and local Chrome/Safari/Firefox HTTP compatibility. The test
prerequisite includes two unchanged upstream C++ ownership-helper declarations;
the initial compile failure without them is retained. Final TLS/HTTP2 and
immutable-image binding remain required before admission. Commit-only scanner matching and an
empty GitHub advisory page do not establish BoringSSL security clearance.

All three FFmpeg probes distinguish the original and repaired code. An actual
MP4 containing 12,000 `pssh` boxes times out after five seconds on the original
ffprobe and parses on the repaired prototype in approximately 0.05 seconds
under the same bounded stack and memory profile. The full encryption repair
includes both iterative freeing and linear-time MOV side-data append; the
upstream encryption-info test also passes. Network and format capabilities
remain restricted.

Source/build/binary evidence supports a separate excluded-component assessment
for SQLite's standalone recovery shell, FFmpeg RTSP/libssh and nghttpx's proxy.
Their absence must be rebound to every final image; nominal library matches
remain in raw reports. PostGIS's earlier FlatGeobuf backport also requires the
final database regression binding. BusyBox's Medium advisory and Python's
separate Low advisory remain recorded. Final exact-image scans, independent
applicability review, complete pipeline tests and soak qualification are still
required before these source-stage results can support publication.

### Fresh baseline and native Python repair on November 6

Grype 0.121.2 with the checksummed official database built November 5 at
06:21:06 UTC rescanned the running RC.4 images by immutable ID. Backend
`461a1de0b150` has **two High, one Medium and one Low**; database `ce9ac0177644`
has **one High and three Medium**; frontend `f69b04afa3c9` has **three Medium**.
No ignore rule was used. Backend and database still fail the raw High gate.
These findings describe the running baseline, not subsequent source builds.

The newly reported backend records are glibc **CVE-2026-84243** (High) and
CPython **CVE-2026-116566** (Medium). The glibc advisory requires attacker
control of `LANGUAGE`, an appropriate non-C locale and a readable crafted
catalog. The measured runtime has `LC_MESSAGES=C`, `LANG=C.UTF-8` and only
C.utf8 locale data. That context does not patch the library; the current
upstream advisory has no fixed commit and the distributor recipe remains
unchanged. [GNU libc advisory](https://sourceware.org/cgit/glibc/plain/advisories/GLIBC-SA-2026-0025)

A network-disabled test confirmed that the original Python module silently
truncates NUL-containing numeric hosts and services. The source Dockerfile now
has a separate native build stage applying the exact pending upstream 3.12
backport. The isolated prototype passes the upstream malformed-input regression;
its socket suite reports 733 tests: **671 passed and 62 explicit
platform/resource skips**. The original module fails the malformed-input
negative control. The final source stage
also passes its offline build-time regression and rejects altered archive,
patch and Python-version fixtures. Final runtime integration is a separate
qualification. The Python APK version and raw scanner match remain visible.
[Upstream fix](https://github.com/python/cpython/commit/131a3a66c5f400b588f9fd2732a5ed4e89623ee3)  / 
[Pending 3.12 backport](https://github.com/python/cpython/pull/160975)  / 
[Source recipe](../backend/container/README.md#native-python-socket-security-backport)

The final local candidate 3 was separately qualified on November 6. Its backend
is `sha256:eacb139a6fc8c19664acb578a40e8fbf9dda4448b1eb49615961f88613dc9638`
and its public frontend is
`sha256:a5a5495bcf6d4c5687b86898ac9cb9f9ed9a781309e68ec6afa53b45c21411b9`.
The exact backend passed the 15 malformed-input subcases and the full socket
suite with **671 passed and 62 skipped**, using only a read-only upstream test
mount, with no application-source override. Installed native bytes, embedded
patch provenance and the unchanged Python package version were verified.

Fresh scans of those two exact images with the same November 5 advisory snapshot
retain **two High, one Medium and one Low backend records** and **three Medium
public-frontend records**. The backend High records are SQLite
CVE-2026-119586 and glibc CVE-2026-84243; the nominal Python Medium record remains
visible despite the qualified native backport. The three frontend records are
one CVE, CVE-2025-60876, matched to `busybox`, `busybox-binsh` and `ssl_client`.
Package-match counts are not distinct-vulnerability counts. No ignore rule or
release-gate change was used; the backend raw High gate still fails. These are
local candidate results, not evidence of a public deployment or website admission.

Fresh supplemental native scans retain FFmpeg **one High/four Medium**,
curl's bundled libraries **one High/two Medium**, and database native
components **two High/one Medium**, including separately assessed nominal
PostGIS and SQLite matches. None of these records was suppressed by the
Python repair or SQLite component analysis. Candidate 3's FFmpeg, ffprobe,
curl binding and SQLite shared-library hashes match the previously inventoried
bytes, binding the supplemental assessments to that backend. Supplemental and
image-match counts must not be added as if they were distinct vulnerabilities.

### RC.4 SQLite admission

The backend build rejects an installed SQLite shell package, an executable
on the command path, or a file or symlink named `sqlite3` under the runtime
paths checked by its Dockerfile. Independent negative controls exercised
each kind of shell presence. The SQLite library supports the live market
cache in the backend and PROJ coordinate transformations in the database.

The fresh baseline scans retain the same SQLite-wide High match. A harmless
CLI reproducer on released 3.54.1 and a pinned 3.55.0 development check-in
confirmed that both shells still emit the injected recovery-output line.
Neither shell ships in the measured runtime. The raw severity threshold
remains a publication gate. [SQLite release history](https://www.sqlite.org/changes.html)  /  [Published CVE record](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2026/119xxx/CVE-2026-119586.json)

### RC.3 candidate on November 4

Grype 0.121.1 used the official advisory database built on November 4 at 06:20 UTC. The Wolfi backend has one High and one Low. The reduced Alpine database image has one High and three Medium. The nginx frontend has three Medium and zero High or Critical. These raw counts include all matches in scope, with no ignore rules. Both backend and database still fail the release's raw High threshold.

The same scanner and advisory database found two Critical and 78 High on the prior local Debian backend, and 12 Critical and 138 High on the prior Trixie database. The two RC.3 replacements have zero Critical. This comparison uses exact runtime image IDs and reports scanner records.

The backend retains a digest-pinned Python 3.12 base, signature-verified FFmpeg with local file and pipe protocols, and nonroot UID 10001. The database retains PostgreSQL 17.11, reduced PostGIS 3.6.4 with the reviewed FlatGeobuf backport, and a locally built signed SQLite 3.54.1 shared-library package with its true upstream origin. It uses the signed Alpine su-exec package to drop to UID 70. The shipped Compose check measured zero effective capabilities and no published database port.

The remaining raw High in both images is CVE-2026-119586. The advisory names the SQLite CLI recovery functionality. The measured images contain the linked library, and the SQLite shell executable is absent. The supplemental native database scan also retains the nominal PostGIS FlatGeobuf version match and the backport evidence separately. Raw scanner findings stay visible. See the [published CVE record](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2026/119xxx/CVE-2026-119586.json) and [database upgrade notes](DB_UPGRADE.md).

### Backend remediation qualified separately on October 30

The final backend is `sha256:9b094edd5879d47d682c62dbb81f977b9ed5597058aa3f4a162434bd31c02877`. The [complete sanitized remediation projection](qualification/2026-10-30-backend-security-remediation.json) retains every backend match, supplemental native-component match, exact image/source hashes, version comparisons, executed media checks and limits. Its complete 90-package inventory and 209-record match multiset equal the prior `1762839c...` candidate; the RC.2 packaged-source binding is separate from that older image's tests. The subsequent [actual-image 597-test run](qualification/2026-10-30-rc2-linux-backend-597-export-rebind.json), [database cutover/regressions](qualification/2026-10-30-rc2-database-cutover-and-regressions.json) and [real RSS-to-MP4 execution](qualification/2026-10-30-rc2-local-generation.json) provide separate completed runtime evidence. This static security review did not perform the live cutover and does not turn those behavioral checks into vulnerability clearance.

Grype 0.121.0 was still the official latest release when checked. Its freshly downloaded/checksummed official database was built **2026-10-29 06:23:34 UTC**. Empty registry auth, disabled external lookups and local immutable image targets were retained; no source/image upload or ignore rule was used. Under the same new database, the previous backend has 819 match records, including 14 Critical and 346 High. The restricted candidate has **209 image-scan records: 2 Critical, 73 High, 64 Medium, 16 Low and 54 Negligible**. The raw High gate still fails. These are record counts, including aliases, rather than unique vulnerabilities or exploitability verdicts.

The material change removes the general-purpose Debian FFmpeg dependency stack: installed Debian binary packages decrease from **292 to 90**. The current Python 3.12 base digest was already the latest official branch image, so no untested Python-major or OS-family replacement was used. A build stage verifies both the SHA-256 and official RSA signature of original **FFmpeg 9.0.2** source, then compiles the formats actually required by local source cards. Only `file` and `pipe` protocols, PNG/PCM/H.264/AAC decoders, local image/WAV/MOV/concat demuxers and required encoders/muxers remain. The first candidate failed concatenation because its required `h264_mp4toannexb` filter was absent; that failed image/receipt is preserved. The repaired candidate passed the complete path.

The initial RC.2 hosted builds subsequently failed fetching official FFmpeg bytes (one connection timeout, one TLS reset); their custom runtime checks were skipped, not passed. A [build-only retry repair](qualification/2026-10-30-rc2-build-fetch-retry.json) adds three bounded attempts for named transient errors, HTTPS-only bounded redirects and unchanged time/size/authenticity gates. Eight actual shell-prefix falsifiers ran offline in an existing Linux container with mocked transport and real original SHA/PGP verification, covering recovery, exhaustion, permanent failures and tampering. The full extract/compile/install tail matches the initial source commit. Running image bytes and observers were not rebuilt or changed. The subsequent [qualified-source hosted build](qualification/2026-10-30-rc2-hosted-qualified-source-ci.json) passed; the original failures remain retained rather than relabeled.

The image runs as UID 10001 and strips SUID/SGID bits from `/usr`. Actual offline qualification repeated on the final image under dropped capabilities, no new privileges, a read-only root filesystem, two CPUs and 2 GiB memory passed **11 checks**: original card rendering, real CPU Piper speech and audio gates, two H.264/AAC segments, safe concatenation, probing, complete audio/video decoding and explicit HTTPS/HLS rejection. The MP4 is an authored synthetic fixture, not a publisher report or incident footage; no byte identity to the earlier TTS output is claimed. The earlier `1762839c...` image ran **574 Linux tests plus 29 subtests, zero skips**, using read-only test/source mounts and development dependencies in a disposable layer. That remains historical evidence. The final `9b094edd...` application bytes independently passed **597 tests plus 29 subtests, zero skipped**, importing `/app/app` without mounting application source. The [later tool/source rebind](qualification/2026-10-30-rc2-linux-backend-597-export-rebind.json) retains that same image and full-suite result; its disposable root test context does not replace the separate nonroot runtime checks.

All **209/209** image records have explicit vendor/CNA assessments: **25** meet measured Debian fixed-version boundaries, **177** remain vendor-open, **six** remain within Python CNA affected ranges, and one Python record excludes the installed branch version. The two Critical records are OpenSSL generic-CPE matches whose installed Debian source version meets the recorded backport boundaries; they are preserved in the raw scan. Vendor-open High findings include privileged mount/ACL operations, particular libc/libstdc++ operations and command/module-specific paths. Nonroot execution, absent privileges and the removed SUID bits reduce named preconditions; they do not patch those packages. Perl `Archive::Tar` and `Pod::Text` modules and C++ headers were absent in the measured runtime. Broader transitive input flow remains unqualified. The zlib CNA range for CVE-2026-85091 starts at 1.3.1.2, while the measured runtime is 1.3.1; Debian still marks the branch open, so that scope conflict remains explicit.

Automatic image inventory **missed the custom FFmpeg executable**. A separate explicit FFmpeg component/CPE scan therefore retains **five more records: one High and four Medium**. The High RTSP issue and SFTP/DASH paths name components that are not compiled. The HDR-metadata issue and necessary MOV-demuxer `pssh` recursion issue remain retained. The reviewed route consumes private generated files and accepts no uploaded media or caller-supplied media URL. That exposure boundary is not exhaustive parser safety or a malicious-input campaign. Source, build flags and GPL notices are described in [the build recipe](../backend/container/README.md).

The actual `curl_cffi` native version string was inventoried separately, because a Python package audit does not qualify statically bundled C libraries. Nine reported components produce **three supplemental records: one High and two Medium**. Its nghttp2 1.63.0 is deliberately pinned by the [immutable upstream build recipe](https://github.com/lexiforest/curl-impersonate/blob/98de20ee6b6ca6f755d59bc502f819079a3c94ac/CMakeLists.txt). The [nghttp2 advisory](https://github.com/nghttp2/nghttp2/security/advisories/GHSA-6933-cjhr-5qg6) distinguishes assertion-enabled builds. The nominal recipe uses Release/NDEBUG, and five sampled assertion-expression strings are absent from the exact wheel binary. This is consistent build evidence, not proof of every compiler flag or an exploitability test; the High record remains. The other records concern the unshipped nghttpx proxy and zlib CRC-combine APIs. Direct application use was not found, but transitive coverage is incomplete. BoringSSL reports no commit in the native version string and remains an inventory/provenance limit.

The admitted 229-test frontend image is `sha256:71dae32e0eb066f835426cdbce78c9d6a0eaedbc51a19cd835edfdb3b7012ce0`. Its [fresh exact-image rebind](qualification/2026-10-30-frontend-security-rebind-71dae-final229.json) uses the verified Grype executable and unchanged local database built October29 06:23:34UTC: **three Medium BusyBox records, zero High/Critical**, raw High gate exit0, no ignore rule or external lookup. All72 actual APK package rows and the complete package/version/vulnerability/severity/fix multiset equal the earlier `4236ac47` baseline. That baseline scan was reused, not rerun; inventories were actual network-disabled, read-only one-shot filesystem reads. Scanner/config/cache and empty Docker credentials were explicit; the vulnerability database hash stayed unchanged. The previous [b6e6 scan](qualification/2026-10-30-frontend-security-rebind-b6e6-final224.json) remains preserved for its own bytes.

The [229-image live admission](qualification/2026-10-30-rc2-frontend-timeline-admission-229.json) records start identity2026-10-30T05:43:01.56454013Z and healthy status:97 exported frontend files,63 tested source files, all403 served static files (402 application files plus nginx error page), all402 local application bytes, seven header/cache cases and UID101/zero effective capabilities/no-new-privileges/read-only root. The timeline-key ownership repair changes product bytes; earlier `b6e6` finite browser checks and its interrupted observations are not carried forward. Final duration and exact merge/tag/archive binding are recorded only in the release-attached verification JSON. No OS finding is waived by UI or duration tests. Earlier `b6e6`, `4236ac47`, `03b08ff4` and RC.1 scans remain dated evidence.

The workflow now also has a separate **45-minute shipped-Compose profile job**, preserving the existing Python/frontend jobs. Its [actual local preflight](qualification/2026-10-30-compose-profile-ci-preflight.json) built all three runtime images, initialized a unique test database with generated fixture credentials, ran the real role/PostGIS/TCP/WebSocket gates without provider ingestion, and passed PID1/capability/port/mount/bootstrap-secret and seven served-header/cache cases. All 56 packaged application/migration source files matched the checked-out source. Only the job's four containers and two volumes were removed. Host orchestration was Windows with Linux containers; a hosted Actions pass is not inferred from that local run. The new job and QA tools retain sanitized measurements and do not emit environment values or original source bodies.

The subsequent [actual hosted run41003507817](qualification/2026-10-30-rc2-hosted-qualified-source-ci.json) passed all three jobs on exact source `b15a60eb...`, including the new custom-image build, initialization, restricted-role/PostGIS/TCP, packaged-source, process-boundary and seven header checks. This is independent hosted execution, not an extrapolation of the local preflight. Its newly built image IDs remain distinct from the admitted local images; no whole-image byte identity or new OS vulnerability clearance is inferred. Final source/tag and long-session admission are separate release-attached results; this source snapshot does not assert their future outcome.

### Independent database-candidate review on October 30

The separately built database candidate `sha256:fc61b5645ca9a0115ef9a4fab2f0a3b35006c90a05d5511c5c010786da75ba65` has **412 raw image records: 10 Critical, 117 High, 100 Medium, 39 Low, 129 Negligible and 17 Unknown**, compared with 750 records for the previous pinned image under the same fresh database. Its 164 installed Debian binary packages retain PostgreSQL 17.11 and the core PostGIS 3.6.4 profile while excluding raster, address standardizer and SFCGAL. The exact final image was rescanned: its entire package inventory and match multiset equal the prior `c0ba...` candidate, while its newly compiled PostGIS shared library is separately hashed and is not claimed byte-identical. This static review did not deploy it or inspect production data. The [full independent database projection](qualification/2026-10-30-database-security-review.json) records all raw matches, source-version comparisons, supplemental components and the limits of backport review.

All **412/412** records are explicitly assessed: **29** meet exact distributor fixed-version boundaries, **382** remain vendor-open and one is a component mismatch involving absent `sudo`. A nominal PostgreSQL/PostGIS supplemental scan adds two retained records. PostgreSQL's CVE-2017-8806 actually concerns Debian `postgresql-common` scripts; measured `293.pgdg13+1` meets its fixed-version boundary. PostGIS CVE-2026-73515 remains visible under nominal version 3.6.4, with a pinned upstream FlatGeobuf validation backport applied. The independent review downloaded the primary patch anew, verified both embedded patch hashes, and established that the adaptation changes only the two documented released-branch numeric conversion contexts. Its length/verifier/property/geometry guards and regression changes otherwise match. The [separate executed qualification](qualification/2026-10-30-rc2-database-cutover-and-regressions.json) records346 CUnit tests/5,495 assertions and two complete250-case SQL runs (500 executions,250 distinct cases), exact native-byte binding and a full ten-table/five-sequence logical restore. Passing those tests does not clear the retained vendor-open findings.

The remaining Critical records require their actual inputs to be considered. The TIFF advisory names `tiffcrop`, which is absent; that is a component observation, not a patched-library assertion. Curl records concern particular HTTP/2 or credential-reuse modes, rather than every PROJ operation. The XML parser finding remains retained for controlled SQL/XML/GML/KML use; the application's public RSS parser uses Python `defusedxml`. Keep database access restricted and PROJ network access disabled. These restrictions do not clear arbitrary SQL, hostile identity-file mounts, all native parsers or another deployment profile.

Gosu 1.20 replaces the older identity-file parser, but reports Go 1.24.6. The image scanner did not enumerate its static Go runtime/modules. The [separate actual Go binary review](qualification/2026-10-30-gosu-go-binary-review.json) uses official govulncheck 1.9.0 in binary/symbol mode on the exact final gosu bytes. It retains **63 module-level and three package-level finding messages, with zero identified affected-symbol findings**; the Go database reports its own last-modified timestamp. Exit 0 alone was not treated as no findings. This bounded static analysis does not prove absence of vulnerabilities or replace runtime/input review. Unknown scanner severity and unqualified paths remain visible.

### Scope and retained scan results

Grype 0.121.0 scanned local immutable Docker images using database v6.1.10 built 2026-10-28 06:23:30 UTC. Application updates, external vulnerability lookups and registry credentials were disabled during scanning; no image or source was uploaded. Its archive matched the official immutable-release asset digest and published checksum. The downloaded Sigstore bundle was not independently cryptographically verified. See the [official release](https://github.com/anchore/grype/releases/tag/v0.121.0).

| Image scope | Retained match records | Reported severity counts | Raw high-severity gate |
| --- | ---: | --- | --- |
| Earlier backend `4202bfc7...` | 817 | 14 Critical, 346 High, 247 Medium, 25 Low, 168 Negligible, 17 Unknown | Failed; findings retained |
| Pinned PostgreSQL/PostGIS `1ac10b25...` | 748 | 31 Critical, 181 High, 164 Medium, 52 Low, 286 Negligible, 34 Unknown | Failed; findings retained |
| Earlier patched frontend `cb2cc67e...` | 3 | 3 Medium | Passed; residual findings retained |

These are scanner **records**, including package aliases and generic binary CPE matches, not unique CVE counts. The database row describes the measured pinned image; deployment/restoration qualification is separate. The [public finding projection](qualification/os-security-findings.json) retains all 1,568 records and their reported severity/fix state, plus the limited vendor/CNA review. Untriaged records remain explicitly untriaged. No ignore rule was added to obtain a passing result.

The [historical image receipt](qualification/os-security-current-images.json) binds those local scans to the then-deployed backend `sha256:4202bfc7add922228c024623b1879ccec7eaf617c718d583b69568b440f90788` and frontend `sha256:cb2cc67e72d8c1fc67049c6b91d621ee2e31de0be3e3c4ccda4890a791e5422a`. The backend repeat completed at 08:25:21 UTC on October 29; its package/version/CVE/severity/fix-state multiset is identical to the original `a57a1426...` scan, with no added or removed matching records. Its raw high-severity gate still fails. The frontend exact-image scan completed at 08:45:18 UTC and retains the same three Medium BusyBox-family records as the earlier `02ee9066...` scan, with no High/Critical matches in that advisory snapshot. These repeats do not rescind unresolved findings or independently re-audit the database, builder or host.

### Frontend remediation and exact runtime binding

The pinned nginx base lacked distributor fixes for Brotli/curl. `frontend/Dockerfile` now installs exact versions `brotli-libs=1.2.1-r0`, `curl=8.23.0-r0` and `libcurl=8.23.0-r0`. The [Alpine 3.24 main security dataset](https://secdb.alpinelinux.org/v3.24/main.json) and APK version comparisons informed the patch. All 49 fixable Brotli/curl/libcurl match records were removed: 52 records before, three after. This does not mean 49 unique CVEs were fixed.

The earlier OS-only frontend deployment was `sha256:36ea69972eb3d50d1ead2419695300f282b34f0a1c0a6ddb2fcf6822862ea29a`. All 11 filesystem layers exactly matched its independently scanned qualification image. Actual installed package versions were read from its APK database. All 400 application assets and nginx's `50x.html` matched the pre-patch application bytes; `nginx -t` passed. That frontend-only recreation left the backend and database image/start-time identities unchanged. The [historical sanitized runtime receipt](qualification/frontend-os-runtime.json) preserves those identities and comparisons. The same 26 browser accessibility states and 20 bounded focus checks passed after that deployment; their manual-review limits remain in [Earth verification](../frontend/EARTH_VERIFICATION.md). Later application/source-policy changes produced `02ee9066...`; a later layout/severity-label repair produced the separately scanned `cb2cc67e...` image. The earlier byte-equality statement does not claim those later application bytes are unchanged.

BusyBox `1.37.0-r31` remains reported for [CVE-2025-60876](https://security.alpinelinux.org/vuln/CVE-2025-60876), through `busybox`, `busybox-binsh` and `ssl_client`. Alpine labels it possibly vulnerable; the scan supplies no fixed version. The issue concerns attacker-influenced request targets passed to BusyBox wget. The inspected healthcheck uses a fixed localhost target. That observation does not establish every applet/input path to be unreachable and does not remove the finding.

### Distributor backports and remaining backend findings

Generic upstream version comparisons can miss Debian backports. Primary per-CVE [Debian tracker data](https://security-tracker.debian.org/tracker/data/json), installed source versions and `dpkg --compare-versions` were used for explicit mappings. Sixty-one retained records meet their distributor fixed-version boundaries: 23 OpenSSL records in each Debian image, 14 FFmpeg records in the backend, and one XZ record in the upgrade candidate. Seven distinct installed/fixed version pairs passed comparison. This narrow result does not resolve other records or turn the raw backend/database scan into a pass.

Eight FFmpeg advisories remain open for Debian `7:7.1.5-0+deb13u1`: CVE-2026-107695, CVE-2026-70632, CVE-2026-107697, CVE-2026-70628, CVE-2026-70631, CVE-2026-70629, CVE-2026-70630 and CVE-2026-107660. For example, [CVE-2026-107695](https://security-tracker.debian.org/tracker/CVE-2026-107695) remains postponed for this branch and concerns crafted HLS playlists. These findings are retained, including duplicate package/CPE records.

The inspected local video route accepts bounded source IDs behind administrator authentication. Its worker creates local PNG cards and WAV narration, invokes FFmpeg through argument arrays, concatenates generated segments, then probes and fully decodes the output. The examined route does not accept uploaded media or a caller-supplied media URL. This is source-level exposure analysis of that path, not a malicious-input test or proof that every codec, protocol, dependency, future route or compromised local file is safe.

PSF CNA records also refine seven Python 3.12.16 matches. CVE-2026-12345 has a branch-specific fix boundary at 3.12.15, below the installed interpreter; the upstream platform/file-flag caveats remain. The measured Linux interpreter reports symlink-resistant `rmtree`. The other six broad affected ranges are retained: CVE-2025-12781 and CVE-2026-3446 (`base64`), CVE-2025-15366 (`imaplib`), CVE-2025-15367 (`poplib`), CVE-2026-6019 (`http.cookies.Morsel.js_output`) and CVE-2026-3479 (`pkgutil.get_data`, disputed documentation/security-model issue). Direct project-source searches found no use of those six APIs; third-party/transitive use was not exhaustively audited. The CNA URLs and version ranges are preserved in the public finding projection. No blanket Python exemption is claimed.

### Unpatched identity-file parser in the database candidate

The measured upgrade candidate contains gosu 1.19 with `github.com/moby/sys/user v0.1.0`. [GHSA-mjcv-p78q-w5fw](https://github.com/moby/sys/security/advisories/GHSA-mjcv-p78q-w5fw), fixed in that module at v0.4.1, remains present. It can exhaust memory when processing an attacker-controlled user/group database file.

In the isolated qualified profile, `/etc/passwd` and `/etc/group` were root-owned and not writable by PostgreSQL UID 999; only the database data volume was mounted. Those observed input constraints are an applicability assessment, not a package fix, a universal waiver or a claim about other deployment profiles. Reassess after identity-file mounts, privileges, image contents or entrypoint inputs change. See [database upgrade qualification](DB_UPGRADE.md).

### Limits

The measured advisory data and image identities are dated snapshots. Known-source version matching does not detect unknown vulnerabilities or replace application exploitability testing. Alpine fixed-boundary data does not enumerate every open issue; missing coverage is unknown, not a pass. Host/Docker daemon, browser/GPU, builder stages, deployment configuration and a full transitive input-flow audit remain outside this review. Rebuilds or input-surface changes require renewed package and runtime qualification.

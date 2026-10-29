# Scoped container OS security review

Measured on 2026-10-29. This review retains unresolved findings; it is not a zero-CVE, exploitability or whole-system security clearance. Python/npm advisory checks cover different dependency sets and do not audit database images, OS packages, builder stages or the host kernel.

## Scope and retained scan results

Grype 0.121.0 scanned local immutable Docker images using database v6.1.10 built 2026-10-28 06:23:30 UTC. Application updates, external vulnerability lookups and registry credentials were disabled during scanning; no image or source was uploaded. Its archive matched the official immutable-release asset digest and published checksum. The downloaded Sigstore bundle was not independently cryptographically verified. See the [official release](https://github.com/anchore/grype/releases/tag/v0.121.0).

| Image scope | Retained match records | Reported severity counts | Raw high-severity gate |
| --- | ---: | --- | --- |
| Current backend `4202bfc7…` | 817 | 14 Critical, 346 High, 247 Medium, 25 Low, 168 Negligible, 17 Unknown | Failed; findings retained |
| Pinned PostgreSQL/PostGIS `1ac10b25…` | 748 | 31 Critical, 181 High, 164 Medium, 52 Low, 286 Negligible, 34 Unknown | Failed; findings retained |
| Current patched frontend `cb2cc67e…` | 3 | 3 Medium | Passed; residual findings retained |

These are scanner **records**, including package aliases and generic binary CPE matches, not unique CVE counts. The database row describes the measured pinned image; deployment/restoration qualification is separate. The [public finding projection](qualification/os-security-findings.json) retains all 1,568 records and their reported severity/fix state, plus the limited vendor/CNA review. Untriaged records remain explicitly untriaged. No ignore rule was added to obtain a passing result.

The [current-image receipt](qualification/os-security-current-images.json) binds fresh local scans to the exact deployed backend `sha256:4202bfc7add922228c024623b1879ccec7eaf617c718d583b69568b440f90788` and frontend `sha256:cb2cc67e72d8c1fc67049c6b91d621ee2e31de0be3e3c4ccda4890a791e5422a`. The backend repeat completed at 08:25:21 UTC on October 29; its package/version/CVE/severity/fix-state multiset is identical to the original `a57a1426…` scan, with no added or removed matching records. Its raw high-severity gate still fails. The frontend exact-image scan completed at 08:45:18 UTC and retains the same three Medium BusyBox-family records as the earlier `02ee9066…` scan, with no High/Critical matches in that advisory snapshot. These repeats do not rescind unresolved findings or independently re-audit the database, builder or host.

## Frontend remediation and exact runtime binding

The pinned nginx base lacked distributor fixes for Brotli/curl. `frontend/Dockerfile` now installs exact versions `brotli-libs=1.2.1-r0`, `curl=8.23.0-r0` and `libcurl=8.23.0-r0`. The [Alpine 3.24 main security dataset](https://secdb.alpinelinux.org/v3.24/main.json) and APK version comparisons informed the patch. All 49 fixable Brotli/curl/libcurl match records were removed: 52 records before, three after. This does not mean 49 unique CVEs were fixed.

The earlier OS-only frontend deployment was `sha256:36ea69972eb3d50d1ead2419695300f282b34f0a1c0a6ddb2fcf6822862ea29a`. All 11 filesystem layers exactly matched its independently scanned qualification image. Actual installed package versions were read from its APK database. All 400 application assets and nginx's `50x.html` matched the pre-patch application bytes; `nginx -t` passed. That frontend-only recreation left the backend and database image/start-time identities unchanged. The [historical sanitized runtime receipt](qualification/frontend-os-runtime.json) preserves those identities and comparisons. The same 26 browser accessibility states and 20 bounded focus checks passed after that deployment; their manual-review limits remain in [Earth verification](../frontend/EARTH_VERIFICATION.md). Later application/source-policy changes produced `02ee9066…`; the final narrow layout/severity-label repair produced the separately scanned current `cb2cc67e…` image. The earlier byte-equality statement does not claim those later application bytes are unchanged.

BusyBox `1.37.0-r31` remains reported for [CVE-2025-60876](https://security.alpinelinux.org/vuln/CVE-2025-60876), through `busybox`, `busybox-binsh` and `ssl_client`. Alpine labels it possibly vulnerable; the scan supplies no fixed version. The issue concerns attacker-influenced request targets passed to BusyBox wget. The inspected healthcheck uses a fixed localhost target. That observation does not establish every applet/input path to be unreachable and does not remove the finding.

## Distributor backports and remaining backend findings

Generic upstream version comparisons can miss Debian backports. Primary per-CVE [Debian tracker data](https://security-tracker.debian.org/tracker/data/json), installed source versions and `dpkg --compare-versions` were used for explicit mappings. Sixty-one retained records meet their distributor fixed-version boundaries: 23 OpenSSL records in each Debian image, 14 FFmpeg records in the backend, and one XZ record in the upgrade candidate. Seven distinct installed/fixed version pairs passed comparison. This narrow result does not resolve other records or turn the raw backend/database scan into a pass.

Eight FFmpeg advisories remain open for Debian `7:7.1.5-0+deb13u1`: CVE-2026-107695, CVE-2026-70632, CVE-2026-107697, CVE-2026-70628, CVE-2026-70631, CVE-2026-70629, CVE-2026-70630 and CVE-2026-107660. For example, [CVE-2026-107695](https://security-tracker.debian.org/tracker/CVE-2026-107695) remains postponed for this branch and concerns crafted HLS playlists. These findings are retained, including duplicate package/CPE records.

The inspected local video route accepts bounded source IDs behind administrator authentication. Its worker creates local PNG cards and WAV narration, invokes FFmpeg through argument arrays, concatenates generated segments, then probes and fully decodes the output. The examined route does not accept uploaded media or a caller-supplied media URL. This is source-level exposure analysis of that path, not a malicious-input test or proof that every codec, protocol, dependency, future route or compromised local file is safe.

PSF CNA records also refine seven Python 3.12.16 matches. CVE-2026-12345 has a branch-specific fix boundary at 3.12.15, below the installed interpreter; the upstream platform/file-flag caveats remain. The measured Linux interpreter reports symlink-resistant `rmtree`. The other six broad affected ranges are retained: CVE-2025-12781 and CVE-2026-3446 (`base64`), CVE-2025-15366 (`imaplib`), CVE-2025-15367 (`poplib`), CVE-2026-6019 (`http.cookies.Morsel.js_output`) and CVE-2026-3479 (`pkgutil.get_data`, disputed documentation/security-model issue). Direct project-source searches found no use of those six APIs; third-party/transitive use was not exhaustively audited. The CNA URLs and version ranges are preserved in the public finding projection. No blanket Python exemption is claimed.

## Unpatched identity-file parser in the database candidate

The measured upgrade candidate contains gosu 1.19 with `github.com/moby/sys/user v0.1.0`. [GHSA-mjcv-p78q-w5fw](https://github.com/moby/sys/security/advisories/GHSA-mjcv-p78q-w5fw), fixed in that module at v0.4.1, remains present. It can exhaust memory when processing an attacker-controlled user/group database file.

In the isolated qualified profile, `/etc/passwd` and `/etc/group` were root-owned and not writable by PostgreSQL UID 999; only the database data volume was mounted. Those observed input constraints are an applicability assessment, not a package fix, a universal waiver or a claim about other deployment profiles. Reassess after identity-file mounts, privileges, image contents or entrypoint inputs change. See [database upgrade qualification](DB_UPGRADE.md).

## Limits

The measured advisory data and image identities are dated snapshots. Known-source version matching does not detect unknown vulnerabilities or replace application exploitability testing. Alpine fixed-boundary data does not enumerate every open issue; missing coverage is unknown, not a pass. Host/Docker daemon, browser/GPU, builder stages, deployment configuration and a full transitive input-flow audit remain outside this review. Rebuilds or input-surface changes require renewed package and runtime qualification.

> Historical October28 qualification. Superseded by the current Earth/local-generation receipt in VERIFICATION.md; its four-view layout and disabled-AI/video statements describe the earlier image.

# Free-profile release-candidate verification

Checked **2026-10-28 America/Chicago**. Candidate: **0.2.0-rc.1**. This receipt supersedes the initial blocked-infrastructure snapshot preserved in `VERIFICATION_PHASE1.md`. The source baseline remains the April8 server backup plus the preserved local changes. The qualified profile is the bounded free-source deployment with Google Earth geographic context; optional paid model/video features are outside this clearance. No GitHub release or repository visibility change has been performed.

## Executed application checks

| Check | Result | Scope |
| --- | --- | --- |
| Windows backend suite | **248 passed +29 subtests** | Final suite completed in15.00seconds. Synthetic provider fixtures are distinguished from the actual persistence/network checks below. |
| Production-platform backend suite | **248 passed +29 subtests;0 skipped** | Python3.12.16 in an ephemeral Linux production-image container;9.55seconds, exit0. Locked development dependencies were installed for the tests; no private credentials were mounted. The rebuilt image matched the running backend, and76 source/tool hashes remained unchanged. |
| Frontend suite | **73 passed in7 files** | Final `npm test` run; includes source states, unscored reports, reconnect recovery, pagination/replay, memory-only Google configuration and keyboard navigation. |
| Frontend build | **PASS** | TypeScript and the production Vite build completed. Docker's static nginx frontend serves the resulting application through the same-origin API proxy. |
| Frontend dependency audit | **0 reported vulnerabilities** | Final resolved dependency tree, including browser-test development dependencies. |
| Production Python dependency audit | **0 known findings across66 packages** | Executed against the production image. This is a dated vulnerability-database result, not a guarantee against unknown issues. |
| Production browser workflows | **3/3 passed in7.6seconds** | Actual Docker/nginx deployment and real non-demo database rows. Google was supplied through the normal server `/config` public browser-key path, without `CM_GOOGLE_KEY` test injection. |
| Restart persistence | **PASS;64 original rows retained** | A backend application restart preserved the original64 rows and their raw-text fingerprint. The PostgreSQL MD5 equality check is a regression comparison, not an authenticity proof. `/health` returned healthy after restart. |
| Bounded API concurrency sample | **140 requests,10 concurrent,0 errors; all required responses200** | Observed p50 23.93ms, p95 85.19ms, max124.82ms. This short local sample does not certify sustained throughput, Internet latency or a long operational soak. |

### Public machine receipts

The sanitized, reviewable receipts are included in this source snapshot:

- [Linux production-platform backend run and source manifest](qualification/linux-backend-final.json)
- [Final backend coverage summary](qualification/backend-coverage-summary.json)
- [Dated live deployment/source-count snapshot](qualification/live-deployment-final.json)
- [Actual12-check database/TCP/WebSocket pipeline result](qualification/live-pipeline-final.json)
- [Bounded API concurrency sample](qualification/live-api-load.json)
- [Restart/persistence equality regression](qualification/restart-verification.json)
- [Production Python and frontend dependency-audit summary](qualification/dependency-audit-summary.json)
- [Final production frontend/browser run and source manifest](qualification/frontend-production-final.json)
- [Reproduced Media error153 before the repair](qualification/media-youtube-before.json) and [selected playback after the repair](qualification/media-youtube-after.json)

These files preserve the checks' scopes and limitations. Private environment files, raw provider/authentication logs and credential-bearing runtime artifacts are excluded.

### Measured execution coverage

The final backend coverage receipt reports **60.08%** combined statement/branch coverage: **62.47%** of statements (**2710/4338**) and **51.69%** of branches (**641/1240**). This is about60% combined coverage, not an every-line or every-branch verification claim. The tests establish the exercised contracts and regressions; they cannot prove that all retained code is correct, optimal or production-ready.

## Docker and actual PostGIS

The Docker startup blocker was resolved by quarantining two stale AF_UNIX runtime endpoint entries through rename. Existing Docker data was preserved; no factory reset, reboot or deletion was used.

Actual PostgreSQL/PostGIS migrations completed through `0003_geography_index`. The baseline now inspects the application's `public` schema explicitly, accepting fresh PostGIS extension tables while still refusing an existing application schema. Tests exercise that distinction. Actual query plans confirmed that the geography-expression index serves the meter-distance clustering query; the tiny history sample legitimately chose a sequential scan and sort. These small-table plans are observations, not a production-scale benchmark.

The isolated qualification database and the clean live display database are separate. The live snapshot contained **0 synthetic rows**. The qualification database contains explicit synthetic fixtures and must never be displayed as live intelligence.

`tools/verify_postgis.py` and `tools/verify_live_pipeline.py --public-feed` ran against real persistence. The latter uses an actual Uvicorn TCP/WebSocket server, not transport or database mocks. Its12 checks cover free RSS persistence/delivery, Unicode, immutable source revisions, failed/undated receipts, bounded oversized-content identities, scoped Telegram processing and monotonic checkpoints, timestamp/ID pagination, creation-ID recovery for newly inserted reports with older publication times, SQL-bounded JSONB snapshots, attributed briefs, query indexes and fail-closed administrative/paid operations. The bounded public BBC step persisted real source reports. Usage-log entries did not increase.

## Bounded real-source snapshot

The final live deployment receipt records64 persisted source rows:53 RSS reports (BBC20, Al Jazeera14, Guardian19),9 Telegram reports and2 NASA thermal-observation records. Its provider-cache snapshot contained3 aircraft,88 vessels,45 orbital records and342 FIRMS observations. These are dated sample counts that can change with polling, expiry and source coverage; counts do not establish factual accuracy or completeness.

- **RSS:** real publisher feeds are ingested in free `reports` mode. Publisher-authored metadata remains attributed, unclassified and unscored; no paid extraction, invented location or automatic confirmation is required.
- **Telegram:** the inherited session authenticated successfully. Three explicitly selected public channels (`qudsnen`, `osint613`, `osintdefender`) each processed3 messages. The API exposed `ok`, no auth/provider error, `history_complete=false` and the limit3. No joining, sending or interactive OTP flow was used. Bounded reads and source/publication ages remain visible; this is not a historical-completeness claim.
- **CelesTrak:** live OMM retrieval and epoch-aware propagation worked with45 records, alongside offline six/nine-digit identifier and failure-cache tests. Propagated orbits are modeled positions, not imagery or a certified real-time orbit solution.
- **Aircraft/AIS:** real responses populated the caches. Coordinates, identities, declared units and source ages have dedicated validation/expiry tests. Receiver coverage, reported identity and registry-derived classification retain their limits.
- **NASA FIRMS:** a live response yielded342 thermal observations;2 eligible observations persisted and live delivery was checked. A thermal anomaly does not establish a strike, its cause, actor, casualties or independent incident corroboration.
- **Free Brief:** a persistent attributed source digest compiles cited reports without a model, risk score, causal inference or fabricated narration. API risk remains `UNASSESSED`/null. An unchanged source hash does not generate a duplicate digest.
- **Media and markets:** the deployed UI exercises their provider/availability surfaces. An iframe-load event is not a listener/playback proof. Market fetch time and observation time remain separate; a network response does not establish a fresh or complete price record. Unavailable, disabled and stale states remain explicit.

## Production browser and Google Earth

The final normal-configuration browser run passed all3 Playwright workflows on the Docker/nginx application, using actual non-demo source rows and live Google photorealistic tiles. It exercised Map, Earth, Media and Brief, source-health presentation, keyboard/Settings dismissal and390×844 portrait navigation. The all-tabs workflow observed no page errors. The earlier live-only Leaflet renderer teardown failure was reproduced and repaired before this run; its local renderer extension must be retested when Leaflet changes.

Google was configured through the server's explicit public browser-key fields. No `CM_GOOGLE_KEY` test injection was used in the final automatic-Google run. Browser API keys are intentionally public to their browser and require provider/API/referrer restrictions and quotas; no private model/session/admin credential belongs in that response. Application code keeps the browser key in React memory rather than browser storage. Google/provider attribution remains visible. Imagery dates and coverage vary; Google Earth supplies geographic context, not event-date or incident-location evidence.

A production Media-frame failure was also reproduced: YouTube returned error153 when the application's prior iframe policy suppressed `Referer`. The iframe now uses `strict-origin-when-cross-origin`, matching the [YouTube embedded-player identity guidance](https://developers.google.com/youtube/terms/required-minimum-functionality#api-client-identity-and-credentials) and [error153 definition](https://developers.google.com/youtube/iframe_api_reference#onError). The selected recorded reference subsequently played after a native Play click: after6seconds its media time was5.66072seconds, `paused=false`, `readyState=4`, with no player error. This verifies that bounded selected playback path and removes the reproduced error153; it does not certify every stream or future provider availability.

Long-range timeline ticks are bounded by viewport spacing; keyboard stepping no longer inverts the requested range. Empty source filters, mapped-only report counts, free source-digest labels and whole-loaded-set source counts have dedicated regressions.

The synthetic showcase remains an explicit separate mode. Live request failure cannot silently become synthetic data. The dated NASA Black Marble2016 reference texture is not current satellite evidence.

## Remaining limits and publication state

| Area | Boundary |
| --- | --- |
| Every-line/best-possible claims | Unsupported. Combined backend execution coverage is about60%, and no test suite proves global optimality. Retained inactive/reference components are not qualified active capabilities. |
| Optional model-assisted analysis | Disabled in the free profile. Schema/citation-ID checks do not establish semantic entailment or multilingual extraction accuracy. No new model was benchmarked or promoted by these free-profile checks. |
| Optional narration/video | Disabled and semantically/operationally unqualified. Legacy dependencies, fonts, deployment paths, timings and produced-media quality need their own executed qualification. |
| Reconnect updates | The creation-ID recovery contract reconciles newly created Event IDs. Updates/revisions to existing IDs require a distinct update/revision cursor and remain outside that recovery contract. |
| Existing historical deployment | The former VPS was unreachable and the owner selected the April backup baseline. A data-preserving restore/migration of a historical nonempty production schema remains a separate rehearsal; this baseline does not guess such a migration. |
| Accessibility/devices/soak | Keyboard flows and desktop-browser portrait emulation were exercised. Physical mobile hardware, a screen-reader audit, long-duration WebGL/resource behavior and a long operational soak remain unqualified. |
| Performance | The140-request local sample is bounded evidence, not sustained-load or service-level certification. Provider/native threads already executing cannot be forcibly killed by asyncio; status does not claim otherwise. |
| Source/data/asset rights | Provider attribution and redistribution terms remain distinct from code licensing. Existing cartographic assets retain the documented lineage/rights limits; no blanket dataset-rights clearance is claimed. |
| GitHub CI/publication | CI is authored but has not run on GitHub. No publication, private-repository visibility change or public release is performed by this receipt. |

The final content scan covered179 allowlisted files with0 detected credential findings. The public export uses immutable scanned-byte manifests. That bounded gate is not exhaustive secret clearance. Generate the source candidate after documentation reconciliation with `python tools/release_gate.py --package-candidate`; the archive contains `RELEASE_MANIFEST.json` and has an adjacent `.zip.sha256` receipt. Packaging does not change the qualification limits or publish a GitHub release.

# Frontend live-pipeline verification

Checked 2026-10-28 America/Chicago. Original project and credentials were not edited. All changes here belong to the isolated release candidate.

## Executed results

- `npm test`: **73 passed** in 7 files. Includes unclassified/unscored free reports, missing location, null briefing scores, source publication versus fetch age, tracking expiry after backend failure, serial polling, malformed snapshots, explicit disabled/failed markets, external-frame availability limits, Telegram bounded-history receipts, reconnect recovery with older publication times, concurrent live delivery, pagination, limits and cancellation, plus live-server Google defaults, manual-session precedence, readable 244-day timeline labels, duration-preserving keyboard navigation, accurate filter/mapped counts, and YouTube-compatible referrer policy.
- `npm run build`: TypeScript and production Vite build pass.
- `npm audit`: zero reported vulnerabilities in the resolved frontend dependency tree, including the exact Playwright development dependency.
- `npm run test:browser`: **3/3 passed** against the static synthetic exercise.
- `CM_BASE_URL=http://127.0.0.1:5191 CM_LIVE=1 CM_EXPECT_GOOGLE=1 npm run test:browser`: **3/3 passed**, 12.3 seconds. This used actual non-demo database reports, live Google imagery, source-health API data, all four desktop tabs, keyboard dialog dismissal, and 390×844 portrait navigation. No page errors were observed in the all-tabs test, and rendered timeline labels had at least 8 pixels of separation.

The parent performs the corresponding final Docker/nginx run after rebuilding the production image. `CM_GOOGLE_KEY` optionally supplies an operator browser key to the same tests through process and React memory. Traces, HAR, automatic screenshots and video are disabled. Default tests do not require a Google key. Tests inspect API and DOM behavior; they do not certify arbitrary third-party stream playback or factual claim accuracy.

Live mode also supports the explicit `/config` Google browser-key fields. Server defaults require `google_earth_enabled=true` and a nonempty `google_maps_browser_key`. They are ignored by the synthetic showcase and by a session in which the user has already applied manual settings. These public browser-restricted credentials stay in React memory; application code does not persist them to browser storage. The production run must verify this normal operator path without test-key injection.

Final source/config hashes and raw frontend test/build outputs are recorded in `artifacts/frontend-qualification-final.json`, `artifacts/frontend-vitest-final.json`, `artifacts/frontend-unit-final.txt` and `artifacts/frontend-build-final.txt`.

## Reproduced and repaired live-only renderer defect

The first real-data browser pass failed with two Leaflet `clearRect` errors while changing views. Removing paths before the renderer fixed one lifecycle ordering problem but was insufficient for live mode. RAF registration evidence traced the remaining callback to Canvas path creation.

Leaflet 1.9's `_updatePaths` can call `_redraw` synchronously while an earlier animation callback remains queued. The stock `_redraw` clears its stored request ID without cancelling that pending callback, so removal cannot cancel it. `OwnedFrameCanvas` cancels the renderer's currently owned frame before invoking the original redraw. It preserves normal rendering and does not catch or suppress rendering exceptions. The same live all-tab regression then passed. This local extension depends on the installed Leaflet implementation and must be retested when changing Leaflet versions.

## Evidence and availability behavior

Free RSS records use the original headline, `classification_status=not_requested`, `event_type=unclassified` and severity zero as **UNSCORED**, never as a low-impact assessment. Missing coordinates remain visibly unresolved. Satellite observations have their own source category. A source digest is labeled as an attributed text compilation with **UNASSESSED** risk; no fabricated 50/100 score or implied video-generation state is used.

Backend failure does not silently become demo data. Tracking refreshes are serial, abortable and bounded; expired cached aircraft/navigation candidates are cleared. Historical snapshot requests discard stale responses when the requested window changes, and unavailable replay data stays empty. Browser receipt time is not presented as provider observation time.

External media requires explicit activation. Frames use `strict-origin-when-cross-origin` so cross-origin players receive the origin referrer required by YouTube client identification; suppressing it causes Error 153. A frame-load event means an external frame was received; playback and live status remain unverified. Blocked/unavailable providers have an explicit state and a direct source link. Recorded analytical references are not described as the newest episode or as current observations.

## Reconnect recovery

An initial latest-report REST snapshot establishes the baseline before opening the event socket. Each connection captures the maximum observed creation ID synchronously, then reconciles `/events?after_id=N&limit=500` in ascending ID order. The local REST cursor advances only through validated response pages; concurrent higher WebSocket IDs cannot move it. Reports are deduplicated by ID. Each connection fetches at most 5,000 records, and the timeline discloses an incomplete recovery on failure or limit. The unfinished cursor survives a reconnect. Requests are aborted on disconnect/unmount and late responses are ignored.

The regression simulates an outage followed by new IDs whose original publication times are older than the existing feed, verifies their inclusion exactly once alongside concurrent WebSocket delivery, follows 1,101 records across pages, resumes after the 5,000-record cap, and checks abort/error boundaries. This reconciles newly created Event IDs. Revisions of existing IDs need a separate update/revision cursor and are outside this contract.

## Scope limits

An earlier TypeScript `preProcessFile` traversal from `src/main.tsx` found 30 reachable source/style files. Retained reference components outside that import graph include both `StrategicPulseBar.tsx` copies, `AccuracyLayer`, `AlertPanel`, `EscalationGauge`, `GlobeView`, `IntelPulsePanel` and `SignalPanel`. Their historical behavior is not a qualified active application capability.

The tests are behavioral samples, not exhaustive line coverage or a proof that every branch is optimal. The build still warns about the approximately 520 kB main chunk and unused satellite.js WASM Node imports. Google imagery, data-provider outages, physical-device performance, accessibility beyond the exercised keyboard flows, long-duration WebGL resource behavior and optional video generation need their own qualification. NASA's keyless reference texture is Black Marble **2016**, not current satellite evidence; its date and credit are visible.


## Final production automatic-Google reconciliation

The subsequent final Docker/nginx run completed all3 Playwright production workflows in **7.6seconds**. It used the actual non-demo live database, real Google photorealistic tiles and the normal server `/config` public browser-key fields; **`CM_GOOGLE_KEY` was not supplied**. This qualifies the normal operator configuration path previously pending above. All four tabs, source-health surfaces, keyboard/Settings behavior and portrait navigation were exercised. The dated private execution log was inspected only for sanitized pass/count evidence; no credential, raw private environment or sensitive log content is copied here.

Final companion checks were73 frontend tests/build,0 frontend dependency findings,248 backend tests +29 subtests on Windows and on the Linux production platform (Python3.12.16,0 skipped), and0 known production Python dependency findings. The clean live deployment contained0 synthetic rows; a restart preserved64 original rows and their equality fingerprint. A bounded140-request/10-concurrent local API sample had0 errors and p95 85.19ms. These samples do not establish sustained-load performance or a long operational soak.

Final measured backend execution coverage is **60.08% combined statement/branch**, **62.47% statements (2710/4338)** and **51.69% branches (641/1240)**. No every-line, every-branch or best-possible claim is made. Optional AI/video semantics, physical-phone and screen-reader behavior, long resource soak, historical migration and recovery of updates to already existing Event IDs remain outside this receipt. GitHub CI/publication has not been performed. The final package/hash is generated separately after documentation reconciliation.


### Final timeline and selected Media playback

The final73-test source also covers viewport-spaced ticks across244 days, valid ArrowRight range stepping, filtered-empty state, explicit mapped-versus-loaded counts, attributed free-digest labeling and full-loaded-set source counts. The final deployed3-workflow result is7.6seconds; [the sanitized production receipt](../docs/qualification/frontend-production-final.json) records the54-file source/config manifest and normal server-Google configuration path.

A selected recorded YouTube reference had reproduced error153 when `Referer` was suppressed. The iframe's `strict-origin-when-cross-origin` policy now follows the [official embedded-player identity guidance](https://developers.google.com/youtube/terms/required-minimum-functionality#api-client-identity-and-credentials) and [error153 contract](https://developers.google.com/youtube/iframe_api_reference#onError). In the separate production after-check, a native Play click followed by6seconds produced media time5.66072seconds, `paused=false`, `readyState=4`, and no player error. This is observed selected playback, not a generic iframe-load proxy or a guarantee for all streams. Sanitized [before](../docs/qualification/media-youtube-before.json) and [after](../docs/qualification/media-youtube-after.json) receipts are included.


The final exact rebuilt-image backend rerun also passed248 tests +29 subtests with0 skipped in9.55seconds. It matched the running backend image and retained76 source/tool hashes. This final Linux receipt is linked from the current application verification document. Documentation reconciliation changed no application, test or deployment source.

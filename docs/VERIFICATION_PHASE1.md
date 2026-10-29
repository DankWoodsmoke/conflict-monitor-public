> **Historical phase1 receipt — superseded.** This file preserves the initial blocked-Docker/synthetic-showcase snapshot. Its counts and incomplete gates are historical and are not the current release status. Read the [current verification receipt](VERIFICATION.md) for the later real Docker/PostGIS, free-source and production Google Earth results.

# Candidate verification receipt

Checked **2026-10-28 America/Chicago**. Candidate: **0.2.0-rc.1**. Source baseline: April 8 server backup plus comparison against the local March working changes. This is a candidate for review, **not a certified production deployment or published GitHub release**.

## Executed checks

| Check | Result | Evidence and scope |
| --- | --- | --- |
| Backend suite | **182 passed, 29 subtests passed** | `.venv/Scripts/python.exe -m pytest -q`, working directory `backend`; latest aggregate completed in 6.86 seconds. Actual service/handler functions run against synthetic provider/persistence fixtures. No skipped checks in this run. |
| Frontend suite | **35 passed, 4 files** | `npm test`; includes sanitization/unsafe URLs, deterministic offline fixtures, provider activation, navigation, Locate, replay and compound history pagination. |
| Production build | **PASS** | `npm run build`: TypeScript and Vite production output. No old-server rsync hook. |
| Python dependencies | **No known vulnerabilities reported** | `python -m pip_audit`; runtime and test dependencies resolved/pinned from PyPI. Bootstrap pip/setuptools were upgraded in the isolated venv after their original versions were flagged. |
| Frontend dependencies | **0 vulnerabilities reported** | `npm audit`; resolved lockfile retained. |
| Export regression tests | **18 passed** | Public/adversarial export fixtures include quoted/JSON credentials, database URLs, private keys, binary-image content, unknown file types, hidden files and scan/package byte identity. |
| Public source scan | **No detected credential findings** | `python tools/release_gate.py --scan-only`; this is a bounded scanner, not exhaustive secret clearance. Export uses allowlisted paths/formats and immutable scanned byte snapshots. |
| Original backup preservation | **PASS** | SHA-256 remains `31d04ebcda8ecf0be13a5b14eed5093892e7d4985957ff91fb45f8d97f9e2ec1`. Original worktree/index/credential files were not edited. |
| CelesTrak adapter | **8 offline tests; bounded live fetch PASS** | 45 validated OMM records at `2026-10-29T01:59:59Z`; source epochs retained. Includes 6/9-digit catalog support and last-good cache/failure tests. Not real-world orbit-accuracy certification. |
| ADS-B adapter | **Bounded live fetch PASS** | 7 normalized positions, 0 rejected at `2026-10-29T02:27:52Z`; observed ages 1–39.5 seconds. This establishes that request/normalization worked for a sample, not regional completeness or aircraft identity certainty. |
| Google photorealistic Earth | **Live rendering PASS** | Recovered browser key loaded into temporary page/process memory only. Actual Google root and GLB tile requests, Dubai city fly-to, and visible Google/Airbus/provider credits observed. No key bundled in public source. |

The scanner/package gates do not validate dataset rights, factual truth, model quality or production behavior. Vulnerability databases and provider behavior can change after this receipt.

## Browser workflows

The stable production preview ran at `http://127.0.0.1:5188/`. A separate loopback-only Google-enabled showcase is available at `http://127.0.0.1:5189/?showcase=true&earth=google&view=3d`; its provider key is held only in the running process. It uses synthetic reports with real Google geographic imagery.

- **Map:** clean reload; report Locate opens the actual marker popup; no observed browser errors or horizontal overflow. The prior Leaflet canvas teardown error and missing cluster-marker index were reproduced and repaired.
- **Media:** view switch and explicitly illustrative media panels loaded; no observed browser errors or external provider requests in the default showcase.
- **Brief:** report history, analysis, and source references loaded; no observed browser errors. Exercise briefing is explicitly illustrative, without a claim of recorded narration/video.
- **Earth:** real Google photorealistic tiles connected; city controls worked; credits visible. The synthetic-only default requests no Google data until enabled.
- **Settings:** focus moved inside the dialog and Escape closed it. Entered key stayed in React memory; local/session storage remained empty during the check.
- **Mobile:** emulated `390×844`, touch and reduced-motion preference; Map/Earth/Media/Brief navigation available; Earth/Settings rendered with no horizontal overflow and no observed console errors. This is desktop-browser emulation, not a physical-phone test.
- **History/replay:** automated DOM/logic tests cover timestamp/ID pagination ties, hard 5,000-report display/request budget, finite coverage labeling, missing tracking snapshots and paused cursor preservation. No claim of complete historical ingestion is made.

Historical screenshots from this phase are preserved locally outside the public export under `artifacts/prior_candidates/phase2-screenshots/`, with byte hashes. They are not the current Earth workspace or independent correctness tests. The Google imagery date/coverage varies by provider. A short browser animation-frame sample during Earth viewing had 90 intervals at p50 5.6 ms/p95 5.7 ms; **that is neither renderer FPS nor interaction/load-test certification**.

## Required gates still incomplete

| Gate | Current result | What completes it |
| --- | --- | --- |
| Fresh PostGIS persistence/migration | **INCOMPLETE** | Docker Desktop failed before any container launched while initializing its inference-manager socket. No machine reset or configuration repair was performed. Run the supplied CI/fresh empty database gate; `tools/verify_postgis.py` exits nonzero without the explicitly isolated test database. |
| Existing production migration | **UNVERIFIED** | The new baseline deliberately refuses a nonempty database. Design and rehearse a data-preserving migration against a verified restore of the actual deployment schema. |
| Former VPS/latest deployment | **UNREACHABLE** | Read-only SSH timed out. The owner selected the April backup as the working baseline. This candidate does not claim to mirror a later server. |
| End-to-end live ingestion | **UNVERIFIED** | Exercise configured Telegram/RSS/X ingestion, real PostGIS writes, ledger failures/revisions, WebSocket delivery and UI freshness in an isolated deployment with bounded provider budgets. |
| AIS, FIRMS and configured media | **OFFLINE TESTED / LIVE UNVERIFIED** | Validate real operator-owned sessions/keys and provider response shapes/rights. Do not infer cause or military identity from receiver metadata. |
| Model semantic accuracy | **UNVERIFIED** | Establish a held-out multilingual event/attribution/negation/time/location set; compare baseline and candidate models with unsupported-claim, false-merge and abstention metrics. No paid model calls or new local model downloads ran in this session. |
| SITREP factual entailment | **UNVERIFIED** | Current gate validates bounded schema, completion and source-ID membership. It cannot establish that a cited report supports every generated proposition. Human/qualified claim-level review remains required. |
| Standalone video engine | **UNVERIFIED** | Legacy external dependencies, fonts/paths, narration timing and output quality require a separate portable-worker qualification. Automatic invocation remains disabled. |
| Load/accessibility/device qualification | **PARTIAL** | Keyboard/selected DOM behaviors and emulated portrait checked. Real-device testing, screen-reader audit, concurrent ingestion/load, WebGL memory lifecycle and long-duration soak are not complete. |
| Inherited cartographic asset lineage | **UNRESOLVED** | Existing assets came with the inherited MIT source; independently verify or replace each asset's provenance before making a separate dataset-license claim. |
| Public GitHub publication | **NOT PERFORMED** | Review the exact packaged snapshot and resolve the required gates. The existing private repository's visibility/history has not changed. |

The build retains warnings about an approximately 509 kB minified entry chunk and unused satellite.js WASM Node imports. The exercised JS orbit path and Earth view ran successfully, but those warnings are not treated as evidence of broad browser compatibility. Running provider threads cannot be forcibly terminated by asyncio; cancellation/status do not falsely claim that an in-flight native thread has stopped.

## Next qualification sequence

1. Run the committed-form CI workflow against a fresh isolated PostGIS database; repair genuine failures without weakening assertions.
2. Rehearse the legacy restore/migration and verify counts, hashes, provenance and correction history.
3. Qualify bounded real source ingestion and every enabled provider, then run a multilingual model/analysis evaluation and operational soak.
4. Resolve asset/data redistribution rights, review the final source ZIP/manifest, and publish the reviewed candidate as a prerelease before promoting a stable release.

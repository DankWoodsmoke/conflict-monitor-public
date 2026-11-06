# Release-candidate verification

## Current candidate 17 qualification update

**RC.5 source release candidate; public hosting is not approved.** Candidate 17 binds 545 frozen source files and five built images. Its only changes from candidate 16 are the NASA publication scheduler and five corresponding regression cases. Skipped `not_due` or `already_running` attempts now recheck the database after 30 seconds; the durable three-hour provider-request gate and advisory ownership remain intact.

Candidate 16's main and composed-raster long runs were intentionally interrupted before four hours after NASA remained on one batch and a scheduler oversleep defect was reproduced. The exact trigger of the observed live single-batch state remains unverified. Original partial samples, launch states and the failed first stop-verification receipt remain preserved. A separate read-only completion audit confirmed both owned observer jobs closed and all five candidate containers plus three original RC.4 containers unchanged. **Candidate 16 supplies no successful four-hour elapsed-time credit to candidate 17.**

Fresh candidate 17 installed-backend execution passed **1,254 tests plus 29 subtests, zero skipped**, with actual pytest process/kernel UID/GID 10001, no effective capabilities and no-new-privileges recorded. A separate fresh collection found all 1,254 tests, including the five new NASA cases. Packaged application bytes and imports matched before/after; the container had no network, read-only application/root and temporary test tooling. Twenty-seven previously downloaded test wheels and their original official metadata were rehashed; their historical provenance was preserved, not relabeled as a new download. Owned cleanup passed.

**11 offline nonroot Media checks passed** on candidate 17 with real CPU speech, authored source cards, encoding and complete decoding. **29 offline publisher-admission tests and 15 observer/coverage contract tests passed**; Ruff's selected correctness checks and the 545-file export scan passed. These authored/offline tests do not establish live-provider accuracy, physical-phone behavior, public uptime or AI classification quality.

Fresh three-engine retained-video replay also qualified with explicit limits and owned cleanup. Firefox's paused-caption failure and unsupported 170.770263-second singleton callback for a 38.379801-second artifact remain raw failures/unqualified observations; the callback cause remains unverified. Windows WebKit raw color identity remains FAIL; fixed standard-range content comparison passed (MAE 1.23753, p99 12) with the independent known-color control. Actual user playback/recovery and decoded-reference content are separate checks. This replay uses an overridden read-only artifact API, no production database or generation; it is frontend playback evidence, not new encoding or production-route qualification.

All **21 fresh candidate 17 Google cases passed**: 12 operator and 9 public browser/viewport cases across Chromium, Firefox and WebKit. Each checked all three tabs on the persistent Earth canvas, nonblank textured photographic output, visible attribution and the applicable data/control boundaries. Independent root review verified 1,030 immutable browser inputs and membership, 545 frozen/current source files, four archived helpers, screenshots and five unchanged service identities. The exact generated Chromium diagnostic log was retained separately; this candidate's direct binder passed. Candidate 16's failed binder/addendum remains historical. These are desktop-engine mobile emulations, not physical-phone, imagery-date or location-ground-truth certification.

Fresh candidate 17 public Compose qualification passed **59 named reader SQL checks**, authored packet/download/API checks and a real database transport outage/recovery without restarting either app. The separate operator fixture passed actual database-role, PostGIS, delivery and pipeline checks and persisted **two real BBC reports with zero model calls**; classification was not requested. The main fixture passed **31 runtime-isolation checks**. Provider accuracy, all-source ingestion and public Internet behavior are outside these finite scopes.

The candidate 17 read-only main snapshot and isolated restore passed **13 checks over 17 tables and 6 sequences**. Its snapshot remained open for **10.407 seconds**; full execution ran 13:02:35-13:03:36 UTC. Restored NASA 647 and aircraft 141 stored/124 displayed records agreed with SQL and exact downloads. Sequence values have explicit non-MVCC bounds; bootstrap reconstructs omitted ownership/ACLs. There were zero additional provider requests or main service mutations, and owned cleanup passed. This is a local restore rehearsal, not encrypted off-machine backup or host disaster recovery.

The fresh candidate 17 bounded-load check passed **48/48 steady HTTP 200 reads** from four loopback clients, with p95 **225.431 ms** over those 48 samples. Bursts capped at 16 concurrent requests produced display **44x200/20x429** and download **1x200/15x429**, with zero 5xx. SQL/download/display projections and gzip/identity bytes agreed. The workload lasted **48.828 seconds**, followed by 12 seconds cooldown; main identities stayed unchanged and the owned job closed. Expected local throttling is not external audience-capacity or provider-availability certification.

Independent candidate 17 component-security review checked **155 matrix references and 1,239 total evidence/source entries**. The later post-soak official-source review independently rehashed **1,363 references**. Its 39-source fetch began at **2026-11-06T17:15:42.110772Z**, after both completed-run parent cleanups; semantic review ended at **17:34:12.501576Z**. The late official database recheck completed at **17:31:46.547865Z** with the same verified tuple, so the eight earlier exact-image/native scans were retained, not relabeled as new executions. They retain 30 raw records and 24 role/CVE rows across 21 CVEs: 8 fixed, 12 affected-code-absent and 4 affected residual rows. Raw High-threshold exit2 findings remain alongside exact repair/absence evidence; BusyBox Medium and Python Low remain affected. The reviewed image/native High conditions are addressed within their stated scope; separate host Critical/High issues remain unresolved. This is not a zero-vulnerability or public-host approval claim.

**COMPLETED, SCOPED FOUR-HOUR CHECKS:** candidate 17's five main observers and two separate operator/public composed-raster observers each completed at least 14,400 seconds with 480 samples. Both parents and all seven observers exited zero; the later parent cleanup ended at **2026-11-06T17:10:31.949267Z**, following the 13:10:01Z start. Independent review verified unchanged source/helper and five-service identities, natural second NASA publication, Google session renewal, successful tile requests begun after three hours, and the applicable HTTP/download/SQL/rendered-scene checks. The offline proof projectors accepted these completed records. This is a bounded local execution, not provider uptime, location truth, memory-leak freedom, fresh AI/video generation or public-host approval. Rehearsals and interrupted candidate 16 observations supplied no elapsed-time credit.

**Release evidence boundary:** final packaging requires independently admitted six-proof evidence, unchanged runtime identity, reviewed source/export and the exact-source hosted CI jobs. The release workflow enforces the later publication and asset-verification steps; their actual result belongs to the exact GitHub release/verification receipt. These local records do not assert a future CI result, published tag, asset checksum or authenticated/anonymous download success. Public hosting remains unapproved. Detailed security evidence and residuals are in the [security review](OS_SECURITY_REVIEW.md).

The public product scope stays two independently licensed contextual datasets: NASA thermal observations and regional adsb.lol snapshots with attribution and exact-batch downloads. Private report text, Telegram, model context/costs and generated Media/Brief remain withheld. Thermal observations do not identify strikes; aircraft broadcasts do not establish missions or ownership. A Windows/GOOL pilot still needs actual public TLS, restricted imagery key/quota controls, encrypted off-machine recovery, startup and shared-host capacity qualification. No website, DNS, tunnel or original RC.4 deployment was changed by these checks.

Source-health claims stay separate from observer integrity results. The completed publication observer sampled 480/480 cached states as `fresh` for each public dataset: two NASA batches (647 then 1,176 displayed observations) and 434 ADS-B batches (89–188 displayed positions). Different browser sampling instants saw up to 193 positions. This is sampled delivery and consistency, not continuous upstream or all-region availability. Saved observer metadata omits NASA last-attempt state and ADS-B regional errors; canonical ADS-B packets/downloads do not retain regional histories. Four query circles describe configured geographic bounds, not four successful acquisitions. The disabled private, key-gated thermal adapter is separate from the working keyless public NASA path.

Private RSS was not uniformly healthy or recently published: `geopolitical_economy_candidate` had 71 sampled `failed` states and 409 `ok` states; its publication, plus Grayzone and Greenwald, stayed age-stale at all 480 samples, while Democracy Now was age-stale at 226. These four catalog entries are default-enabled for private attributed report/context preservation, with unassessed reliability; the identifier suffix does not mean disabled, and it confers no public redistribution approval. The age flag means the newest parsed dated item was over 24 hours old, independent of retrieval success. The failure state covers retrieval/parsing exceptions and can persist through backoff; these are not 71 separately counted requests. Error/HTTP/attempt details were omitted from the saved observer rows and were not found in inspected saved logs, so the cause and any code defect remain unverified. All private RSS reports remain withheld from the public profile.

The separate progress watcher exited 1; its original traceback was not retained. A terminal empty-output JSON read failure was reproduced separately as a possible explanation, not recovered as the original traceback. It supplies no elapsed-time or qualification credit. The seven observer results and parent cleanup/identity checks were independently verified from their sealed records; the watcher failure was not rewritten as success.

**Completed-run resource limitation:** each desktop browser stream contains 480 samples. Public raster observation reached **1,050.2 MiB used JavaScript heap at 16:51:47.436Z**; its complete final-hour median was about **643 MiB**, versus **300 MiB** for the main public stream. Their final samples were about 605 and 361 MiB. The main public maximum was 655.7 MiB earlier; its final-hour maximum was 373.5 MiB. Public DOM/document counters stayed comparatively stable and heap repeatedly dropped, but allocation ownership and instrumentation overhead remain unresolved. The raster helper adds in-page PNG/Image/canvas work; the scene also grew from 647 to 1,176 NASA observations and changed cities/sessions. These facts establish neither a leak nor its absence. Cesium tile-cache parameters govern estimated GPU tile memory, not whole-page JS heap. Physical-device and realistic mobile long-session memory pressure remain unqualified; proposed device-aware budgets and external screenshot decoding were not applied. This material pre-site limit is retained alongside the scoped soak pass; no acceptance gate was changed.

**Separate host deployment blocker:** the measured Windows Docker/WSL environment has newly reviewed host-level security issues. Docker Desktop 4.98.0 plus WSL 3.0.3 alone is not established as a complete remedy because the separately supplied kernel also requires a verified fix. Public hosting on this PC remains blocked for safe maintenance and requalification; no update was made during the completed runs. Application-image findings and source-release qualification remain separate. See the [host-security gate](PUBLIC_HOSTING.md#separate-windows-host-security-deployment-blocker).

## Preserved candidate 16 and earlier baseline

The qualification results below are historical and retain their original candidate scope. Candidate 16 long-run statements recorded as in-progress or pending are superseded by its INTERRUPTED_INCOMPLETE outcome above; candidate 16 URLs, counts, hashes and CI identifiers remain historical. Usage, license, safety and credential instructions remain retained. No historical result is silently promoted to candidate 17.

### Historical candidate 16: measured results and then-pending gates

Private draft dated November 6, 2026. Candidate 16 is a local RC.5 development build, not a published download or a deployed public site. Its build receipt SHA-256 is `301cec892f92f33d54380d8038f3d7ddf8a38bed5cf54551c06609d99ea73f99`, binding **545 original source files** and five successful image builds. These five documentation drafts are later, separate changes; they are not represented as bytes already built into those images.

| Check | Measured scope and status |
| --- | --- |
| Frozen build/runtime binding | Five exact images passed. Fresh Docker inspection shows every role's full RootFS, runtime Config, OS and architecture equal to candidate 15; image IDs differ. The only source deltas are `verify.yml` and the authored WebGL browser test. Native/source claims use actual identity evidence, not tag/version assumptions. |
| Backend | **1,249 tests plus 29 subtests passed, zero skipped**, newly executed as UID 0 in a disposable candidate 16 packaged-backend test container; the runner did not drop to UID 10001. Application source was not mounted; test/build tooling was mounted and package bytes were checked. Test-only dependencies are not claimed to ship in the release image. |
| Backend nonroot repeat | **1,249 tests plus 29 subtests passed, zero skipped**, separately executed at 10:03:05-10:03:23 UTC with measured process/kernel UID/GID 10001 on the exact packaged backend. Offline, read-only root, temporary test tooling, packaged application imports and verified cleanup. The original UID 0 execution remains separate. |
| Offline Media | **11/11 passed** on the exact backend: real CPU Piper speech, source-card rendering, local segment/concatenation encoding, stream probing and full audio/video decoding. This uses authored synthetic cards, not real incident footage, live report publication, browser replay or listener audibility. |
| Frontend unit/build evidence | **433 unit tests in 33 files passed** in the actual hosted frontend job for commit `8f267a4c405d38f8b433bc381402e94c0ca4fdcf`; seven offline browser tests also passed. The job succeeded; hosted images remain distinct from local runtime images. |
| Focused authored browser tests | **Windows 7/7 and Linux/Xvfb 7/7; zero skipped, failed or flaky.** They cover offline pixel/attribution fixtures with the exact browser-test source. Earlier Linux headless/null-context failures are retained. These tests do not by themselves qualify Google, the application tabs or physical phones. |
| Main fixture isolation | **31 checks passed**, including actual reader/writer identity, two publication-table privileges, network/port boundaries, read-only public root, bounded resources and one collection owner. This is local runtime isolation, not Internet-host admission. |
| Public Compose/data recovery | **59 named reader SQL checks passed** on candidate 16, with authored public packets, exact downloads, API restrictions and actual database-outage/retry/recovery. The backend and reader start identities remained stable through that fixture's recovery; owned fixture cleanup was verified. No external provider or live Cloudflare tunnel was exercised by this check. |
| Operator pipeline | A separate candidate 16 fixture passed four pipeline/boundary gates and ingested **two real BBC reports, zero model calls**. SQL/TCP/committed delivery evidence and cleanup are retained. Two fetched reports are not broad source-accuracy or continuous-ingestion proof. |
| Security | **8 fresh scans, 30 raw records; 24 role/CVE rows, 21 distinct CVEs: 8 fixed, 12 affected-code-absent, 4 affected residual rows.** Matrix validation checked 135 reference files; independent root review checked 149 total references. Raw High exit2 results remain. See [security](OS_SECURITY_REVIEW.md). |
| Native compatibility | Fresh candidate 16 installed hashes/provenance/absence and ordinary linkage passed. Prior candidate 15 installed TLS 32 and upstream217 nghttp2/117 BoringSSL/18 zlib suites transfer through full runtime and newly measured native equality. They are historical executions, not new candidate 16 suite runs. |
| Full Google/browser matrix | **21/21 case assertions completed, zero case failures; admitted with an explicit root binding addendum.** Original binder FAIL for changed Chromium generated `debug.log` remains preserved. All 1,030 immutable browser inputs, 545 source files, four helpers and five service identities were independently checked; no rendering assertion was relaxed. |
| Browser Media replay | **Qualified with explicit engine limits on the exact candidate 16 operator frontend.** Chromium raw pixels passed. Firefox paused-caption repaint still fails, with actual user-resume recovery and transcript passing. Windows WebKit raw RGB identity still fails; independent known-color control plus fixed standard range conversion passes unchanged content thresholds. The out-of-duration Firefox singleton callback remains unsupported/unqualified, cause UNVERIFIED; it is not playback or frame-time proof. No raw-pixel, Safari/iPhone, AI or audibility equivalence is claimed. |
| Main snapshot/restore | **Fresh read-only main snapshot and isolated full restore passed.** Full data/index/revision/locale comparison, explicit non-MVCC sequence bounds, next-key safety, bootstrap and reader/writer grants passed. Cached NASA 647 and aircraft 163 stored/95 displayed records matched SQL/HTTP downloads. No extra provider requests or main restart; cleanup verified. This is local recovery, not encrypted off-machine durability. |
| Bounded final load | **PASS:** four steady loopback clients, 48/48 HTTP 200; p95=249.699 ms for 48 samples. Max 16-concurrent bursts: display 44x200/20x429; downloads 1x200/15x429; zero 5xx. Exact SQL/download/display/gzip identity and recovery passed; 56.562 s workload plus 12 s cooldown, unchanged main identities. Local bounds, not external audience-capacity proof. |
| Four-hour exact-build session | **Historical pre-interruption record, now INTERRUPTED_INCOMPLETE: started `2026-11-06T09:45:37Z`; four real hours and final review remain PENDING**, complete sample coverage, stable intended service identities, natural publication advancement, API/download/SQL/rendered-position agreement, real Google renewal and post-three-hour tile traffic. Prior RC.4 hours and short rehearsals count as zero toward this gate. |
| Supplemental composed-raster sessions | **Historical pre-interruption record, now INTERRUPTED_INCOMPLETE:** separate operator/public observers started `2026-11-06T10:08:12Z`, each requesting 14,400 actual seconds. Final admission requires both complete runs, at least 479 samples each, exact sample parity/cadence, visible-raster thresholds, zero findings and unchanged source/service identities. The main lifecycle observer and 330-second rehearsal do not replace this gate. |
| Post-soak security freshness | **PENDING: official DB/advisory refresh starting strictly after the later successful main/raster child/parent-cleanup completion.** If the official DB changes, all five images and three supplements require new raw scans and reviewed deltas. |
| Hosted CI | Frontend, backend and Shipped Compose jobs passed for exact public commit `8f267a4c405d38f8b433bc381402e94c0ca4fdcf`, run 42192911137; independent artifact review checked 59 reader/118 ingress/23 edge cases. Hosted image IDs are distinct from local ones, without assumed equivalence. Packaging/publication jobs were skipped. |
| Final source/download | **PENDING: final documentation/export scan, source-to-final-CI rebind, commit/tag/archive checksums and downloaded asset verification.** Current hosted job success does not qualify later docs/source or a released archive. |

Historical candidate 16 local Chrome inspection observed photographic Google Dubai imagery at approximately 5 km on the public fixture at `http://127.0.0.1:32774/`. This is an ephemeral local inspection URL, not the default install port, a public deployment, or proof of all 21 browser cases. Imagery is dated photography rather than a live satellite feed.

The public product is NASA thermal context and separately licensed regional adsb.lol observations. It does not publish private reports, Telegram, operator Media/Brief, market data or model costs. Thermal detections are not strikes; broadcasts do not establish aircraft mission, intent, ownership or complete receiver coverage. Model factual accuracy, physical phones, assistive technology, every code path and commercial intelligence-platform parity are not certified.

The 1,249-test/29-subtest packaged application suite ran as UID 0 in a disposable test container to install test-only dependencies; it did not drop to the image default UID 10001. The production runtime identity/isolation checks and 11 offline Media checks separately exercised their nonroot contexts. Passing the root test suite is not a nonroot-permission test.

A separate fresh execution at 10:03:05-10:03:23 UTC passed the same **1,249 tests plus 29 subtests, zero skipped**, with actual process and kernel UID/GID **10001** recorded at pytest entry and completion. It used the exact packaged backend, an offline network, read-only root and temporary test tooling; application module paths and bytes stayed packaged, and owned cleanup passed. This adds bounded nonroot suite evidence without relabeling the earlier UID 0 run or replacing live database/production-profile checks.

Nonroot suite receipt SHA-256: `4430a4a8255fdaee0d535c8e6c1e1f1a07fdeee9bba4545e0a66fb25cc65c82c`.

The fresh candidate 16 bounded-load run passed: four steady loopback clients completed 48/48 HTTP 200 reads (p95 latency 249.699 ms over those 48 samples). Bursts capped at 16 concurrent requests produced 44 HTTP 200 and 20 HTTP 429 display responses, plus 1 HTTP 200 and 15 HTTP 429 download responses, with zero 5xx. SQL, exact downloads, display projection and gzip/identity bytes agreed; successful reads recovered after throttling. The measured workload lasted 56.562 seconds plus 12 seconds cooldown. Main service identities stayed unchanged and the owned job closed. This is one loopback-peer workload, not Internet, CDN, TLS or audience-capacity certification; expected 429s establish local limits, not provider availability.

Bounded-load receipt SHA-256: `e10f5f069eee7762be7475b56b6e7fe8f67cd1b3d6ead9e74a242f9f0b2cab74`.

### Google binding addendum and Media limits

All 21 candidate 16 Google browser/viewport cases completed with zero case failures. The original binder remains **FAIL** because Chromium changed its generated `debug.log`; a separate independent addendum accepted that exact runtime-output exception after verifying all 1,030 immutable browser inputs, 545 source files, four archived helpers, five unchanged service identities and the case screenshots. The original failure was not rewritten and no general exception was added. This is desktop-engine mobile emulation, not physical-phone or location-ground-truth certification.

Original binder SHA-256: `74b3b7e99b6c7eaee8546c8c4cc664a033d8e11789c2baff61fe048fe4019106`; independent addendum: `47a839995c4cae90d130e1592e11aba315dc2c7b97e08c7bc9c31a719662f175`.

Candidate 16 retained-video replay qualified with explicit engine limits: Chromium raw pixels passed; Firefox paused-caption repaint remained **FAIL**, while actual user-resume recovery and the exact transcript passed. Firefox also returned a single callback `media_time` of 170.770263 seconds for the 38.379801-second artifact, without the required two advancing callbacks. That raw observation is unsupported and unqualified, its cause is **UNVERIFIED**, and it supports no playback or frame-time claim. The separately measured decoded-pixel/reference comparison and actual user time advance remain distinct valid checks. Windows WebKit unadjusted RGB comparison remained **FAIL**; an independently encoded known-color control established the range behavior, and a fixed standard range conversion passed the original content-error thresholds. Raw color identity remains unqualified. The exact backend image used an overridden, read-only replay API entrypoint serving retained artifacts. Production FastAPI routes, its database and the encoder pipeline were not running in that replay fixture; the new qualification is frontend playback. Production-route/pipeline checks and the nonroot offline 11 encoding checks are separate. The replay made no generation/model calls and connected to no database; it establishes neither current AI accuracy, new report truth, physical-iPhone behavior nor listener audibility.

Media receipt SHA-256: `3199be9f2769c49f472318e4d92c75ae84d6f0f6ec03d1ae9e6901f99f0f94bc`. Hosted frontend log review: `1fb45005b8e8f59d9a62643a27c935197afb99f9cb2c3de8c380379b12b2673d`.

A fresh read-only snapshot of the candidate 16 main database and isolated full restore passed at 09:30:35-09:31:28 UTC. Tables/rows/indexes/revision/locale, explicit non-MVCC sequence bounds and next-key safety, bootstrap and reader/writer privileges were checked. Cached NASA 647 and aircraft 163 stored/95 fresh displayed rows matched restored SQL and exact HTTP downloads. No extra provider request or main service restart occurred; five main identities remained unchanged and owned temporary resources were cleaned. This is a local restore rehearsal, not encrypted off-machine backup durability.

Snapshot/restore receipt SHA-256: `c87606d7dd1b5e15cc6ebe569ac3f51c7b1494f662a6970ebccb8d4d56dfb4b9`.

### Docker interruption and recovery

At approximately `2026-11-06T08:18:13Z`, Docker's Linux VM stopped unexpectedly. Retained logs show transport shutdown/EOF and API 502 symptoms, but no explicit initiating shutdown, kernel panic or OOM record. The bounded log coverage cannot rule those causes out; rotation access errors and later recovery errors are not established causes.

Recovery handled stale Inference/Secrets IPC state and restored the **same original RC.4 container IDs, images and database volume**, without recreating that deployment. Their new starts are approximately 08:33:44-08:34:01 UTC; health was observed at 08:35:29 UTC. Existing environment/image/volume/restart-policy identity was preserved according to the recovery receipt, but the host was changed by recovery and uninterrupted uptime was lost. PostgreSQL completed automatic WAL recovery; no exhaustive data-loss or corruption certification is claimed. Candidate 16's four-hour clock had not started before this interruption.

The exact public verification commit `8f267a4c405d38f8b433bc381402e94c0ca4fdcf` passed the hosted frontend, backend and Shipped Compose jobs in [run 42192911137](https://github.com/DankWoodsmoke/conflict-monitor-public/actions/runs/42192911137). Its independently reviewed artifact covers 59 reader SQL checks, 118 ingress cases and 23 edge cases. Hosted image IDs differ from local ones; no runtime-byte equivalence is asserted. Admission/package and publish/download jobs were skipped, so this is not a released archive. The exact hosted frontend log confirms 433 unit tests in 33 files and seven separate offline browser tests passed; those authored offline tests do not replace live Google checks.

### Evidence identifiers and publication boundary

Candidate 16 security matrix SHA-256: `45a06ed39376b7afb30989799ee61b1581174137e0944dd850ba6f2359141d26`. Matrix validation: `76955243d6db4074bb6cbe50cf7b60239a5ba6f3d7c4951e39630e19003937c8`. Independent review: `818d6a1e6769e71b7fffbd3e6dd51ff2cf1096bbc3a0ef703e43fe2d95414a9c`. Public Compose receipt: `984aed74df7b329e9ac12cff0360c0b18d024498ee6923acd062831f3a2f458f`. Operator receipt: `4ab60d126c455642e20996d75e8b377cdb21a9375c827c7aebfbef86265e54ab`.

The private security projection has separate 152-reference review, SHA-256 `e4147f9b6e4a5225c38e6d2217bdde436e39cc76642ed6f5f783a9d188652985`. It is a draft admission projection, not READY and not the post-soak refresh. Private receipts contain operational details and are not automatically public release assets. Sanitized publication evidence must be separately bound to the final source/tag/archive.

Public HTTPS, Google restrictions/quotas, encrypted off-machine backup, intended-host startup/recovery, sustained reader capacity and the coordinated other-PC website build remain launch gates. The Windows profile is a pilot; a dedicated Linux deployment is the stronger sustained-host option but has not been qualified or provisioned. See [public hosting](PUBLIC_HOSTING.md) and [site integration](WEBSITE_INTEGRATION.md).

## Historical qualification archive

Historical browser matrices executed before the composed-raster guard qualify only their recorded control, layout, transport and provider/network assertions. They do not retrospectively establish visible photographic output. A blank candidate 14 WebKit capture exposed that coverage gap and prompted the current guard. Current candidate 16 pixel/raster evidence and its explicit binding addendum remain separate; older uses of "Google pass" must not be read as photographic-render qualification.

Everything below retains the result and scope of its named earlier phase. Words such as "current", "final", "live" and "pending" in the archive describe that phase only. Candidate 3's private-table reader proposal is superseded by the two independent publication tables; historical grants are not current hosting instructions. No earlier uptime, scanner result, browser pass or release asset automatically qualifies candidate 16.

### Historical candidate 3: November 5 evening public-hosting and native security

This is development after RC.4, not a new published release or a replacement
for the admitted RC.4 live deployment. Candidate 3 was frozen and built as
separate operator and public frontend images with one backend image. Candidate
1's failed source-freeze check and earlier qualification attempts are retained.
The final application image is `eacb139a6fc8`; operator/public frontends are
`c442f03c415d` and `a5a5495bcf6d`. Documentation corrections after qualification
are recorded separately from the unchanged application and build inputs.

The final application source passed **1,080 backend tests and 29 subtests** both
on the Windows host and inside its exact nonroot runtime image. The image test
mounted test/development tooling only; application code came from the image and
matched the frozen bytes. The frontend passed **416 tests** and its production
TypeScript/Vite build. Showcase Settings again permits manual Google imagery
configuration; public non-showcase views keep operator settings hidden.

The exact new operator Compose profile passed migrations, restricted database
roles, PostGIS, TCP/WebSocket source processing, committed delivery and HTTP
boundary checks. Two current BBC feed reports were fetched and persisted in
the disposable database with original URLs and without model classification.
Telegram bot/account transport checks used explicit provider fixtures; they
are not claims of an authorized live Telegram deployment.

A separate exact-image operator instance received all 31 configured RSS feeds,
held 59 real RSS reports and observed 175 aircraft initially and 183 afterward.
All reports remained unclassified/unscored with unresolved positions. Its
12 Google Earth cases across Chromium, Firefox and WebKit passed at 320 x 740,
390 x 844, 768 x 1024 and 844 x 390, preserving the canvas, native attribution,
dialogs and aging controls with zero uncaught page errors. Between 174 and 183
aircraft were rendered during the cases. The actual container had empty
CORS_ORIGINS and a custom frontend port: same-origin WebSocket access passed;
an untrusted origin received 403. Preserving the original Host port repairs
the previous nginx failure. The earlier failed fixture and synthetic PostGIS
rows remain in their separate receipts; the final instance had real RSS-only
reports. Disposable operator containers, volumes and networks were removed.

The exact public application passed nine Google browser cases across the three
engines at 320 x 740, 390 x 844 and 1440 x 900, with at least 35 settled seconds per
case. Nine Google root sessions and 654 successful content responses were
observed. All tabs preserved Earth and clickable native attribution; withheld
reports/media were explicit. There were zero uncaught page errors, hidden
report/tracking/media requests, background WebSockets or layout failures.
The final nginx boundary passed 96 checks, including methods/raw paths,
credential/body stripping, security/cache headers, limits and Compose isolation.

Public containers omit the private environment file and application volumes,
run with a read-only root, and bound temporary storage to 64 MiB with
noexec/nosuid. Actual runtime checks rejected application-directory writes with
EROFS, allowed temporary writes, and confirmed the separate monitor_public
login. Its application-database access is SELECT-only on the three report and
delivery tables; DML, DDL, sequences, private ledgers, publisher writes,
large-object creation and role escalation were rejected by actual SQL checks.
An earlier source-level fixture separately tested role adoption, rotation and
14 unexpected-privilege scenarios. These are application-database controls,
not a universal SQL sandbox or a restriction of every database in the cluster.
See [public hosting](PUBLIC_HOSTING.md) for the cluster limitations.

The final reader passed 47 SQL/API checks with an empty database and 48 with
one explicitly authored synthetic report. Actual HTTP event and committed
baseline responses retained its original text, unscored assessment and absent
position. No real source dataset was admitted. Both default-closed and
reports-enabled local load checks passed: 24 steady health reads each, then
96-request bursts returning 41 successful responses and 55 throttles with no
5xx, followed by successful recovery. Four simultaneous WebSockets were
accepted, a fifth received 429, and capacity recovered after disconnect.
This measures one loopback TCP peer, not internet audience capacity. The public
fixture and its database volume were removed after these checks.

The native CPython getaddrinfo backport is tied to the distributor's exact
source, upstream patch and final extension bytes. All 15 malformed-input
subcases passed; the original module's failures are retained as a negative
control. The actual final image passed 671 upstream socket tests with 62
explicit platform/resource skips. Its unmodified nominal package version
still appears in the raw vulnerability scan. This is one repaired flaw, not
a whole-image security clearance. Fresh Grype 0.121.2/November 5 database
results retain backend 2 High/1 Medium/1 Low, database 1 High/3 Medium and
public frontend 3 Medium package records, plus native supplemental findings.
The frontend records represent one BusyBox CVE in three packages. No ignore
or version override was introduced. See [security review](OS_SECURITY_REVIEW.md).

Eleven offline media checks passed on candidate 2 with a read-only Piper voice,
no network, two CPUs and 2 GiB memory: actual speech, two source-card segments,
concatenation, full H.264/AAC decode and rejection of HTTPS/HLS input. The final
candidate retains those media implementation and native binary bytes; this is
a recorded rebind, not a second rendering run. The route now hashes bounded
chunks in a worker thread; final-image tests cover range delivery, same-length
tampering, an I/O race and event-loop responsiveness.

These are finite local checks. Physical phones, a new multi-hour observation,
public source rights, shared tracking publication, host-level backup/restore,
trusted-edge rate limits, external load and actual DNS/TLS remain separate
gates. The raw High security gate remains blocked. No website, DNS, Cloudflare
or GitHub release was changed by this qualification.

The [sanitized qualification summary](qualification/2026-11-05-public-reader-candidate.json)
binds these results to the image and evidence hashes. The admitted RC.4 images,
container start times, database volume and sealed source archive were rechecked
and remained unchanged.

### Development review after RC.4

The November 5, 2026 product review added always-visible report search,
original-text matching, canonical Unicode matching and filter state retained
across workspace changes. The visual update improves narrative typography,
selection contrast, search controls, scrollbars and narrow-screen source totals.
The backend now requires explicit permission configuration before its optional
OpenSky fallback can issue a request.

The frontend passed 412 tests, TypeScript and Vite. Build `e24051a47c5d`
matched the source at that checkpoint. Its production preview passed
12 real Google browser/viewport combinations across Chromium, Firefox and
WebKit. Six additional production workflows checked query/source criteria
across Earth, Media and Brief, mobile drawer remounts, clear-focus restoration
and native keyboard scrolling. All retained the Earth canvas. Five keyless
showcase workflows passed. Eight changed palette pairs met the measured
contrast thresholds, with the lowest tested text contrast 8.24 to 1.
This is a scoped contrast check, with complete accessibility qualification
remaining separate.

The backend source passed 997 tests and 29 subtests on the Windows host,
including permission-off and permission-on tests through the aircraft polling
loop. The development frontend preview uses the existing live backend.
The new backend permission setting was subsequently image-qualified above;
live deployment admission remains separate.
The earlier RC.4 archive and four-hour soak retain their original identities.
This development build has no new long-session or public-load qualification.
Physical phones remain outside this emulation result.

See the [capability comparison](PRODUCT_GAP_REVIEW.md) and
[website integration assessment](WEBSITE_INTEGRATION.md) for priorities
and unresolved public-serving gates.

### 0.2.0-rc.4 local candidate

The packaged backend passed 994 tests and 29 subtests. The exact Compose
profile passed restricted-role, PostGIS, committed delivery, TCP, process
and HTTP boundary checks. The Bot API fixture checked durable
acknowledgement, immutable edits and separation from the legacy history
checkpoint. The local profile runs with Telegram disabled and has no
deployment bot token. A publisher-authorized provider run is a separate gate.

Frontend build `75a234f02100` passed 405 tests and five keyless browser
workflows. All 403 application files served by the live profile matched
the admitted build. The database volume and original briefing were
preserved during the app image transition. The [private GOOL operator
workflow](GOOL_REVIEW.md) validated three questions from one authored
fixture through its explicitly selected Azure route.

The exact live build passed 12 browser and viewport combinations
covering real Google Earth imagery, native attribution, Earth, Media,
Brief, Feed, Settings, Methods and source health. The separate iPhone 15
WebKit emulation passed trusted taps, Feed scrolling by keyboard and
same-context landscape resizing. Its first attempt timed out before
completing the tabs. Physical-device behavior remains unmeasured.

The independent four-hour confirmation completed on November 5 at
07:00 UTC with unchanged backend, frontend and database container
identities. All 480 sample rounds, 3,840 REST requests and 48 SQL checks
passed. The separate delivery observer matched 27 natural publication
offsets to PostgreSQL. The Google browser completed 478 samples with
zero findings or page errors, renewed its root automatically and received
300 successful new tile responses after three hours. Aircraft, maritime,
satellite and thermal provider states were healthy in all 480 sampled
rounds. Telegram was explicitly disabled throughout. The live usage ledger
remained zero, with the separate private GOOL exercise recorded above.

The first four-hour run is retained separately. Its browser had one
provider-readiness timeout, and one container-identity inspection was
unavailable around the same early interval. Its strict identity assessment
remains incomplete. Thermal observations were unavailable in two rounds.
The later confirmation does not resolve those initiating causes. These
sampled observations do not establish source truth, physical-device
behavior, every code path or absence of memory leaks.

The backend and database each retain a raw High SQLite match. The
backend excludes the standalone SQLite shell with a build guard. See
[security review](OS_SECURITY_REVIEW.md) for the actual component scope.

### RC.3 local evidence

**0.2.0-rc.3 local candidate, November 4, 2026 UTC.** Frontend build `2a333395c5f8` passed 404 tests. The packaged backend passed 911 tests, 29 subtests and 11 offline media checks. The exact three-image profile passed isolated Compose, restricted-role, PostGIS, TCP WebSocket, committed delivery and served-header checks. The archived restore preserved 12 tables and five sequences. The live logical restore preserved the original volume and retained briefing artifacts. Physical-device testing and source factual accuracy have separate evidence requirements. Publication is held while backend and database retain High image findings. See [security review](OS_SECURITY_REVIEW.md) and [database upgrade](DB_UPGRADE.md).

The exact Alpine spatial profile passed 250 upstream SQL cases on a clean
database and the same 250 after an extension upgrade. Its source-matched
CUnit runner passed 346 tests and 5,495 assertions with the qualified native
dependencies. Auxiliary source-tree checks had separate tooling limitations.

The live Google workspace passed 12 browser and viewport combinations plus
targeted iPhone and Pixel device-profile emulation. Three engines played the
retained briefing. Firefox needed a user resume to restore paused captions.
Three fresh stock-model attempts failed. Two preserved responses violated the
literal-source validation rule. Separately, a retained valid response passed validation
and a new source-card video from the same authored fixture passed HTTP
range delivery and full audio/video decoding. This qualifies the video
and validation paths within that fixture.

An uninterrupted four-hour loopback observation on the exact same three
containers passed 480 sample rounds, 3,840 REST requests, 48 SQL checks and
244 natural WebSocket messages. The independent REST delivery observer
matched 244 publication offsets to PostgreSQL. There were zero sampled
REST or SQL integrity errors and zero recorded paid usage. The same
Google Earth browser renewed its root automatically and received 300
successful tile responses after three hours.

Provider availability had separate findings. Telegram entered a terminal
`ConnectionError` state and stayed failed for 139 of the 480 samples.
Aircraft were stale in 11 samples, and FIRMS thermal observations were
unavailable in two. These observations qualify the bounded local serving
and delivery path and leave continuous provider coverage open.

### RC.2 evidence archive

The following tables retain the scope and image identities of the October 30 release. [RC.2 public release and verification assets](https://github.com/DankWoodsmoke/conflict-monitor-public/releases/tag/v0.2.0-rc.2)

### Completed RC.2 checks

| Check | Measured result and scope |
| --- | --- |
| Admitted 229-test frontend | `sha256:71dae32e0eb066f835426cdbce78c9d6a0eaedbc51a19cd835edfdb3b7012ce0`, live start `2026-10-30T05:43:01.56454013Z`. **229 tests/21 files, zero failed/skipped**, TypeScript/Vite and Cesium compatibility passed. Package/lock bytes were unchanged from the earlier zero-advisory npm result; that result was not called a new audit. All97 exported frontend files/63 tested source files bound to the build, all402 local application files matched, and all403 served static files (including nginx error page), seven header/cache cases, healthy status, UID101/zero capabilities/no-new-privileges/read-only root passed. [Build/live admission](qualification/2026-10-30-rc2-frontend-timeline-admission-229.json). |
| Native keyboard ownership repair | The same 33-case harness measured **12 failures/21 passes on the old image**, then **33 passes on isolated 71dae and 33 passes live**, across Chromium/Firefox/WebKit. Native video, modal buttons and input arrows preserve LIVE/range/focus; neutral timeline arrows still change the window. Firefox's standalone native seek of plus/minus5s was suppressed before and restored after the repair. Chromium retained its measured native behavior; WebKit's zero native seek in this host remains zero, not an invented seek pass. Earth/Media/Brief preserve the canvas. [Before/after receipt](qualification/2026-10-30-rc2-timeline-keyboard-229.json). This is targeted regression evidence, not a rerun of all earlier102 accessibility states. |
| Actual final backend image | `sha256:9b094edd5879d47d682c62dbb81f977b9ed5597058aa3f4a162434bd31c02877`. **597 tests plus 29 subtests passed, zero skipped**; pytest 9.64s, runner elapsed 16.719s. Only tests/tools were mounted, application imports resolved to `/app/app`, and 27 missing development packages were added in the disposable layer. No private environment or application source was mounted. The disposable unit container ran as root; production UID/capabilities are separately checked. [Exact receipt](qualification/2026-10-30-rc2-linux-backend-597.json). |
| Final database and upstream regression | `sha256:fc61b5645ca9a0115ef9a4fab2f0a3b35006c90a05d5511c5c010786da75ba65`: PostgreSQL 17.11/PostGIS 3.6.4 with the pinned upstream FlatGeobuf backport. **Two complete 250-case SQL runs** (500 case executions, not 500 distinct cases) and **346 CUnit tests/5,495 assertions** passed. Native PostGIS bytes matched the final image before/after testing. [Receipt](qualification/2026-10-30-rc2-database-cutover-and-regressions.json). |
| Executed database cutover | Consistent dump and complete table hashes share the exported repeatable-read snapshot at `2026-10-30T02:16:09.106052+00:00`. Restore into a new volume preserved all ten recorded tables, five sequences, 23 indexes, geometry, locale and extensions; the original volume remains preserved. Fresh separate-database bootstrap, restricted-role, PostGIS and TCP pipeline gates passed. An earlier reused-fixture spatial assertion failed and remains retained. This is no zero-downtime or arbitrary-extension claim. [Full comparison](qualification/2026-10-30-rc2-database-cutover-and-regressions.json); [required migration procedure](DB_UPGRADE.md). |
| Actual RSS  ->  local analysis  ->  narrated MP4 | **24 checks passed** on the final backend/database through the actual loopback API and PostGIS, one owned Qwen3.5:4B CPU inference, Piper and restricted FFmpeg. Real RSS report 1257, snapshot hashes, literal Unicode/UTF-16 spans, no source mutation, atomic content-addressed video, complete independent decode and HTTP 206 delivery passed. MP4: 759,731 bytes, 38.379801s, H.264/AAC 720p/24fps, SHA-256 `c39e44477dad85763f0c6d573140f55643e82fc6f72fc8e0b04efa693a7e1e6e`. Paid UsageLog stayed zero; local inference/resources are separate usage. Initial Telegram selection was rejected before generation and no gate was relaxed. [Receipt](qualification/2026-10-30-rc2-local-generation.json). This does not certify factual accuracy, human audibility or pronunciation. |
| Restricted media build | Original SHA/signature-verified FFmpeg 9.0.2, required local codecs/demuxers and only `file`/`pipe` protocols. **11 actual offline media checks** on final backend bytes passed under read-only/no-network/dropped-capability limits, including CPU Piper, two-segment concatenation, probe/full decode and HTTPS/HLS rejection. This synthetic fixture is separate from the real-source run. [Security/media projection](qualification/2026-10-30-backend-security-remediation.json). |
| Fresh shipped-Compose profile | All three images built in a unique isolated project. Real bootstrap/runtime-role/PostGIS/TCP/WebSocket checks, all 56 packaged application/migration byte hashes, process UIDs/effective capabilities/no-new-privileges, private ports, read-only frontend/database filesystems, blank HTTP bootstrap secrets and seven HTTP header/cache cases passed. Fixture credentials and synthetic data only; four owned containers and two volumes were removed. This Windows-orchestrated Linux-container run is a **local preflight**, not hosted Actions. [Full runtime receipt](qualification/2026-10-30-compose-profile-ci-preflight.json). A later [workflow-only artifact handoff repair](qualification/2026-10-30-compose-artifact-handoff.json) requires sanitizer success before upload from a separate sanitized directory, retaining always-cleanup. Exact offline valid/three rejection fixtures, Actionlint, 25 Bash blocks and four Python heredocs passed; the earlier full-runtime receipt retains its original workflow hash. |
| Earlier 224-test frontend build | **224 tests/21 files, zero failed/skipped**, TypeScript/Vite, Cesium compatibility and npm audit passed. Image `sha256:b6e6bc17ba236fd46c6f7f64e3bb4efb0da2c0dfb7797b14668bdd888123b998` uses 97 exported frontend files. Isolated preflight checked every one of its **403 served static files** (402 application files plus nginx's error page), seven HTTP header/cache cases, UID 101, zero effective capabilities, no-new-privileges and a read-only root filesystem. Source/build/runtime identity remained unchanged during that byte check. These are historical build/preflight results for those bytes. [Exact image security binding](qualification/2026-10-30-frontend-security-rebind-b6e6-final224.json). |
| Earlier b6e6 native video/captions | Actual playback, exact transcript/cue metadata and visible caption on/off qualified in **three engines** on admitted `b6e6bc17...`, with a retained limit. Chromium/WebKit passed immediate paused-frame restoration; **Firefox failed paused repaint** but native user Play/Pause recovered visible caption pixels, retained the same video/one track and cleared conditional guidance, with no generation POSTs/page errors. The real `c39e4447...` MP4 has three hash-matching segments: audio 38.359365s versus container 38.379801s (20.436ms difference). Cues are segment timed, not word aligned. This is **two strict paused-restoration passes plus one qualified user-resume recovery**, not three paused-repaint passes. Earlier development/preflight failures remain preserved; no publisher prose or caption imagery is redistributed. [Production receipt](qualification/2026-10-30-rc2-mobile-accessibility.json). |
| Earlier 225-test portability fix | One unimported test was split after a hosted 5-second timeout; all count/name boundaries and modal assertions remain, with no timeout increase, retry or skip. **225 tests/21 files passed** locally and in qualified-source hosted CI. The admitted image's actual 224-test execution remains preserved. A fresh225-source build has the same11 uncompressed layers, runtime configuration and 403 static files as `b6e6bc17...`; all402 local files and17,218,939 served bytes match. It was not substituted for the observed running image. [Portability/byte proof](qualification/2026-10-30-frontend-test-portability-225.json). |
| Earlier b6e6 accessibility/reflow | **102 axe states, zero violations at all impact levels;71 keyboard samples, zero failures;30 reflow states passed**, including controlled200-percent text enlargement and actual Firefox24px minimum-font preference. **190 incomplete rule occurrences** and **four unavailable usage-popover states** remain unqualified; zero reported violations is not complete WCAG/contrast clearance. [Scoped production projection](qualification/2026-10-30-rc2-mobile-accessibility.json). |
| Earlier b6e6 matrix/network/touch | **12 browser/viewport cases, five E2E workflows (zero skipped/unexpected/flaky) and 18 network-recovery checks passed**. Eight strict touch checks passed; both strict8/9 runs retain incomplete pan assertions. A separately declared native-camera method passed with322 enabled positions, visible mask322 -> 0,36.920% of50,544 unobscured ROI pixels changed and exact decoded-pixel restoration. This is additional bounded camera-motion evidence, not a relabeled9/9 strict run or exact track-identity/camera-center proof. Native OS background/eviction, physical iPhone and screen-reader speech remain unqualified. [Full limits and failed attempts](qualification/2026-10-30-rc2-mobile-accessibility.json). |
| Earlier hosted three-job CI | Exact source commit `b15a60eb19bfa141e1c6c9ec576c7e9205e338c1`: [run41003507817](https://github.com/DankWoodsmoke/conflict-monitor-public/actions/runs/41003507817), all three jobs successful. Frontend225, backend597+29, build/compatibility/npm/pip checks passed. The custom shipped profile freshly built all three images, verified original FFmpeg SHA/PGP, ran21 restricted-role checks, fresh PostGIS,12 synthetic TCP/WebSocket checks,56 packaged application-byte comparisons, all three process-boundary checks and seven header/cache cases; sanitization/upload/owned cleanup passed. Those hosted image IDs are not claimed byte-identical to local deployed images. [Logs and exact job/source binding](qualification/2026-10-30-rc2-hosted-qualified-source-ci.json). |
| Current security findings | Exact backend scan: **209 records, 2 Critical/73 High**; database: **412, 10 Critical/117 High**; admitted frontend `71dae32e`: **three Medium, zero High/Critical**. Its72 APK rows and complete finding/fix multiset equal the earlier `4236ac47` baseline under the same pinned database. Raw backend/database High gates still fail. Vendor comparisons retain open findings, backports and supplemental custom FFmpeg/native curl/static Go inventory. Counts include aliases; they are not exploitability or unique-CVE totals. [229 frontend rebind](qualification/2026-10-30-frontend-security-rebind-71dae-final229.json), [OS review](OS_SECURITY_REVIEW.md), [backend](qualification/2026-10-30-backend-security-remediation.json), [database](qualification/2026-10-30-database-security-review.json), [Go binary](qualification/2026-10-30-gosu-go-binary-review.json). |

An independent [Gitleaks 8.30.1 source scan](qualification/2026-10-30-rc2-public-source-gitleaks.json) retained five raw matches (exit 1): one public signing fingerprint and four recomputed source-file digests, with zero confirmed or unresolved credential matches. No custom suppression was added. A [separate lockfile scan](qualification/2026-10-30-rc2-public-lockfile-gitleaks.json) covered its 86,621 bytes with zero findings after removing only that file's default path exclusion. A [subsequent exact-span/byte-gate repair](qualification/2026-10-30-rc2-public-export-span-and-byte-gate.json) rejects an unrelated match on the same line rather than inheriting a public-hash exemption, requires exact engine-byte reconciliation and retains the original five detections. Historical DEBUG logs can expose decoder source fragments despite report redaction; all raw logs stay private and later scans use INFO. Eleven raster files and documented default value/rule allowlists remain outside that text-scanner coverage. Final export bytes require their own scan and archive binding; this is not exhaustive secret clearance.

The subsequent [final Python tool/source rebind](qualification/2026-10-30-rc2-linux-backend-597-export-rebind.json) reran all **597 tests plus 29 subtests** on the same backend image after repairing cross-platform release-manifest ordering: zero failures/skips, 13.36s pytest / 20.375s runner. Executed Python test/tool hashes stayed unchanged through that run. The earlier 9.64s receipt above remains preserved.

### Post-freeze release admission

The source snapshot deliberately has no final-duration or future-tag PASS. When published, the [RC.2 release](https://github.com/DankWoodsmoke/conflict-monitor-public/releases/tag/v0.2.0-rc.2) carries `conflict-monitor-0.2.0-rc.2-verification.json`. Admission requires its PASS result, bound to the exact tag commit, immutable source-ZIP name/size/SHA-256 and in-ZIP manifest SHA-256. Its measured gate evidence must include the final **183-minute Google** and **185-minute server** observations, exact merge/tag CI, image/start identities, sample gaps and retained failures/limits. Independent public-download verification then compares all three assets against the trusted local bytes and the tag's complete Git tree. An asset cannot attest its own completed public download in advance.

The stable verification-asset fields are `schema_version:1`, `release_version`, `status`, `tag_name`, `tag_commit`, `archive_filename`, `archive_bytes`, `archive_sha256` and `source_manifest_sha256`, with measured qualification/limitations alongside them. Keeping post-freeze evidence outside the ZIP avoids a self-referential source/archive checksum. Absence, an incomplete result or a different binding does not qualify this candidate. Do not infer gate completion from the source-document date or a moving branch badge.

Earlier `b6e6` browser time of4866.541s/163samples and server sampling through4891.52s/164samples was interrupted for the confirmed keyboard repair; **zero seconds carry into71dae**. Its broad [finite browser batch](qualification/2026-10-30-rc2-mobile-accessibility.json), 224-test admission and 225-test-only portability proof remain phase-specific. Browser emulation does not qualify physical devices, screen readers, native background eviction or field networks. Firefox paused-caption repaint remains a failure despite measured user-resume recovery.

The earlier shipped-container job passed on source `b15a60eb`; initial transport failures and the test timeout remain retained. The [bounded fetch repair](qualification/2026-10-30-rc2-build-fetch-retry.json) preserves authenticity gates; hosted rebuilt images are distinct from the locally qualified media image. That source-commit CI does not stand in for the final merge or tag. No zero-vulnerability, full WCAG, every-line or sustained-production-SLA assurance is made.

### Retained RC.1 and intermediate Earth evidence

The [imagery quality review](EARTH_QUALITY_REVIEW.md), [03b08f verification](qualification/2026-10-29-earth-quality-verification.json) and [source/runtime manifest](qualification/2026-10-29-earth-quality-source-manifest.json) record the later Earth phase before this security/mobile follow-up. Its 178-test UI and bounded browser windows remain dated evidence, not tests of RC.2's final frontend or new backend/database images.

The remaining historical tables and measurements below describe **0.2.0-rc.1**, checked October 29, 2026, or the explicitly named intermediate profile. They preserve [phase 1](VERIFICATION_PHASE1.md), [phase 2](VERIFICATION_PHASE2.md) and their original limits. The original April 8 backup, local changes, former VPS and original private Git history remain separate and preserved. The clean destination is [DankWoodsmoke/conflict-monitor-public](https://github.com/DankWoodsmoke/conflict-monitor-public).

The current workspace uses one persistent Cesium/Google Earth canvas. Media and Brief open within that workspace; previous map/3d links resolve to Earth. The qualified local profile uses real free-source ingestion and operator-triggered local extraction/narrated source cards. Google imagery requires its own billing, API restrictions and attribution; it is not a free/open dataset.

### Historical RC.1 executed checks

| Check | Measured result and scope |
| --- | --- |
| RC.1 Linux backend | **574 passed +29 subtests;0 failures/0 skipped**, Python3.12.16,17.84s. Six added public-export password-key regressions leave that production image/application bytes unchanged; earlier568-test receipts remain preserved. Nonroot UID10001,2CPU/2GiB; source mounts readonly, no credentials mounted, external network disconnected before execution. Production dependency versions unchanged by installing test dependencies. This historical execution is separate from RC.2's actual-image 597-test run above. |
| GitHub-hosted CI | Qualified source commit `575ffff431edad9e00f2a9bf189b6117488ca26e`: [run40884082179](https://github.com/DankWoodsmoke/conflict-monitor-public/actions/runs/40884082179) completed with both jobs successful. Logs confirm149 frontend tests and574 backend tests +29 subtests; build, compatibility, npm/pip audits and actual bootstrap/restricted-role/PostGIS/TCP steps passed. Final documentation/tag CI and uploaded hashes are separate release metadata. This does not substitute for local live-provider/browser/media/hour checks. |
| Backend image/source binding | `sha256:4202bfc7add922228c024623b1879ccec7eaf617c718d583b69568b440f90788`;58 deployed runtime/dependency/migration files matched candidate bytes. Source manifest and unchanged-during-run checks passed. |
| Frontend repaired source | **149 tests/15 files**, TypeScript/Vite/compatibility pass;65 unused packages removed. Final image `sha256:cb2cc67e72d8c1fc67049c6b91d621ee2e31de0be3e3c4ccda4890a791e5422a`. Repairs cover focus continuity, modal traps, request races, truth labels, explicit failures, source permission, wrapping native attribution and embedded Media layout. The all-severity control includes UNSCORED records explicitly. |
| Database restore and permissions | Actual PostgreSQL17.11/PostGIS3.6.4 logical restore into a new volume: all9 tables/counts/full-row hashes, raw/receipt hashes,3 checkpoints, sequences and 23 index definitions matched the frozen source. Spatial/replay/digest/collation checks passed. Separate runtime `monitor` has no administrative flags, memberships or object ownership; actual denied-DDL/escalation checks and allowed DML/advisory-lock behavior passed. Live cutover/preservation and absence of administrator secrets from HTTP environment values passed. |
| Separate historical recovery | The original April archive's211,771,511-byte compressed PostgreSQL16.4 dump restored privately into an isolated17.11/3.6.4 instance. **All53,715 rows/seven tables round-trip exactly**, including19,818 events and12,361 snapshots. Of those events,5,991 retain a known dummy location. No historical facts/locations/model scores are thereby verified, no active-schema migration or live merge occurred, and the isolated container is stopped with its volume preserved. |
| Actual PostGIS/TCP/WebSocket | **13 checks passed** with real persistence and an actual Uvicorn server; source revisions, retained failures, scoped checkpoints, late-publication recovery, snapshot bounds, citations and fail-closed administrative operations. Synthetic qualification DB is separate from the live DB. |
| Expanded source collection | **34 native feeds parsed;31 selected**. Initial126-second natural sample:234 RSS WebSocket deliveries, all31 sources persisted,50 sampled API/ordinary-role SQL/source-hash bindings exact. A separate post-backlog30-minute window captured8 new reports from5 sources, with all eight WS/API/DB bindings exact and26 quiet feeds. Declared-publication -> transaction-created median22.347s/max174.505s; created -> WS median8.216ms/max22.418ms. No global firstness, publisher ranking, truth or SLA inference. |
| Google Earth/mobile workflows | Final cb2 image: **12/12** Chromium/Firefox/WebKit  x 320 x 740,390 x 844,768 x 1024,844 x 390; Google configured through normal server browser-key delivery, with attribution, one canvas, panel/camera continuity, last-known controls and far-side masking. **4/4** actual-live Google workflows passed. **9/9** native touch/emulation checks passed, including measured pinch/pan, real feed scroll and portrait-to-landscape canvas preservation. These are browser viewport/touch emulations, not physical phones. |
| Actual local analysis/video | **24 checks passed**, actual nginx API  -> PostGIS source55  -> owned local Qwen3.5:4B CPU model  -> validated analysis  -> Docker Piper/FFmpeg  -> HTTP MP4. Source/analysis/video snapshot hashes agree; full independent decode and HTTP206 range delivery passed. Paid UsageLog0 before/after. |
| Actual MP4 | New upgraded-profile H264/AAC720p24fps,33.503s; SHA256 `0932039e271f22c6afa7f25afab4fca9947b795b98ca567dde959c404d16470d`,650,081 bytes. Native playback advanced on all3 engines at390px through final cb2, with the same Earth canvas, no media errors and no implicit generation POST. The earlier `cba3069b...`33.160s MP4/analysis survived cutover byte for byte and remain independently preserved. No incident footage is generated. |
| Audio consistency | Cached offline CPU/int8 ASR against the new exact MP4:0 edits/70 expected words, **0% unadjusted WER**, both uncertainty/no-footage disclaimers recognized. The earlier69-word sample's1.449% WER remains preserved; its publisher display spelling was corrected through the trusted catalog. Automated consistency is not a human listener, pronunciation or MOS certificate. |
| Dependency audits | Production Python: **0 known advisories/0 skipped across71 packages**. Full Linux test environment: **0 known advisories/0 skipped across98 packages**. Frontend:0 reported vulnerabilities,174 total resolved dependency entries including optional/development packages. Dated advisory results do not establish absence of unknown vulnerabilities. |
| OS image findings | Exact backend817/database748 scanner records retain failed raw high-severity gates and limited explicit vendor-backport/applicability review. Patched final frontend retains3 Medium BusyBox aliases and no reported High/Critical matches. No ignore rule or blanket exemption was added; [OS review](OS_SECURITY_REVIEW.md) retains the unresolved scope. |
| Accessibility | Final cb2 image: **26/26** Earth/Media/Brief/Settings/SourceHealth/optional-dialog/filter states at desktop/portrait/landscape, zero reported violations at every impact; **20/20** bounded keyboard scenarios passed. Contrast remains incomplete in23 cases (643 repeated node occurrences/116 selector forms); symbolic label checks remain incomplete in20 cases (51 nodes/eight forms). Incomplete checks are not passes or WCAG certification. Earlier failures, intermediate passes and later screenshot defects remain preserved. |
| Clean source reconstruction | Fresh allowlisted snapshot: npm ci,149 tests, Cesium compatibility, TypeScript/Vite build and 4/4 keyless browser workflows passed. All400 built assets matched cb2. Four native screenshots passed separate manual visual review after earlier portrait-credit and Media-clipping defects were repaired. Final distribution packaging is a separate check. |
| Browser lifecycle and markets | Actual final-profile30-minute Chromium observation:60 samples across Earth/local-analysis/narrated panels, same Google-ready canvas,0 findings/page errors/implicit generation POSTs, unchanged service identities. Separately420.355 real seconds observed0 -> 9 SVG market sparklines from two five-minute browser-memory samples each. No historical-market API, physical-device or leak-free claim. |
| Final image soak | **Completed3600.0s/120 samples/960 REST/12 scheduled SQL checks**, normal observer exit0, bound to both application image/start identities, actual PostgreSQL/PostGIS versions and the new database volume: one unchanged profile,0HTTP/integrity/raw-hash/WS payload errors,32 natural WebSocket messages and0disconnects. Earlier mixed/intermediate observations remain separate evidence. This is a bounded local sample, not a production SLA. |

Earlier Linux runs and failures remain preserved. A test assumed deep JSON must exceed the decoder recursion limit; Python3.11 did, while3.12 parsed it and rejected its shape. The portability correction accepts either explicit fail-closed rejection and separately tests genuinely malformed JSON and decoder recursion. Later source-collection, permission and metadata repairs increased the suite to568. No assertion was skipped or marked expected-failure.

### What Earth plots

Unknown report coordinates remain unknown. Every retained entity refreshes its position and details; coordinates must be finite/in range. Aircraft and vessels are explicitly **surface projections**, with reported aircraft altitude/reference retained as metadata. No fallback altitude, datum conversion or extrapolated motion is invented. An independent WGS84 camera-ray horizon check masks the far hemisphere even when Google's globe primitive is hidden. Active frontend orbital markers, polling and cosmetic sensor-like shaders are removed. The retained backend OMM collector/API is a separate modeled-data capability; it supplies no current imagery or observation-coverage proof.

Four named250NM aircraft circles rotate at the existing one-request/15s budget. This improves the chosen regional coverage and is not global tracking. Each region retains its last-good result and failure/source age. Live aircraft/vessels expire after120/600s; source-stale positions within that bound are visibly muted, hollow **LAST KNOWN** observations, with an optional hide control. Freshness remains45/120s, and fetching old data never makes it current. Replay shows **RECORDED** positions against their observation clock, within bounded6h snapshot queries. Infrastructure/routes remain optional, off by default and unverified.

The narrow Cesium1.139.1/engine23.0.1 compatibility repair guards upstream `OffscreenCanvas` checks using exact original/patched hashes and versions. It fails closed on changed dependency bytes. Native Windows WebKit WebGL2 worked without inventing an OffscreenCanvas implementation. See [Earth behavior and tests](../frontend/EARTH_VERIFICATION.md).

### Source and analytical limits

The clean live database contains real source reports, not showcase fixtures. RSS is attributed publisher metadata; Telegram reads explicitly selected public channels. Source observation/publication/collection clocks and incomplete coverage stay visible. AIS/ADS-B identities and receiver coverage have limits. Thermal anomalies are sensor observations, not evidence of a strike, actor, casualties or independent confirmation. No publisher/network count automatically becomes factual certainty. Immutable originals, scoped source IDs, revisions, failure receipts and corrections remain inspectable.

Source digests require no model. Optional local extraction labels topic, linguistic stance and exact source spans; it never assigns event coordinates, severity or a fact verdict. Qwen3.5:4B scored11/12 topic and11/12 stance labels on the frozen12-case synthetic CPU sample, with one batch rejected and8/12 reports accepted. This is a small measured task comparison, not general factual or multilingual accuracy. Original failed outputs, development-tuning disclosures, model digests and offline replay are in the [public evaluation bundle](qualification/local-ai-evaluation/README.md). A separate [24-case stress extension](qualification/local-ai-evaluation-extended/README.md) of the selected4B scored22/24 topic and 21/24 stance labels, accepting16/24 reports in4/6 batches. It exposed CJK token-boundary and military-band false rejections, actor extraction misses, and a literal quantity from an injected source instruction. Literal-span validation establishes substring identity, not evidence, role attribution or factual truth. No tuning/retry followed these results.

Narrated video reads attributed source reports over editorial cards, preserving citations/publication clocks and disclaimers. Full media validation and atomic publication preserve the previous good result on failure. Piper's optional standalone speech worker is GPL-3.0-or-later; application MIT scope, engine, voice/model and FFmpeg rights are documented separately. See [local AI/video](LOCAL_AI_VIDEO.md) and [current upgraded-profile generation summary](qualification/2026-10-29-postgresql17-local-generation.json). The [earlier production summary](qualification/local-generation-production-summary.json) is historical evidence for the preserved pre-cutover artifact.

GOOL remains a separate optional analyst investigation. Its current text dispatcher shares logs, memory and enrichment side effects; no supported fully isolated GOOL bench was found. No GOOL call, voice/transport start or corpus/persona change occurred. A dedicated read-only draft boundary is needed before a useful role can be measured. See [GOOL analyst boundary](qualification/GOOL_ANALYST_BOUNDARY.md). Private GOOL material is excluded.

### Measured coverage and operational boundaries

At the568-test checkpoint, application unit coverage measured **69.6961%** combined statement/branch coverage:3819/5284 statements (**72.2748%**) and951/1560 branches (**60.9615%**), with no excluded lines. Combining those traces with actual administrator bootstrap, restricted-role PostGIS and12-check TCP execution measured3883/5284 statements (**73.4860%**),973/1560 branches (**62.3718%**) and **70.9527%** combined coverage. File inventories/denominators match; no old463 traces were reused. The final574-suite adds six release-scanner tests outside the measured application source; it is a separate execution, not a relabeled coverage run. The13-check public-feed proof is also separate. Reading code and passing tests do not verify every line, factual truth or global optimality.

| Remaining boundary | Consequence |
| --- | --- |
| Physical devices/screen readers | No physical phone identified. Browser emulation and axe/keyboard checks cannot establish physical performance or full assistive-technology accessibility. |
| Duration/load | The final one-hour server and30-minute browser observations are bounded local samples, with no24/7 SLA, sustained public load or Internet latency certification. The earlier140-request/10-concurrent sample had0 errors/p95 85.19ms and remains only that short sample. |
| Event revisions after reconnect | Creation-ID recovery handles newly created IDs, including old publication times. Revisions of an existing ID require a distinct update cursor; they are not covered by that recovery contract. |
| Historical deployment | The former VPS was unreachable. The newly collected candidate database has a hash-preserving live upgrade, and the separate April production dump has a full-row archival restore. The latter lacks the current provenance/schema contract and was not merged. Unknown post-backup server writes remain unrecovered. |
| Data and imagery rights | Code licensing does not clear provider/data/asset redistribution. Imagery dates/coverage vary and do not prove event location/time. Private source bodies, sessions, weights and environments are excluded from public export. |
| Paid legacy paths | Inherited paid classifier/SITREP/video remain disabled in this profile and are not certified by free local-tool results. |
| GitHub | Hosted qualified-source CI passed; final tag/asset checks are linked from the release. Passing build/unit/integration/advisory checks does not verify source truth, every code path, the OS/host or a stable-release SLA. |

Docker's original startup blocker was resolved by preserving/renaming stale Windows AF_UNIX endpoint directories while Docker/WSL were stopped; no reset, reboot or VM/volume deletion. PostGIS migrations and the geography index ran against actual PostgreSQL. The original archive SHA256 remains `31d04ebcda8ecf0be13a5b14eed5093892e7d4985957ff91fb45f8d97f9e2ec1`.

Historical public machine receipts include:

- [568-test exact Linux image run and source manifest](qualification/2026-10-29-postgresql17-linux-backend-568.json); the [463-test coverage receipt](qualification/2026-10-29-earth-backend-coverage-463.json) is retained as historical evidence.
- [Final 574-test Linux/source/audit binding](qualification/2026-10-29-postgresql17-linux-backend-574.json) and [24-test public-export database-password repair](qualification/2026-10-29-public-export-database-password-gate.json).
- [Actual GitHub-hosted qualified-source workflow and job outcomes](qualification/2026-10-29-github-qualified-source-ci.json); final commit/tag/package receipts are release assets to avoid a self-referential in-tree checksum.
- [Final verifier-source Linux rebind](qualification/2026-10-29-postgresql17-linux-backend-568-tools-rebind.json) and [149-test frontend/runtime/accessibility/Google/native playback binding](qualification/frontend-layout149-runtime.json).
- [Clean cb2 source reconstruction and four manually reviewed synthetic/keyless previews](qualification/clean-source-reconstruction-cb2.json).
- [Final 12-case browser matrix, four live Google workflows and nine native-touch checks](qualification/2026-10-29-postgresql17-cb2-browser-mobile-touch.json). The tested native-touch harness is included at [tools/verify_native_touch.cjs](../tools/verify_native_touch.cjs); the earlier experimental scroll-command failure remains in the receipt history.
- [Production/test dependency audits](qualification/2026-10-29-earth-python-audits.json).
- [13-check actual PostGIS/TCP/WebSocket gate](qualification/2026-10-29-earth-postgis-pipeline-13.json).
- [Report/receipt/checkpoint and analysis/video restart equality](qualification/2026-10-29-earth-restart-and-video.json).
- [PostgreSQL restore](qualification/2026-10-29-postgresql17-restore-rehearsal.json), [restricted runtime](qualification/2026-10-29-postgresql17-restricted-runtime-rehearsal.json) and [final-image actual SQL pipeline](qualification/2026-10-29-postgresql17-final-image-sql-pipeline.json).
- [Actual live cutover and old artifact persistence](qualification/2026-10-29-postgresql17-live-cutover-and-artifact-persistence.json).
- [Separate historical database recovery and dummy-coordinate counts](qualification/2026-10-29-historical-database-recovery.json), with [archival scope and schema limits](HISTORICAL_RECOVERY.md).
- [Final unit/actual SQL coverage](qualification/2026-10-29-postgresql17-backend-coverage-568.json), [new actual local generation and audio](qualification/2026-10-29-postgresql17-local-generation.json) and [31-source natural DB/API/WebSocket delivery](qualification/source-collection-live-2026-10-29.json).
- [Post-backlog fresh-source arrival clocks and all eight bindings](qualification/fresh-source-arrival-latency-2026-10-29.json) and [final browser lifecycle/market observation](qualification/2026-10-29-postgresql17-cb2-browser-lifecycle-market.json).
- [Final uninterrupted hour, strict assessor, exact runtime identities and all data checks](qualification/2026-10-29-postgresql17-cb2-final-hour.json). The [interrupted 02ee workload](qualification/2026-10-29-postgresql17-02ee-intermediate-workload.json) separately records actual generation coexistence and failed verifier attempts; it is not counted as final-hour time.
- [34 native feed probes](qualification/2026-10-29-source-feed-probes-34.json), [source review](SOURCE_REVIEW.md), [source collection](SOURCE_COLLECTION.md), [OS findings and vendor review](OS_SECURITY_REVIEW.md) and [software inventories](qualification/software-inventory/README.md).

Public receipts are curated under [qualification](qualification/); raw private execution evidence remains outside export. `python tools/release_gate.py --scan-only` checks allowlisted source bytes. Final packaging additionally needs ZIP CRC, byte-manifest and private-value exclusion checks. None is an exhaustive secret-clearance or every-line correctness certificate.

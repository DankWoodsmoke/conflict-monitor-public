# 0.2.0-rc.1 — one Earth workspace and accountable source collection

Earth is the persistent workspace. Reports, source/time filters, regional tracking,
thermal context, search and recorded replay share one Google/Cesium canvas. Media
and Brief panels preserve its camera; earlier map/3d links still work. Unknown
locations stay unplotted. Surface-projected aircraft/vessels retain actual source
clocks, distinct last-known states and expiry; horizon masking removes far-side
markers. Active orbital markers and cosmetic sensor-like effects are removed.

The reviewed native-feed catalog expands from 16 to 34, with 31 selected for free
attributed report intake and three explicit clock/context candidates. Four bounded
concurrent fetches, fair source quotas, durable exact-content identities, resumable
work and backoff improve collection. In a 126-second natural sample, 234 RSS reports
reached WebSocket, all 31 sources had persisted reports and 50 sampled deliveries
matched API/ordinary-role SQL hashes and clocks. Failures and revisions remain
inspectable. Alignment, repetition and short request times never become truth,
independence or globally-first-reporting scores.

PostgreSQL 17.11/PostGIS 3.6.4 replaces the old database profile through a verified
logical restore into a new volume. All nine tables, source/receipt hashes,
checkpoints, sequences and 23 index definitions matched before cutover. A separate
restricted, non-owning runtime role replaces the former superuser application
login. The old volume, private backup, exact rollback profile and original
analysis/video artifacts are preserved. See [upgrade instructions](DB_UPGRADE.md).

The separate April production dump was also recovered privately: all 53,715 rows
across seven legacy tables round-trip exactly, including 19,818 event rows.
Of those events, 5,991 retain the old unknown-location dummy coordinate. The
archive is stopped and preserved without importing those locations, claims or
old scores into live data. See [historical recovery](HISTORICAL_RECOVERY.md).

Optional operator-triggered stock Qwen3.5:4B CPU extraction produces unreviewed
topic/stance/literal spans; it assigns no coordinates, severity or fact verdict.
Piper/FFmpeg creates real narrated editorial source cards with citations and
disclaimers, using no paid inference or speech API. The upgraded-profile 24-check
gate passed full MP4 decode, range delivery and source/hash binding. Cached ASR
matched 70/70 expected words; human audibility/pronunciation is unverified. Frozen
12-case and separate 24-case model evaluations retain errors and rejected batches.
The local AI/video permission guard excludes Telegram material; legacy paid/model
engines remain disabled and unqualified. Private GOOL corpus/persona is excluded,
and no side-effecting GOOL dispatcher was called as a purported isolated bench.

Exact Linux backend testing passes 574 tests +29 subtests with no failures/skips;
the earlier568-test checkpoint's application plus actual bootstrap/PostGIS/TCP
traces measure 70.95% combined statement/branch coverage. Repaired frontend source passes 149 tests, build, compatibility
and npm audit. Browser, accessibility, native-touch emulation, clean reconstruction
and final image-bound observation are tracked individually in [verification](VERIFICATION.md).
Earlier passing automated checks did not conceal later screenshot defects: the
final layout reserves wrapping native credits, fits embedded Media content and
labels the all-severity control accurately.

The final one-hour server observation completed120 samples with one unchanged
profile,32 valid WebSocket messages, no disconnects and no recorded HTTP,
integrity or source-hash errors. A separate30-minute browser lifecycle check
completed60 samples without runtime findings or implicit generation. A final
synthetic regression also repaired export-scanner coverage for all three
PostgreSQL password field names;24 targeted scanner tests passed. These are
bounded checks, not a stable-release, exhaustive secret or24/7 guarantee.

Python/npm advisory passes do not clear OS images. Narrow Brotli/curl fixes remove
49 frontend scanner records; three Medium BusyBox aliases remain. Raw backend/
database high-severity gates retain failed results with limited explicit vendor
backport/applicability review. See [OS security scope](OS_SECURITY_REVIEW.md).

This is a source release candidate. It does not establish every-line correctness,
general model accuracy, global source completeness, physical-device/screen-reader
qualification, a 24/7 SLA or sustained public load. Existing-ID revision recovery
needs a separate update cursor. The unreachable former VPS was not changed;
unknown later server writes are not recovered. Actual GitHub CI passed the
qualified source's frontend/backend, build/audit and restricted-role database/
pipeline gates. The [release page](https://github.com/DankWoodsmoke/conflict-monitor-public/releases/tag/v0.2.0-rc.1)
links the final tag, workflow result and independently checked source archive;
this candidate is explicitly a prerelease.

# PostGIS and free-source pipeline qualification

Checked **2026-10-28 America/Chicago**. This receipt covers the isolated database named `conflict_monitor_test`. Qualification rows are explicitly synthetic and must never be used as the dashboard's real live database.

**October29 follow-up:** the final extended verifier passed13 real
PostGIS/TCP/WebSocket checks, including bounded legacy-provenance parsing and
explicit missing-source disclosure. The production backend, one-Earth frontend,
local generation and restart/soak results have separate current receipts in
[VERIFICATION.md](VERIFICATION.md). Counts and four-view statements below describe
their original dated runs, not the consolidated frontend.

## Executed infrastructure and persistence gates

The stock PostGIS image sets a search path containing extension schemas `tiger` and `topology`. The original fresh-baseline inspector treated their extension tables as an existing application deployment. The baseline now inspects `public` explicitly. Two regression tests establish that extension-owned tables do not block a fresh baseline and that an actual existing `public.events` table still refuses admission before any schema mutation.

Actual migrations ran successfully through `0003_geography_index` against PostgreSQL/PostGIS. Query indexes cover the timestamp/ID pagination cursor, source URL, event type/time, source-ledger time and the exact geography cast used by meter-distance clustering. `EXPLAIN (ANALYZE, BUFFERS)` on a 22-row qualification sample selected `ix_events_geography` for the distance query. The tiny history query naturally selected sequential scan and sort. Observed execution times, 7.312 ms for the first geography call and 0.053 ms for the history sample, are **not** a production-volume throughput or load-test result.

`tools/verify_postgis.py` ran against real persistence. Its fixtures are now unique per invocation, so rerunning the gate does not confuse a previous qualification run with a duplicate delivery in the current run. It verifies channel-scoped message IDs, an immutable report ledger, spatial deduplication and the read API.

## Actual TCP/WebSocket pipeline

`tools/verify_live_pipeline.py --public-feed` completed **twice**, on separate runs, using actual database writes and an actual loopback Uvicorn HTTP/WebSocket server. No persistence, HTTP transport or WebSocket mocks were used in these executions.

Each run verifies:

1. A Unicode/Arabic source report goes through the actual free RSS processor, PostGIS persistence, TCP REST response and WebSocket delivery.
2. The free report has `event_type=unclassified`, `severity=0`, `classification_status=not_requested` and null position. It does not invent a military event, precise location or calibrated confidence.
3. Identical delivery is idempotent. Changed text at the same source URL retains a separate revision receipt while preserving the original public report for review.
4. An undated report is retained in the source ledger with an explicit failure/status and no fabricated event time.
5. Reports sharing an identical timestamp remain fully pageable using the timestamp/ID cursor.
6. A 601-row JSONB snapshot fixture is sampled in SQL to at most 17 returned snapshots.
7. A free source digest persists, exposes source citations, has an unknown/null escalation score, and skips an unchanged source snapshot.
8. Paid generation and administrative write endpoints refuse an unconfigured key with HTTP 503.
9. The usage-log count does not increase; no paid model key or request is used.

The optional real provider step fetched BBC Middle East RSS with HTTP 200, parsed current provider data and persisted two source reports. Repeating the same bounded fetch maintained idempotence. Source URLs, the full check results and the separate query-plan receipt are saved locally in `artifacts/live-pipeline-verification.json`, `artifacts/live-pipeline-verification-repeat.json` and `artifacts/postgis-query-plans.json`. These runtime artifacts are excluded from the public source export. The verification does not establish the factual truth of an article or the completeness of a publisher's coverage.

The default CI invocation omits `--public-feed` to keep provider outages distinct from application failures while still requiring real PostGIS and TCP/WebSocket behavior. Both commands fail with a nonzero/incomplete result unless the database is explicitly named `conflict_monitor_test`.

## Free Brief behavior

`source_digest.py` compiles attributed source titles/excerpts and citations. It does not call a model, estimate conflict severity, infer causal effects, generate an actor's intent or fabricate narration. It uses a stable source snapshot hash and the trigger `source_digest`. API list/detail responses identify it as `attributed_source_digest`, expose a bounded provenance summary, return `UNASSESSED` and null escalation score, and leave speculative sections empty. No available source reports means no manufactured brief.

Legacy report questions and citation IDs are parsed defensively. Malformed, oversized or incomplete legacy structures are labeled, rather than producing HTTP 500 or invented replacements. The original full source snapshot remains internal; only bounded provenance metadata is public.

## Remaining boundaries

- The separate clean live database and Dockerized nginx/backend path were subsequently qualified by the parent deployment run; the in-process Uvicorn gate remains a distinct receipt and does not supply that proof by implication.
- Real source ingestion, transport and report identity do not establish independent factual corroboration, geolocation accuracy or semantic correctness of a separate model output.
- The optional Google Earth, aircraft, satellite, maritime, thermal, media and market providers require their own current response/rendering receipts. This gate does not clear them by implication.
- Model-assisted synthesis, existing production restore/migration, paid narration/video, a long operational soak and physical-device accessibility remain separate checks.


## Bounded free Telegram mode

The free Telegram processor preserves original text/captions as `telegram`, `unclassified`, severity0, `not_requested` and null position. It cannot invoke the classifier, geocoder or anomaly model. A source message ID is scoped to its channel; duplicate content is idempotent, edits retain review receipts and pending/uncompleted receipts cannot authorize advancing the channel cursor. Concurrent checkpoint updates use a PostgreSQL upsert with `greatest`, so old deliveries cannot move the cursor backward.

Reports mode requires an explicit list of at most five public usernames; it never expands an empty selection to the inherited source registry. Startup/cycle reads default to20 per channel with a hard100 maximum. First startup reads the bounded newest slice in chronological order; later polls use the persisted source cursor. Media is not downloaded, and this worker never joins, sends messages, marks read or starts an interactive phone/OTP flow. An existing authorized StringSession is required. The client and polling task are disconnected/cancelled on stop and source/auth errors remain visible by sanitized error type.

Eleven new offline free-mode regressions and existing lifecycle/model-handler tests passed. The real PostGIS/TCP/WebSocket gate was extended with an explicitly synthetic Telegram processor fixture: publication/delivery and concurrent cursor73/71/72→73 passed, and replay42 did not regress it. **That fixture is not a Telegram network/authentication check.** The separate parent Docker deployment then authenticated the inherited StringSession successfully and performed a bounded read of the explicitly selected public channels `qudsnen`, `osint613` and `osintdefender`. Each channel processed3 messages;9 new real Telegram source reports persisted. The status was `ok` without a provider/auth error, `history_complete=false` and limit3 remained explicit, `/health` returned200 and the usage-log count remained0. No joins, sends or interactive OTP flow were used. This establishes the observed bounded authentication/read/persistence path, not complete channel history or factual corroboration.


## Separate Docker/browser receipt

After the real database and source runs, the parent executed the production Docker/nginx browser workflows with the inherited Google browser key held in page memory. Three Playwright workflows passed in11.7seconds, covering every main tab, Google Earth, keyboard/Settings behavior and a portrait viewport. This evidence belongs to the deployed container/UI path and is separate from the mock-free TCP application verifier. Subsequent code/data changes require the relevant checks again; these runs do not turn an untested legacy feature into a verified one.


## Oversized failure-receipt identity

A reproduced edge case showed that two oversized source texts sharing their first12,000 characters could collide when identity used only the retained prefix. The trusted RSS/Telegram adapters already compute the full original UTF-8 SHA-256. Truncated reports now require that valid64-hex original hash for identity/content hash and separately retain `stored_raw_sha256` for the stored prefix. The flag still explicitly says the full text was not retained. Normal, untruncated report identities remain unchanged.

Eight new regressions passed. The actual PostGIS/TCP gate also executed both oversized originals with the same retained prefix: two `input_too_large` receipts persisted with different original content hashes and the same prefix hash; repeating the first original was idempotent. No oversized report became a public event. The updated11-check live-pipeline receipt passed with the real bounded BBC step and no model usage.

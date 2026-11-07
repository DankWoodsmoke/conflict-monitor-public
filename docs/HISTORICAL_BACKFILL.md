# Bounded Telegram history collection

Historical collection is an explicit operator action, separate from live Telegram
catch-up. It preserves source reports and their original publication clocks; it
does not establish incident time, truth, precise location or redistribution rights.

## Requirements and migration

Run the ordinary privileged database initializer against a backed-up, qualified
installation to apply `0004_telegram_history_jobs` after `0003_geography_index` and
grant the restricted runtime role access to its two new tables. The normal HTTP
process must continue to use the restricted runtime role. Follow
[database upgrade and rollback guidance](DB_UPGRADE.md); do not point a fresh
baseline migration at an unrelated legacy database.

All history endpoints require the configured administrative key through the
existing `X-Admin-Key` header. Do not expose that key in public browser code,
URLs or published examples. Collection additionally requires:

- `LIVE_INGESTION_ENABLED=true`, `DEMO_MODE=false` and
  `TELEGRAM_PROCESSING_MODE=reports`.
- An already connected Telegram listener and an explicitly selected public
  broadcast channel in `TELEGRAM_CHANNELS`.
- A source-publication window on or after `CONFLICT_START_DATE` and entirely in
  the past. Boundaries require a timezone and whole-second precision.

History jobs never start a Telegram client, join a channel, fetch a private chat,
download media, invoke a model or modify live collection checkpoints. They use
the existing configured provider session. No Anthropic or GOOL key is needed.

## Operator API

| Method and path | Purpose |
| --- | --- |
| `POST /history/backfill/jobs` | Create an immutable, bounded job |
| `GET /history/backfill/jobs` | Inspect the most recent 50 jobs |
| `GET /history/backfill/jobs/{job_id}` | Inspect one job and its progress |
| `POST /history/backfill/jobs/{job_id}/run` | Execute one bounded page |

Creation accepts this shape; generate a fresh UUID and choose an actually
selected public channel and a suitable past window for the installation:

```json
{
  "request_id": "7a1ccca0-8386-4f90-ab18-4aef31cec65a",
  "channel_name": "selected_public_channel",
  "start_at": "2026-10-23T00:00:00Z",
  "end_at": "2026-10-24T00:00:00Z",
  "max_messages": 50
}
```

The window is inclusive at `start_at` and exclusive at `end_at`, with a maximum
duration of 31 days. `max_messages` defaults to 200 and must be an integer from 1
through 5,000. Replaying the same UUID and parameters returns the same job;
reusing that UUID with different parameters returns 409. No browser job-management
workflow or automatic history scheduler is included yet.

Each run processes at most 50 provider messages, subject to the job's remaining
budget and a 60-second provider-work deadline. Database connection/recovery work
has separate operational limits; the provider deadline is not an end-to-end
HTTP latency guarantee. A single advisory lock excludes simultaneous historical
pages, including pages for different jobs. The public entity ID and upper message
ID freeze when the job first resolves the channel and window. Newer posts cannot
extend that job indefinitely. Entity changes and invalid ID order stop the page.

After a page returns, inspect status and outcomes before explicitly running the
next page. There is no automatic retry loop. Client disconnection is not a
documented cancellation API. Process cancellation or interruption retains durable
progress; an operator can inspect the job before deciding whether to resume it.

## Progress and completion

`processed_messages` counts inspected provider messages, including duplicates,
empty captions, rejected inputs and messages outside the requested time window.
It is not a count of newly recovered Events. `outcomes` distinguishes those
results. Each historical item records its original content hash and, where
applicable, the immutable source-receipt identity. Item and historical cursor
updates commit together after source persistence. Error recovery cannot overwrite
an already committed cursor with stale in-memory progress.

| Status | Meaning and next action |
| --- | --- |
| `queued` | Created; no historical page requested yet |
| `running` | A page began; inspect again after its request finishes. A process termination may leave this status until an explicit resume. |
| `paused` | Page boundary or interrupted/blocked work. Inspect `last_error_type`, `blocked_message_id` and outcomes before resuming. |
| `budget_exhausted` | The immutable job budget was reached before provider-visible completion could be established. Further runs of this job do not collect more. Plan another appropriately bounded window/job. |
| `completed` | The provider-visible requested window under the frozen ID fence was exhausted. |

`requested_window_complete` is true only for `completed`. **Every response keeps
`history_complete=false`**, including successful HTTP responses and completed
jobs. Deleted, unavailable, edited or provider-omitted posts are not reconstructed;
the channel's historical ownership and original pre-edit versions are not proven.
An empty provider result is not proof that no real-world event occurred.

Duplicate content reuses its existing source receipt. Changed source text is an
immutable correction requiring review and does not overwrite the earlier Event.
Unfinished receipts for the same channel and message resume from their stored
text and source time before processing the provider-visible version. An exact
already-committed event is linked without inserting it again. If ownership is
busy or the receipt remains unresolved, the job pauses before advancing past
the message. An older version that was never retained cannot be reconstructed
after the provider stops returning it. Oversized content retains its adapter-computed original full-text
hash and rejection status without promoting a truncated prefix into an Event.

The older `POST /events/admin/backfill` endpoint remains **forward catch-up** from
live checkpoints, bounded by the normal startup/cycle limit. Its response now
states that scope explicitly. In report mode, only a provider-ordered page
advances the live checkpoint. Real-time notifications and historical jobs can
retain reports ahead of that checkpoint. Older IDs skipped by a previous version
require a separately bounded historical job. Forward catch-up neither creates
such jobs nor requires a paid-provider key in report mode.

## Qualification and archive boundary

On October 30, 2026, 58 focused tests passed, including lost-commit-acknowledgement
and repeated-cancellation regressions. An isolated pinned PostGIS run also
executed 13 database/API invariant groups with a synthetic Telegram provider:
both old 0003→0004 and fresh 0001→0004 migration paths, all eight original-table
hashes through migration, restricted runtime privileges, authorization,
idempotency, durable source links, fixed fences, duplicate/correction preservation,
partial outcomes, atomic progress, advisory concurrency and cancellation/recovery.
Actual durable PostgreSQL commits followed by injected acknowledgement loss
preserved progress; delayed advisory cleanup retained its connection through
repeated cancellation and released the lock before return.

These are synthetic provider and real PostgreSQL checks. They do not qualify
real Telegram historical retrieval, completeness, throughput or continuous
provider availability. At the time of this document's initial qualification,
this workflow had not collected real historical messages or modified the live
database. A later operational receipt must state its actual source/window/budget,
outcomes, persisted identities and unchanged live-checkpoint boundary.

The later [October 30 local operational review](LOCAL_REVIEW_2026-10-30.md)
records one real, bounded public-channel window: 49 messages inspected,
44 reports added and five duplicates, with unchanged live checkpoint and no
paid usage. This is not a qualification of other windows or complete history.

The recovered April archive remains a separate, stopped private restoration.
No archive rows are imported by this workflow. Its 5,991 known unknown-location
sentinels and unreviewed legacy interpretations must not become current map
evidence. See [historical recovery](HISTORICAL_RECOVERY.md). Public code licensing
does not grant redistribution or AI-processing permission for collected bodies
or the private archive; those permissions require their own source review.

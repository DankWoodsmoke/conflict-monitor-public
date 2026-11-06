# Retained future-dated RSS reports

Free report mode preserves a publisher item whose source timestamp is more than
five minutes ahead of the collection clock as `future_source_time`. The source
text, hash and original timestamp remain immutable. Migration
`0006_rss_due_retries`, after `0005_event_delivery`, adds a separate operational
schedule so the item can be reconsidered after its **original timestamp** is due,
even if it has disappeared from the publisher's rolling feed.

This is collection recovery, not factual verification, automatic geolocation,
severity classification, or corrected-incident chronology. Optional model mode
does not use this queue and does not gain automatic paid retries.

## Bounds and recovery

Only currently configured RSS sources in free report mode are processed. Due work
shares the ordinary source and global cycle quotas. At most two items, and no
more than half of a source's quota, are reserved for due work; a one-item quota
alternates per source between due work and new items whenever that source receives
a positive one-item quota. Cycles with a zero quota do not advance its turn, so
rotation under a small global budget cannot permanently select one kind of work.
Empty or failed publisher retrievals
do not prevent already-retained due reports from being processed.

The indexed queue claims rows with `FOR UPDATE SKIP LOCKED` and a 120-second
lease. Actual ingestion also takes the existing receipt advisory lock and
revalidates the source identity, body hash, channel and original clock. A stale
worker cannot acknowledge a newer claim. Cancellation leaves a claim to expire;
errors retry with capped exponential delay from 60 seconds to one hour. Source
records do not expire and are not rewritten. A crash after Event commit uses the
existing exact-source recovery path rather than creating a second Event.

Each queue database operation is bounded to ten seconds, including connection
acquisition. Each claimed processing attempt is bounded to 30 seconds. The
timeout is an incomplete attempt, never a successful publication.

`GET /status` exposes `news_feeds.retry_queue`, including pending and currently
eligible counts, original oldest due time, next attempt and typed errors. Counts
are the most recently sampled operational state. Per-feed `retried_items` and
`retry_outcomes` describe that collection attempt, not all-time totals.

## Migration and source clocks

The migration seeds existing free-RSS future receipts without editing their
source JSON, content hash, timestamp or outcome. It inspects at most 10,001
future-status candidates through the existing status-query path; more than
10,000 requires a separately reviewed staged migration. The new pending index
orders by source, next-attempt time and receipt identity.

Supported clocks have an explicit `Z` or numeric offset, calendar-valid dates,
hours 00–23, seconds 00–59, at most six fractional digits, and years 1970–9998.
Offsets are limited to ±14 hours. PostgreSQL input validation guards the cast;
naive, malformed, unsupported historical/model snapshots remain in the original
ledger without speculative scheduling. PostgreSQL 16 or later is required for
that validation. The new table must be empty and have the expected schema if a
fresh baseline already created it; unrelated existing retry state is not adopted.
Migration0006 freezes its own columns, defaults, relationships and pending index;
it does not derive old migration behavior from later application models.

Before applying to an existing installation, retain and verify a database backup
and qualify the migration and grants on a disposable copy. Automatic destructive
downgrade is disabled. The runtime role gets DML on the modeled retry table through
the existing restricted bootstrap process; no administrator credential belongs
in the HTTP worker.

## Remaining clock-correction limit

The existing receipt identity does not include the source timestamp. A later
same-body/same-link publisher clock correction therefore cannot replace the
retained clock. This queue deliberately preserves that original snapshot.
Append-only source-time observations and a review workflow for choosing among
publisher clock claims remain separate work. Neither publication nor update
time establishes when the reported incident occurred.

Offline regressions are in `backend/tests/test_rss_due.py`; the guarded
`tools/verify_rss_due_queue.py` exercises synthetic PostgreSQL fixtures. It must
only run through an explicitly isolated, disposable fixture with generated test
credentials and the matching database ownership marker. It is not a maintenance
command for a live installation.

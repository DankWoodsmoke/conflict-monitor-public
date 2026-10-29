# Public source collection

The fixed RSS/Atom catalog contains 34 measured native feeds. Thirty-one are
default-eligible for attributed report preservation. UN News remains an explicit
opt-in candidate because its newest source clock was in the future at the probe;
WHO and Lyn Alden are explicit contextual candidates because their latest feed
publications were old. This does not establish author inactivity or the
freshness of another publishing channel. Roles such as reporting, commentary,
macro analysis and institutional context describe the feed, not factual accuracy.
Legacy numerical priors remain explicitly historical and uncalibrated; new
sources have no numerical prior. Affiliation and agreement are not verification.

All 34 feed URLs parsed during bounded public HTTP checks on 2026-10-29. Those
checks establish dated connector compatibility, not continued availability,
complete coverage, permission to redistribute articles, or an accuracy/speed
ranking. No headless browser, paywall bypass, authenticated scraping, new
Telegram client, channel join, private GOOL corpus, or paid API was used.

Free collection has two explicit profiles:

- `RSS_PROCESSING_MODE=reports`, `RSS_RELEVANCE_MODE=keywords`: compatibility
  mode, using the inherited English discovery substring filter.
- `RSS_PROCESSING_MODE=reports`, `RSS_RELEVANCE_MODE=selected_sources`: preserve
  posts from the explicitly selected publishers without that language/topic
  filter. Commentary and unrelated posts remain source reports, unclassified,
  unscored and without inferred geometry. This does not turn them into verified
  conflict incidents. The separate model mode retains its English discovery gate.

The qualified fast profile targets 60 seconds between cycle starts, five actual
processing attempts per feed and 200 globally. With 31 selected sources, at most
155 attempts are reserved. Every source is fetched each cycle with at most four
concurrent requests; processing is serial. A slow request cannot hold up an
already completed feed's reserved work. Tight custom global limits distribute
quotas fairly with a rotating remainder. Unused quotas are not borrowed within
the same cycle, so low custom budgets may be underused. Cycles that exceed the
target interval do not overlap or create an unbounded catch-up queue.

Transport bounds remain 15-second HTTP timeouts inside a 30-second feed deadline
and a two-megabyte decoded response cap, checked before adding bounded chunks.
The parser rejects unsafe XML, unsupported documents and more than 1,000 items.
Source failures use bounded exponential backoff and bounded `Retry-After`.
Fetch duration/status, publication clocks, per-cycle quotas, terminal skips,
outcomes and ingestion failures are exposed separately. A successful HTTP fetch
does not make a future source date valid or establish incident time.

Conditional HTTP is deliberately deferred. A 304 response must not hide items
left unprocessed by an earlier quota. This version makes full bounded requests
and relies on the durable content ledger; it does not send `If-None-Match` or
`If-Modified-Since`. ETag/Last-Modified presence is observable for future work.

Known terminal receipt identities skip without spending a processing or
classifier-invocation quota. Changed text has a different immutable identity and
is retained as a revision. Received, pending and transient work can retry while a
PostgreSQL transaction advisory lock prevents concurrent work on the same exact
identity. The lock releases on transaction/connection termination. Retrying uses
the original stored source text and publication clock; a new retrieval clock
cannot repair or replace them. Source JSON and its first-received timestamp are
not rewritten. If an Event committed before the receipt finished, recovery
requires the same source, URL, exact content hash and publication clock.
Otherwise the source revision remains for review.

Oversized, unknown-date and future-date inputs retain explicit failure receipts;
they are not silently shortened into publishable reports. Some measured feeds
contain oversized descriptions. New publisher text does not automatically
replace an earlier Event. Source clocks and HTTP freshness are not factual
verification.

The item budget bounds processing/classifier invocations, not provider HTTP
retries, tokens or dollars in the optional legacy paid model mode. The free
profile makes no such model call. Its data and pipeline checks are separate from
AI semantic evaluation and from OS/database vulnerability review.

Current scoped evidence: 85 focused RSS tests pass. Nine additional checks ran
against real patched PostgreSQL/PostGIS using the ordinary runtime role in an
isolated test database, including advisory exclusion/cancellation, immutable
receipt recovery and original-clock preservation. These checks observed
in-process broadcast payloads and were followed by an independent production
DB/API/WebSocket observation after the patched, least-privilege database cutover.

The [sanitized live receipt](qualification/source-collection-live-2026-10-29.json)
records the 08:17:12–08:19:19 UTC window on October 29. All 31 selected feeds had
successful retrieval/parser state and persisted RSS events. Three completed
cycles were visible in status, taking 3.727, 3.239 and 2.891 seconds with 149, 145
and 94 processing attempts. The first completed before the observer connected;
two began during the WebSocket window. They delivered 234 actual RSS events from
29 sources. Fifty sampled deliveries matched the HTTP API, PostgreSQL content
and URL hashes, source/publication clocks and their immutable reported receipts.
All observed RSS events were unclassified, unscored and without coordinates;
the 50 database samples also had null PostGIS geometry. Quiet or fully consumed
feeds did not need to produce another event in that short window.

The ordinary runtime role had no superuser, create-database, create-role or
replication privileges. Paid-provider UsageLog rows remained zero before and
after; this is not a count of separately recorded local model evaluations.
The cumulative RSS ledger retained eight oversized inputs, fourteen source
revisions needing review and one future-time input instead of promoting them.
These counts include earlier receipts, not only this observation window.
This proves bounded acquisition and delivery for that configuration and sample;
it does not measure factual accuracy, global first reporting, rights clearance,
continuous availability or complete coverage. Selected-source intake preserves
context and commentary as UNSCORED reports with unknown geometry; it is not a
topic or truth classifier.

A separate [fresh-arrival observation](qualification/fresh-source-arrival-latency-2026-10-29.json)
ran from 08:55:00 to 09:25:01 UTC, after a normal cycle processed zero new items
from the existing feed backlog. Eight newly created RSS reports from five
publishers arrived through the normal collector: four from Middle East Monitor
and one each from RFI, Consortium News, OilPrice and Naked Capitalism. Twenty-six
configured sources had no new WebSocket delivery during that window; this is
quiet-source evidence, not a failure or coverage score. All eight matched exact
API/database hashes, source clocks and reported receipts. API reconciliation
found no additional RSS creation IDs missed by the observer. Thirty sampled
health checks were healthy with all 31 feeds in retrieval/parser state `ok`;
the WebSocket stayed connected and the paid-provider ledger remained zero.

For these eight samples, publisher-declared publication to database Event
creation had a median of 22.347 seconds and maximum of 174.505 seconds. Event
creation to client WebSocket receipt had a median of 8.216 milliseconds and
maximum of 22.418 milliseconds. `created_at` is PostgreSQL's transaction
timestamp, not the exact commit instant. All eight immutable source clocks
declared publication time; no Atom updated fallback was included. The receipt
retains raw timestamps, source/receipt identities, content hashes and
database/client clock brackets without article bodies or URLs. Publisher clock
accuracy, granularity and feed-cache delay remain unknown. This small
30-minute sample establishes neither an SLA, globally first reporting, factual
truth nor a ranking of publishers. It is separate from the image-bound hour
of collection monitoring.

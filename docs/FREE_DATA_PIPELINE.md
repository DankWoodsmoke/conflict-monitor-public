# Free publisher-report pipeline

The default RSS processing mode is `reports`. It requires public feed access and
PostGIS, with no model key, geocoder service, X API, or background AI charge.
Collectors still require `LIVE_INGESTION_ENABLED=true` explicitly.

The pipeline is:

1. Read a configured, fixed-registry RSS/Atom URL with a 15-second per-operation timeout, 30-second total deadline
   and a 2 MB decompressed response limit.
2. Parse XML with entity expansion/external entities forbidden. XML-declared
   character encodings are respected. Invalid/unsafe/unknown documents are failed
   feeds; a valid empty RSS/Atom document is separately reported as empty.
3. Select keyword-relevant items within the configured per-feed and cycle budgets.
   This is a discovery filter, not a factual classifier or comprehensive coverage.
4. Capture an immutable receipt before publication. Preserve the source title,
   excerpt, canonical link, publication clock, source identity and raw text hash.
   The receipt and event's report metadata also identify the feed URL, retrieval
   clock and SHA-256 of the fetched feed bytes. The full feed byte stream is not
   persistently archived, so its hash is not a claim of later source availability.
5. Publish a source-authored headline as an **unclassified, unscored report**:
   `event_type=unclassified`, `severity=0`, `classification_status=not_requested`.
   Zero is the explicit unscored sentinel, not a low impact assessment. Coordinates
   remain null; no geographic guess is made from a mentioned country or city.
6. Send the persisted report through the same API/WebSocket contract as other
   events. No model, anomaly analyzer or geocoder is invoked in this mode.

An exact content replay is idempotent. Changed text at an existing source URL gets
a `source_revision_needs_review` receipt while the original published report is
preserved. Missing/naive/future publication clocks and oversized or invalid source
metadata receive explicit nonpublication statuses. Oversized source text is kept
only as an explicitly truncated receipt with its original-text hash; it does not
silently become a shortened published report.

`RSS_PROCESSING_MODE=model` selects the optional structured-extraction path. This
requires deliberate configuration and provider access. An unavailable model is a
failed extraction, and never silently turns into a successful model assessment.

## Configuration and source health

| Setting | Default | Bound |
| --- | --- | --- |
| `RSS_PROCESSING_MODE` | `reports` | `reports` or `model` |
| `RSS_SOURCES` | empty, all registry IDs | comma-separated known source IDs only |
| `RSS_MAX_ITEMS_PER_FEED` | 20 | 1–100 relevant item attempts |
| `RSS_MAX_INGEST_PER_CYCLE` | 60 | 1–500 attempts; source order rotates between cycles |
| `RSS_MAX_RESPONSE_BYTES` | 2,000,000 | 1,024–5,000,000 decompressed bytes |
| `RSS_POLL_INTERVAL_SECONDS` | 300 | 60–3,600 seconds after each completed cycle |

For a bounded local qualification, use
`RSS_SOURCES=bbc_mideast,aljazeera,guardian_mideast` with report mode. No original
environment file needs to be copied. These IDs refer to publisher feed metadata,
not a license to republish their entire article archives or bodies.

`/status.news_feeds` includes per-source retrieval state, last attempt/success, latest
source publication time, retrieval age, publication age, item counts and redacted
error type. A recently fetched feed can contain old articles. A failed poll keeps
its previous successful/source clocks but reports the failure. Inactive collection
is disabled; unknown configured IDs are misconfigured. Feed availability is not
evidence that any reported underlying incident occurred.

## Executed checks

On October 28, 2026 CDT (`2026-10-29T03:10Z`), bounded public metadata checks fetched:

| Feed | Bytes | Parsed items | Keyword-relevant items | Latest publication UTC |
| --- | --- | --- | --- | --- |
| BBC Middle East | 18,446 | 23 | 21 | October 28 20:24:39 |
| Al Jazeera | 17,068 | 25 | 13 | October 29 02:48:38 |
| Guardian Middle East | 75,514 | 20 | 19 | October 29 00:24:12 |

These checks establish feed HTTP/parser compatibility at that time. Real database
and transport integration has its separate qualification receipt; these fetches
alone do not establish that PostGIS or WebSocket delivery succeeded.


## FIRMS and AIS live adapter qualification

A separate bounded check at `2026-10-29T03:16:56Z` fetched 342 valid FIRMS observations
above the explicit 10 MW display threshold; latest acquisition was October 28
22:57 UTC, with native high/nominal/low categories. A 60-second AIS subscription
collected 33 positions across 39 cached identities, confirmed compression and known
observation clocks on all 33 positions, and rejected 0 frames. The helper closed its
socket at completion. These were adapter checks without database writes; later
real PostGIS persistence/transport is reported separately by the parent gate.

FIRMS requests have a 40-second total network deadline, 5 MB response limit and
20,000-row limit; errors retain the last-good cache and keep fetch/cache/sensor
clocks distinct. The key-bearing HTTP path is redacted from HTTPX INFO logs.
Thermal association examines at most 5,000 recent located reports and exposes
truncation if that bound is reached; it does not certify causation. Sensor
observations are unscored severity 0, and never become strike confidence.


The actual running API subsequently returned **342 map observations at FRP≥10 MW**,
of which **exactly two** met the separate FRP≥80 MW event-publication threshold
(maximum 170.92 MW). Parent database verification found two persisted thermal
observation events. Thus 342 available map observations must not be reported as 342
new database events. These thresholds are visible operator policies, and neither
threshold determines conflict cause or military impact. `/status.thermal_observations` exposes
both thresholds. `confirmed_events` remains zero.

## October29 deployment follow-up

The expanded selected-source profile now admits31 native publisher/author feeds
from a34-feed reviewed catalog. It uses60-second cycle targets, four bounded
concurrent fetches and independent per-source quotas, preserving original
publication clocks and resumable receipt identities. An actual passive main-process
sample observed234 naturally delivered RSS reports through the WebSocket,
with50 exact API/ordinary-role SQL/source-hash comparisons. All31 feeds had
persisted reports;29 produced new RSS deliveries during that126-second window.
No classifier invocation or paid usage was recorded. Read [source review](SOURCE_REVIEW.md)
and [collection](SOURCE_COLLECTION.md) for source roles, retained failures,
cycle quotas and the distinction between watchlist selection and factual relevance.

The dated adapter-only samples above were followed by actual PostGIS/TCP and
Docker/nginx source-delivery checks, recorded in [verification](VERIFICATION.md).
The current aircraft adapter rotates four named250NM circles (Levant, Gulf,
Iran/Iraq and Red Sea) at the original one-request/15s recurring budget, merging
last-good regional data by source time. It is partial regional receiver coverage.
The Earth workspace shows bounded, explicit last-known observations instead of
making an older observation appear newly collected or current.

Optional local Qwen extraction and Piper/FFmpeg narrated source cards are
operator-triggered, separate from the no-model RSS report processor. They do not
change the original report, coordinates, severity or factual-verification state.
They require deliberately configured local resources; no model/voice download or
generation occurs automatically. Google Earth imagery has separate billing and
provider terms, even when the source collection and local tools use no paid API.

## Source eligibility for AI and synthesized narration

This deployment excludes Telegram records from local model and speech work because no context-specific continued creator consent has been supplied. This guard follows [Telegram content-licensing terms](https://telegram.org/tos/content-licensing) and [API terms §1.5](https://core.telegram.org/api/terms). It is not a content/topic filter or an assertion that other publishers permit every use.

Automatic selection skips `Event.source=telegram` and known `t.me`/`telegram.me` citations within a bounded recent candidate scan. Explicit selections are all-or-nothing: one restricted record raises the fixed `SourcePermissionRequired` before model or TTS work. The UI uses automatic eligible selection rather than silently selecting recent mixed-platform rows. There is no operator consent checkbox or general override. Other source rights still require review for the intended processing.

Known restricted analysis/video artifacts are withheld by read and media endpoints with the same fixed reason; files and original reports are preserved. Citation hosts and explicit platform metadata identify these records; publisher display names are not guessed and mutable database lookups are not used for old artifacts. New snapshots retain `source_platform`. Previously qualified RSS artifacts remain readable without rewriting their bytes. Ordinary authorized report viewing and deterministic source digests are unchanged by this AI/speech eligibility guard.

The recovered channel registry, scores and notes are March 2026 unverified historical editorial metadata. They are not calibrated accuracy/speed measurements, independent confirmation, or current identity/funding findings. Registry values remain preserved for review.

Public channel list/detail responses now mark `metadata_status=inherited_unverified`, `reliability_basis=uncalibrated_legacy_editorial_prior`, and `affiliation_status=unverified`. Displayed notes carry a March 2026 historical prefix without mutating registry values; handle lookup is case-insensitive and returns the canonical handle. RSS analysis/narration display labels use exact trusted catalog names, with literal underscore spacing as fallback. Canonical `source_platform`, source ID/URL, original text and its hash remain unchanged.

## Local guard scope and disabled legacy engines

The source-permission guard qualified here applies to the **local structured triage and local narrated-video pipeline**. It is not a universal Telegram guard across every inherited engine. The inherited Telegram model-ingestion branch, paid SITREP engine and standalone paid analysis paths remain unqualified and must stay disabled pending their own source-permission and technical review.

The qualified private profile retains `TELEGRAM_PROCESSING_MODE=reports`, `ENABLE_SITREP_GENERATION=false`, disabled X model ingestion and blank paid-provider credentials. Changing those settings is outside this qualification. Ordinary authorized non-AI viewing and deterministic source digests are separate uses; this boundary grants no general RSS/content license.

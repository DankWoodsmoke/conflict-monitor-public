# Source coverage and collection review

Checked October 29, 2026. This review follows the owner's request for wider source coverage, useful aligned analysts, fast original reporting and robust free collection. It separates editorial selection from measured source behavior. No person, publisher, badge, network category or repository ranking is a calibrated truth score.

## Executed source discovery

The inherited registry contained 16 publisher feeds, 31 optional paid-X accounts and 27 Telegram handles. The live qualification initially selected only three publisher feeds and three explicitly chosen public Telegram channels. Several inherited availability, affiliation, accuracy and ranking descriptions were dated or unsupported. Those notes are historical editorial assertions, not current verification.

Two bounded sets checked **34 native RSS/Atom URLs**, using the actual application's XML parser and network byte/deadline limits. All 34 parsed at the sampled time. The [machine receipt](qualification/2026-10-29-source-feed-probes-34.json) records response hashes, byte counts, publication clocks, item counts and per-feed request durations; it contains no article bodies or article headlines. The initial requests used at most three concurrent fetches; the additional five ran read-only in the existing deployed application image with at most two. No model, Telegram client or database write was used.

Thirty-one are admitted to the explicit bounded default report-intake profile; the scheduler and actual production database/API/WebSocket gate have now passed for a short observation window. UN News supplied a future latest publication time, WHO's sampled feed was approximately 19 days old, and Lyn Alden's sampled RSS last publication was July 15, approximately 106 days old. Those three remain explicit context/review candidates. This does not establish that the authors or organizations themselves are inactive. No timestamp is moved to the current clock to make a source appear fresh.

Several responses also contain oversized individual descriptions. Those items must retain failure receipts; a successful HTTP/XML result does not authorize silently truncating an original into a supposedly complete report.

## Coverage added to the review

| Role | Examples checked | Interpretation |
| --- | --- | --- |
| Regional reporting | Middle East Eye, Drop Site, Middle East Monitor, +972 Magazine, Al Jazeera, BBC Middle East, Guardian Middle East, Times of Israel, Jerusalem Post | Attributed publisher reports. Access, source interests and shared wire origins remain case-level questions. |
| Technical and maritime | The War Zone, Defense One, War on the Rocks, OilPrice, FreightWaves, Hellenic Shipping News, Splash247 | Equipment, strategy, logistics and economic context; reporting and analysis can appear together. |
| Independent analysis and commentary | Chris Hedges, Glenn Greenwald, Caitlin Johnstone, Consortium News, The Grayzone, Antiwar.com, Responsible Statecraft, Democracy Now | Useful candidate lenses and original investigations. Commentary is not automatically a detected incident or corroborating witness. |
| Macro and structural context | Peak Prosperity, GZERO, Geopolitical Economy, Naked Capitalism; Lyn Alden as a stale-feed context candidate | A route to people represented in the inherited analyst watchlist, using native publisher feeds rather than assuming their old social/video endpoint is current. |
| Humanitarian and press context | CPJ; UN News and WHO as explicit candidates | Organizational statements retain their author and clock. Official authorship is not independent verification of every underlying claim. |

The table describes editorial roles. It does not assert that every listed voice matches the owner's preferences, is independent, reports first or has a measured accuracy record. The configured watchlist is explicit and inspectable.

Glenn Greenwald's own [return-to-Substack announcement](https://greenwald.substack.com/p/welcome-back-to-substack) illustrates why endpoint history matters: an inherited Rumble-first description is not a substitute for checking where a person currently publishes. His native newsletter feed parsed in this review. Similar checks must precede adding renamed or impersonated accounts.

## Fast collection without hidden certainty

The old sequential scheduler, repeated duplicate attempts and cycle-wide budget rotation could delay a broad watchlist for several cycles. The revised scheduler is qualified with bounded concurrent fetches, deterministic per-source quotas, durable exact-content duplicate checks, resumable incomplete work, independent publication/retrieval clocks and per-source backoff. Persistence stays serial; a source's speed cannot consume another source's processing quota.

The deployed free profile is explicit: report mode, selected-source preservation, a target of 60 seconds between cycle starts, five processing attempts per feed and a 200-attempt global ceiling. With 31 admitted feeds, the reserved maximum is 155 attempts per cycle. This is an application processing bound, not a provider-HTTP, token or dollar ceiling for a separately enabled paid classifier.

Selected-source preservation avoids dropping non-English or contextual publisher posts merely because they miss an English substring filter. Such posts remain unclassified, unscored and unresolved. Keyword intake remains an explicit compatibility option. No model or geocoder is required for preservation.

Conditional RSS requests are useful where supported, but a 304 implementation must not lose unprocessed items or corrections after a restart. They are deferred until cache/resume semantics are proved. Native feeds, small bounded requests and provider-directed backoff are the current reproducible path.

Local first-seen time, publisher-declared publication time, correction time and incident time are different clocks. A short request duration is not evidence that a source was first to report a fact globally. A proper latency study must observe the same original claims across independent acquisition paths and retain missed observations and corrections.

## More practical acquisition paths

- **Publisher newsletters and author sites:** use the publisher's native feed and permitted public excerpts, with canonical source links and content hashes. A login wall or subscriber-only article is not bypassed.
- **Mastodon:** its [official syndication documentation](https://docs.joinmastodon.org/user/network/#syndication-feeds) describes discoverable account/tag RSS. The [account-status API](https://docs.joinmastodon.org/methods/accounts/#statuses) supports public posts, pagination and excluding boosts, subject to an instance's access settings. These are candidates for verified public watchlists, not evidence that a particular account was authenticated or ingested here.
- **Bluesky:** the [official HTTP reference](https://docs.bsky.app/docs/api/app-bsky-feed-get-author-feed) documents public AppView reads. Prefer exact DIDs and source-owned domain/profile links over name matching; retain original versus repost attribution and honor access/visibility controls. No Bluesky adapter is represented as live-qualified by this review.
- **ReliefWeb:** the current [official API documentation](https://apidoc.reliefweb.int/) requires a pre-approved appname. It is a useful humanitarian discovery candidate, with original-source rights retained. No unapproved appname or borrowed credential is used.
- **WebSub and change discovery:** push callbacks need a reachable owned endpoint, authenticated/bounded delivery and replay protection. Sitemaps' last-modified dates are discovery metadata, not incident or first-publication timestamps. These paths need executed contracts before adoption.
- **Bridges and headless scraping:** evaluate each route's rights, authentication, rate policy, correction handling and maintenance burden. A publicly hosted bridge can disappear or serve cached data. No CAPTCHA, paywall or access-control bypass is part of this release.

## Telegram and AI are distinct uses

Telegram's current [API terms](https://core.telegram.org/api/terms) and [content-licensing terms](https://telegram.org/tos/content-licensing) restrict AI development, benchmarking and deployment without the required context-specific continued consent. This release has no such source-consent record. The local AI/video path must therefore exclude Telegram content and known Telegram citations; a general operator checkbox is not treated as creator consent.

Authorized non-AI report viewing and source digests remain distinct. No new Telegram client, channel joining, messaging, mark-read action or bulk public-preview harvesting was performed in this source review. The inherited 27-handle roster is not thereby verified. Platform access and publisher/content rights require separate review; native RSS availability is not blanket AI or redistribution clearance.

## Source admission record

Before promoting any new person or feed, record the canonical identity, source-owned profile/domain links, available transport and terms, topic/region/language, declared versus observed clocks, original/forwarded/syndicated role, response/failure history and correction observations. Describe what was actually measured. Keep preference alignment as an operator lens and require case-level evidence, counterevidence and falsifiers for claims.

The [production source-collection receipt](qualification/source-collection-live-2026-10-29.json) adds a passive 126-second main-process observation from 08:17:12 to 08:19:19 UTC after the database cutover. All 31 selected feeds had successful retrieval/parser state and persisted RSS events. Three completed cycles were observable at 3.727, 3.239 and 2.891 seconds, using 149, 145 and 94 attempts within the 155 reserved/200 global bound. The first cycle completed before WebSocket connection; two began during the observation window. The observer received 234 RSS events from 29 sources and bound 50 sampled deliveries to exact HTTP API, database source/content/URL hashes, publication clocks and reported ledger receipts. Quiet or fully consumed feeds did not need to deliver another event during the sample. No synthetic event or secondary poller was introduced.

All observed RSS events remained unclassified, UNSCORED and without inferred coordinates; the 50 database samples had null PostGIS geometry. The cumulative ledger retained eight oversized inputs, fourteen revisions requiring review and one future-time input. Those are cumulative snapshot counts, not all new during the window. The runtime database role had no superuser/create-database/create-role/replication privileges, and the paid-provider UsageLog count stayed zero before and after. Separately recorded local model evaluations are outside that paid ledger count. Source-specific acquisition/publication clocks and source-code/image hashes are in the receipt; an image-bound soak is separate evidence maintained in the release verification record.

This gate establishes bounded acquisition, attribution and delivery for a measured configuration. It does not rank factual accuracy, firstness, continuing availability, global completeness or rights clearance. Selected-source intake deliberately preserves unrelated/contextual posts and commentary as reports; it is not a topic or truth classifier. The HTTP/parser discovery sample alone never supplied the production proof.

The [separate fresh-arrival receipt](qualification/fresh-source-arrival-latency-2026-10-29.json) observes 08:55:00–09:25:01 UTC after a normal cycle processed zero new backlog items. Eight newly created reports arrived from five sources: Middle East Monitor four; RFI, Consortium News, OilPrice and Naked Capitalism one each. Twenty-six configured sources had no new WebSocket delivery in that window; quiet is not a failure or an accuracy score. All eight deliveries matched exact API/database content and URL hashes, publication clocks and immutable reported receipts. No additional RSS IDs appeared only in API reconciliation. Thirty sampled health checks were healthy with all 31 feed retrieval/parser states `ok`; one continuous WebSocket connection and zero observer errors were recorded, and the paid-provider ledger stayed zero.

For this **n=8, 30-minute** sample, declared publication to database Event creation had a median of **22.347 seconds**, maximum **174.505 seconds**; Event creation to client WebSocket receipt had a median of **8.216 milliseconds**, maximum **22.418 milliseconds**. Event creation uses PostgreSQL's transaction timestamp, rather than the precise commit instant. The exact immutable receipt metadata identifies all eight source clocks as publication time, with no Atom updated fallback; source/receipt IDs, hashes, raw timestamps and database/client clock brackets are public without article bodies or article URLs. Publisher clock precision/accuracy and upstream feed-cache delay are unverified. These signed differences were not adjusted. They establish no SLA, global firstness, publisher ranking or factual truth, and do not substitute for the separate image-bound collection hour.

## Local guard scope and disabled legacy engines

The source-permission guard qualified here applies to the **local structured triage and local narrated-video pipeline**. It is not a universal Telegram guard across every inherited engine. The inherited Telegram model-ingestion branch, paid SITREP engine and standalone paid analysis paths remain unqualified and must stay disabled pending their own source-permission and technical review.

The qualified private profile retains `TELEGRAM_PROCESSING_MODE=reports`, `ENABLE_SITREP_GENERATION=false`, disabled X model ingestion and blank paid-provider credentials. Changing those settings is outside this qualification. Ordinary authorized non-AI viewing and deterministic source digests are separate uses; this boundary grants no general RSS/content license.

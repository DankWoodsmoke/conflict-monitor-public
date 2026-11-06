# Website integration assessment

Reviewed November 5, 2026. This is a deployment proposal and source review.
The live website, DNS, credentials and admitted RC.4 containers were outside
the changes in this review.

## Product fit

Conflict Monitor would be a useful addition to ianmalcolm84.com once the public
deployment gates below are met. The current website centers on an independent
Spaces archive, with Archive, Moments, Documentary, Explore and Listen navigation.
A Monitor item can add geographic context and source inspection to that existing
research workflow. A later curated link from a report to a relevant transcript
chapter could connect discussion to its original timestamp. That association
would need its own label and review, because a discussion is not independent
confirmation of the report. [Current website](https://ianmalcolm84.com/)

Use a full-page application at `monitor.ianmalcolm84.com`, reached from the
archive's navigation, with a clear return link. This keeps the Earth canvas,
native attribution and mobile controls at full size and permits separate release,
resource and quota management. The current nginx configuration emits
`X-Frame-Options: SAMEORIGIN`, so a subdomain iframe would be blocked. The current
Vite and API URLs also assume a root deployment. A `/monitor/` subpath would
require its own asset, API, Cesium-worker and deep-link qualification.

## Observed public-serving gaps

| Evidence in the current source | Consequence and proposed admission requirement |
| --- | --- |
| `frontend/nginx.conf` forwards all `/api/` paths. | Define the public read surface explicitly at the production ingress. Allow required GET and WebSocket paths and reject other paths/methods. Put operator analysis, generation, maintenance and job inspection behind private authenticated ingress. |
| `backend/app/security.py` and `routes/report_analysis.py` require a configured `X-Admin-Key`. Briefing generation POSTs use the same guard. | Existing unauthorized generation is fail-closed. Verify the production proxy preserves that boundary, and keep the key out of public configuration and frontend storage. This review found no unauthenticated analysis invocation path in these routers. |
| `/costs/summary` is an unauthenticated read of deployment cost configuration and usage totals. | Decide deliberately whether public cost transparency is part of the product. Exclude this endpoint from the public allowlist until that decision is made. |
| `services/broadcaster.py` limits one process to 128 WebSocket clients and bounded per-client queues. | This is a useful bound, but audience capacity has not been measured. Test realistic concurrent readers, reconnect bursts and slow clients against the intended hosting profile. |
| `main.py` sets API responses to `no-store`. Tracking polls run at 10â€“15 seconds per visible client. | At 100 continuously polling clients, aircraft, vessels and navigation queries alone imply roughly 23 requests/second before other APIs. Measure this workload. Introduce short-lived shared caches only for explicitly public, nonpersonal responses with preserved source clocks and appropriate provider rights. |
| `routes/briefing.py` reads and hashes the complete video before serving each request. | Browser range requests may repeat disk work. Measure media fan-out before public promotion. A later approved-artifact serving path can validate content once and serve range responses efficiently without weakening integrity checks. |
| The current Compose profile has one application process with collection started during application lifespan. | Adding HTTP workers also starts more collectors and separate in-memory caches. Keep one collection owner when scaling, with an explicitly qualified publication/fan-out path. |

These are code-review findings. The existing four-hour local observation
qualifies its recorded profile and workload. It supplies no public concurrency
or hosting-provider capacity measurement. See [verification](VERIFICATION.md).

## Provider and redistribution gates

| Surface | Current finding and required deployment decision |
| --- | --- |
| Google Earth | Map Tiles requires billing. Restrict the browser key to the deployed site and required API, configure quotas, monitor root-session demand, and preserve visible native attribution. The documentation currently describes a three-hour session and 10,000 default daily root queries. Recheck actual project quotas and pricing before launch. Google imagery stays in the visualization path, subject to its caching and content-use rules. [Usage and billing](https://developers.google.com/maps/documentation/tile/usage-and-billing), [key restrictions](https://developers.google.com/maps/api-security-best-practices), [imagery policies](https://developers.google.com/maps/documentation/tile/policies) |
| ADSB.lol | The actual primary aircraft adapter uses this provider. Its API documentation specifies ODbL 1.0 and asks production users to contact the provider. Record attribution and applicable database redistribution obligations. Free availability carries no guarantee of capacity or accuracy. [API documentation](https://api.adsb.lol/docs), [open-data license](https://www.adsb.lol/docs/open-data/api) |
| OpenSky fallback | Current official terms require a prior written agreement for operational REST use, including nonprofit and internal automated services. This review added `OPENSKY_FALLBACK_ENABLED=false`. Enable it only with that permission. The flag governs outbound fallback calls and leaves the primary ADSB.lol adapter available. [OpenSky terms](https://opensky-network.org/about/terms-of-use) |
| AIS Stream | The provider instructs applications to connect server-side and proxy only client-needed information. It limits connections to three per account and three per originating IP and provides no durable replay or uptime guarantee. The adapter already uses compression, bounded frames and reconnect backoff. Confirm the intended public display and retention scope with the account's applicable terms. [Official documentation](https://aisstream.io/documentation) |
| Market ribbon | The application uses yfinance. Its official documentation describes Yahoo Finance API data as intended for personal use. Public market redistribution therefore needs an appropriate data agreement or a provider whose license explicitly covers it. Hiding the ribbon alone would still leave its public API route reachable. [yfinance documentation](https://ranaroussi.github.io/yfinance/index.html) |
| RSS and source text | Feed access and attribution do not establish a general redistribution license. Maintain a publisher-specific record of permitted fields, excerpts, links, retention and correction/removal handling before exposing stored text publicly. The current acquisition record remains in [source collection](SOURCE_COLLECTION.md). |
| Telegram | A deployment bot requires publisher authorization for collection, display and retention. Pending updates last up to 24 hours, so this transport cannot supply historical backfill. The local profile has Telegram disabled. Preserve the existing exclusion from AI/video and qualify actual provider delivery only after authorized deployment. [Bot API](https://core.telegram.org/bots/api#getting-updates), [content licensing](https://telegram.org/tos/content-licensing) |

An open-source application license and free network access are separate from
rights to publish each dataset. Google session charges, hosting, data transfer
and optional inference also need separate accounting. The monitor's existing
usage ledger does not measure every external provider bill.

## Admission sequence

1. Resolve the recorded backend/database High security gate, preserve the
   supplemental component findings and verify the actual deployment images.
2. Approve a public source/display catalog, Google project restrictions and
   spending limits. Resolve the market-data and optional aircraft-fallback gates.
3. Build the public ingress, private operator path and visitor-facing controls.
   Confirm source clocks, coverage limits and incomplete assessments remain clear.
4. Run concurrent-reader, reconnect, slow-client, API throttling and media-range
   tests on the proposed host. Check origin rules, HTTPS, caching and immutable
   static assets through the actual public hostname.
5. Qualify backup/restore and rollback on that host, then perform an external
   read-only staging check across desktop and mobile engines with real imagery.
   Set public capacity and availability claims from those measurements.
6. Publish the qualified build and add the Monitor navigation item together.

## Source change verified in this review

The OpenSky opt-in is enforced before its HTTP request and quota timestamp
update. The normal collection loop was tested with primary-provider failure and
fallback disabled/enabled through an intercepted HTTP transport. The existing
fallback credit-budget check still passes when enabled. The targeted aircraft,
freshness and metadata suite passed 58 tests, and critical Ruff checks passed.
This source change requires a new build and admission before it changes the
previously qualified RC.4 deployment.

## Explicit public reader policy (source candidate, November 5)

`PUBLIC_READ_ONLY=false` preserves the private operator profile. The public
hosting override sets it to `true`; neither a valid administrator key nor a
frontend setting can override that backend policy. An exact API allowlist
rejects unknown routes and all mutations. Cost/configuration ledgers, provider
management, generated sitreps, analysis jobs, briefing/video artifacts and market
APIs are denied. Yahoo acquisition is also disabled inside the provider service.
The frontend waits for `/config` before mounting data consumers or operator
controls, then renders explicit withheld states instead of repeated denied
requests or zero-activity statistics. Earth navigation and Methods remain usable.
The synthetic showcase is a separate, explicit visitor choice.

The earlier whole-corpus reader proposal is superseded. `PUBLIC_REPORTS_ENABLED`
and `PUBLIC_TRACKING_ENABLED` no longer admit private data, even when true.
Private event/history/delivery endpoints and their WebSocket stay unavailable;
no original evidence is transformed or deleted. Generated briefs and the
operator media archive still require their own future publication contract.

The public database login now SELECTs only two dedicated immutable publication
tables. The private publisher supplies independently licensed NASA thermal
observations and adsb.lol aircraft snapshots, with strict field allowlists,
source clocks, hash checks, visible coverage limits and exact-batch downloads.
The old reader's private event/delivery grants are revoked after auditing its
previous privileges. This does not license the private corpus. See
[independent public datasets](PUBLIC_DATA.md) for source terms and limits.

The public process starts no collectors, seeders, inference or delivery jobs.
One private collection owner must explicitly enable the relevant publication
jobs. NASA uses a fixed keyless download; aircraft uses the existing adsb.lol
cache without extra upstream polls. A stopped publisher produces aging or
unavailable datasets, not synthetic activity. Vessels, navigation heuristics,
private tracking history and mixed report snapshots remain excluded.

`/config` exposes only visitor capabilities and the intentionally public Maps
browser key; `/status` reports public scope rather than private provider,
channel, classifier or usage diagnostics. Browser-key restrictions, provider
rights, actual hostname verification, capacity, backup/restore and rollback
remain launch gates. These changes close accidental API exposure paths; they
do not declare the current local corpus licensed or public deployment complete.
See [public hosting profile](PUBLIC_HOSTING.md) for the ingress configuration.

## Other-PC handoff verified on November 5

The supplied handoff contains 27 byte-hashed current source files. All hashes
matched and the loose handoff text matched its ZIP entry. These are selected
working files, not a complete runnable archive or a clean commit snapshot.
The source confirms that one `Masthead.astro` links array supplies desktop and
mobile navigation. A one-line Monitor entry was prepared and applied only to
an isolated copy; its resulting bytes matched the proposed hash.

The archive is built locally and directly uploaded to its existing Pages
project. Its publisher hashes uncommitted source and can publish a navigation
edit on its next scheduled run. The separate daily regeneration wrapper does
not acquire the shared site lease. Both triggers need a coordinated maintenance
window before editing the authoritative site. No website code, scheduler, DNS
or Cloudflare configuration was changed by this integration review.

Keep the existing archive and its canonical origin intact. Pages Functions use
the Workers runtime; the existing static archive upload does not provision this
project's Docker application, collectors or PostGIS database.
[Cloudflare Functions documentation](https://developers.cloudflare.com/pages/functions/).
A separate container host can be placed behind a reviewed Cloudflare Tunnel;
the connector establishes outbound connections, while the host still supplies
the application process, storage and availability.
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/).
An account login and a DNS record alone do not establish a running application.

The archive's current headers include HSTS for subdomains. Verify HTTPS for
the monitor before publishing its navigation link. Preserve the full-page
handoff and add a return-to-archive link to the eventual monitor deployment.
Check the archive's actual layout around its 1000/1100-pixel breakpoints,
mobile-menu reachability, focus and both navigation directions on the complete
site build; the partial handoff cannot qualify that rendering. Authenticated
Cloudflare reads, the reported deployment success and public-probe 403s are
handoff observations, not fresh host or visitor-access qualification here.

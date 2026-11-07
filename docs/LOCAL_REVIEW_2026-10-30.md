# Unreleased local review — October 30, 2026

This working candidate follows the published `v0.2.0-rc.2` snapshot. It is not a
new public release, a public website deployment or a qualification of every
source claim. The original project, April archive and published RC.2 archive
remain separate. Private execution receipts identify the exact local images
and observation windows; earlier release observations do not transfer to them.

## GOOL: a useful role needs measurement

GOOL is not currently part of the qualified monitor pipeline. Its strongest
candidate role is a **private, cited evidence reviewer**: identify conflicting
accounts, missing evidence and alternative interpretations that a reviewer can
check. Existing source capture, identifiers, timestamps, deduplication and
coordinate validation should remain deterministic. Paid inference should earn
its place through measured improvement over the current local baseline.

The new [review contract](GOOL_REVIEW.md) binds a permitted source snapshot to
exact hashes and literal citations, limits the response to unreviewed questions,
and rejects coordinates, severity, classification and verified-status fields.
Its tests include a leading but literally cited question that remains unreviewed:
matching words is not sufficient evidence of a correct interpretation.

The ordinary GOOL dispatcher uses shared memory, diagnostics and tool paths.
A fresh conversation does not isolate them. No shared service was started and
no GOOL inference was paid for here. Before integration, qualify an isolated
adapter with read-only permitted retrieval, disabled ambient controls/tools,
per-run cost/deadline limits and charged-failure accounting. Then run a held-out,
blinded comparison measuring useful findings, unsupported premises, abstention,
reviewer time, latency and actual cost. An attractive answer is not that benchmark.

## Earth and evidence corrections

Aircraft and vessels now have distinct silhouettes, stable identifiers and
searchable callsign/registration/ICAO/MMSI/IMO fields. Unknown direction does not
appear northbound; hollow tracks remain last-known or recorded observations.
An accessible legend explains category and precision cues. Bracketed `AREA REF`
markers distinguish coarse/unassessed report positions without inventing an
uncertainty radius. Camera/horizon checks retain far-side occlusion.

Live inspection also found a surface service vehicle displayed as an aircraft
with an ICAO label. A leading `~` now retains its provider-defined **non-ICAO
address** meaning; malformed IDs stay source IDs. Explicit C0–C3 emitter
categories use neutral surface/obstruction symbols, without inferring object
type from callsign, address prefix or `on_ground` alone. The inherited UAV
mapping is corrected from B2 (lighter-than-air) to B6, retaining its unverified
classification status. Primary references: [readsb address fields](https://github.com/wiedehopf/readsb/blob/dev/README-json.md#aircraftjson-and---json-port)
and [tar1090 category definitions](https://github.com/wiedehopf/tar1090/blob/master/html/formatter.js).

Future compact aircraft snapshots preserve the optional raw emitter category;
older snapshots keep it unknown. Existing snapshot collection excludes on-ground
contacts and applies regional/aircraft filters. Historical replay is therefore a
recorded subset, not a complete reconstruction of the live aircraft layer or a
new history of airport ground vehicles.

The generic military explosion badge was removed from the report feed. An Earth
burst requires an explicit airstrike/explosion subtype and source-reviewed
asserted stance. Current live feeds do not supply that review metadata, so this
does not create new live strike classification. A thermal sensor observation
does not establish an attack, actor or cause.

The inherited geocoder incorrectly treated bare organization names as
headquarters locations and selected specific points from ambiguous/relative
phrases. Those reproduced cases are now rejected before cache lookup. Multiple
external matches do not select the first result; automatic requests to public
Nominatim are refused. Existing local gazetteer points remain unverified
references, not incident locations. Imagery links reject invalid coordinates and
the legacy unknown-location sentinel. Undated basemaps remain reference imagery.

[Place review](LOCATION_REVIEW.md) checks literal source prose on demand, with
source hashes, exact Unicode/browser spans and explicit incomplete coverage.
RSS markup, image attributes and URLs are excluded from matching without
rewriting preserved source bytes. It never writes an event or plots a candidate.
Accurate incident placement still needs provenance, explicit precision and a
separate acceptance/correction record, plus a reviewed multilingual evaluation
set covering denials, quotations, multiple locations and relative areas.

## Historical recovery

[Bounded historical jobs](HISTORICAL_BACKFILL.md) use admin authorization,
selected public channels, immutable date/message budgets and a frozen upper
message-ID fence. Historical progress and live collection cursors are separate.
The new tables preserve item hashes and outcomes; cancellation after a durable
commit cannot rewind progress, and lock cleanup finishes before releasing the
database connection. Budget exhaustion and incomplete receipts remain explicit.

A real, single-page OSINTdefender run covered the provider-visible publication
window **October 22 13:55:35 through October 29 13:55:35 UTC**, with a 50-message
cap. It inspected **49 messages: 44 reports added, five duplicates**. The live
checkpoint was unchanged and the paid-usage ledger stayed at zero. The job
completed that provider-visible window; deleted/edited/unavailable messages and
all other missing periods remain unqualified. It does not verify the reports.

The separately restored April archive remains unchanged. Its old coordinates,
model outputs, correction state and redistribution permissions are not promoted
by these tests. The 5,991 preserved unknown-location sentinels must remain
quarantined from incident plotting. RSS present-feed collection does not recover
months of missing history; source-native permitted archive adapters are needed.

## Verification and boundaries

The local schema update paused collection, retained a same-snapshot logical
backup, and compared every pre-existing application data rowset, live cursor,
sequence, index, geometry and extension before restarting. Those values remained
identical; the schema revision intentionally advanced from 0003 to 0004.
Synthetic-provider tests against real PostgreSQL/PostGIS separately covered both
migration paths, duplicate/corrected inputs, preserved Unicode canary rows,
pending receipts, budgets, timeouts, atomic progress, concurrent exclusion and
cancellation fault injection. Oversized Unicode provider input was covered by
focused unit tests.

The Earth changes passed desktop Chromium, Android-sized Chromium and two
iPhone-sized WebKit fixture cases, including source-hash rejection, retry,
escaping, literal spans, incomplete-markup notices and unchanged coordinates.
Separate live Google tests passed all 12 combinations of Chromium/Firefox/WebKit
and four viewport sizes, including all three workspaces, attribution, controls,
same-canvas continuity and hemisphere visibility. These are browser emulations;
physical-device GPU/background behavior and assistive-technology speech remain
unqualified. Test counts and final image bindings are recorded in the private
aggregate receipt after the final integration pass.

Final application verification on this local candidate:

| Check | Measured result | Scope |
| --- | --- | --- |
| Actual backend image tests | 765 passed, 29 subtests passed | Image application bytes matched the source; no application-source or private-environment mount |
| Frontend suite and production build | 286 tests passed; TypeScript/Vite and Cesium compatibility passed | Final frozen source |
| Synthetic symbol and place-review browsers | 4 cases passed | Desktop/Android Chromium and two WebKit sizes; source integrity, identifiers and hemisphere occlusion |
| Live Google imagery browsers | 12 cases passed, 14:32:25–14:33:45 UTC | Final images; three engines × four viewport sizes, Earth/Media/Brief continuity |
| HTTP boundary | 7 cases passed | Actual loopback HTML/assets, direct and proxied APIs; not public TLS qualification |
| History staging | 13 invariant groups passed | Real PostGIS, synthetic provider; separate from the real 49-message page above |
| GOOL contract/source permissions/local briefing | 111 focused tests passed | No GOOL inference or semantic-utility measurement |
| npm audit | 0 advisories reported | Installed dependency graph; does not clear OS packages |

The final local backend image starts `d2d54158f0d4`, frontend `8593cb5e43df`,
and unchanged database `fc61b5645ca9`. Full image hashes, source hashes and
receipt hashes are retained in the private aggregate. This new candidate has
bounded smoke observations only; the earlier RC.2 three-hour observation does
not qualify these new application bytes for long-session operation.

A canonical backend rebuild encountered FFmpeg upstream TLS/timeouts and failed
closed after bounded retries. The local development image inherits the exact
qualified RC.2 runtime layers and changes application/migration files only;
its actual application bytes and tests are checked separately. This does not
turn the failed fresh rebuild into a pass. The [existing OS security findings](OS_SECURITY_REVIEW.md)
also remain; no zero-vulnerability or public-production clearance is asserted.

## Website decision

If hosting proceeds, prefer an ordinary **Conflict Monitor navigation tab linking
to a separate monitor origin**, such as a subdomain, with a consistent visual
identity. This keeps the existing site independent from database/collector
availability. The inspected site's CSP and this app's frame policy/root-relative
routes make an iframe or subdirectory mount an additional integration project.
No hostname, hosting purchase, DNS change or deployment has been selected.

Before exposing live data, implement an explicit public read projection: permitted
content and citations only, durable correction labels and no private raw archive,
GOOL corpus, administrative actions or operator cost/configuration data. Keep the
collector and analyst controls private. Qualify TLS/WSS, exact origins, restricted
Google browser credentials/quotas, attribution, backups, restore, rate/load limits
and continuous source freshness. Receiving more feeds or polling sooner does not
establish independence, truth or first reporting. Topic relevance and duplicate
presentation also need evaluation without deleting original receipts.

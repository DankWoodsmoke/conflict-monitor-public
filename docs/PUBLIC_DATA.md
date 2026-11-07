# Independent public observation datasets

The public workspace publishes separate NASA thermal and adsb.lol aircraft
datasets. Neither contains private reports, article text, Telegram messages,
GOOL content, generated briefings or private report associations. Neither
establishes strikes, missions, causes, casualties or complete conflict coverage.
Private evidence remains unchanged.

## Source permission

NASA's [FIRMS README, citation and disclaimer](https://nrt4.modaps.eosdis.nasa.gov/api/v2/content/archives/FIRMS/README.pdf)
describes third-party distribution with source citation and a disclaimer link.
Both are carried by the NASA packet and UI. The fixed NOAA-20 CSV appears in the
[NASA download manifest](https://firms.modaps.eosdis.nasa.gov/api/active_fire_files/all?format=json).
This adapter uses no account or MAP_KEY. Near-real-time data may contain errors;
thermal pixels are context, not strike detection or a life-safety service.

[adsb.lol's API policy](https://www.adsb.lol/docs/open-data/api) identifies its
public data as ODbL1.0. [License sections4.2–4.6](https://opendatacommons.org/licenses/odbl/1-0/)
require notices, share-alike for derivatives and access to the derivative data.
Aircraft packets identify the provider and license URI, are offered under the
same license, and have exact complete JSON downloads. Attribution, license and
download links are visible in the map workspace. NASA is not included in the
aircraft derivative. The [API documentation](https://api.adsb.lol/docs) requests
production contact to avoid disruptive changes; it does not state that prior
permission is required for redistribution under the license. Provider contact
and capacity planning remain operational work; no messages were sent.

## Publication boundary

`PUBLIC_OBSERVATION_PUBLISHER_ENABLED=true` enables the fixed NASA adapter.
`PUBLIC_AIRCRAFT_PUBLISHER_ENABLED=true` publishes the existing adsb.lol cache
without additional upstream requests. Both also require live ingestion, demo off
and public-read-only off. OpenSky records are excluded. Public HTTP processes
never start these collectors.

`public_observation_batches` and `public_aircraft_batches` are independent tables
of immutable packets. The public login can SELECT only these application tables;
the previous private event/delivery grants are revoked after auditing the prior
role. Legacy whole-corpus flags cannot reopen private data. The private runtime
gets SELECT/INSERT/DELETE, without UPDATE/TRUNCATE, on publication tables. An
update-rejecting trigger adds protection. Retention deletion affects publication
copies only.

Batch IDs are SHA256 of UTF-8 JSON with sorted keys, compact separators and
nonfinite numbers rejected, over `{source,published_at,status,payload}`. A
transaction/advisory lock makes publication atomic; durable due-time checks
prevent duplicate collectors or restarts from accelerating publication. Readback
validates schema and digest. NASA's response hash references received bytes; the
global source file is not archived. Aircraft record hashes cover selected
normalized cache fields, not raw radio messages. No heuristic military ownership
or emergency assessment is published.

## Coverage and bounds

NASA:32MB/400,000-row input limit;25°E–65°E/10°N–42°N; actual acquisition within
48hours; FRP≥10MW. Filenames are not clocks. Malformed records or conflicting
same-pixel/time rows fail the batch; exact duplicates are counted. Stored packets
are limited to10,000 eligible pixels/6MB. The map displays at most2,000 pixels,
highest FRP first with stable ID tie-break, with source/regional/filter/display
counts. This ranking is a display limit, not impact severity. Collection is due
every3hours, stale after12hours, packet retention7days. Failed fetches retain the
previous batch with visible failure state and unchanged clocks. Acquisition
expiry is reapplied on reads.

Aircraft:30-second publication from four250-nautical-mile circles in Eastern
Mediterranean, Persian Gulf, Iran/Iraq and Red Sea; at most5,000 records/3MB per
packet;120-second observation expiry;1-hour exact-packet retention. Missing,
failed, stale and empty states differ. Failed collection is not successful empty
coverage. Aircraft are surface projections with no inferred motion or altitude
correction. Browser request failure/timeout clears map observations until
recovery; each request has a15-second deadline and fresh abort signal.

GET/HEAD latest APIs: `/publication/observations`, `/publication/aircraft`.
Exact downloads: `/publication/observations/download/{batch_id}` and
`/publication/aircraft/download/{batch_id}`. Missing/expired IDs return410;
newer data is never substituted. NASA's `/publication/observations/download`
also supplies the latest successful complete packet. Queries are rejected.
Google imagery has separate terms and acquisition dates. Media and Brief remain
explicitly withheld.

## Qualification

Unit/API tests cover privacy, clocks, wrong sources, conflicting duplicates,
integrity, role privileges, exact downloads and browser deadlines. Real isolated
PostGIS/provider checks and exact-build multi-hour receipts are separate gates.
An open license does not verify source truth; this is a useful public context
view, not a complete public incident monitor or universal SQL sandbox.

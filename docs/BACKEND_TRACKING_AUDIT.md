# Backend tracking and empty-state audit

Checked October 28, 2026 America/Chicago (October 29 UTC). This receipt covers source inspection, deterministic HTTP/provider tests and one live aircraft-adapter check. It is not a fresh PostgreSQL/PostGIS integration receipt, an AIS live-stream qualification, a load test, or proof of incident accuracy.

**October29 follow-up:** the single-circle policy below is superseded by four
named250NM circles at the same one-request/15s budget. Per-region failures and
last-good source clocks remain separate; overlapping identities prefer the newest
actual observation. Reported altitude/reference is retained as metadata, while
Earth displays explicit surface projections and bounded last-known observations.
Actual deployed provider/browser/database checks are recorded separately in
[VERIFICATION.md](VERIFICATION.md); the original audit below is preserved.

## Implemented provider contracts

The aircraft and maritime endpoints retain their existing arrays. Records now distinguish source observation time from receipt time; `/status` exposes provider/cache clocks, coverage, failure state and expiry. A successful process is not reported as successful source collection. Synthetic mode remains explicitly labelled.

Aircraft changes in `backend/app/services/opensky.py`:

- Validate finite coordinates, bounded source timestamps and identities before caching. Do not promote `rr_lat`/`rr_lon` receiver estimates or `lastPosition` into current positions.
- Normalize both providers to meters, meters/second and degrees. Preserve valid zero altitude, north heading and level-flight climb rate.
- Expire positions after 120 seconds; mark them stale after 45 seconds. Preserve the last-success clock on a failed refresh. Valid empty snapshots and unavailable/malformed snapshots are different states.
- Limit provider responses to 2 MB decoded data and 5,000 rows. Bound history to 1,000 identities, 120 points per identity and 30 minutes. Replayed source timestamps do not add track points. Getters return detached records.
- Use the [documented adsb.lol radius limit](https://api.adsb.lol/docs) of 250 nautical miles around 30°N, 45°E. The inherited 2,500nm request was unsupported by the documented contract. This circle is partial coverage, not a whole-region or global census. ODbL attribution remains necessary.
- [OpenSky's current contract](https://openskynetwork.github.io/opensky-api/rest.html) uses OAuth2 for authenticated access; Basic authentication is retired. The existing fallback is now anonymous, sends no obsolete username/password, and is limited to one broad-area request per 15 minutes. It obeys rate-limit backoff. This budget is per process; other clients and multiple workers can consume the same IP quota. No new OAuth integration is claimed.
- Navigation-quality/MLAT clusters stay explicitly unverified inspection aids. They do not establish jamming, its cause, an emitter, or attribution; their short-window heuristic is not GPSJAM methodology.

Maritime changes in `backend/app/services/maritime.py`:

- Bound decoded WebSocket frames to 65 KB, queue depth to 16 and cached identities to 5,000. Expire static-only records as well as positions; cleanup also occurs on reads and connection failure.
- Require a valid ship MMSI, matching message identity, validated in-area coordinates and a provider-valid position record. AIS unavailable heading/speed sentinels remain unknown; course may be shown as a separately labelled heading fallback.
- Retain full provider observation timestamps when present. AIS seconds-within-minute and local receipt time cannot establish an observation date. Unknown observation time remains null. Older/replayed timestamps cannot refresh or overwrite a newer position; static messages cannot refresh a position.
- Replace raw-frame/exception-content logging with bounded error types. Reconnect with exponential backoff and jitter. Negotiate compression and expose subscription confirmation, as required by [current AISStream documentation](https://aisstream.io/documentation). This adapter covers the existing Class A position/static message types; it does not imply coverage of every AIS type.
- Correct inherited MID allocation errors against the [ITU table](https://www.itu.int/gladapp/Allocation/MIDs), including China incorrectly labelled Iran, Israel labelled Jordan, Japan labelled Syria and Hong Kong labelled Oman. Flag inference means registry allocation from broadcast identity, not independently established ownership or operator nationality.
- Correct individual [AIS ship-type semantics](https://www.navcen.uscg.gov/ais-class-a-static-voyage-message-5): towing is not fishing, sailing is not tug activity, and SAR/anti-pollution type codes do not establish government ownership. Categories derived from broadcast metadata/names remain heuristic.

## API boundary verification

`test_empty_api_contract.py` exercises empty result sets for events, anomalies, event batches and time range, media, SITREP history/latest, replay and unconfigured costs. Missing records return 404. Declared query limits reject oversized values before provider work. Legacy Telegram session-auth routes are not registered in this public app. These tests substitute empty database results; they cannot prove migration execution or SQL behavior on PostGIS.

The audit also identified and relayed independent issues in the legacy implementation: replay loaded all JSONB rows before downsampling; anonymous market queries could queue provider jobs and reuse the wrong history window; WebSocket broadcasting was sequential and unbounded by client count; destructive deduplication ignored source lineage; unqualified dataset imports claimed confirmation. The main implementation work subsequently added SQL-bounded replay, single-flight market requests, bounded WebSocket queues, review-oriented maintenance and a disabled unqualified import adapter. Those changes belong to the broader release checks, not the tracking test receipt below.

Additional inspection boundaries: validate event timestamp filters as UTC-aware/ordered; distinguish unknown usage prices from zero billed cost; qualify the full required database schema rather than only the events table; preserve report-version metadata in public SITREP responses. These are separate contracts from tracking freshness and need their own validation in the final release.

## Verification receipt

From `backend/`:

```text
../.venv/Scripts/python.exe -m pytest tests/test_tracking_freshness.py tests/test_empty_api_contract.py tests/test_release_safety.py -q
62 passed
```

The run includes 29 tracking cases, 21 empty-API cases and 12 existing release-safety cases; no skips. Provider calls in tests use an in-memory HTTP transport, and database results are substituted. A separate bounded unauthenticated adsb.lol adapter fetch at **2026-10-29T02:27:52Z** validated **7 positions, 0 rejected records**, with source ages approximately **1–39.5 seconds** and explicit SI units. No AIS account, Google billing service, paid model or new source adoption was exercised.

## Google Earth-style rendering boundary

[Google Photorealistic 3D Tiles](https://developers.google.com/maps/documentation/tile/3d-tiles) is the supported geographic-context path for a compatible renderer, with billing, an enabled API and a restricted key. Its root tileset supports at least three hours of subsequent tile requests. Use the renderer's tile lifecycle rather than recreating the root on each UI update. Google's official Cesium example enables `requestRenderMode` and hides the globe under the photorealistic tiles.

[Google's tile policies](https://developers.google.com/maps/documentation/tile/policies) require the Google logo plus visible per-tile copyright attribution; Cesium should use `showCreditsOnScreen: true`. Do not create an offline imagery archive or hide attribution during a showcase. Photorealistic context does not supply an incident capture date or verify a reported event. Runtime key/quota/coverage errors need a visible state and graceful fallback; unconfigured access must not silently imply Google imagery is active. This audit did not validate rendering performance or invoke a billable Google endpoint.

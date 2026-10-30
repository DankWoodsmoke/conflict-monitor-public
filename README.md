# Conflict Monitor

An OSINT workspace centered on one persistent Google Earth canvas, with source reports, regional ADS-B/AIS, thermal observations, replay, Media and Brief panels. It preserves original evidence and makes source age, unresolved locations and coverage limits visible. Optional local Qwen extraction and Piper/FFmpeg narrated source cards use no paid inference or speech API.

**Published version: 0.2.0-rc.1; 0.2.0-rc.2 is under qualification.** This branch contains subsequent [Earth imagery and usability improvements](docs/EARTH_QUALITY_REVIEW.md) and [container security remediation](docs/OS_SECURITY_REVIEW.md). The new backend passed **597 Linux tests plus 29 subtests**; the frozen frontend passed **224 tests**, build and compatibility checks. Frontend image `b6e6bc17…` passed isolated source/asset/header/process checks and its [exact security rebind](docs/qualification/2026-10-30-frontend-security-rebind-b6e6-final224.json). The database restore and real narrated-video path have separate completed gates.

The final frontend is [live-admitted](docs/qualification/2026-10-30-rc2-frontend-build-and-admission.json) with healthy/byte/header/process checks complete. Full production mobile/browser checks, the running 183-minute Google and 185-minute server observations, new hosted Compose CI and RC.2 publication remain pending. The [existing release](https://github.com/DankWoodsmoke/conflict-monitor-public/releases/tag/v0.2.0-rc.1) retains its original bytes. See [verification](docs/VERIFICATION.md) for dated identities and limits. The former server and original private repository were not changed.

[![Historical RC.1 workflow](https://github.com/DankWoodsmoke/conflict-monitor-public/actions/workflows/verify.yml/badge.svg?branch=codex%2Fpublic-release)](https://github.com/DankWoodsmoke/conflict-monitor-public/actions/workflows/verify.yml)

The badge currently reports the earlier RC.1 branch; it is not a hosted CI result for the changed RC.2 container profile.

## Explore without credentials

Use Node.js 22.12 or newer:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173/?showcase=true**. The explicit exercise uses local cartography and synthetic reports, tracks, media panels, markets and analysis. No database or model service is required. The capability tour opens panels within Earth; export saves the exercise data and reference clock. Earlier `view=map` and `view=3d` links resolve to Earth.

The **Earth** view uses Cesium and Google Photorealistic 3D Tiles. Configure a browser-restricted Google Maps key in Settings to enable detailed photography. A self-hosted deployment can set `GOOGLE_EARTH_ENABLED=true` and `GOOGLE_MAPS_BROWSER_KEY` for automatic Earth configuration without rebuilding the frontend. That explicitly public browser key is delivered by `/config`; backend credentials remain server-only. Google requires its Map Tiles API, billing and visible attribution. Imagery dates and 3D coverage vary; it is not a live satellite feed and does not establish an event's date or location.

**To inspect real imagery**, leave the keyless exercise using **Open live Earth**, select a reference city such as Dubai or Tehran, then choose **Top down** or **Oblique 3D**. **Focus Earth** expands the desktop workspace; **Imagery and detail** exposes the provider, loading state and balanced/detail setting. Native-resolution rendering is bounded to 2× device pixel ratio and eight million pixels. Controls collapse on small screens, while Earth, Media and Brief share the same canvas. On imagery failure a named reference layer remains available with an explicit retry. The keyless exercise uses a static NASA May 2004 daytime globe for orientation; it cannot show city detail.

## Capabilities

| Workspace | Implemented capability | Verification boundary |
| --- | --- | --- |
| Earth | Persistent Cesium/Google imagery, close city views, native-resolution/detail controls, focus mode, report feed and filters, coordinate/place search, source selection, regional aircraft/vessels, thermal observations and replay | Unknown locations stay unplotted. Tracking is explicitly projected onto the surface; no altitude conversion or motion extrapolation is invented. Unknown headings use a neutral marker. |
| Media panel | External media activation and real locally narrated source-card MP4s, with segment-timed captions and an exact narration transcript, preserving the Earth camera | Video reads attributed reports; it contains no incident footage. Caption timing is per source card, not word aligned. External broadcasters retain their own availability and rights. |
| Brief panel | Source digest, report references and optional local topic/stance/mention extraction; inherited analysis remains labeled | Model labels and source mentions remain unreviewed. Literal spans and valid JSON do not establish factual truth or an incident location. |
| Evidence | Preserved original reports, content hashes, source-scoped identities, revisions, explicit extraction failures | Report/network counts never automatically become independent confirmation. |
| Tracking | Four bounded regional ADS-B circles, AIS, explicit fresh/last-known ages, recorded replay and optional navigation-quality candidates | Partial receiver coverage is explicit. Expired positions disappear. Navigation degradation alone does not establish jamming. Active orbital markers and cosmetic sensor-like shaders have been removed. |

The default free profile preserves publisher text with `UNSCORED` severity and unresolved locations unless a sensor supplies coordinates. It never sends those reports to a paid classifier. Optional model-assisted extraction/synthesis requires deliberate configuration and separate accuracy qualification.

## Demonstrate the workspace

1. Open live Earth and enable Google imagery through Settings or your deployment's restricted browser key. Choose a city view, inspect the imagery at street/building scale, then use Focus Earth or Top down/Oblique 3D. Check provider attribution and source health before describing anything as current. The keyless showcase labels its synthetic data and static reference globe explicitly.
2. Explore reports and source/time filters, open a cited source, then compare its publication clock with collection time. Unlocated reports stay in the feed. Tracking controls distinguish fresh, last-known and recorded positions; the four aircraft regions describe the actual coverage.
3. Open Media, then return to Earth to show that the camera and canvas persist. External broadcasts need deliberate activation; an embedded page is not proof of live playback. The narrated briefing contains editorial source cards, not incident footage.
4. Open Brief for the attributed source digest and, when configured, optional local analysis. Inspect original citations and unreviewed labels. Local generation requires the operator key and a deliberate action; opening a panel starts no inference or speech job.

The capability tour and export in the keyless showcase can demonstrate these controls without disclosing credentials or redistributing live publisher text. See [verification](docs/VERIFICATION.md) for measured browser, source and media behavior.

## Preview

These previews show the synthetic, keyless exercise with the **NASA Blue Marble May 2004 daytime reference** at globe scale. They do not depict the detailed Google imagery available in a configured deployment. Use **Open live Earth** and an inspection-city control to see that capability.

![Earth workspace with synthetic reports and a dated daytime reference globe](docs/screenshots/may2004-showcase-earth-desktop-20261030T001722Z.png)

Also see [Media](docs/screenshots/may2004-showcase-media-desktop-20261030T001722Z.png), [Brief](docs/screenshots/may2004-showcase-brief-desktop-20261030T001722Z.png) and [390-pixel portrait](docs/screenshots/may2004-showcase-earth-portrait390-20261030T001722Z.png). The [preview receipt](docs/screenshots/may2004-showcase-20261030T001722Z-receipt.json) binds them to the earlier `03b08f` image, with no external imagery, live-data or generation requests. They are retained previews of that phase, not final RC.2 UI qualification or current imagery/source truth. Original RC.1 previews remain preserved. The live workspace uses the operator's configured Google imagery and offers close city inspection; these public screenshots deliberately use the distributable NASA reference.

The optional free tools are configured in [local AI/video](docs/LOCAL_AI_VIDEO.md). The application never pulls a model or voice automatically. Operator-triggered work is authenticated, bounded and published only after its respective validation gates. The measured model comparison includes rejected batches and remaining errors. The inherited paid standalone video script is retained as historical source; automatic paid generation remains disabled by default.

Narrated briefings verify the manifest's exact narration hashes before enabling captions or the transcript. Native Firefox preflight retained a paused-frame caption repaint failure: user-triggered playback restored the visible captions, while the transcript remained available. The page explains that recovery without forcing playback or seeking. This is a documented browser limit; final production mobile qualification remains separate, and no physical iPhone or screen reader is certified.

## Self-host with an empty database

Copy `.env.example` to `.env`. Set different new `POSTGRES_PASSWORD` and `POSTGRES_APP_PASSWORD` values (32 random bytes, represented as 64 hexadecimal characters each), plus a new `ADMIN_API_KEY`, then:

```sh
docker compose up --build
```

Open **http://localhost:5173/**. Collection defaults to disabled. Configure your own providers before setting `LIVE_INGESTION_ENABLED=true`. Paid situation reports additionally require `ENABLE_SITREP_GENERATION=true` and a configured model key. Administrative writes require `X-Admin-Key`; a missing server key disables them.

Compose builds the database from the pinned source recipe in `tools/postgis`: PostgreSQL 17.11/PostGIS 3.6.4, an explicit upstream FlatGeobuf security backport and gosu 1.20. This reduced profile retains core spatial/topology/Tiger support and excludes raster, address standardizer and SFCGAL. A one-shot `migrate` service initializes Alembic and grants the separate `monitor` runtime role; HTTP workers receive no database administrator secret. The new default `pgdata17_36_secure` volume deliberately avoids both older volume names. **Existing data requires a rehearsed logical restore into a new volume**, with the old volume and rollback profile preserved. Follow [database upgrade and permissions](docs/DB_UPGRADE.md); do not attach the new image directly to old database files. The [executed RC.2 restore](docs/qualification/2026-10-30-rc2-database-cutover-and-regressions.json) verifies ten tables and five sequences for this deployment, not compatibility with every excluded extension. The old server's environment, database and sessions are not bundled.

The shipped profile runs backend UID 10001 and frontend UID 101 with all capabilities dropped and no new privileges. Frontend/database root filesystems are read-only; the database entrypoint has narrowly listed initialization capabilities, while its observed server PID1 runs as UID 999 with no effective capabilities. Local ports bind to loopback and the database has no published port. [Actual isolated Compose qualification](docs/qualification/2026-10-30-compose-profile-ci-preflight.json) checked these boundaries and seven HTTP header/cache cases; it does not clear the Docker host or unresolved vendor advisories.

The original April production dump was recovered separately into a private, isolated archive: all 53,715 rows round-tripped exactly. It contains legacy schema, source-clock anomalies and 5,991 dummy event coordinates, so it was preserved without merging its claims or locations into live data. See [historical recovery](docs/HISTORICAL_RECOVERY.md). No publisher bodies or private database are part of this source release.

Development API: `cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000`. Vite proxies `/api`; the production frontend uses the same-origin nginx proxy. `/health` checks the database/schema, `/status` reports process state and provider-specific freshness. A running process does not establish fresh upstream observations.

## Verify

```sh
python -m venv .venv
# Windows: .venv/Scripts/python.exe; POSIX: .venv/bin/python
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q
cd ../frontend
npm ci
npm test
npm run build
npm audit
```

The fresh-PostGIS gate is `python tools/verify_postgis.py` with `DATABASE_URL` naming a separately initialized `conflict_monitor_test` database. Initialize it through `python -m app.bootstrap` as the administrator, then run the gate as the restricted runtime role. The separate actual HTTP/WebSocket gate can additionally exercise `python tools/verify_live_pipeline.py --public-feed`. Missing infrastructure returns an incomplete/failing exit code. The [final backend-image run](docs/qualification/2026-10-30-rc2-linux-backend-597.json) passed 597 tests plus 29 subtests with no application-source mount. The new 45-minute shipped-Compose CI job builds all three images and checks the actual restricted-role database, TCP pipeline, container boundaries and HTTP headers using synthetic fixtures. Its [local preflight passed](docs/qualification/2026-10-30-compose-profile-ci-preflight.json); hosted execution for RC.2 is pending. The [earlier hosted CI](docs/qualification/2026-10-29-github-qualified-source-ci.json) remains evidence for RC.1, and does not qualify the changed images.

`python tools/release_gate.py --scan-only` checks the allowlisted public source. `--package-candidate` creates a source ZIP and SHA-256 manifest; it does not certify a stable release. Export excludes secrets, sessions, databases, logs, dependency trees and private Git history.

## Method and research

Read [methodology](docs/METHODOLOGY.md), [current research](docs/CURRENT_RESEARCH.md), [decisions](docs/DECISIONS.md), and [security](SECURITY.md). The structural analytical lens remains visible as testable interpretation; evidence and unknowns remain inspectable.

See [source review](docs/SOURCE_REVIEW.md), [bounded source collection](docs/SOURCE_COLLECTION.md), [free data](docs/FREE_DATA_PIPELINE.md), [container security review](docs/OS_SECURITY_REVIEW.md) and [asset provenance](docs/ASSET_PROVENANCE.md) for source choices, operational bounds and execution receipts. The measured catalog has 34 native feeds; the selected free profile admits 31, with explicit stale/future-clock candidates kept separate. Publisher selection is an editorial lens, not a calibrated truth or first-reporting score.

Current research covers relevant public tools, source terms, formats and model candidates. No general model leaderboard or repository activity claim substitutes for a measured event-extraction evaluation. Model selection is limited to the measured task and sample described below.
 
The October 29 follow-up measured three local models on a frozen twelve-case sample and selected Qwen3.5 4B only for unreviewed source triage. It does not establish general factual or multilingual accuracy. See [Earth behavior](frontend/EARTH_VERIFICATION.md) and [context/history reconciliation](docs/CONTEXT_RECONCILIATION.md) for the consolidation and recovered-history limits.

## License

MIT application code with an explicitly GPL-3.0-or-later standalone optional speech worker and GPL-2.0-or-later upstream-derived PostGIS patch, preserving the original copyright notices. The restricted FFmpeg/libx264 build has its own GPL and corresponding-source obligations. See [third-party notices](THIRD_PARTY_NOTICES.md). Dependencies, weights, provider terms and data redistribution rights are separate. No private GOOL corpus/persona, third-party dataset dump or model cache is bundled.

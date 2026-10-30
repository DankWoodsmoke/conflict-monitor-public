# Conflict Monitor

An OSINT workspace centered on one persistent Google Earth canvas, with source reports, regional ADS-B/AIS, thermal observations, replay, Media and Brief panels. It preserves original evidence and makes source age, unresolved locations and coverage limits visible. Optional local Qwen extraction and Piper/FFmpeg narrated source cards use no paid inference or speech API.

**Published version: 0.2.0-rc.1.** This branch also contains the subsequent [Earth imagery and usability improvements](docs/EARTH_QUALITY_REVIEW.md); the existing release download retains its original bytes. See the [release](https://github.com/DankWoodsmoke/conflict-monitor-public/releases/tag/v0.2.0-rc.1), [GitHub CI](https://github.com/DankWoodsmoke/conflict-monitor-public/actions/workflows/verify.yml) and [verification](docs/VERIFICATION.md) for dated checks and remaining limits. The former server and original private repository were not changed.

[![Verify release candidate](https://github.com/DankWoodsmoke/conflict-monitor-public/actions/workflows/verify.yml/badge.svg?branch=codex%2Fpublic-release)](https://github.com/DankWoodsmoke/conflict-monitor-public/actions/workflows/verify.yml)

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
| Media panel | External media activation and real locally narrated source-card MP4s, preserving the Earth camera | Video reads attributed reports; it contains no incident footage. External broadcasters retain their own availability and rights. |
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

Also see [Media](docs/screenshots/may2004-showcase-media-desktop-20261030T001722Z.png), [Brief](docs/screenshots/may2004-showcase-brief-desktop-20261030T001722Z.png) and [390-pixel portrait](docs/screenshots/may2004-showcase-earth-portrait390-20261030T001722Z.png). The [preview receipt](docs/screenshots/may2004-showcase-20261030T001722Z-receipt.json) binds them to the deployed `03b08f` image, with no external imagery, live-data or generation requests. The four previews illustrate synthetic layouts, not current imagery or source truth. Original RC.1 previews remain preserved. The live workspace uses the operator's configured Google imagery and offers close city inspection; these public screenshots deliberately use the distributable NASA reference.

The optional free tools are configured in [local AI/video](docs/LOCAL_AI_VIDEO.md). The application never pulls a model or voice automatically. Operator-triggered work is authenticated, bounded and published only after its respective validation gates. The measured model comparison includes rejected batches and remaining errors. The inherited paid standalone video script is retained as historical source; automatic paid generation remains disabled by default.

## Self-host with an empty database

Copy `.env.example` to `.env`. Set different new `POSTGRES_PASSWORD` and `POSTGRES_APP_PASSWORD` values (32 random bytes, represented as 64 hexadecimal characters each), plus a new `ADMIN_API_KEY`, then:

```sh
docker compose up --build
```

Open **http://localhost:5173/**. Collection defaults to disabled. Configure your own providers before setting `LIVE_INGESTION_ENABLED=true`. Paid situation reports additionally require `ENABLE_SITREP_GENERATION=true` and a configured model key. Administrative writes require `X-Admin-Key`; a missing server key disables them.

The pinned image runs PostgreSQL 17.11/PostGIS 3.6.4. A one-shot `migrate` service initializes Alembic and grants the separate `monitor` runtime role; HTTP workers receive no database administrator secret. The new default `pgdata17_36` volume deliberately avoids the older volume. **Existing data requires a rehearsed logical restore into a new volume**, with the old volume and rollback profile preserved. Follow [database upgrade and permissions](docs/DB_UPGRADE.md); do not attach the new image directly to old database files. The old server's environment, database and sessions are not bundled.

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

The fresh-PostGIS gate is `python tools/verify_postgis.py` with `DATABASE_URL` naming a separately initialized `conflict_monitor_test` database. Initialize it through `python -m app.bootstrap` as the administrator, then run the gate as the restricted runtime role. The separate actual HTTP/WebSocket gate can additionally exercise `python tools/verify_live_pipeline.py --public-feed`. Missing infrastructure returns an incomplete/failing exit code. [Actual GitHub CI](docs/qualification/2026-10-29-github-qualified-source-ci.json) passed the hosted build/unit/advisory and restricted-role database/pipeline gates; local live-provider, Google/browser and media observations remain separate evidence.

`python tools/release_gate.py --scan-only` checks the allowlisted public source. `--package-candidate` creates a source ZIP and SHA-256 manifest; it does not certify a stable release. Export excludes secrets, sessions, databases, logs, dependency trees and private Git history.

## Method and research

Read [methodology](docs/METHODOLOGY.md), [current research](docs/CURRENT_RESEARCH.md), [decisions](docs/DECISIONS.md), and [security](SECURITY.md). The structural analytical lens remains visible as testable interpretation; evidence and unknowns remain inspectable.

See [source review](docs/SOURCE_REVIEW.md), [bounded source collection](docs/SOURCE_COLLECTION.md), [free data](docs/FREE_DATA_PIPELINE.md), [container security review](docs/OS_SECURITY_REVIEW.md) and [asset provenance](docs/ASSET_PROVENANCE.md) for source choices, operational bounds and execution receipts. The measured catalog has 34 native feeds; the selected free profile admits 31, with explicit stale/future-clock candidates kept separate. Publisher selection is an editorial lens, not a calibrated truth or first-reporting score.

Current research covers relevant public tools, source terms, formats and model candidates. No general model leaderboard or repository activity claim substitutes for a measured event-extraction evaluation. Model selection is limited to the measured task and sample described below.
 
The October 29 follow-up measured three local models on a frozen twelve-case sample and selected Qwen3.5 4B only for unreviewed source triage. It does not establish general factual or multilingual accuracy. See [Earth behavior](frontend/EARTH_VERIFICATION.md) and [context/history reconciliation](docs/CONTEXT_RECONCILIATION.md) for the consolidation and recovered-history limits.

## License

MIT application code with an explicitly GPL-3.0-or-later standalone optional speech worker, preserving the original copyright notice. See [third-party notices](THIRD_PARTY_NOTICES.md). Dependencies, weights, provider terms and data redistribution rights are separate. No private GOOL corpus/persona, third-party dataset dump, model cache or external platform source code is bundled.

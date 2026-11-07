# Conflict Monitor

Explore source reports and regional tracking in one persistent Earth workspace. Earth, Media and Brief share the same Cesium canvas, so opening a panel preserves your camera position. Reports retain citations, collection clocks, revisions and unresolved locations.

**Start with the keyless exercise below, or run a private operator instance with Docker Compose.** Detailed Google photography needs a restricted browser key and Google billing. The public reader is a separate, limited data surface - not permission to expose the operator instance.

**Release status: RC.5 source release candidate 18; public hosting is not approved.** Finite checks, seven four-hour core streams and a separate four-hour mobile-emulated public session are complete. The post-observation official security refresh is complete in its stated image/native scope; the release workflow and exact downloaded-asset evidence govern final publication.

## Try it without credentials

From the repository root, use Node.js 22.12 or newer:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173/?showcase=true**. This explicitly synthetic exercise needs no database or model service. Its capability tour opens panels within Earth; export saves exercise data and its reference clock. Old `view=map` and `view=3d` links resolve to Earth.

The exercise's globe is a static **NASA Blue Marble May 2004** reference, not detailed or current satellite imagery. [Retained exercise previews](docs/screenshots/may2004-showcase-earth-desktop-20261030T001722Z.png) show that earlier synthetic workspace, not the current Google imagery or live-data qualification.

## Enable real Earth imagery

Choose **Open live Earth**, then configure a browser-restricted Google Maps key in **Settings**. Enable the Map Tiles API and restrict the key to the intended HTTP referrers and API. A self-hosted deployment can set `GOOGLE_EARTH_ENABLED=true` and `GOOGLE_MAPS_BROWSER_KEY` to configure Earth without rebuilding the frontend.

That browser key is intentionally delivered through `/config`; never use a server credential there. Google requires billing and visible attribution. Root sessions can incur charges: free source data does not make Google imagery unlimited or free. Verify actual quotas and pricing before sharing a deployment; budget alerts are not a hard spending cap. See [imagery and hosting controls](docs/PUBLIC_HOSTING.md).

Select a reference city such as Dubai or Tehran, then use **Top down** or **Oblique 3D**. **Focus Earth** expands the desktop workspace; **Imagery and detail** shows provider state and detail controls. Rendering is bounded to 2x device pixel ratio and eight million pixels. Controls collapse on small screens; a labeled reference layer and explicit retry remain available on imagery failure.

Photographic coverage and capture dates vary. This is not a live satellite feed, and imagery alone does not establish an incident's date or location.

## Choose the right workspace

| Surface | What it provides | What its evidence means |
| --- | --- | --- |
| Private operator | Source feed, filters, citations, regional ADS-B/AIS, thermal context and recorded replay | Unknown locations stay unplotted. Fresh, last-known and recorded positions remain distinct; surface projections do not invent altitude or motion. |
| Operator Media | Deliberately activated external media and optional locally narrated source-card MP4s, captions and transcript | Source cards are not incident footage. External availability and rights remain with the publisher; caption timing is per card. |
| Operator Brief | Attributed source digest and optional local topic, stance and mention extraction | Model labels and mentions remain unreviewed; valid JSON and literal spans are not factual confirmation. |
| Public reader | Separately published NASA thermal observations and regional adsb.lol snapshots, with clocks, attribution and exact-batch downloads | Thermal pixels do not identify strikes; broadcasts do not establish missions, ownership or complete regional coverage. |

Public visitors can inspect Earth and dataset provenance; Media and Brief explain their withheld state. Private reports, Telegram, GOOL context, operator controls, model costs and generated artifacts are not published. The public SQL role reads only two dedicated publication tables. See [public data and redistribution terms](docs/PUBLIC_DATA.md).

The default free operator profile preserves reports with `UNSCORED` severity and unresolved locations unless a sensor supplies coordinates. It does not send those reports to a paid classifier. Source counts do not automatically become independent confirmation, and cached freshness does not establish every upstream region's availability.

## Run a private instance with an empty database

Use Docker with Compose. Copy `.env.example` to `.env`; set different new `POSTGRES_PASSWORD` and `POSTGRES_APP_PASSWORD` values, each 32 random bytes represented as 64 hexadecimal characters, plus a new `ADMIN_API_KEY`. Keep `.env` private. From the repository root:

```sh
docker compose up --build
```

Open **http://localhost:5173/**. Collection defaults to disabled. Configure your providers before setting `LIVE_INGESTION_ENABLED=true`. Paid situation reports additionally require `ENABLE_SITREP_GENERATION=true` and a configured model key. Administrative writes require `X-Admin-Key`; a missing server key disables them. Telegram defaults to disabled; its authorized Bot API path does not require a personal account session.

Compose builds PostgreSQL 17.11/PostGIS 3.6.4 on a pinned Alpine base. A one-shot initializer applies migrations and grants a separate restricted runtime role; HTTP workers receive no database administrator secret. Local ports bind to loopback and the database has no published port. The default `pgdata17_36_alpine` is a fresh volume.

**Existing data needs a rehearsed logical restore into a new volume.** Preserve the old volume and rollback profile; glibc-to-musl changes can affect Unicode ordering. Read [database upgrade and permissions](docs/DB_UPGRADE.md) before migration. The private April archive was preserved separately, including legacy clock and dummy-coordinate issues; it is not merged into live observations or bundled here. See [historical recovery](docs/HISTORICAL_RECOVERY.md).

For a configured development database, the API command is `cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000`. Vite and production nginx proxy `/api` on the same origin. `/health` checks database/schema availability; `/status` describes process state and provider freshness. A running process is not evidence of fresh upstream data.

Public deployment uses different publisher/reader profiles and credentials. Follow [public hosting](docs/PUBLIC_HOSTING.md) and [website integration](docs/WEBSITE_INTEGRATION.md); do not expose the private operator port as a shortcut. The measured Windows host has unresolved Critical/High deployment findings. TLS, trusted-edge identity, key/quota restrictions, encrypted off-machine recovery, startup and capacity qualification remain separate launch gates.

## Optional local AI, video and GOOL

Local Qwen triage and Piper/FFmpeg narrated source cards use local computation without a paid inference or speech API. The application does not download models or voices automatically. Generation requires deliberate operator configuration and an authenticated action; opening a panel starts no inference or speech job. Follow [local AI/video setup](docs/LOCAL_AI_VIDEO.md).

The measured model comparison selected Qwen3.5 4B only for unreviewed source triage on a small frozen sample, not general factual or multilingual accuracy. The inherited paid standalone video script remains historical and automatic paid generation is disabled by default.

The optional [GOOL operator workflow](docs/GOOL_REVIEW.md) reviews an approved frozen packet through an explicitly selected route in an existing GOOL checkout. No private corpus, persona or model cache is bundled, and source collection does not automatically invoke GOOL.

## Verify your checkout

Create a Python environment from the repository root:

```sh
python -m venv .venv
```

Activate it with `.\.venv\Scripts\Activate.ps1` in Windows PowerShell or `. .venv/bin/activate` on POSIX, then run the commands below. Alternatively, invoke the virtual environment's Python by its absolute path for each Python command; its repository-relative location is `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on POSIX.

```sh
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q
cd ../frontend
npm ci
npm test
npm run build
npm audit
```

From the repository root, `python tools/verify_postgis.py` requires `DATABASE_URL` naming a separately initialized `conflict_monitor_test` database. Initialize it from `backend/` with `python -m app.bootstrap` as administrator, then return to the repository root and run the gate as the restricted runtime role. `python tools/verify_live_pipeline.py --public-feed` additionally exercises actual HTTP/WebSocket and public-feed behavior. Missing infrastructure yields an incomplete/failing result.

`python tools/release_gate.py --scan-only` checks allowlisted public source. `--package-candidate` creates a source ZIP and SHA-256 manifest; it does not certify a stable release. Export excludes secrets, sessions, databases, logs, dependency trees and private Git history.

## Measured status and remaining limits

Candidate 18 fixes the PostGIS build race by serializing build/install. Fresh finite checks cover 21 Google browser/viewport cases, three retained-video replay engines with limits, public reader SQL and database recovery, local load, isolation and snapshot/restore. The rebuilt database has fresh scoped checks; unchanged image contents carry explicitly historical native/backend tests. Detailed counts, raw failures, image identities and earlier candidate history belong in [verification](docs/VERIFICATION.md) and [container security review](docs/OS_SECURITY_REVIEW.md).

The candidate 18 main/raster observations each completed four real hours with 480 samples, two NASA packets, 480 ADS-B packets and natural Google renewal. Public JavaScript heap peaked at 986.233 MiB in the main observer and 1,011.279 MiB in the raster observer; lower-memory mobile usability remains a material limit. Cached freshness is not complete upstream coverage.

The separate public mobile emulation completed 14,400.530 seconds and 480 samples at 390 x 844 with touch and DPR 3. All three tabs retained Earth; natural Google renewal and 144 successful tile requests begun after three hours were observed, with zero recorded findings or generation calls. Page JavaScript peaked at 732.500 MiB and the contained Windows browser job at 1,913.508 MiB committed memory. This narrows the long-session emulation gap without qualifying physical-phone memory, Safari or background eviction.

**Completed security refresh:** The 39-source official refresh and selected-consumer review completed after all observation closures, 02:43:57-02:50:11 UTC on November 7. The late official database tuple was unchanged, so the eight earlier actual scans remain retained rather than being relabeled as new scans. Image/native scope retains zero unresolved reviewed High/Critical findings, four affected Medium/Low role rows and all raw scan records; host Critical/High deployment findings remain unresolved. Every registered observation has a recorded terminal closure; earlier runs supply no elapsed-time credit. The release workflow must verify the exact final commit through all three hosted jobs and the six admitted proofs before publication. Its actual run/publisher receipts bind the commit, tag and four asset digests; authenticated and anonymous downloaded-byte verification remain separate final checks. Early candidate 18 CI does not qualify a later documentation/proof tree, and this precommit document does not assert its own future CI or publication outcome.

Firefox paused-caption repaint remains a measured limitation: user playback restores captions and the exact transcript remains available. Its out-of-duration singleton frame callback is unsupported/unqualified, with cause unverified. Windows WebKit raw RGB identity remains failed despite a qualified fixed-range decoded-content check. No physical iPhone/Safari, listener-audibility, memory-leak freedom, model truth or public-uptime claim is made. Retained replay is not fresh generation or production API/database qualification.

Read [security and reporting](SECURITY.md), [methodology](docs/METHODOLOGY.md), [source review](docs/SOURCE_REVIEW.md), [bounded collection](docs/SOURCE_COLLECTION.md), [free data](docs/FREE_DATA_PIPELINE.md), [research](docs/CURRENT_RESEARCH.md) and [decisions](docs/DECISIONS.md) for the reasoning and operational limits. Publisher selection is an editorial lens, not a calibrated truth or first-reporting score.

## License

MIT application code, an explicitly GPL-3.0-or-later optional standalone speech worker and a GPL-2.0-or-later upstream-derived PostGIS patch preserve their notices. The restricted FFmpeg/libx264 build has separate GPL and corresponding-source obligations. See [third-party notices](THIRD_PARTY_NOTICES.md) and [asset provenance](docs/ASSET_PROVENANCE.md). Dependency, model-weight, provider and data-redistribution rights are separate; no third-party dataset dump is bundled.

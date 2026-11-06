# Public hosting pilot

This is a prepared hosting candidate, **not a live deployment or launch approval**.
The selected initial host is this Windows PC, alongside GOOL. The existing
ianmalcolm84.com archive stays on its other PC and Cloudflare Pages. No DNS,
tunnel, website navigation, Windows startup, power policy or live RC.4 setting
has been changed by this work.

## What can be published

The public reader serves only the independent NASA thermal and adsb.lol aircraft
publication tables described in [PUBLIC_DATA.md](PUBLIC_DATA.md). It cannot read
private event text, Telegram messages, GOOL context, delivery history, model
costs or generated media. `monitor_public` receives SELECT on
`public_observation_batches` and `public_aircraft_batches` only; bootstrap
revokes the previous private-table grants after auditing the existing role.
`PUBLIC_REPORTS_ENABLED` and `PUBLIC_TRACKING_ENABLED` cannot admit old private
corpora. Public Media and Brief remain explicitly unavailable.

One private writer collects and publishes approved packets. The separate reader
never collects or generates; it receives a dedicated database login and no
provider, operator or model credentials. Freshness comes from committed packets
with acquisition clocks and failure states, not the age of the webpage. A
missing, failed or stale publication must remain distinguishable from an empty
successful observation. NASA thermal detections are not military-strike claims;
aircraft broadcasts do not establish mission or ownership.

## Deployment topology and resource limits

Use Docker Compose 2.24.4 or newer. Apply `compose.publisher.yml` directly after
`docker-compose.yml`; **do not also apply `compose.public.yml`**. The publisher
profile imports the public reader service's explicit security contract itself.
Use a new project and fresh database volume, never the private RC.4 project.

| Component | Network access | Memory / CPU / PIDs |
| --- | --- | --- |
| Database | Private writer and internal public-reader networks; no host port | 1 GiB / 1 / 128 |
| Private collector | Private network and outbound providers; no API host port | 1 GiB / 2 / 128 |
| Public reader | Internal reader network only; no host port | 512 MiB / 0.5 / 64 |
| Private console | Private network; loopback port only | 128 MiB / 0.5 / 64 |
| Public frontend | Internal reader network plus its own loopback ingress bridge | 128 MiB / 0.5 / 64 |
| Optional tunnel | Dedicated edge bridge and outbound network only | 192 MiB / 1 / 64 |

The five steady application services total 2.75 GiB and 4.5 CPU ceilings. The
one-shot migration has a separate 512 MiB / 1 CPU ceiling. These are containment
limits, not a throughput promise or reserved host capacity. GOOL retains its
existing configuration and GPU use; this profile requests no GPU. Logs are
bounded to three 10 MiB files per service. All steady services use
`restart: unless-stopped`; this does not start Docker Desktop after Windows boot.

The private pilot collector deliberately removes its inherited `env_file`,
artifact mounts, paid credentials and administrator key. RSS and Telegram
processing modes are fixed to `reports`, Telegram transport and X ingestion are
disabled, local inference/video/SITREP jobs and OpenSky fallback are off. A
hostile fixture containing model modes, paid keys and an unknown private token
verified that these cannot enter the resolved pilot profile. The ordinary
operator profile remains available separately.

The local public frontend alone joins `public_ingress`, a normal Docker bridge required for Docker to publish its loopback port. The reader and database never join that bridge. The tunnel override replaces this local ingress membership with the dedicated internal edge network; it also removes the host port. Qualification checks actual runtime port bindings, not just the requested Compose settings.

The reader filesystem is read-only, with a 64 MiB noexec/nosuid `/tmp`; inherited
artifact and voice mounts are absent. Reader and writer DSNs use separate roles.
Set three distinct private bootstrap secrets: `POSTGRES_PASSWORD`, a new
64-character hexadecimal `POSTGRES_APP_PASSWORD`, and a different
64-character hexadecimal `POSTGRES_PUBLIC_PASSWORD`. HTTP workers never receive
the administrator password. Ordinary PostgreSQL catalog visibility and PostGIS
function access remain; this is not an arbitrary-SQL sandbox.

## Prepare the local candidate

Keep the pilot environment and tunnel credentials outside the source/export
tree, under an account-restricted private directory. The pilot environment
supplies the three database secrets, loopback frontend ports, optional reviewed
Google browser configuration, CORS origins and conflict start date. The NASA
publisher is enabled by the profile. Set `PUBLIC_AIRCRAFT_PUBLISHER_ENABLED=true`
only for the qualified adsb.lol publication candidate. No personal Telegram
credentials are needed. Shell variables override Compose `--env-file`; qualify
the resolved configuration without printing it into public logs.

First create a private image override binding **all six services**, including
migration, to the exact qualified immutable image IDs or registry digests, with
`pull_policy: never`. Use the public nginx image for `publicfrontend` and the
operator image for `frontend`. The database must be the exact qualified PostGIS
image. Keep the override with the release receipt; mutable tags are insufficient.
Do not use `--build` during a deployment or rollback.

```powershell
docker compose --env-file C:/private/monitor/pilot.env -p conflict-monitor-pilot -f docker-compose.yml -f compose.publisher.yml -f C:/private/monitor/images.yml config --quiet
```

Only after security, migration, privilege, real-provider, browser and multi-hour
soak gates pass, use that same complete file list for `up -d --no-build`, `ps`,
`stop` and subsequent operations. Startup must show one successful migration,
one private publisher, one public reader and no duplicate collection workers.
Use loopback first. Verify packet changes across publication cycles, exact-hash
downloads, source clocks, network isolation and denial of every private route.
The release receipt must bind app/database image IDs and all Compose/config
hashes, rather than reuse a previous build's observation.

## Public HTTP and trusted edge

The exact GET/HEAD `/api` allowlist is:

| Paths | Meaning |
| --- | --- |
| `/health`, `/config`, `/status` | Sanitized public availability/capabilities |
| `/publication/observations`, `/publication/aircraft` | Dedicated public dataset states |
| `/publication/observations/download` | Latest complete NASA packet |
| `/publication/observations/download/{64 lower-case hex}` | Exact immutable NASA packet |
| `/publication/aircraft/download/{64 lower-case hex}` | Exact immutable aircraft packet |

Publication query parameters are rejected. All private `/events`, `/tracking`,
`/ws`, media, generation, configuration secrets, cost, documentation and unknown
API paths are denied at nginx and independently by backend policy/SQL grants.
Raw encoded paths, duplicate slashes, dot paths and other methods cannot expand
this list. Public cookies, Authorization, X-Admin-Key, method overrides and
caller forwarding headers are discarded before proxying; Set-Cookie is removed
from responses.

API/HTML/config/status/errors are `no-store`. Only successful Vite content-hashed
JS/CSS gets one-year immutable caching; missing assets never do. No API, imagery,
provider or private-media cache is introduced. API bounds are 5 requests/sec,
burst 40, 32 concurrent per visitor and 32 globally. Downloads add 6/minute,
burst 2, one active per visitor, four globally and 512 KiB/sec per response.
These limits are defense bounds, not measured public audience capacity.

Public text responses use gzip level 4, a 1 KiB minimum, 128 KiB output buffers
per compressed response and `Vary: Accept-Encoding`. JSON, JavaScript, CSS, SVG
and WASM are eligible; nginx's default HTML type is also eligible above the
minimum. Raster imagery, audio and video are excluded. An isolated actual-nginx
run passed 118 ingress checks and exact decompression comparisons: the tested
built JS transferred 394,854 to 124,763 bytes, CSS 53,749 to 12,808 bytes and an
authored public JSON fixture 5,319 to 366 bytes. Decompressed bytes, security
headers and cache policies were unchanged; sub-1-KiB responses stayed plain.
These measurements bind that fixture's assets, not a throughput benchmark for
the final build. Google attribution and imagery behavior still require the
final browser matrix; this change does not edit those application assets.

`compose.tunnel.yml` is an **optional subsequent override**, with the connector
behind opt-in profile `public-edge`. It removes the public frontend's host port.
A dedicated internal bridge has only connector 172.31.250.2 and frontend
172.31.250.3; check address overlap before use. The connector never joins either
application/database network. Its pinned-source build recipe and template are committed;
actual tunnel-scoped credentials and UUID remain private and unconfigured.
[Cloudflare origin parameters](https://developers.cloudflare.com/tunnel/reference/origin-parameters/).

The reviewed edge config trusts CF-Connecting-IP from **only the connector IP**,
requires exact Host `monitor.ianmalcolm84.com` and forwarded HTTPS, rejects absent,
malformed or multi-value visitor identity, and retains only a precise localhost
container-health exception. `X-Forwarded-For` never selects rate-limit identity.
The example tunnel maps that one hostname to `http://publicfrontend:80`, fixes
the upstream Host, and ends with a 404 catch-all. Treat edits to the hostname,
bridge or connector address as a coupled configuration change requiring retest.
[Cloudflare header semantics](https://developers.cloudflare.com/fundamentals/reference/http-headers/).

Before opening the connector, scan its exact pinned image, create the named
outbound tunnel through the signed-in account, scope credentials to that tunnel,
and configure HTTPS plus an explicit Cloudflare cache bypass for `/api/*`.
Do not create a public origin port or disable Host/origin checks. Then qualify
actual visitor headers, TLS/HSTS, API no-store, static cache behavior and 429
recovery through the real hostname. Local edge emulation cannot prove those
account settings. Do not enable Cloudflare Workers Paid or purchase a host as
part of this preparation.

### Connector image qualification

The official 2026.10.7 image's fresh raw scan retained 24 findings, including four
High records in Debian libc/zlib. Its actual cloudflared executable is static:
ELF inspection found no interpreter or dynamic segment, and its embedded build
metadata records `CGO_ENABLED=0`. `tools/hosting/Dockerfile` copies that exact
pinned official executable and CA bundle into scratch, along with user/group
identity files, certificate provenance and license texts. It does not rebuild,
strip or replace the executable or hide scanner records. The unused libraries,
shell and package runtime are physically absent. The complete before/after
inventories preserve all 69 Go module names and versions. License archives for
all 67 third-party modules matched the official source's `go.sum`; the combined
notices retain 97 license files, including cloudflared and Go.

The local static prototype passed 17 offline byte/ELF/CA/CLI/config checks and a
fresh Grype High gate with zero matched records. CLI/config containers used `--network=none`;
no real tunnel, credentials, DNS or account operation occurred. The official
binary's dirty VCS marker remains documented: this is byte preservation of an
official artifact, not a reproducible source build or verified signed attestation.
See [the retained security projection](qualification/2026-11-06-cloudflared-static-runtime.json).

Build with `docker build --platform linux/amd64 -t
conflict-monitor-cloudflared:2026.10.7-static.1 tools/hosting`, then scan and run
`tools/verify_cloudflared_static.py --image sha256:EXACT_IMAGE_ID --output
PRIVATE_RECEIPT_PATH`. The Compose connector tag is a local build convenience,
not a release identity. Add its exact qualified image ID/digest to the private
deployment image override along with the six application services, and use
`--no-build`. Repeat scanner/inventory qualification on the final built image;
an offline prototype does not qualify actual public networking or unknown flaws.

## Google imagery launch configuration

Use a separate browser key restricted to the actual monitor HTTPS referrer and
Map Tiles API only. A localhost key working is not proof that the public origin
is permitted or safely restricted. Native attribution remains visible. Google
photorealistic imagery has acquisition dates and does not represent a live
satellite feed.

The checked Google pricing lists 1,000 free Photorealistic 3D root events/month,
then $6 per 1,000 in the next tier. Root requests are billable; child tile
requests do not consume the daily root quota, and sessions last up to three
hours. Recheck before launch. Set and verify a daily root-request quota for a
bounded pilot; budget alerts alone are not a hard spending cap. A free data
adapter does not make Google imagery unlimited or necessarily free.
[Google pricing](https://developers.google.com/maps/billing-and-pricing/pricing),
[Map Tiles usage and billing](https://developers.google.com/maps/documentation/tile/usage-and-billing).

## Backup, recovery and Windows availability

Use `tools/database_backup.py backup --container EXACT_DB_CONTAINER --directory
C:/private/monitor-backups` for a consistent custom-format dump. It passes no
password on the command line, excludes ownership/ACLs, hashes the binary bytes,
and refuses incomplete dumps. Defaults bound each dump to 256 MiB, 15 minutes,
seven retained dumps and a 2 GiB directory budget. It reserves capacity before
starting and serializes jobs with an exclusive directory lock. It never deletes
old backups automatically. Review and adjust bounds from actual dataset size;
copy verified backups to encrypted off-machine storage before retiring any.
The tool rejects backup destinations inside this source tree. Restrict directory
ACLs; a database backup contains private material even if the reader is limited.

```powershell
python tools/database_backup.py restore-rehearsal --manifest C:/private/monitor-backups/CHOSEN.json --image sha256:QUALIFIED_DATABASE_IMAGE --output C:/private/monitor-backups/restore-receipt.json
```

Rehearsal checks length/hash, restores into a newly created disposable volume
with no network or host ports, records table counts and removes its own fixture.
It never restores over an existing database. The structural restore receipt
alone does not prove role grants, offsite durability or recovery time. Before a
real cutover, restore to a separate preserved volume, run current bootstrap,
verify reader/writer negative SQL gates, compare required content and follow
[DB_UPGRADE.md](DB_UPGRADE.md). Preserve the old volume and exact rollback images.
Never run `down -v`. Stop the connector first to withdraw public access; stop the
writer before a final migration dump. Reverting to an older database does not
merge new writes.

Before pilot admission, verify Docker Desktop can start under the intended
Windows login, enough disk remains for the database plus reserved backup budget,
and the PC's actual sleep/restart behavior meets the chosen availability.
Container restart policy only works while Docker is running. An intentionally
stopped container remains stopped. A power failure, logout policy, Windows
update or suspended PC can interrupt this pilot; do not claim production uptime.
No global WSL memory changes, startup task registration, power changes or PC
restart are part of these files. Qualify recovery in a planned maintenance
window, preserving GOOL's workload. Run a private health/packet-age check after
recovery and retain a fresh backup/restore receipt.

## Verified scope and remaining launch gates

The isolated new-route nginx fixture passed 102 checks; the actual trusted-edge
fixture passed 23 checks including Host/scheme and identity spoof negatives,
independent visitors and concurrent download caps. Fixtures used no host ports,
providers, existing application data or tunnel, and cleanup was verified. The
hostile-environment Compose test passes for both publisher and tunnel profiles.
These receipts are under `artifacts/private/public-hosting-20261106/` and must be
bound to unchanged config hashes.

The earlier nine-case Google matrix verified the previous fully withheld public
workspace in Chromium, Firefox and WebKit at 320x740, 390x844 and 1440x900. It is
historical evidence, not a pass for the newly added live-publication UI. Repeat
that matrix and the full live soak on the new immutable images. Physical iPhone
behavior, real public hostname, Google quota/key restrictions, off-machine
backup, startup recovery and sustained external-reader capacity remain separate
qualification limits until directly measured.

The signed-in Cloudflare account was inspected read-only: the existing archive
is one direct-upload Pages application, Containers is not enabled, and no tunnel
exists. Pages does not host this FastAPI/PostGIS stack. A separate static Pages
front with approved expiring snapshots could reduce host exposure, but would
need a different freshness/publication/signing design and separate qualification;
it is not silently substituted for this persistent reader/publisher design.
The archive handoff and safe navigation change sequence remain in
[WEBSITE_INTEGRATION.md](WEBSITE_INTEGRATION.md). Publish its Monitor link only
after the real HTTPS tool and return navigation pass, while coordinating both
other-PC publishing triggers.

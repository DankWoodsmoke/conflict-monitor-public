# PostgreSQL 17 / reduced PostGIS 3.6 profile upgrade

The RC.2 Compose profile builds `conflict-monitor-postgis:0.2.0-rc.2` from the public source recipe in `tools/postgis`. It uses the pinned official PostgreSQL 17/Trixie base, SHA-256-verified PostGIS **3.6.4** source and a pinned upstream FlatGeobuf validation backport, plus signature-verified gosu **1.20**. The qualified image is `sha256:fc61b5645ca9a0115ef9a4fab2f0a3b35006c90a05d5511c5c010786da75ba65`; actual SQL reports PostgreSQL **17.11** and PostGIS **3.6.4**. This replaces the earlier full `postgis/postgis` image. It retains core PostGIS, topology, fuzzystrmatch and Tiger support, while excluding raster, address standardizer and SFCGAL. Inspect existing extension/function dependencies before adopting this reduced profile; unsupported dependencies block admission rather than being silently removed.

Existing installations must restore into a **new volume** before using this profile. Compose now names its default database volume `pgdata17_36_secure`; it deliberately reuses neither `pgdata` nor `pgdata17_36`. Starting an empty profile is not an upgrade of existing data. Rebuilding from the pinned recipe can yield a different image identity or newer distributor packages; independently qualify the actual built bytes rather than assuming the measured image identity carries forward.

The database initializer is `monitor_admin`; a one-shot `migrate` service runs `python -m app.bootstrap` with that administrator, applies Alembic, and grants a separate runtime login `monitor`. The HTTP service starts only after successful initialization and runs uvicorn without migrations. Set `POSTGRES_PASSWORD` for the administrator and a **different** `POSTGRES_APP_PASSWORD` containing 64 random hex characters for runtime access. Known database administrator/password/DSN variables are explicitly blanked in the HTTP container even when present in its `env_file`.

The [executed RC.2 cutover and regression receipt](qualification/2026-10-30-rc2-database-cutover-and-regressions.json) records the final `fc61b564…` image and backend `9b094edd…`: a consistent exported-snapshot dump, equality of all ten recorded tables and five sequences, 23 indexes, geometry/locale/extensions, preservation of the original volume and fresh separate-database bootstrap/role/PostGIS/TCP gates. It also records two complete 250-case upstream SQL runs (500 executions) and 346 CUnit tests/5,495 assertions with no failures, bound to the final native PostGIS bytes. A reused-fixture spatial assertion failed earlier and remains retained. This does not certify excluded extensions, zero downtime or the still-pending final UI/three-hour observation.

The [October 29 restricted-runtime rehearsal](qualification/2026-10-29-postgresql17-restricted-runtime-rehearsal.json), [restore rehearsal](qualification/2026-10-29-postgresql17-restore-rehearsal.json) and [earlier live cutover](qualification/2026-10-29-postgresql17-live-cutover-and-artifact-persistence.json) remain historical evidence for the previous full image `postgis/postgis:17-3.6@sha256:1ac10b2551ba84ae05db8e7da477afcd0a3fede99bcb7705da2ee157390cb095`. That prior switch preserved recorded data and artifacts when moving from PostgreSQL 17.5/PostGIS 3.5.2 to 17.11/3.6.4. It is not relabeled as qualification of the new reduced image.

Runtime `monitor` has no superuser, role/database creation, replication, RLS bypass or role memberships, and owns no application objects, public schema or database. It receives modeled-table SELECT/INSERT/UPDATE/DELETE, application-sequence USAGE/SELECT and Alembic-revision SELECT. Database/schema creation, temporary tables, revision writes, extension installation and privilege escalation are denied. PostgreSQL's normal catalog visibility and ordinary PostGIS/advisory-lock function calls remain available. Unknown existing roles or a privileged/owning runtime identity block initialization; do not bypass that check by demoting an old role in place.

## Why logical restore

PostgreSQL's [17.11 notes](https://www.postgresql.org/docs/17/release-17-11.html) describe a same-major minor upgrade. The earlier full-image migration also crossed Bullseye/Trixie glibc collation implementations, for which the [official image instructions](https://github.com/postgis/docker-postgis#readme) recommend dump/restore. The RC.2 change additionally reduces installed spatial components and introduces an explicitly reviewed source backport. A logical restore into a new database rechecks dependency availability and rebuilds indexes while preserving a rollback volume; attaching the new image to older data files bypasses that procedure even when the PostgreSQL major/version is unchanged.

## Required sequence

1. Record the current database volume, exact database/application image IDs, extension versions and required native spatial functions, locale versions, migration revision, table counts, sequences, checkpoint values and source/receipt hashes. Check for raster, address-standardizer or SFCGAL dependencies before selecting this target. Capture the local analysis manifest and narrated video's filename, full SHA-256 and byte length. Store credentials and raw database backups outside the public source tree.
2. Rehearse the complete restore into an isolated new volume. Use the target PostgreSQL 17 client to create a custom-format dump (`pg_dump -Fc --no-owner --no-acl`). For an exact comparison while a source remains active, hold a read-only repeatable-read transaction, export its snapshot and pass that snapshot to `pg_dump --snapshot`. Never close that transaction before the dump finishes.
3. For the final cutover, stop application collectors/writers and confirm generation jobs are idle. Take a **new** consistent private dump and checksum it. The rehearsal dump is not the final backup. Preserve the source volume and both dumps.
4. Build and qualify the target source recipe, then initialize a new PostgreSQL 17 volume with `monitor_admin`. Create the application database from `template0`, retaining the source's UTF-8 encoding and locale names. Restore as `monitor_admin` with `pg_restore --no-owner --no-acl --exit-on-error`, then execute `SELECT postgis_extensions_upgrade();` as described in the [PostGIS upgrade instructions](https://postgis.net/docs/postgis_administration.html#upgrading). Any missing extension/function or restore error blocks admission. Run the one-shot initializer to create/grant the restricted runtime role. Excluding ownership/ACLs makes restored application objects administrator-owned instead of carrying forward the old privileged runtime identity.
5. Require equality of every application table's count and canonical full-row hash, event raw-text hashes, receipt content hashes, checkpoints and sequence state. Check all required index definitions and `pg_index.indisvalid`, geography values/SRID/column agreement, actual locale version, extension versions, replay sampling and stored source-digest citation/hash reconstruction. Run the runtime-permission, PostGIS and real pipeline gates against a **separate qualification database**, using `monitor`, and verify administrator credentials are absent from the actual HTTP container. Never inject test rows into the live restored database.
6. Stop the staging database process before Compose mounts its new volume. Two PostgreSQL processes must never mount the same data directory concurrently. Point Compose at the verified new volume using an explicit persistent override, start the database, confirm its actual SQL versions and only then start the backend. Keep the local briefing volume and voice mount unchanged.
7. Verify REST/WebSocket readiness, preserved source/receipt/checkpoint data and unchanged local analysis/video artifacts. Record the observed service transition, including any expected startup failures. Begin a fresh observation period bound to the new database and application image identities; earlier observations remain evidence for their original profiles.

For a restored external volume, the persistent override has this shape (replace the example name with the independently verified volume):

```yaml
volumes:
  pgdata17_36_secure:
    external: true
    name: conflict_monitor_restored_pg17_36_secure
```

Use that override for **every** subsequent Compose invocation. For example, a local operator with a private `compose-restored-db.yml` uses:

```powershell
docker compose --env-file .env -f docker-compose.yml -f compose-restored-db.yml up -d
```

Keep the override alongside the deployment's private configuration. Do not run `docker compose down -v` or remove the old volume during qualification.

## Rollback

Before the switch, save a **standalone** rollback Compose profile containing the original database image/volume and exact locally available backend/frontend image IDs with `pull_policy: never`. Preserve the old deployed environment privately; the new runtime password is deliberately different and cannot authenticate to the old volume. A standalone profile avoids inheriting the new migration dependency or restricted-role DSN. Keep credentials in private environment files rather than YAML. Raw-format environment files require Docker Compose 2.30 or newer.

Stop collectors before rollback, and preserve the new volume and a new backup if writes have occurred since cutover. Stop the current database process before replacing it. Start the original profile **without** `--build`; validate service and artifact manifests again. Use the original Compose project name so the expected service/network names are retained.

```powershell
docker compose --project-name conflict-monitor -f compose-rollback.yml up -d --no-build
```

Returning to the old volume serves its earlier snapshot. It does not merge post-cutover writes. Reconciliation or another logical restore is required before discarding either history. The qualified procedure retains both volumes and all comparison receipts.

## Security scope

Updated PostgreSQL/PostGIS versions do not imply a vulnerability-free image. The refreshed exact-image scan retains **412 records, including 10 Critical and 117 High**, and the raw High gate still fails. The [complete database security review](qualification/2026-10-30-database-security-review.json) distinguishes 29 distributor fixed-boundary matches, 382 vendor-open records and one absent-component mismatch, retaining aliases rather than suppressing them. The nominal PostGIS 3.6.4 match for CVE-2026-73515 remains visible alongside the reviewed, pinned upstream backport and independent native/SQL tests. Input constraints are not package patches.

The former gosu 1.19/moby user v0.1.0 finding belongs to the older full image. The target uses gosu 1.20 with `github.com/moby/sys/user v0.4.1`, meeting that module's recorded fix boundary. Its static Go 1.24.6 inventory still requires separate review: [actual binary analysis](qualification/2026-10-30-gosu-go-binary-review.json) retains 63 module-level and three package-level finding messages, with no identified affected-symbol finding. Neither exit 0 nor zero identified symbols is a zero-vulnerability guarantee.

The shipped database root filesystem is read-only, with explicit writable data/tmpfs locations and PROJ network access disabled. All default capabilities are dropped; listed initialization capabilities permit the entrypoint to hand off to PostgreSQL. In the [isolated profile preflight](qualification/2026-10-30-compose-profile-ci-preflight.json), actual server PID1 was UID 999 with zero effective capabilities and no-new-privileges set, with no published database port. Keep identity files trusted and SQL access restricted. XML/curl/native-library advisories remain retained; arbitrary hostile SQL and all native parser paths were not exhaustively tested. Reassess after mounts, privileges, image bytes or input paths change.

The early PostgreSQL 17.5 profile used a superuser runtime login; rolling back to that particular profile restores those privileges. The immediately preceding PostgreSQL 17.11 full-image profile already had a restricted runtime role, but retained its older package/component exposure. Preserve and verify the actual rollback profile's permissions rather than assuming all earlier versions are equivalent. The migration administrator remains privileged by design, has no HTTP ports, and is not a normal application worker. Do not expose the database port publicly or treat loopback HTTP binding as an authentication control for other containers or local users.

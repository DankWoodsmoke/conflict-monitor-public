# PostgreSQL 17 / PostGIS 3.6 upgrade

The release profile pins `postgis/postgis:17-3.6@sha256:1ac10b2551ba84ae05db8e7da477afcd0a3fede99bcb7705da2ee157390cb095`. An executed isolated qualification on 2026-10-29 returned PostgreSQL **17.11** and PostGIS **3.6.4**. See the [restore rehearsal receipt](qualification/2026-10-29-postgresql17-restore-rehearsal.json).

Existing installations must restore into a **new volume** before using this profile. Compose now names its default database volume `pgdata17_36`; it deliberately does not reuse the earlier `pgdata` volume. Starting an empty profile is not an upgrade of existing data.

The database initializer is `monitor_admin`; a one-shot `migrate` service runs `python -m app.bootstrap` with that administrator, applies Alembic, and grants a separate runtime login `monitor`. The HTTP service starts only after successful initialization and runs uvicorn without migrations. Set `POSTGRES_PASSWORD` for the administrator and a **different** `POSTGRES_APP_PASSWORD` containing 64 random hex characters for runtime access. Known database administrator/password/DSN variables are explicitly blanked in the HTTP container even when present in its `env_file`.

The [restricted-runtime rehearsal](qualification/2026-10-29-postgresql17-restricted-runtime-rehearsal.json) records actual Compose startup, denied administrative operations, runtime PostGIS/TCP/WebSocket gates and a restored-data comparison. It is an isolated rehearsal; a final live cutover requires its own receipt.

The [executed live cutover receipt](qualification/2026-10-29-postgresql17-live-cutover-and-artifact-persistence.json) records the later PostgreSQL 17.5/PostGIS 3.5.2 to 17.11/3.6.4 switch: all preexisting source/receipt/snapshot/brief rows and checkpoints were preserved, runtime administrator credentials were removed, and the old recorded analysis/video survived unchanged before deliberate regeneration. It records a planned service interruption and retains the old volume; it does not claim zero downtime or complete the separate final observation period.

Runtime `monitor` has no superuser, role/database creation, replication, RLS bypass or role memberships, and owns no application objects, public schema or database. It receives modeled-table SELECT/INSERT/UPDATE/DELETE, application-sequence USAGE/SELECT and Alembic-revision SELECT. Database/schema creation, temporary tables, revision writes, extension installation and privilege escalation are denied. PostgreSQL's normal catalog visibility and ordinary PostGIS/advisory-lock function calls remain available. Unknown existing roles or a privileged/owning runtime identity block initialization; do not bypass that check by demoting an old role in place.

## Why logical restore

PostgreSQL's [17.11 notes](https://www.postgresql.org/docs/17/release-17-11.html) describe a same-major minor upgrade, but the [official PostGIS image instructions](https://github.com/postgis/docker-postgis#readme) add an important constraint: maintained images moved from Bullseye to Trixie, changing glibc collation behavior. The image maintainers recommend dump/restore into a fresh database. Old `*-3.5` tags no longer receive updates. This procedure rebuilds text indexes under the new locale implementation instead of attaching the new image to old data files.

## Required sequence

1. Record the current database volume, exact database/application image IDs, extension versions, locale versions, migration revision, table counts, sequences, checkpoint values and source/receipt hashes. Capture the local analysis manifest and narrated video's filename, full SHA-256 and byte length. Store credentials and raw database backups outside the public source tree.
2. Rehearse the complete restore into an isolated new volume. Use the target PostgreSQL 17 client to create a custom-format dump (`pg_dump -Fc --no-owner --no-acl`). For an exact comparison while a source remains active, hold a read-only repeatable-read transaction, export its snapshot and pass that snapshot to `pg_dump --snapshot`. Never close that transaction before the dump finishes.
3. For the final cutover, stop application collectors/writers and confirm generation jobs are idle. Take a **new** consistent private dump and checksum it. The rehearsal dump is not the final backup. Preserve the source volume and both dumps.
4. Initialize a new PostgreSQL 17 volume with `monitor_admin`. Create the application database from `template0`, retaining the source's UTF-8 encoding and locale names. Restore as `monitor_admin` with `pg_restore --no-owner --no-acl --exit-on-error`, then execute `SELECT postgis_extensions_upgrade();` as described in the [PostGIS upgrade instructions](https://postgis.net/docs/postgis_administration.html#upgrading). Run the one-shot initializer to create/grant the restricted runtime role. Excluding ownership/ACLs makes restored application objects administrator-owned instead of carrying forward the old privileged runtime identity.
5. Require equality of every application table's count and canonical full-row hash, event raw-text hashes, receipt content hashes, checkpoints and sequence state. Check all required index definitions and `pg_index.indisvalid`, geography values/SRID/column agreement, actual locale version, extension versions, replay sampling and stored source-digest citation/hash reconstruction. Run the runtime-permission, PostGIS and real pipeline gates against a **separate qualification database**, using `monitor`, and verify administrator credentials are absent from the actual HTTP container. Never inject test rows into the live restored database.
6. Stop the staging database process before Compose mounts its new volume. Two PostgreSQL processes must never mount the same data directory concurrently. Point Compose at the verified new volume using an explicit persistent override, start the database, confirm its actual SQL versions and only then start the backend. Keep the local briefing volume and voice mount unchanged.
7. Verify REST/WebSocket readiness, preserved source/receipt/checkpoint data and unchanged local analysis/video artifacts. Record the observed service transition, including any expected startup failures. Begin a fresh observation period bound to the new database and application image identities; earlier observations remain evidence for their original profiles.

For a restored external volume, the persistent override has this shape (replace the example name with the independently verified volume):

```yaml
volumes:
  pgdata17_36:
    external: true
    name: conflict_monitor_restored_pg17_36
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

Updated PostgreSQL/PostGIS versions do not imply a vulnerability-free image. Preserve raw scanner output and distinguish Debian backported package fixes from generic binary CPE matches. The measured target contains `gosu 1.19` with `github.com/moby/sys/user v0.1.0`; [GHSA-mjcv-p78q-w5fw](https://github.com/moby/sys/security/advisories/GHSA-mjcv-p78q-w5fw) remains present. Its documented attack requires an attacker-controlled identity file. The isolated profile had root-owned non-writable `/etc/passwd` and `/etc/group`, only the PostgreSQL data volume mounted, and a PostgreSQL process running as UID 999. That observed constraint is an applicability assessment, not a patched-package or universal exemption claim. Reassess if mounts, privileges or input paths change.

The historical profile used a superuser runtime login. A rollback to it restores those earlier permission properties; it does not retain the new role separation. The migration administrator remains privileged by design, has no HTTP ports, and is not a normal application worker. Do not expose the database port publicly or treat loopback HTTP binding as an authentication control for other containers or local users.

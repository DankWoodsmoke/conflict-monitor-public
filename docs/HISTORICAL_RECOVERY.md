# Historical database recovery boundary

Checked October 29, 2026. The April archive contains a separate historical
database dump. It is not a source/assets-only backup. The initial recovery
selected 87 source/assets files and deliberately excluded the database payload
from the public candidate. The subsequent fresh 98-event candidate database and
its PostgreSQL upgrade were separate work; they did not restore this history.

The [sanitized archival receipt](qualification/2026-10-29-historical-database-recovery.json)
records a completed private, isolated restoration. No historical record was
merged into the active pipeline or bundled into the public source release.

## Archive and static validation

The unchanged 281,863,447-byte outer archive has SHA-256
`31d04ebcda8ecf0be13a5b14eed5093892e7d4985957ff91fb45f8d97f9e2ec1`.
Only its `conflict_monitor_db.sql.gz` member was extracted into private review
storage. The member is 211,771,511 bytes, with SHA-256
`84e6ff04552f3ffbe5aadc1d567067c3a53524d256e1c1f1651523006ea19e47`.
Gzip CRC/EOF validation produced a 1,036,439,928-byte plain PostgreSQL dump with
SHA-256 `1ecf2aca2fd2eab11bd06b27e70b41a500623ed7b00c7cb5d9ce99a50800cf69`.
Its header identifies PostgreSQL 16.4 and pg_dump 16.4.

Two static passes agreed on schema, COPY counts and 96 SQL statements. The
observed commands were standard dump DDL/data, literal settings, ownership
changes and `pg_catalog.set_config`/`setval`. No psql shell/include commands,
COPY PROGRAM/server-file access, custom functions/DO/triggers, foreign objects,
role/database creation, DROP or TRUNCATE were observed. Four fixed installed
extensions and 15 ownership changes required explicit review. This bounded
review is not a general SQL safety or malware certificate.

## Executed private restoration

The approved restore used the pinned PostgreSQL 17.11/PostGIS 3.6.4 image, a new
dedicated volume/container, no network or TCP listener, no published ports or
host bind mounts, and no production credentials. It ran as UID 999 with all
capabilities dropped, no-new-privileges, a read-only root filesystem, bounded
tmpfs, two CPUs, 2 GiB memory and 256 PIDs. The old dump owner became a local
NOLOGIN, non-superuser role. No application, migration, collector, model or
speech process ran against the archive.

Validated gzip was streamed into fixed `psql --no-psqlrc`, `ON_ERROR_STOP` and
single-transaction execution. The process exited zero with no stderr. Every
escaped field in every row was then compared using COPY-text SHA-256 multisets,
with explicit UTC/ISO output settings and no field-value normalization:

| Application table | Rows preserved | Full-field row comparison |
| --- | ---: | --- |
| events | 19,818 | Exact match |
| sitreps | 112 | Exact match |
| tracking_snapshots | 12,361 | Exact match |
| intel_media | 251 | Exact match |
| usage_log | 21,159 | Exact match |
| channel_checkpoints | 7 | Exact match |
| cost_config | 7 | Exact match |
| **Total** | **53,715** | **No missing or extra row hashes** |

PostGIS structural checks found all 19,818 stored geometries non-null, valid and
SRID 4326. Indexes and constraints were valid. These checks do not establish
correct incident locations. In particular, **5,991 points retain the legacy
UNKNOWN placeholder at latitude −25, longitude 80** despite being geometrically
valid. All points are finite and within geographic ranges; stored longitude
spans −157.9991492 to 151.2082848 and latitude −38.8973641 to 77.6192349. Geometry
and numeric latitude/longitude fields agree exactly. The other points are not
thereby confirmed locations or site-precise observations. No archived coordinate
was changed or admitted into the current map.

The historical container is stopped and its volume,
dump and private receipts are preserved. Active database/application image,
start-time and volume identities stayed unchanged throughout the review.

## Interpretation and remaining limits

Stored event source fields comprise 5,382 `rss_x_`-prefixed rows, 3,423 other
RSS-prefixed rows, 10,997 literal `telegram` rows and 16 satellite-prefixed rows.
These are stored-label counts. They do not verify native publisher transport,
underlying platform, author identity, independence, content rights or truth.

Event creation clocks span March 20 through April 8, 2026. Stored source
timestamps span July 9, 2011 through April 8, 2026 at 22:25:36 UTC; the latest
creation clock is April 8 at 20:23:56.952264 UTC. Such clocks are preserved,
including old or anomalous values, and are not an established incident timeline.
The receipt separately records brief, snapshot, media and checkpoint clocks.

The 21,159 archived usage-log rows belong to the historical database. They are
separate from the new qualified live profile's zero-paid-usage observations;
neither count is a statement about the other's costs. No archived cost values
are published, and no inference or speech job was run on historical content.

Legacy summaries, scores, locations and model interpretations remain unreviewed
historical assertions. This schema predates the current provenance/receipt
tables and has not been migrated into the active application. Any future
historical viewer or reconciliation needs its own read-only boundary, identity
and provenance checks, and must not silently import old confidence claims as
current evidence. Unknown writes after the April backup remain unrecovered.
Public code licensing does not authorize redistribution or AI processing of
the private archive; no source bodies, author names, URLs, usage-cost rows,
credentials or database payload are included in the public receipt.

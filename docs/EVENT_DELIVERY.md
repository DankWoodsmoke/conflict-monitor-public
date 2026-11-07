# Committed Event delivery

The live report stream acknowledges committed delivery offsets. An Event ID is assigned before the insert transaction commits. A higher ID can become visible before a lower one, so `/events?after_id=` remains a legacy lookup and is unsuitable as a lossless reconnect cursor. The browser uses WebSocket messages as refresh hints and resumes from the last validated REST page. [PostgreSQL transaction visibility](https://www.postgresql.org/docs/17/transaction-iso.html#XACT-READ-COMMITTED)

## REST contract

`GET /events/delivery/baseline` returns `epoch`, `after` and a bounded current `events` list. Its offset and events share a read-only repeatable snapshot. It starts a live subscription, while older reports remain available through ordinary event history. The epoch distinguishes live and demo mode. A report created by a historical backfill after the baseline is still a new delivery, even if its source date is older.

`GET /events/delivery/changes?epoch=…&after=…&limit=50` returns ordered `changes`, `next_after` and `has_more`. Both endpoints accept a limit of 1–100, with a default of 50. Offsets are nonnegative signed-64-bit values represented as decimal strings. Other-mode deliveries can leave gaps in a page. An empty page keeps the previous cursor. An upsert carries the current Event view. A delete carries an Event ID and `event=null`, including when an earlier creation was already purged before the reader retrieved it.

The server returns HTTP 409 and `detail.code=delivery_baseline_required` when the epoch differs, the cursor is ahead, or retained offsets no longer cover it. Clients must establish a new baseline. They must never acknowledge a WebSocket ID, history cursor, malformed page or abandoned request.

## Storage and operation

Alembic revision `0005_event_delivery` adds an outbox and one state row without rewriting existing Events or source receipts. Event insert and delete triggers enqueue IDs and operations in the original write transaction. The publisher assigns at most 100 offsets per transaction to visible pending rows. It fences only other publishers. A rollback leaves its work eligible again. The restricted runtime role can read the stream and invoke this fixed publisher function. It cannot directly forge, remove or reorder delivery rows. [PostgreSQL transactional triggers](https://www.postgresql.org/docs/17/trigger-definition.html)

The publisher resumes after an application restart even with collectors disabled. `/status.event_delivery` exposes publication and retry clocks, while a transient publication failure degrades readiness. Published storage retains the most recent 50,000 global offsets. Unpublished work remains queued. This is a count bound across live and demo deliveries. It does not promise a particular offline duration.

Normal Event purging still removes Event rows while preserving existing immutable source receipts. Delivery tombstones retain only IDs and offsets. In-place updates of already-delivered Event IDs do not create a delivery record in this contract. Initial history loading and analytical source verification retain their separate scopes.

## Migration and recovery

Stop and drain old writers, take the verified database snapshot, apply the additive migration and recheck source, receipt and role grants before starting the new application pair. The migration begins with an empty delivery stream. It does not replay pre-migration Events or modify their source times. Keep the stream and state on ordinary image rollback. A restored database needs a new epoch before it serves writes or reconnect clients, even when it is restored from the same delivery-enabled instance. Have the migration administrator rotate the singleton epoch with `UPDATE public.event_delivery_state SET epoch = gen_random_uuid() WHERE singleton` under the same controlled restore procedure. This prevents reusing offsets from an earlier copy of the database under the old epoch. Avoid destructive schema downgrade.

## Qualification commands

Run `tools/verify_database_role.py` and `tools/verify_event_delivery.py` with a restricted runtime DSN for a disposable `conflict_monitor_test` database. The delivery gate creates synthetic Event fixtures, holds the publication fence briefly and uses a real loopback HTTP server. It checks the lower-ID late commit, publication and producer rollback, tombstones, mode boundaries and ordered pagination. Do not point it at a live database. Browser reconnect and long-running provider availability require separate runtime observations.

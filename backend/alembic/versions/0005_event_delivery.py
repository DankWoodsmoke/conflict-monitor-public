"""Queue committed Event creations and deletions for cursor-based delivery."""
from alembic import op

revision = "0005_event_delivery"
down_revision = "0004_telegram_history_jobs"
branch_labels = None
depends_on = None


def upgrade():
    # Events already present at migration remain available through the initial
    # baseline and ordinary history. Only new writes enter this delivery epoch.
    op.execute("""
        CREATE TABLE public.event_delivery_state (
            singleton boolean PRIMARY KEY CHECK (singleton),
            epoch uuid NOT NULL DEFAULT gen_random_uuid(),
            last_offset bigint NOT NULL DEFAULT 0,
            retired_through bigint NOT NULL DEFAULT 0,
            CHECK (retired_through >= 0 AND last_offset >= retired_through)
        )
    """)
    op.execute("INSERT INTO public.event_delivery_state (singleton) VALUES (true)")
    op.execute("""
        CREATE TABLE public.event_deliveries (
            queue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_id integer NOT NULL CHECK (event_id > 0),
            stream text NOT NULL CHECK (stream IN ('live', 'demo')),
            action text NOT NULL CHECK (action IN ('upsert', 'delete')),
            publication_offset bigint UNIQUE CHECK (publication_offset > 0)
        )
    """)
    op.execute("""
        CREATE INDEX ix_event_deliveries_pending ON public.event_deliveries (queue_id)
        WHERE publication_offset IS NULL
    """)
    op.execute("""
        CREATE INDEX ix_event_deliveries_stream_offset ON public.event_deliveries (stream, publication_offset)
        WHERE publication_offset IS NOT NULL
    """)
    # No foreign key to Event: the existing retention operation must be able to
    # remove a report. Tombstones carry IDs only and never retain source bodies.
    op.execute("""
        CREATE FUNCTION public.enqueue_event_delivery() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        DECLARE
            source_name text;
            source_id integer;
            operation text;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                source_name := OLD.source;
                source_id := OLD.id;
                operation := 'delete';
            ELSE
                source_name := NEW.source;
                source_id := NEW.id;
                operation := 'upsert';
            END IF;
            IF source_id > 0 AND source_name <> 'situational' THEN
                INSERT INTO public.event_deliveries (event_id, stream, action)
                VALUES (source_id, CASE WHEN source_name = 'demo' THEN 'demo' ELSE 'live' END, operation);
            END IF;
            RETURN NULL;
        END
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION public.enqueue_event_delivery() FROM PUBLIC")
    op.execute("""
        CREATE TRIGGER event_delivery_enqueue AFTER INSERT OR DELETE ON public.events
        FOR EACH ROW EXECUTE FUNCTION public.enqueue_event_delivery()
    """)
    # Only publication transactions share this fence. Event inserts/deletes
    # never wait on it. Lock lifetime and counter updates are transactional.
    op.execute("""
        CREATE FUNCTION public.publish_event_deliveries() RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog SET lock_timeout = '2s' AS $$
        DECLARE
            previous_offset bigint;
            next_floor bigint;
            published integer;
        BEGIN
            IF NOT pg_try_advisory_xact_lock(70415, 9) THEN
                RETURN -1;
            END IF;
            SELECT last_offset INTO STRICT previous_offset
            FROM public.event_delivery_state WHERE singleton FOR UPDATE;
            WITH pending AS MATERIALIZED (
                SELECT queue_id FROM public.event_deliveries WHERE publication_offset IS NULL
                ORDER BY queue_id LIMIT 100 FOR UPDATE
            ), numbered AS (
                SELECT queue_id, row_number() OVER (ORDER BY queue_id) AS position FROM pending
            )
            UPDATE public.event_deliveries AS queued
            SET publication_offset = previous_offset + numbered.position
            FROM numbered WHERE queued.queue_id = numbered.queue_id;
            GET DIAGNOSTICS published = ROW_COUNT;
            IF published > 0 THEN
                next_floor := greatest(0, previous_offset + published - 50000);
                DELETE FROM public.event_deliveries WHERE publication_offset <= next_floor;
                UPDATE public.event_delivery_state
                SET last_offset = previous_offset + published, retired_through = next_floor
                WHERE singleton;
            END IF;
            RETURN published;
        END
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION public.publish_event_deliveries() FROM PUBLIC")


def downgrade():
    raise RuntimeError("Delivery offsets must be preserved; restore a verified backup instead.")

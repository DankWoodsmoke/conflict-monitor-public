"""Preserve future RSS receipts and schedule bounded retries independently of feeds."""
from alembic import op
import sqlalchemy as sa

revision = "0006_rss_due_retries"
down_revision = "0005_event_delivery"
branch_labels = None
depends_on = None

MAX_LEGACY_FUTURE_RECEIPTS = 10_000
# Versioned here, independent of future application parser edits.
CLOCK_PATTERN = r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(Z|[+-]((0[0-9]|1[0-3]):[0-5][0-9]|14:00))$"
SEED_SQL = """
INSERT INTO public.source_report_retries (identity, source_name, due_at, next_attempt_at)
SELECT identity, report->>'channel_name', due_at, due_at
FROM (
    SELECT identity, report,
      CASE WHEN report->>'timestamp' ~ :clock_pattern
             AND substring(report->>'timestamp',1,4) BETWEEN '1970' AND '9998'
             AND pg_input_is_valid(report->>'timestamp', 'timestamp with time zone')
           THEN (report->>'timestamp')::timestamptz END AS due_at
    FROM public.source_reports WHERE status = 'future_source_time'
) eligible
WHERE due_at IS NOT NULL
  AND report->>'source' = 'rss_' || (report->>'channel_name')
  AND length(report->>'channel_name') BETWEEN 1 AND 255
  AND report->>'processing_mode' = 'publisher_metadata'
  AND report->>'classification_status' = 'not_requested'
  AND jsonb_typeof(report->'raw_text') = 'string'
  AND length(report->>'raw_text') <= 12000
  AND jsonb_typeof(report->'summary') = 'string' AND length(btrim(report->>'summary')) > 0
  AND jsonb_typeof(report->'source_url') = 'string'
  AND jsonb_typeof(report->'feed_context') = 'object'
  AND COALESCE(report->>'raw_text_truncated', 'false') = 'false'
"""

# Freeze this revision independently of application metadata. The fresh0001
# baseline intentionally creates current metadata; only this exact empty table
# is compatible with0006. Later model changes must get their own migration.
EXPECTED_COLUMNS = {
    "identity": ("VARCHAR(64)", False),
    "source_name": ("VARCHAR(255)", False),
    "due_at": ("TIMESTAMP WITH TIME ZONE", False),
    "next_attempt_at": ("TIMESTAMP WITH TIME ZONE", False),
    "attempts": ("INTEGER", False),
    "claim_token": ("VARCHAR(36)", True),
    "last_attempt_at": ("TIMESTAMP WITH TIME ZONE", True),
    "last_outcome": ("VARCHAR(40)", True),
    "last_error_type": ("VARCHAR(80)", True),
    "created_at": ("TIMESTAMP WITH TIME ZONE", False),
    "finished_at": ("TIMESTAMP WITH TIME ZONE", True),
}


def _validate_empty_table(bind):
    inspector = sa.inspect(bind)
    columns = inspector.get_columns("source_report_retries", schema="public")
    actual = {c["name"]: (c["type"].compile(dialect=bind.dialect), c["nullable"]) for c in columns}
    if actual != EXPECTED_COLUMNS or any(c.get("identity") or c.get("computed") for c in columns):
        raise RuntimeError("Unexpected RSS retry table definition")
    for column in columns:
        default = column.get("default")
        allowed = {"0", "'0'", "'0'::integer"} if column["name"] == "attempts" else {"now()"} if column["name"] == "created_at" else {None}
        if default not in allowed:
            raise RuntimeError("Unexpected RSS retry column default")
    if inspector.get_pk_constraint("source_report_retries", schema="public")["constrained_columns"] != ["identity"]:
        raise RuntimeError("Unexpected RSS retry primary key")
    keys = inspector.get_foreign_keys("source_report_retries", schema="public")
    if (len(keys) != 1 or keys[0]["constrained_columns"] != ["identity"]
        or keys[0]["referred_table"] != "source_reports" or keys[0]["referred_columns"] != ["identity"]
        or keys[0].get("referred_schema") not in {None, "public"} or keys[0].get("options")):
        raise RuntimeError("Unexpected RSS retry source relationship")
    indexes = inspector.get_indexes("source_report_retries", schema="public")
    if (len(indexes) != 1 or indexes[0]["name"] != "ix_source_retry_pending_due"
        or indexes[0]["column_names"] != ["source_name", "next_attempt_at", "identity"] or indexes[0]["unique"]
        or str(indexes[0].get("dialect_options", {}).get("postgresql_where", "")).strip("()") != "finished_at IS NULL"):
        raise RuntimeError("Unexpected RSS retry pending index")
    if inspector.get_unique_constraints("source_report_retries", schema="public") or inspector.get_check_constraints("source_report_retries", schema="public"):
        raise RuntimeError("Unexpected RSS retry constraints")
    if bind.execute(sa.text("SELECT count(*) FROM pg_trigger WHERE tgrelid='public.source_report_retries'::regclass AND NOT tgisinternal")).scalar_one():
        raise RuntimeError("Unexpected RSS retry trigger")
    if bind.execute(sa.text("SELECT count(*) FROM public.source_report_retries")).scalar_one():
        raise RuntimeError("Pre-existing RSS retry state requires explicit review")


def _create_table():
    op.create_table("source_report_retries",
        sa.Column("identity", sa.String(64), nullable=False, primary_key=True),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outcome", sa.String(40), nullable=True),
        sa.Column("last_error_type", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["identity"], ["public.source_reports.identity"]), schema="public")
    op.create_index("ix_source_retry_pending_due", "source_report_retries",
        ["source_name", "next_attempt_at", "identity"], unique=False,
        postgresql_where=sa.text("finished_at IS NULL"), schema="public")


def upgrade():
    bind = op.get_bind()
    if int(bind.execute(sa.text("SHOW server_version_num")).scalar_one()) < 160000:
        raise RuntimeError("RSS retry migration requires PostgreSQL input validation")
    # Status has an existing index. Cap inspected legacy candidates; a large or
    # unsupported archive needs a separately reviewed staged migration.
    candidates = bind.execute(sa.text("SELECT identity FROM public.source_reports WHERE status='future_source_time' LIMIT :limit"),
                              {"limit": MAX_LEGACY_FUTURE_RECEIPTS + 1}).fetchall()
    if len(candidates) > MAX_LEGACY_FUTURE_RECEIPTS:
        raise RuntimeError("Legacy future-receipt population requires staged review")
    inspector = sa.inspect(bind)
    if "source_report_retries" in inspector.get_table_names(schema="public"):
        _validate_empty_table(bind)
    else:
        _create_table()
    # Original source JSON/hash/time and status are never edited by this seed.
    # Invalid/naive clocks and model-mode/unknown source snapshots remain in the
    # ledger, quarantined, without speculative scheduling or forced casts.
    bind.execute(sa.text(SEED_SQL), {"clock_pattern": CLOCK_PATTERN})


def downgrade():
    raise RuntimeError("Retry evidence must be preserved; restore a verified backup instead.")

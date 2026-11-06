"""Separate durable bounded historical scans from the live Telegram cursor."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_telegram_history_jobs"
down_revision = "0003_geography_index"
branch_labels = None
depends_on = None


def upgrade():
    # Fresh0001 creates current modeled tables; existing0003 databases need them.
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names(schema="public"))
    names = {"telegram_backfill_jobs", "telegram_backfill_items"}
    if existing & names:
        #0001 uses current metadata on a fresh database. Only its exact empty
        # definitions are admissible here; unknown existing data is not adopted.
        from app.models import TelegramBackfillItem, TelegramBackfillJob
        if not names <= existing:
            raise RuntimeError("Partial historical schema requires explicit review")
        inspector = sa.inspect(bind)
        for table in (TelegramBackfillJob.__table__, TelegramBackfillItem.__table__):
            expected = {c.name: (c.type.compile(dialect=bind.dialect), c.nullable) for c in table.columns}
            actual = {c["name"]: (c["type"].compile(dialect=bind.dialect), c["nullable"])
                      for c in inspector.get_columns(table.name, schema="public")}
            if actual != expected or inspector.get_pk_constraint(table.name, schema="public")["constrained_columns"] != [c.name for c in table.primary_key.columns]:
                raise RuntimeError("Unexpected historical table definition")
            if bind.execute(sa.select(sa.func.count()).select_from(table)).scalar_one():
                raise RuntimeError("Existing historical rows require explicit migration review")
        foreign_keys = inspector.get_foreign_keys("telegram_backfill_items", schema="public")
        if len(foreign_keys) != 1 or foreign_keys[0]["constrained_columns"] != ["job_id"] or foreign_keys[0]["referred_table"] != "telegram_backfill_jobs" or foreign_keys[0]["referred_columns"] != ["id"]:
            raise RuntimeError("Unexpected historical receipt relationship")
        return
    if "telegram_backfill_jobs" not in existing:
        op.create_table("telegram_backfill_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("request_hash", sa.String(64), nullable=False),
            sa.Column("channel_name", sa.String(255), nullable=False),
            sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("max_messages", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("source_entity_id", sa.BigInteger(), nullable=True),
            sa.Column("upper_message_id", sa.BigInteger(), nullable=True),
            sa.Column("cursor_message_id", sa.BigInteger(), nullable=False),
            sa.Column("processed_messages", sa.Integer(), nullable=False),
            sa.Column("outcomes", postgresql.JSONB(), nullable=False),
            sa.Column("last_error_type", sa.String(80), nullable=True),
            sa.Column("blocked_message_id", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    if "telegram_backfill_items" not in existing:
        op.create_table("telegram_backfill_items",
            sa.Column("job_id", sa.String(36), sa.ForeignKey("telegram_backfill_jobs.id"), primary_key=True),
            sa.Column("message_id", sa.BigInteger(), primary_key=True),
            sa.Column("content_sha256", sa.String(64), nullable=False),
            sa.Column("source_report_identity", sa.String(64), nullable=True),
            sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
            sa.Column("outcome", sa.String(40), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    raise RuntimeError("Historical receipts must be preserved; restore a verified backup instead.")

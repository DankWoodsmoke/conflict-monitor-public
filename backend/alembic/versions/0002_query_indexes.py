"""Indexes for bounded history and source-identity reads."""
from alembic import op

revision = "0002_query_indexes"
down_revision = "0001_public_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_events_timestamp_id", "events", ["timestamp", "id"])
    op.create_index("ix_events_source_url", "events", ["source_url"])
    op.create_index("ix_events_type_timestamp", "events", ["event_type", "timestamp"])
    op.create_index("ix_source_reports_received_at", "source_reports", ["received_at"])


def downgrade():
    op.drop_index("ix_source_reports_received_at", table_name="source_reports")
    op.drop_index("ix_events_type_timestamp", table_name="events")
    op.drop_index("ix_events_source_url", table_name="events")
    op.drop_index("ix_events_timestamp_id", table_name="events")

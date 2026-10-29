"""Match the geography cast used by meter-distance report clustering."""
from alembic import op

revision = "0003_geography_index"
down_revision = "0002_query_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE INDEX ix_events_geography ON events USING GIST ((geometry::geography))")


def downgrade():
    op.drop_index("ix_events_geography", table_name="events")

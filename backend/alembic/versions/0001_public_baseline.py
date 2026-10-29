"""Fresh public baseline. Existing deployments require a reviewed migration."""
from alembic import op
import sqlalchemy as sa
from app.models import Base
revision = "0001_public_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # The stock PostGIS image adds tiger/topology to search_path. Those extension
    # tables do not make the application's public schema a legacy deployment.
    existing = set(sa.inspect(bind).get_table_names(schema="public")) - {"alembic_version", "spatial_ref_sys"}
    if existing:
        raise RuntimeError("This baseline is for an empty database. Review legacy migration before upgrading existing data.")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind=bind)


def downgrade():
    raise RuntimeError("Destructive downgrade is intentionally not automatic; restore a verified backup.")

"""Separate publication batches; preserve private evidence and reader isolation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_public_observations"
down_revision = "0006_rss_due_retries"
branch_labels = None
depends_on = None


def _table(bind, name, index):
    inspector = sa.inspect(bind)
    if name in inspector.get_table_names(schema="public"):
        # Fresh baseline creates current model metadata. Never adopt populated
        # or differently shaped tables from an unknown prior publication system.
        expected = {"id": ("VARCHAR(64)", False), "source": ("VARCHAR(50)", False),
                    "published_at": ("TIMESTAMP WITH TIME ZONE", False),
                    "status": ("VARCHAR(16)", False), "payload": ("JSONB", False)}
        columns = inspector.get_columns(name, schema="public")
        actual = {c["name"]: (c["type"].compile(dialect=bind.dialect), c["nullable"]) for c in columns}
        if (actual != expected or any(c.get("default") or c.get("identity") or c.get("computed") for c in columns)
                or inspector.get_pk_constraint(name, schema="public")["constrained_columns"] != ["id"]
                or inspector.get_foreign_keys(name, schema="public")
                or inspector.get_unique_constraints(name, schema="public")
                or inspector.get_check_constraints(name, schema="public")
                or bind.execute(sa.text(f"SELECT count(*) FROM public.{name}")).scalar_one()
                or bind.execute(sa.text("SELECT count(*) FROM pg_trigger WHERE tgrelid=CAST(:name AS regclass) AND NOT tgisinternal"), {"name": "public."+name}).scalar_one()):
            raise RuntimeError("Unexpected existing publication table requires review")
        indexes = inspector.get_indexes(name, schema="public")
        if len(indexes) != 1 or indexes[0]["name"] != index or indexes[0]["column_names"] != ["source", "published_at"] or indexes[0]["unique"]:
            raise RuntimeError("Unexpected publication index")
    else:
        op.create_table(name,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("source", sa.String(50), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("payload", postgresql.JSONB(), nullable=False), schema="public")
        op.create_index(index, name, ["source", "published_at"], schema="public")


def upgrade():
    bind = op.get_bind()
    _table(bind, "public_observation_batches", "ix_public_observation_source_time")
    _table(bind, "public_aircraft_batches", "ix_public_aircraft_source_time")
    op.execute("""CREATE FUNCTION public.reject_publication_update() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
        RAISE EXCEPTION 'Publication batches are immutable'; END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.reject_publication_update() FROM PUBLIC")
    op.execute("CREATE TRIGGER publication_immutable BEFORE UPDATE ON public.public_observation_batches FOR EACH ROW EXECUTE FUNCTION public.reject_publication_update()")
    op.execute("CREATE TRIGGER publication_immutable BEFORE UPDATE ON public.public_aircraft_batches FOR EACH ROW EXECUTE FUNCTION public.reject_publication_update()")


def downgrade():
    raise RuntimeError("Publication provenance must be preserved; restore a reviewed backup instead")

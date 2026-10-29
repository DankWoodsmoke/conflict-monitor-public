"""Baseline admission must inspect the application schema, not search_path."""
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
import pytest

path = Path(__file__).resolve().parents[1] / "alembic/versions/0001_public_baseline.py"
spec = importlib.util.spec_from_file_location("baseline_migration", path)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_fresh_postgis_admission_is_public_schema_only(monkeypatch):
    inspector = MagicMock()
    inspector.get_table_names.side_effect = lambda *, schema: ["spatial_ref_sys", "alembic_version"] if schema == "public" else ["edge", "addr"]
    monkeypatch.setattr(migration.sa, "inspect", lambda bind: inspector)
    operation = MagicMock()
    monkeypatch.setattr(migration, "op", operation)
    create = MagicMock()
    monkeypatch.setattr(migration.Base.metadata, "create_all", create)
    migration.upgrade()
    inspector.get_table_names.assert_called_once_with(schema="public")
    operation.execute.assert_called_once_with("CREATE EXTENSION IF NOT EXISTS postgis")
    create.assert_called_once()


def test_actual_public_legacy_table_still_refuses_admission(monkeypatch):
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["spatial_ref_sys", "events"]
    monkeypatch.setattr(migration.sa, "inspect", lambda bind: inspector)
    operation = MagicMock()
    monkeypatch.setattr(migration, "op", operation)
    with pytest.raises(RuntimeError, match="empty database"):
        migration.upgrade()
    operation.execute.assert_not_called()

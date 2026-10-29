import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("release_gate", Path(__file__).resolve().parents[2] / "tools/release_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.mark.parametrize("relative", ["backend/data/secret.db", "frontend/cert.p12",
    "backend/conflict_monitor.session-journal", "docs/.aws/credentials", "backend/.env.local"])
def test_unknown_private_content_cannot_enter_export(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    file = tmp_path / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("private fixture")
    with pytest.raises(ValueError):
        list(gate.export_files())


def test_credentials_are_detected_even_inside_binary_asset(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["release_gate.py", "--scan-only"])
    path = tmp_path / "frontend" / "public" / "picture.jpg"
    path.parent.mkdir(parents=True)
    credential = b"AIza" + b"A" * 35
    path.write_bytes(b"\xff\xd8fixture" + credential)
    assert gate.main() == 1
    output = capsys.readouterr().out
    assert "google_browser_key" in output
    assert credential.decode() not in output


def test_allowlist_does_not_export_backup_or_runtime_trees(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    for relative in ["README.md", "frontend/src/App.tsx", "frontend/node_modules/secret.js",
                     "backend/sessions/credential.session", "backup.tar.gz", ".env"]:
        p = tmp_path / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture")
    exported = {p.relative_to(tmp_path).as_posix() for p in gate.export_files()}
    assert exported == {"README.md", "frontend/src/App.tsx"}

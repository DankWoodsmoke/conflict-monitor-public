import importlib.util
import hashlib
import io
import json
import zipfile
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


def versioned_files(version="0.2.0-rc.2"):
    return {
        "frontend/package.json": json.dumps({"version": version}).encode(),
        "frontend/package-lock.json": json.dumps({"version": version, "packages": {"": {"version": version}}}).encode(),
        "backend/app/main.py": f'app = FastAPI(version="{version}")\n'.encode(),
    }


def test_release_archive_is_reproducible_and_manifest_matches_actual_bytes():
    files = versioned_files()
    manifest = [{"path": p, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()} for p, b in sorted(files.items())]
    version = gate.release_version(files)
    data = gate.candidate_archive(files, manifest, version)
    # Filesystem ordering differs across Windows/POSIX and must not change
    # manifest bytes between the reviewed Git tree and packaged download.
    assert data == gate.candidate_archive(dict(reversed(list(files.items()))), list(reversed(manifest)), version)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        receipt = json.loads(archive.read("conflict-monitor/RELEASE_MANIFEST.json"))
        assert receipt["version"] == version
        for row in receipt["files"]:
            actual = archive.read("conflict-monitor/" + row["path"])
            assert len(actual) == row["bytes"]
            assert hashlib.sha256(actual).hexdigest() == row["sha256"]


@pytest.mark.parametrize("changed", ["frontend/package-lock.json", "backend/app/main.py"])
def test_release_identity_mismatch_is_rejected(changed):
    files = versioned_files()
    files[changed] = files[changed].replace(b"rc.2", b"rc.1")
    with pytest.raises(ValueError, match="versions differ"):
        gate.release_version(files)


def test_release_version_cannot_escape_destination():
    with pytest.raises(ValueError, match="Invalid release version"):
        gate.release_version(versioned_files("../../escape"))


def test_version_comment_cannot_mask_an_old_running_api_version():
    files = versioned_files()
    files["backend/app/main.py"] = b'app = FastAPI(version="0.2.0-rc.1")\n# planned version="0.2.0-rc.2"\n'
    with pytest.raises(ValueError, match="versions differ"):
        gate.release_version(files)


def test_missing_release_identity_is_a_controlled_failure():
    with pytest.raises(ValueError, match="Missing required"):
        gate.release_version({"README.md": b"fixture"})


def test_release_packaging_never_overwrites_an_existing_version(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["release_gate.py", "--package-candidate"])
    for name, data in versioned_files().items():
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
    assert gate.main() == 0
    archive = tmp_path / "artifacts/conflict-monitor-0.2.0-rc.2-source.zip"
    original = archive.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        gate.main()
    assert archive.read_bytes() == original

"""Synthetic credentials only; verify source tests and quoting cannot bypass export."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location("adversarial_release_gate", Path(__file__).resolve().parents[2] / "tools/release_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.mark.parametrize("key,style", [
    ("TELEGRAM_SESSION", "quoted"),
    ("ADMIN_API_KEY", "quoted"),
    ("telegram_session", "json"),
    ("TELEGRAM_API_HASH", "plain"),
    ("AISSTREAM_API_KEY", "plain"),
    ("FIRMS_MAP_KEY", "plain"),
    ("TWITTER_BEARER_TOKEN", "plain"),
    ("OPENSKY_PASSWORD", "plain"),
])
def test_assignment_credentials_inside_tests_are_scanned(tmp_path, monkeypatch, capsys, key, style):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["release_gate.py", "--scan-only"])
    # Constructed synthetic value avoids embedding credential-shaped literals
    # in the public test source itself.
    credential = "7db2" * 16
    if style == "json":
        content = json.dumps({key: credential})
    elif style == "quoted":
        content = f'{key} = "{credential}"\n'
    else:
        content = f"{key}={credential}\n"
    path = tmp_path / "backend" / "tests" / "fixture.py"
    path.parent.mkdir(parents=True)
    path.write_text(content)
    assert gate.main() != 0
    assert credential not in capsys.readouterr().out


def test_database_uri_credentials_are_not_exported_from_documentation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["release_gate.py", "--scan-only"])
    password = "7db2" * 8
    path = tmp_path / "README.md"
    path.write_text("DATABASE_URL=postgresql+asyncpg://operator:" + password + "@database.example/conflicts\n")
    assert gate.main() != 0
    assert password not in capsys.readouterr().out


@pytest.mark.parametrize('key', ['POSTGRES_PASSWORD','POSTGRES_APP_PASSWORD','PGPASSWORD'])
def test_filled_database_password_example_blocks_export_without_echoing_value(tmp_path,monkeypatch,capsys,key):
    monkeypatch.setattr(gate,'ROOT',tmp_path)
    monkeypatch.setattr('sys.argv',['release_gate.py','--scan-only'])
    # Deterministic synthetic bytes, not an environment or a real credential.
    constructed='7db2'*16
    (tmp_path/'.env.example').write_text(key+'="'+constructed+'"\n')
    assert gate.main()!=0
    output=capsys.readouterr().out
    assert 'credential_assignment' in output and '.env.example' in output
    assert constructed not in output


@pytest.mark.parametrize('key', ['POSTGRES_PASSWORD','POSTGRES_APP_PASSWORD','PGPASSWORD'])
def test_database_password_placeholders_remain_reviewable_without_weakening_detection(key):
    placeholder=b'fixture-only-not-a-live-password'
    assert gate.content_findings(key.encode()+b'='+placeholder,'.env.example')==[]
    assert gate.content_findings(key.encode()+b'=','.env.example')==[]
    assert gate.content_findings(key.encode()+b'='+(b'7db2'*16),'.env.example')


def test_encrypted_private_key_in_source_text_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["release_gate.py", "--scan-only"])
    path = tmp_path / "README.md"
    path.write_text("-----BEGIN " + "ENCRYPTED PRIVATE KEY-----\nfixture\n")
    assert gate.main() != 0


def test_packaged_bytes_are_exactly_the_bytes_scanned_and_manifested(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["release_gate.py", "--package-candidate"])
    version = "0.2.0-rc.2"
    version_inputs = {
        "frontend/package.json": json.dumps({"version": version}),
        "frontend/package-lock.json": json.dumps({"version": version, "packages": {"": {"version": version}}}),
        "backend/app/main.py": f'app = FastAPI(version="{version}")\n',
    }
    for name, contents in version_inputs.items():
        version_file = tmp_path / name
        version_file.parent.mkdir(parents=True, exist_ok=True)
        version_file.write_text(contents, encoding="utf-8")
    path = tmp_path / "README.md"
    original = b"reviewed source bytes\n"
    path.write_bytes(original)
    real_write = zipfile.ZipFile.write
    def concurrent_edit(archive, filename, *args, **kwargs):
        # Simulates another editor touching a source after scan and before ZIP
        # re-read. A snapshot-based packager never invokes this unsafe path.
        Path(filename).write_bytes(b"unreviewed replacement\n")
        return real_write(archive, filename, *args, **kwargs)
    monkeypatch.setattr(gate.zipfile.ZipFile, "write", concurrent_edit)
    assert gate.main() == 0
    archives = list((tmp_path / "artifacts").glob("*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as archive:
        packed = archive.read("conflict-monitor/README.md")
        manifest = json.loads(archive.read("conflict-monitor/RELEASE_MANIFEST.json"))
    entry = next(item for item in manifest["files"] if item["path"] == "README.md")
    assert packed == original
    assert hashlib.sha256(packed).hexdigest() == entry["sha256"]


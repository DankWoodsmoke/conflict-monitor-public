"""Exercise bounded backup and real PostGIS restore on authored disposable data."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time

from database_backup import backup, bounded_capture, docker, restore_rehearsal, validate_archive


def verify(image: str) -> dict:
    rows = {}
    with tempfile.TemporaryDirectory(prefix="cm-backup-check-") as temporary:
        directory = Path(temporary)
        existing = directory / "existing.partial"
        existing.write_bytes(b"preserve existing file")
        try:
            bounded_capture([sys.executable,"-c","print('fixture')"],existing,1024,5)
            rows["existing_file_never_overwritten_or_deleted"] = False
        except FileExistsError:
            rows["existing_file_never_overwritten_or_deleted"] = existing.read_bytes() == b"preserve existing file"
        existing.unlink()
        for case, command, limit, seconds, expected in [
            ("byte_cap_aborts_and_removes_partial", [sys.executable,"-c","import sys;sys.stdout.buffer.write(b'x'*100000)"], 1024, 5, ValueError),
            ("wall_clock_cap_aborts_and_removes_partial", [sys.executable,"-c","import time;time.sleep(5)"], 1024, 0.1, TimeoutError),
        ]:
            target = directory / (case + ".partial")
            try:
                bounded_capture(command, target, limit, seconds)
                rows[case] = False
            except expected:
                rows[case] = not target.exists()
        source = "cm-backup-source-" + secrets.token_hex(6)
        try:
            docker("run","-d","--pull=never","--name",source,"--network=none","--memory=512m","--cpus=1","--pids-limit=128",
                   "--env","POSTGRES_USER=monitor_admin","--env","POSTGRES_DB=conflict_monitor",
                   "--env","POSTGRES_PASSWORD=" + secrets.token_hex(32),"--tmpfs","/var/lib/postgresql/data",image)
            for attempt in range(100):
                try:
                    docker("exec",source,"pg_isready","-h","127.0.0.1","-U","monitor_admin","-d","conflict_monitor",timeout=5)
                    break
                except RuntimeError:
                    if attempt == 99:
                        raise
                    time.sleep(0.25)
            sql = """CREATE EXTENSION IF NOT EXISTS postgis;
                CREATE TABLE backup_fixture (id integer PRIMARY KEY, label text NOT NULL, position geography(Point,4326));
                INSERT INTO backup_fixture VALUES (1,'synthetic restore fixture',ST_SetSRID(ST_Point(44.2,33.3),4326)),
                  (2,'authored Unicode: Ελληνικά',ST_SetSRID(ST_Point(-0.12,51.5),4326));"""
            docker("exec",source,"psql","-X","-v","ON_ERROR_STOP=1","-U","monitor_admin","-d","conflict_monitor","-c",sql)
            receipt = backup(source,directory,max_bytes=8*1024**2,max_total_bytes=64*1024**2)
            manifest = Path(receipt["manifest"])
            rows["backup_complete_custom_format"] = receipt["format"] == "postgresql-custom" and receipt["bytes"] > 0
            rows["no_source_repo_backup"] = directory.resolve() not in Path(__file__).resolve().parents
            restored = restore_rehearsal(manifest,image,timeout=120)
            rows["actual_postgis_restore_succeeds"] = restored["status"] == "PASS"
            rows["authored_rows_restored"] = restored["table_counts"].get("backup_fixture") == 2
            rows["postgis_spatial_reference_restored"] = restored["table_counts"].get("spatial_ref_sys",0) > 8000
            rows["restore_isolated_and_removed"] = restored["network"] == "none" and not restored["host_ports"] and restored["cleanup_verified"]
            try:
                backup(source,directory,max_backups=1)
                rows["retention_count_refuses_overflow"] = False
            except ValueError:
                rows["retention_count_refuses_overflow"] = True
            try:
                backup(source,directory,max_bytes=1024,max_total_bytes=1024)
                rows["directory_quota_refuses_overflow"] = False
            except ValueError:
                rows["directory_quota_refuses_overflow"] = True
            archive, details = validate_archive(manifest)
            original = archive.read_bytes()
            archive.write_bytes(original[:-1])
            try:
                restore_rehearsal(manifest,image)
                rows["truncated_backup_refused_before_container_creation"] = False
            except ValueError:
                rows["truncated_backup_refused_before_container_creation"] = True
            archive.write_bytes(original)
            details["sha256"] = "0"*64
            manifest.write_text(json.dumps(details),encoding="utf8")
            try:
                validate_archive(manifest)
                rows["checksum_mismatch_refused"] = False
            except ValueError:
                rows["checksum_mismatch_refused"] = True
            rows["lock_and_partial_files_clean"] = not list(directory.glob("*.partial")) and not (directory/".conflict-monitor-backup.lock").exists()
        finally:
            docker("rm","--force",source)
            rows["source_fixture_cleanup_verified"] = not docker("ps","-aq","--filter","name="+source)
        return {"checked_at":datetime.now(UTC).isoformat(),"status":"PASS" if all(rows.values()) else "FAIL",
                "checks":rows,"fixture_backup_bytes":receipt["bytes"],"database_image":restored["restore_image"],
                "tool_sha256":hashlib.sha256(Path(__file__).with_name("database_backup.py").read_bytes()).hexdigest(),
                "scope":"Authored two-row PostGIS fixture; no existing installation, database, environment or credentials used",
                "limitations":["Actual host backup destination, encrypted offsite copy and post-restore application roles remain unqualified."]}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=verify(args.image)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["status"]=="PASS" else 2)

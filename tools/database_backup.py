"""Bounded private pg_dump and isolated restore rehearsal; never restores a live DB."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import secrets
import subprocess
import threading
import time
from datetime import UTC, datetime

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def docker(*args: str, timeout: int = 30) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, timeout=timeout)
    if result.returncode:
        # Docker errors can include environment/connection strings. Do not echo them.
        raise RuntimeError("Docker operation failed; inspect its private diagnostics")
    return result.stdout.decode("utf8").strip()


def bounded_capture(command: list[str], target: Path, max_bytes: int, timeout: float) -> tuple[int, str]:
    """Drain binary stdout with bounded memory/disk and an independent wall-clock cap."""
    items: queue.Queue[bytes | None] = queue.Queue(maxsize=2)
    stopped = threading.Event()
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def pump() -> None:
        assert process.stdout is not None
        try:
            while not stopped.is_set():
                chunk = process.stdout.read(65536)
                while not stopped.is_set():
                    try:
                        items.put(chunk or None, timeout=0.1)
                        break
                    except queue.Full:
                        continue
                if not chunk:
                    break
        finally:
            process.stdout.close()

    worker = threading.Thread(target=pump, daemon=True)
    worker.start()
    deadline, size, digest = time.monotonic() + timeout, 0, hashlib.sha256()
    created = False
    try:
        with target.open("xb") as stream:
            created = True
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Backup exceeded its wall-clock limit")
                try:
                    chunk = items.get(timeout=min(remaining, 0.25))
                except queue.Empty:
                    continue
                if chunk is None:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Backup exceeded its byte limit")
                stream.write(chunk)
                digest.update(chunk)
            if process.wait(timeout=max(0.1, deadline - time.monotonic())) != 0:
                raise RuntimeError("pg_dump failed; no complete backup was admitted")
            stream.flush()
            os.fsync(stream.fileno())
        return size, digest.hexdigest()
    except BaseException:
        if created and target.exists():
            target.unlink()  # This function's exclusive-create partial file only.
        raise
    finally:
        stopped.set()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        worker.join(timeout=2)


def private_directory(path: Path) -> Path:
    path = path.resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError("Backups must be outside the export/source repository")
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup(container: str, destination: Path, *, database: str = "conflict_monitor", user: str = "monitor_admin",
           max_bytes: int = 256 * 1024 * 1024, max_total_bytes: int = 2 * 1024**3,
           max_backups: int = 7, timeout: int = 900) -> dict:
    if not IDENTIFIER.fullmatch(database) or not IDENTIFIER.fullmatch(user):
        raise ValueError("Database and user must be ordinary PostgreSQL identifiers")
    if min(max_bytes, max_total_bytes, max_backups, timeout) <= 0:
        raise ValueError("Every resource bound must be positive")
    directory = private_directory(destination)
    # Exclusive per-directory lock prevents two scheduled jobs from racing the quota.
    lock = directory / ".conflict-monitor-backup.lock"
    with lock.open("x", encoding="utf8") as stream:
        stream.write(str(os.getpid()))
    try:
        entries = [item for item in directory.iterdir() if item.is_file()]
        if sum(item.suffix == ".dump" for item in entries) >= max_backups:
            raise ValueError("Backup count cap reached; review retention/offsite copies before proceeding")
        used = sum(item.stat().st_size for item in entries)
        if used + max_bytes + 65536 > max_total_bytes:
            raise ValueError("Backup directory quota has insufficient reserved capacity")
        name = datetime.now(UTC).strftime("monitor-%Y%m%dT%H%M%SZ-") + secrets.token_hex(4)
        partial, final = directory / (name + ".partial"), directory / (name + ".dump")
        source_image = docker("inspect", "--format", "{{.Image}}", container)
        size, digest = bounded_capture([
            "docker", "exec", container, "timeout", "-s", "KILL", str(timeout), "pg_dump", "--format=custom", "--no-owner", "--no-acl",
            "--lock-wait-timeout=30s", "--username", user, "--dbname", database,
        ], partial, max_bytes, timeout)
        with partial.open("rb") as stream:
            signature = stream.read(5)
        if size < 5 or signature != b"PGDMP":
            partial.unlink()
            raise ValueError("pg_dump did not produce a custom-format archive")
        partial.replace(final)
        receipt = {"created_at": datetime.now(UTC).isoformat(), "format": "postgresql-custom",
                   "file": final.name, "bytes": size, "sha256": digest, "source_image": source_image,
                   "database": database, "ownership_acl_included": False, "restore_verified": False}
        manifest = directory / (name + ".json")
        manifest.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf8")
        return {**receipt, "manifest": str(manifest)}
    finally:
        lock.unlink()


def validate_archive(manifest: Path) -> tuple[Path, dict]:
    receipt = json.loads(manifest.read_text(encoding="utf8"))
    filename = receipt.get("file", "")
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".dump"):
        raise ValueError("Invalid backup filename")
    archive = manifest.parent / filename
    digest, size = hashlib.sha256(), 0
    with archive.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise ValueError("Not a PostgreSQL custom-format backup")
        stream.seek(0)
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
            size += len(chunk)
    if size != receipt.get("bytes") or digest.hexdigest() != receipt.get("sha256"):
        raise ValueError("Backup checksum or length mismatch; restore refused")
    return archive.resolve(), receipt


def restore_rehearsal(manifest: Path, image: str, *, timeout: int = 900) -> dict:
    archive, source = validate_archive(manifest.resolve())
    image_id = docker("image", "inspect", "--format", "{{.Id}}", image)
    # The image is resolved before use. It is never pulled or rebuilt by this tool.
    name = "cm-restore-" + secrets.token_hex(6)
    volume = name + "-data"
    created_volume = created_container = False
    try:
        docker("volume", "create", "--label", "conflict-monitor.restore-rehearsal=true", volume)
        created_volume = True
        docker("create", "--pull=never", "--name", name, "--network=none", "--memory=1g", "--cpus=1",
               "--pids-limit=128", "--security-opt=no-new-privileges:true", "--cap-drop=ALL",
               "--cap-add=CHOWN", "--cap-add=DAC_OVERRIDE", "--cap-add=FOWNER", "--cap-add=SETGID", "--cap-add=SETUID",
               "--read-only", "--tmpfs", "/tmp:mode=1777", "--tmpfs", "/var/run/postgresql:mode=3775",
               "--mount", f"type=volume,source={volume},target=/var/lib/postgresql/data",
               "--mount", f"type=bind,source={archive},target=/backup.dump,readonly",
               "--env", "POSTGRES_USER=monitor_admin", "--env", "POSTGRES_DB=restore_bootstrap",
               "--env", "POSTGRES_PASSWORD=" + secrets.token_hex(32), "--env", "PROJ_NETWORK=OFF", image_id)
        created_container = True
        docker("start", name)
        deadline = time.monotonic() + min(timeout, 90)
        while True:
            try:
                docker("exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "monitor_admin", "-d", "restore_bootstrap", timeout=5)
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Disposable restore database did not become ready")
                time.sleep(0.5)
        # Image initialization preinstalls PostGIS/Tiger schemas. A template0 DB
        # avoids hiding duplicate-schema failures or adding --clean to restore.
        docker("exec", name, "createdb", "--template=template0", "-U", "monitor_admin", "restore_check")
        docker("exec", name, "pg_restore", "--list", "/backup.dump", timeout=30)
        docker("exec", name, "pg_restore", "--no-owner", "--no-acl", "--exit-on-error", "--single-transaction",
               "-U", "monitor_admin", "-d", "restore_check", "/backup.dump", timeout=timeout)
        tables = json.loads(docker("exec", name, "psql", "-X", "-At", "-U", "monitor_admin", "-d", "restore_check",
                    "-c", "SELECT COALESCE(json_agg(tablename ORDER BY tablename),'[]') FROM pg_tables WHERE schemaname='public';"))
        counts = {}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            counts[table] = int(docker("exec", name, "psql", "-X", "-At", "-U", "monitor_admin", "-d", "restore_check",
                                      "-c", f"SELECT count(*) FROM public.{quoted};", timeout=timeout))
        return {"checked_at": datetime.now(UTC).isoformat(), "status": "PASS", "backup_sha256": source["sha256"],
                "restore_image": image_id, "table_counts": counts, "network": "none", "host_ports": [],
                "cleanup_verified": True, "permissions_requalified": False,
                "limitations": ["Structural restore only. Run current bootstrap and reader/writer privilege checks before admission.",
                                "This receipt does not prove offsite backup, recovery time or equality with a changing live source."]}
    finally:
        if created_container:
            docker("rm", "--force", name)
        if created_volume:
            docker("volume", "rm", volume)
        if docker("ps", "-aq", "--filter", "name=" + name) or docker("volume", "ls", "-q", "--filter", "name=" + volume):
            raise RuntimeError("Disposable restore cleanup was not verified")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("backup")
    make.add_argument("--container", required=True)
    make.add_argument("--directory", type=Path, required=True)
    make.add_argument("--max-bytes", type=int, default=256 * 1024**2)
    make.add_argument("--max-total-bytes", type=int, default=2 * 1024**3)
    make.add_argument("--max-backups", type=int, default=7)
    make.add_argument("--timeout", type=int, default=900)
    restore = commands.add_parser("restore-rehearsal")
    restore.add_argument("--manifest", type=Path, required=True)
    restore.add_argument("--image", required=True)
    restore.add_argument("--output", type=Path, required=True)
    restore.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.command == "backup":
        result = backup(args.container, args.directory, max_bytes=args.max_bytes, max_total_bytes=args.max_total_bytes,
                        max_backups=args.max_backups, timeout=args.timeout)
    else:
        result = restore_rehearsal(args.manifest, args.image, timeout=args.timeout)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

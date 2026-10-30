"""Read-only policy checks for a uniquely named shipped-profile CI project.

Never prints container environments, DSNs, host mount sources or credentials.
This tool performs no cleanup and cannot qualify an unrelated live project.
"""

import argparse
import hashlib
import ipaddress
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

BOOTSTRAP_FIELDS = (
    "POSTGRES_PASSWORD",
    "POSTGRES_ADMIN_PASSWORD",
    "POSTGRES_APP_PASSWORD",
    "PGPASSWORD",
    "MIGRATION_DATABASE_URL",
    "BOOTSTRAP_DATABASE_URL",
)
DISABLED_FLAGS = (
    "LIVE_INGESTION_ENABLED",
    "DEMO_MODE",
    "X_INGESTION_ENABLED",
    "ENABLE_LOCAL_AI",
    "ENABLE_SITREP_GENERATION",
    "ENABLE_VIDEO_GENERATION",
)


def qualification_project(value):
    if not re.fullmatch(r"cmonitor-ci-[a-z0-9][a-z0-9-]{0,48}", value):
        raise ValueError("Use a unique cmonitor-ci-* qualification project")
    return value


def process_fields(raw):
    return dict(line.split(":", 1) for line in raw.splitlines() if ":" in line)


def service_checks(service, inspection, process, project):
    config = inspection.get("Config", {})
    host = inspection.get("HostConfig", {})
    state = inspection.get("State", {})
    labels = config.get("Labels", {})
    environment = dict(
        value.split("=", 1) for value in config.get("Env", []) if "=" in value
    )
    checks = {
        "owned_project": labels.get("com.docker.compose.project") == project,
        "expected_service": labels.get("com.docker.compose.service") == service,
        "running_healthy": state.get("Running") is True
        and state.get("Health", {}).get("Status") == "healthy",
        "no_new_privileges_policy": "no-new-privileges:true"
        in host.get("SecurityOpt", []),
        "all_default_capabilities_dropped": "ALL" in host.get("CapDrop", []),
        "pid1_effective_capabilities_zero": process.get("CapEff", "").strip()
        == "0000000000000000",
        "pid1_no_new_privileges": process.get("NoNewPrivs", "").strip() == "1",
        "pid1_expected_uid": process.get("Uid", "").split()
        == [str({"frontend": 101, "backend": 10001, "db": 999}[service])] * 4,
        "not_privileged": host.get("Privileged") is False,
        "no_publish_all_ports": host.get("PublishAllPorts") is False,
    }
    bindings = host.get("PortBindings") or {}
    if service == "db":
        checks["no_database_published_ports"] = not any(bindings.values())
        checks["readonly_rootfs"] = host.get("ReadonlyRootfs") is True
        checks["isolated_test_database"] = (
            environment.get("POSTGRES_DB") == "conflict_monitor_test"
        )
        checks["proj_network_off"] = (
            environment.get("PROJ_NETWORK", "").upper() == "OFF"
        )
    else:
        published = [
            binding for values in bindings.values() for binding in values or []
        ]
        checks["loopback_only_published_ports"] = bool(published) and all(
            binding.get("HostIp")
            and ipaddress.ip_address(binding["HostIp"]).is_loopback
            for binding in published
        )
        checks["no_added_capabilities"] = not host.get("CapAdd")
    if service == "frontend":
        checks["readonly_rootfs"] = host.get("ReadonlyRootfs") is True
    if service == "backend":
        checks["bootstrap_environment_explicitly_blank"] = all(
            environment.get(key) == "" for key in BOOTSTRAP_FIELDS
        )
        checks["collectors_demo_and_models_explicitly_disabled"] = all(
            environment.get(key, "").lower() == "false" for key in DISABLED_FLAGS
        )
        parsed = urlsplit(environment.get("DATABASE_URL", ""))
        checks["restricted_test_dsn"] = (
            parsed.scheme == "postgresql+asyncpg"
            and parsed.username == "monitor"
            and parsed.hostname == "db"
            and parsed.path == "/conflict_monitor_test"
        )
    return checks


def command(args):
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def bounded(stream, budget):
        data = bytearray()
        while chunk := stream.read(8192):
            if len(data) + len(chunk) > budget:
                process.kill()
                raise ValueError("Container inspection exceeds metadata budget")
            data.extend(chunk)
        return bytes(data)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            stdout = pool.submit(bounded, process.stdout, 2_000_000)
            stderr = pool.submit(bounded, process.stderr, 200_000)
            try:
                process.wait(timeout=30)
                output = stdout.result(timeout=2)
                stderr.result(timeout=2)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
        if process.returncode:
            raise RuntimeError("Container inspection command failed")
        return output.decode("utf8")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def qualify(project, compose_file, override, environment_file):
    project = qualification_project(project)
    base = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(environment_file),
        "-f",
        str(compose_file),
        "-f",
        str(override),
    ]
    rows = []
    backend_identifier = None
    for service in ["frontend", "backend", "db"]:
        identifiers = command(base + ["ps", "-q", service]).split()
        if len(identifiers) != 1 or not re.fullmatch(
            r"[a-f0-9]{12,64}", identifiers[0]
        ):
            raise ValueError("Exactly one running qualification container is required")
        identifier = identifiers[0]
        inspection = json.loads(command(["docker", "inspect", identifier]))[0]
        process = process_fields(
            command(["docker", "exec", identifier, "cat", "/proc/1/status"])
        )
        checks = service_checks(service, inspection, process, project)
        rows.append(
            {"service": service, "image_id": inspection.get("Image"), "checks": checks}
        )
        if service == "backend":
            backend_identifier = identifier
    source_root = compose_file.resolve().parent / "backend"
    expected = {
        str(path.relative_to(source_root)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for directory in (source_root / "app", source_root / "alembic")
        for path in directory.rglob("*")
        if path.is_file() and path.suffix in {".py", ".mako"}
    }
    if not expected or backend_identifier is None:
        raise ValueError("The source and built-backend identity must be available")
    script = (
        "import hashlib,json;from pathlib import Path;root=Path('/app');"
        "print(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() "
        "for d in [root/'app',root/'alembic'] for p in d.rglob('*') "
        "if p.is_file() and p.suffix in {'.py','.mako'}}))"
    )
    actual = json.loads(
        command(["docker", "exec", backend_identifier, "python", "-c", script])
    )
    mismatches = sorted(
        key
        for key in expected.keys() | actual.keys()
        if expected.get(key) != actual.get(key)
    )
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "Actual PID1 and Docker boundary of an isolated shipped Compose qualification profile",
        "status": "PASS"
        if not mismatches and all(all(row["checks"].values()) for row in rows)
        else "FAIL",
        "services": rows,
        "packaged_application_source_binding": {
            "files": len(expected),
            "mismatches": mismatches,
            "all_bytes_equal": not mismatches,
        },
        "environment_values_exported": False,
        "mutations_or_cleanup_performed": False,
        "limits": [
            "Configuration/process observations are not proof of container escape resistance, a host audit or all future process behavior.",
            "Database entrypoint initialization capabilities are distinct from its observed nonroot PID1 effective capability set.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--override-file", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = qualify(
            args.project, args.compose_file, args.override_file, args.env_file
        )
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyError,
        IndexError,
        TypeError,
    ) as error:
        result = {"status": "FAIL/INCOMPLETE", "error_type": type(error).__name__}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)

import copy
import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


def load_tool(name):
    path = Path(__file__).resolve().parents[2] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


headers = load_tool("verify_http_headers")
boundary = load_tool("verify_container_boundary")


@pytest.mark.parametrize(
    "value",
    [
        "https://example.org",
        "http://127.0.0.1@example.org",
        "http://127.0.0.1?credential=fixture-only",
        "http://127.0.0.1/#fragment",
        "file:///tmp/a",
        "http://0.0.0.0",
        "http://[::]",
    ],
)
def test_http_qualification_never_contacts_nonloopback_or_credential_origins(value):
    with pytest.raises(ValueError):
        headers.local_origin(value)


@pytest.mark.parametrize(
    "value", ["cmonitor-live", "", "cmonitor-ci-../../live", "cmonitor-ci-$(command)"]
)
def test_container_qualification_rejects_unrelated_or_unsafe_project(value):
    with pytest.raises(ValueError):
        boundary.qualification_project(value)


def valid_backend():
    environment = {key: "" for key in boundary.BOOTSTRAP_FIELDS}
    environment.update({key: "false" for key in boundary.DISABLED_FLAGS})
    environment["DATABASE_URL"] = (
        "postgresql+asyncpg://monitor:fixture-only@db:5432/conflict_monitor_test"
    )
    inspection = {
        "Config": {
            "Labels": {
                "com.docker.compose.project": "cmonitor-ci-fixture",
                "com.docker.compose.service": "backend",
            },
            "Env": [f"{key}={value}" for key, value in environment.items()],
        },
        "State": {"Running": True, "Health": {"Status": "healthy"}},
        "HostConfig": {
            "SecurityOpt": ["no-new-privileges:true"],
            "CapDrop": ["ALL"],
            "Privileged": False,
            "PublishAllPorts": False,
            "PortBindings": {
                "8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "12345"}]
            },
        },
    }
    process = {
        "Uid": "10001 10001 10001 10001",
        "CapEff": "0000000000000000",
        "NoNewPrivs": "1",
    }
    return inspection, process


def test_actual_pid1_privilege_and_secret_regression_fail_without_printing_environment():
    inspection, process = valid_backend()
    assert all(
        boundary.service_checks(
            "backend", inspection, process, "cmonitor-ci-fixture"
        ).values()
    )
    changed = copy.deepcopy(inspection)
    changed["Config"]["Env"].append("POSTGRES_PASSWORD=fixture-not-for-http")
    checks = boundary.service_checks(
        "backend",
        changed,
        {**process, "Uid": "0 0 0 0", "CapEff": "0000000000000001", "NoNewPrivs": "0"},
        "cmonitor-ci-fixture",
    )
    assert checks["bootstrap_environment_explicitly_blank"] is False
    assert checks["pid1_expected_uid"] is False
    assert checks["pid1_effective_capabilities_zero"] is False
    assert checks["pid1_no_new_privileges"] is False
    assert "fixture-not-for-http" not in str(checks)


def test_wildcard_port_or_missing_health_cannot_be_reported_safe():
    inspection, process = valid_backend()
    inspection["HostConfig"]["PortBindings"]["8000/tcp"][0]["HostIp"] = "0.0.0.0"
    inspection["State"].pop("Health")
    checks = boundary.service_checks(
        "backend", inspection, process, "cmonitor-ci-fixture"
    )
    assert checks["loopback_only_published_ports"] is False
    assert checks["running_healthy"] is False


def test_database_rootfs_and_published_port_regression_fail():
    inspection, _ = valid_backend()
    inspection["Config"]["Labels"]["com.docker.compose.service"] = "db"
    inspection["Config"]["Env"] = [
        "POSTGRES_DB=conflict_monitor_test",
        "PROJ_NETWORK=OFF",
    ]
    inspection["HostConfig"]["ReadonlyRootfs"] = False
    checks = boundary.service_checks(
        "db",
        inspection,
        {"Uid": "999 999 999 999", "CapEff": "0000000000000000", "NoNewPrivs": "1"},
        "cmonitor-ci-fixture",
    )
    assert checks["readonly_rootfs"] is False
    assert checks["no_database_published_ports"] is False


def test_http_redirect_is_not_followed_and_body_bound_is_enforced():
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            self.send_response(302 if self.path == "/redirect" else 200)
            if self.path == "/redirect":
                self.send_header("Location", "/must-not-fetch")
            self.end_headers()
            if self.path == "/large":
                self.wfile.write(b"x" * (headers.MAX_BODY + 1))

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        assert headers.fetch(origin, "/redirect")[0] == 302
        assert paths == ["/redirect"]
        with pytest.raises(ValueError, match="body bound"):
            headers.fetch(origin, "/large")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_inspection_output_flood_is_bounded_and_child_is_reaped():
    with pytest.raises(ValueError, match="metadata budget"):
        boundary.command(
            [sys.executable, "-c", "import os; os.write(1, b'x' * 2100000)"]
        )

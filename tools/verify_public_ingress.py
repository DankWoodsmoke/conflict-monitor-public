"""Qualify real nginx public ingress with a disposable, offline echo backend.

No application database, .env, provider, live container or externally bound port
is used. Images must already exist locally. Outputs contain flags, not headers.
This qualifies the HTTP boundary, not source rights or backend authorization.
"""

import argparse
import concurrent.futures
import gzip
import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64, hashlib, json, socket
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args): pass
    def do_GET(self):
        proof = {"path": self.path, "method": self.command,
                 "headers": sorted(k.lower() for k in self.headers),
                 "body_length": int(self.headers.get("Content-Length", "0"))}
        if self.path == "/ws/events":
            key = self.headers.get("Sec-WebSocket-Key", "")
            accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.send_header("X-Fixture-Credentials", str(any(k in proof["headers"] for k in ["authorization", "cookie", "x-admin-key"])).lower())
            self.send_header("X-Fixture-Origin", str("origin" in proof["headers"]).lower())
            self.end_headers()
            self.wfile.flush()
            self.connection.settimeout(15)
            try: self.connection.recv(1024)
            except (OSError, socket.timeout): pass
            self.close_connection = True
            return
        if self.path == "/publication/observations":
            proof["fixture_observations"] = [{"id":i,"kind":"thermal observation","not_a_strike":True} for i in range(80)]
        data = json.dumps(proof).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Set-Cookie", "fixture=not-public")
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(data)
    do_HEAD = do_GET
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
'''


def docker(*args, check=True, env=None):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60, env=env)
    if check and result.returncode:
        # Do not echo arbitrary container output (could include configuration).
        raise RuntimeError(f"Docker operation {args[0]} failed")
    return result.stdout.strip()


def request(port, path, method="GET", headers=None, body=None):
    connection = http.client.HTTPConnection("frontend", port, timeout=10)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Fixture response exceeded limit")
        return response.status, dict(response.getheaders()), data
    finally:
        connection.close()


def websocket(port):
    connection = socket.create_connection(("frontend", port), timeout=10)
    connection.sendall((
        f"GET /api/ws/events HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        f"Origin: http://127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
        "Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\nAuthorization: fixture-only\r\n"
        "Cookie: fixture-only\r\nX-Admin-Key: fixture-only\r\n\r\n"
    ).encode())
    response = bytearray()
    while b"\r\n\r\n" not in response:
        packet = connection.recv(4096)
        if not packet or len(response) + len(packet) > 16_384:
            connection.close()
            raise ValueError("Invalid fixture handshake")
        response.extend(packet)
    head = bytes(response).split(b"\r\n\r\n", 1)[0].decode("ascii")
    status = int(head.split(" ", 2)[1])
    headers = {line.split(":", 1)[0].lower(): line.split(":", 1)[1].strip()
               for line in head.split("\r\n")[1:]}
    return connection, status, headers


def check_boundary(port=80):
    rows, sockets = [], []

    def record(name, passed, **facts):
        rows.append({"case": name, "passed": bool(passed), **facts})

    def security_headers(headers):
        return (headers.get("X-Content-Type-Options") == "nosniff"
                and headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
                and headers.get("X-Frame-Options") == "SAMEORIGIN")

    try:
        for _ in range(40):
            try:
                status, _, _ = request(port, "/")
                if status == 200:
                    break
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("Fixture nginx startup failed")
        status, headers, html = request(port, "/")
        record("html_no_store_security_headers", status == 200 and security_headers(headers)
               and headers.get("Cache-Control") == "no-store")
        asset = re.search(rb'src="(/assets/[A-Za-z0-9_-]+\.js)"', html)
        if not asset:
            raise ValueError("Built HTML must declare a hashed local script")
        status, headers, _ = request(port, asset.group(1).decode("ascii"), method="HEAD")
        record("hashed_asset_success_immutable_security_headers", status == 200 and security_headers(headers)
               and headers.get("Cache-Control") == "public, max-age=31536000, immutable")
        style = re.search(rb'href="(/assets/[A-Za-z0-9_-]+\.css)"', html)
        if not style:
            raise ValueError("Built HTML must declare a hashed local stylesheet")
        for label, path, cache in [
            ("built_javascript", asset.group(1).decode("ascii"), "public, max-age=31536000, immutable"),
            ("built_css", style.group(1).decode("ascii"), "public, max-age=31536000, immutable"),
            ("public_json", "/api/publication/observations", "no-store"),
            ("svg", "/assets/compressionFixture-hash1234.svg", "no-store"),
            ("wasm", "/assets/compressionFixture-hash1234.wasm", "no-store"),
        ]:
            status, identity_headers, identity = request(port, path, headers={"Accept-Encoding":"identity"})
            compressed_status, compressed_headers, compressed = request(port, path, headers={"Accept-Encoding":"gzip"})
            compressed_ok = compressed_headers.get("Content-Encoding") == "gzip"
            record("gzip_exact_roundtrip:"+label, status == compressed_status == 200 and compressed_ok
                   and gzip.decompress(compressed) == identity and len(compressed) < len(identity),
                   identity_bytes=len(identity), compressed_bytes=len(compressed),
                   decoded_sha256=hashlib.sha256(identity).hexdigest())
            record("gzip_cache_security_and_vary:"+label, security_headers(compressed_headers)
                   and compressed_headers.get("Cache-Control") == identity_headers.get("Cache-Control") == cache
                   and "Accept-Encoding" in compressed_headers.get("Vary", "")
                   and "Set-Cookie" not in compressed_headers)
        status, headers, body=request(port,"/",headers={"Accept-Encoding":"gzip"})
        decoded=gzip.decompress(body) if headers.get("Content-Encoding")=="gzip" else body
        record("html_markup_cache_and_security_unchanged",status==200 and decoded==html
               and security_headers(headers) and headers.get("Cache-Control")=="no-store")
        for extension in ["png", "jpg", "mp4", "mp3"]:
            path="/assets/compressionFixture-hash1234."+extension
            status, headers, body=request(port,path,headers={"Accept-Encoding":"gzip"})
            record("compressed_media_excluded:"+extension,status==200 and "Content-Encoding" not in headers and len(body)>1024)
        status, headers, body=request(port,"/assets/smallFixture-hash1234.js",headers={"Accept-Encoding":"gzip"})
        record("gzip_small_responses_skipped",status==200 and "Content-Encoding" not in headers and len(body)<1024)
        status, headers, _ = request(port, "/assets/missing-fixtureHash.js")
        record("hashed_asset_missing_not_immutable", status == 404 and security_headers(headers)
               and headers.get("Cache-Control") == "no-store")
        batch_hash = "a" * 64
        allowed = ["/health", "/config", "/status", "/publication/observations",
                   "/publication/observations/download", "/publication/observations/download/" + batch_hash,
                   "/publication/aircraft", "/publication/aircraft/download/" + batch_hash]
        for path in allowed:
            status, headers, data = request(port, "/api" + path)
            record("allowed:" + path.split("?")[0], status == 200 and json.loads(data)["path"] == path
                       and security_headers(headers) and "no-store" in headers.get("Cache-Control", ""), status=status)
        status, _, data = request(port, "/api/health", method="HEAD")
        record("head_allowed_without_body", status == 200 and not data, status=status)
        headers = {"Authorization": "fixture-only", "X-Admin-Key": "fixture-only",
                   "Cookie": "fixture-only", "X-Forwarded-For": "198.51.100.1",
                   "X-Real-IP": "198.51.100.1", "X-HTTP-Method-Override": "POST"}
        status, response_headers, data = request(port, "/api/config", headers=headers, body=b"fixture-only")
        proof = json.loads(data)
        record("credentials_forwarding_and_body_removed", status == 200 and proof["body_length"] == 0
               and not (set(k.lower() for k in headers) & set(proof["headers"]))
               and "Set-Cookie" not in response_headers)
        denied = ["/api", "/api/", "/API/health", "/api/costs/summary", "/api/market", "/api/config/",
                  "/api/sitreps/latest", "/api/sitreps/1/events", "/api/briefing/status",
                  "/api/briefing/reports", "/api/report-analysis/1", "/api/report-analysis/jobs/fixture",
                  "/api/events/admin/ingestion", "/api/events/admin/geo-stats", "/api/events/1/imagery",
                  "/api/media/intel", "/api/docs", "/api/openapi.json", "/api/unknown", "/videos/manifest.json",
                  "/api//health", "/api/%68ealth", "/api/events/../health", "/api/events/%2e%2e/health",
                  "/api%2fhealth", "/api/health/", "/api/health;ignored", "/api/health.json",
                  "/assets/../api/health", "/api\\health", "/.env",
                  "/api/events", "/api/events/anomalies", "/api/events/batch", "/api/events/time-range",
                  "/api/events/delivery/baseline", "/api/events/delivery/changes", "/api/events/42",
                  "/api/events/42/location-candidates", "/api/tracking/aircraft", "/api/tracking/vessels",
                  "/api/tracking/snapshots", "/api/tracking/jamming", "/api/tracking/tle", "/api/satellite/hotspots",
                  "/api/publication/unknown", "/api/publication/observations?limit=1",
                  "/api/publication/aircraft?source=private", "/api/publication/aircraft/download",
                  "/api/publication/aircraft/download/" + "A" * 64,
                  "/api/publication/observations/download/" + "a" * 65]
        for path in denied:
            status, headers, _ = request(port, path)
            record("denied:" + path, status in (400, 404) and security_headers(headers)
                   and "no-store" in headers.get("Cache-Control", ""), status=status)
        for method in ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"]:
            status, _, _ = request(port, "/api/config", method=method)
            record("method_denied:" + method, status in (400, 405), status=status)
        status, _, _ = request(port, "/api/ws/events")
        record("private_websocket_get_denied", status == 404, status=status)
        status, _, _ = request(port, "/api/ws/events", method="HEAD")
        record("private_websocket_head_denied", status == 404, status=status)
        connection, status, _ = websocket(port)
        sockets.append(connection)
        record("private_websocket_upgrade_denied", status == 404, status=status)
        status, _, _ = request(port, "/api/publication/observations/download")
        record("download_separate_request_limit", status == 429, status=status)
        with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
            statuses = list(pool.map(lambda _: request(port, "/api/health")[0], range(80)))
        record("api_request_limit", 429 in statuses and set(statuses) <= {200, 429},
               accepted=statuses.count(200), throttled=statuses.count(429))
        return rows
    finally:
        for connection in sockets:
            connection.close()


def check_compose(temp):
    fixture_env = Path(temp) / "fixture.env"
    fixture_env.write_text(
        "LIVE_INGESTION_ENABLED=true\nDEMO_MODE=true\nENABLE_LOCAL_AI=true\n"
        "ENABLE_VIDEO_GENERATION=true\nENABLE_SITREP_GENERATION=true\n"
        "PRIVATE_CUSTOM_MODEL_API_TOKEN=fixture-only-private-canary\n"
        "ANTHROPIC_API_KEY=fixture-only-provider-secret\n"
        "TELEGRAM_SESSION=fixture-only-private-session\n"
        "GOOGLE_EARTH_ENABLED=true\nGOOGLE_MAPS_BROWSER_KEY=fixture-only-public-browser-key\n"
        "CORS_ORIGINS=https://public.example.invalid\nCONFLICT_START_DATE=2026-03-01\n",
        encoding="utf8")
    env = {**os.environ, "CONFLICT_ENV_FILE": str(fixture_env),
           "POSTGRES_PASSWORD": "fixture-admin-bootstrap-only", "POSTGRES_APP_PASSWORD": "f" * 64,
           "POSTGRES_PUBLIC_PASSWORD": "e" * 64,
           "PUBLIC_REPORTS_ENABLED": "false", "PUBLIC_TRACKING_ENABLED": "false",
           "GOOGLE_EARTH_ENABLED": "true", "GOOGLE_MAPS_BROWSER_KEY": "fixture-only-public-browser-key",
           "CORS_ORIGINS": "https://public.example.invalid", "CONFLICT_START_DATE": "2026-03-01"}
    args = ["compose", "--env-file", str(fixture_env), "-f", str(ROOT / "docker-compose.yml")]
    original = json.loads(docker(*args, "config", "--format", "json", env=env))["services"]
    public = json.loads(docker(*args, "-f", str(ROOT / "compose.public.yml"),
                               "config", "--format", "json", env=env))["services"]
    policy = public["backend"]["environment"]
    public_unresolved = json.loads(docker(*args, "-f", str(ROOT / "compose.public.yml"),
        "config", "--no-env-resolution", "--format", "json", env=env))["services"]["backend"]
    secret_names = {"ANTHROPIC_API_KEY", "ADMIN_API_KEY", "TELEGRAM_API_HASH", "TELEGRAM_PHONE",
                    "TELEGRAM_SESSION", "TELEGRAM_BOT_TOKEN", "OPENSKY_USERNAME", "OPENSKY_PASSWORD",
                    "AISSTREAM_API_KEY", "FIRMS_MAP_KEY", "TWITTER_BEARER_TOKEN", "TWITTER_AUTH_TOKEN",
                    "TWITTER_CT0", "POSTGRES_PASSWORD", "POSTGRES_ADMIN_PASSWORD", "POSTGRES_APP_PASSWORD",
                    "PGPASSWORD", "MIGRATION_DATABASE_URL", "BOOTSTRAP_DATABASE_URL", "POSTGRES_PUBLIC_PASSWORD"}
    missing_reader_env = {key: value for key, value in env.items() if key != "POSTGRES_PUBLIC_PASSWORD"}
    missing_reader = subprocess.run(["docker", *args, "-f", str(ROOT / "compose.public.yml"),
        "config", "--quiet"], capture_output=True, text=True, timeout=60, env=missing_reader_env)
    checks = {
        "compose_original_backend_stays_loopback": all(p["host_ip"] == "127.0.0.1" for p in original["backend"]["ports"]),
        "compose_original_nginx_stays_default": "NGINX_CONFIG" not in original["frontend"]["build"].get("args", {}),
        "compose_public_backend_not_published": not public["backend"].get("ports"),
        "compose_public_frontend_loopback": bool(public["frontend"].get("ports")) and all(p["host_ip"] == "127.0.0.1" for p in public["frontend"]["ports"]),
        "compose_public_nginx_selected": public["frontend"]["build"]["args"]["NGINX_CONFIG"] == "nginx-public.conf",
        "compose_public_api_read_only": policy["PUBLIC_READ_ONLY"] == "true",
        "compose_public_data_default_closed": policy["PUBLIC_REPORTS_ENABLED"] == policy["PUBLIC_TRACKING_ENABLED"] == "false",
        "compose_public_collection_disabled": policy["LIVE_INGESTION_ENABLED"] == "false",
        "compose_private_canary_present_in_operator_only": original["backend"]["environment"].get("PRIVATE_CUSTOM_MODEL_API_TOKEN") == "fixture-only-private-canary"
            and "PRIVATE_CUSTOM_MODEL_API_TOKEN" not in policy,
        "compose_public_env_file_removed": not public_unresolved.get("env_file"),
        "compose_public_private_credentials_empty": all(policy.get(name) == "" for name in secret_names),
        "compose_public_generation_and_demo_disabled": all(policy.get(name) == "false" for name in
            ["DEMO_MODE", "X_INGESTION_ENABLED", "ENABLE_LOCAL_AI", "ENABLE_VIDEO_GENERATION", "ENABLE_SITREP_GENERATION"]),
        "compose_public_model_endpoints_empty": all(policy.get(name) == "" for name in
            ["LOCAL_AI_URL", "LOCAL_AI_MODEL", "PIPER_MODEL_PATH", "NOMINATIM_URL", "SENTINEL_HUB_INSTANCE_ID"]),
        "compose_public_telegram_disabled": policy.get("TELEGRAM_TRANSPORT") == "disabled" and policy.get("TELEGRAM_API_ID") == "0",
        "compose_public_root_read_only": public["backend"].get("read_only") is True,
        "compose_public_private_volumes_removed": not public["backend"].get("volumes"),
        "compose_public_tmp_bounded": public["backend"].get("tmpfs") == ["/tmp:rw,noexec,nosuid,size=64m,mode=1777"],
        "compose_public_no_bytecode_writes": policy.get("PYTHONDONTWRITEBYTECODE") == "1" and policy.get("HOME") == "/tmp",
        "compose_public_google_browser_input_preserved": policy.get("GOOGLE_EARTH_ENABLED") == "true"
            and policy.get("GOOGLE_MAPS_BROWSER_KEY") == "fixture-only-public-browser-key",
        "compose_public_cors_and_start_input_preserved": policy.get("CORS_ORIGINS") == "https://public.example.invalid"
            and policy.get("CONFLICT_START_DATE") == "2026-03-01",
        "compose_public_reader_dsn_separate": policy.get("DATABASE_URL") ==
            "postgresql+asyncpg://monitor_public:" + env["POSTGRES_PUBLIC_PASSWORD"] + "@db:5432/conflict_monitor"
            and original["backend"]["environment"].get("DATABASE_URL") ==
            "postgresql+asyncpg://monitor:" + env["POSTGRES_APP_PASSWORD"] + "@db:5432/conflict_monitor",
        "compose_public_reader_password_required": missing_reader.returncode != 0,
        "compose_public_reader_secret_bootstrap_only": public["migrate"]["environment"].get("POSTGRES_PUBLIC_PASSWORD") == env["POSTGRES_PUBLIC_PASSWORD"]
            and "POSTGRES_PUBLIC_PASSWORD" not in original["migrate"]["environment"],
        "compose_public_bootstrap_requires_reader_mode": public["migrate"]["environment"].get("PUBLIC_READ_ONLY") == "true"
            and "PUBLIC_READ_ONLY" not in original["migrate"]["environment"],
        "compose_public_no_writer_admin_secret": not any(secret in str(value) for secret in
            [env["POSTGRES_PASSWORD"], env["POSTGRES_APP_PASSWORD"]] for value in policy.values()),
        "compose_operator_filesystem_unchanged": not original["backend"].get("read_only")
            and bool(original["backend"].get("volumes")),
    }
    return [{"case": name, "passed": passed} for name, passed in checks.items()]


def qualify(frontend_image, backend_image):
    token = uuid.uuid4().hex[:12]
    network, frontend, backend = (f"cm-public-fixture-{token}-{x}" for x in ("net", "front", "back"))
    with tempfile.TemporaryDirectory(prefix="cm-public-fixture-") as temp:
        fixture = Path(temp) / "fixture.py"
        fixture.write_text(FIXTURE, encoding="utf8")
        fixture_assets = []
        for suffix, payload in {
            "svg": '<svg xmlns="http://www.w3.org/2000/svg"><desc>' + "offline fixture "*150 + '</desc></svg>',
            "wasm": b'\x00asm\x01\x00\x00\x00' + b'offline fixture '*150,
            # MIME fixtures verify transfer encoding only, not media decoders.
            "png": b'offline PNG MIME fixture '*150, "jpg": b'offline JPEG MIME fixture '*150,
            "mp4": b'offline MP4 MIME fixture '*150, "mp3": b'offline MP3 MIME fixture '*150,
        }.items():
            asset=Path(temp)/("compressionFixture-hash1234."+suffix)
            asset.write_bytes(payload.encode() if isinstance(payload,str) else payload)
            fixture_assets += ["--mount",f"type=bind,src={asset},dst=/usr/share/nginx/html/assets/{asset.name},readonly"]
        small=Path(temp)/"smallFixture-hash1234.js"
        small.write_bytes(b"/* authored small fixture */\n")
        fixture_assets += ["--mount",f"type=bind,src={small},dst=/usr/share/nginx/html/assets/{small.name},readonly"]
        try:
            rows = check_compose(temp)
            images = {name: docker("image", "inspect", image, "--format", "{{.Id}}")
                      for name, image in [("frontend", frontend_image), ("backend", backend_image)]}
            docker("network", "create", "--internal", network)
            docker("run", "-d", "--pull=never", "--name", backend, "--network", network,
                   "--network-alias", "backend", "--read-only", "--cap-drop=ALL",
                   "--security-opt", "no-new-privileges:true", "--pids-limit", "64",
                   "--memory", "128m", "--cpus", "1", "--entrypoint", "python",
                   "--mount", f"type=bind,src={fixture},dst=/tmp/fixture.py,readonly",
                   "--mount", f"type=bind,src={Path(__file__).resolve()},dst=/tmp/verifier.py,readonly",
                   backend_image, "-B", "/tmp/fixture.py")
            docker("run", "-d", "--pull=never", "--name", frontend, "--network", network,
                   "--network-alias", "frontend", "--read-only", "--user", "101:101", "--cap-drop=ALL",
                   "--security-opt", "no-new-privileges:true", "--pids-limit", "128",
                   "--memory", "256m", "--cpus", "1", "--tmpfs", "/var/cache/nginx:uid=101,gid=101",
                   "--tmpfs", "/var/run:uid=101,gid=101",
                   "--mount", f"type=bind,src={ROOT / 'frontend/nginx-public.conf'},dst=/etc/nginx/conf.d/default.conf,readonly",
                   *fixture_assets, frontend_image)
            docker("exec", frontend, "nginx", "-t")
            rows.extend(json.loads(docker("exec", backend, "python", "-B", "-c",
                "import runpy,json; m=runpy.run_path('/tmp/verifier.py'); print(json.dumps(m['check_boundary']()))")))
            return {"checked_at": datetime.now(UTC).isoformat(), "status": "PASS" if all(r["passed"] for r in rows) else "FAIL",
                    "scope": "Real nginx public config, offline disposable backend, exact publication paths, private API/WS denial, methods/credentials/rate bounds",
                    "nginx_config_sha256": hashlib.sha256((ROOT / "frontend/nginx-public.conf").read_bytes()).hexdigest(),
                    "images": images, "cases": rows, "provider_requests": 0,
                    "fixture_cleanup_verified": True,
                    "limitations": ["No public deployment, TLS/CDN, visitor identity behind a proxy, provider rights, or real API data qualification.",
                                    "API/download concurrency and bandwidth are bounded in config but not separately load-qualified here."]}
        finally:
            for container in [frontend, backend]:
                docker("rm", "--force", container, check=False)
            docker("network", "rm", network, check=False)
            if docker("ps", "-aq", "--filter", f"name=cm-public-fixture-{token}-") or docker(
                    "network", "ls", "-q", "--filter", f"name={network}"):
                raise RuntimeError("Fixture cleanup incomplete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-image", required=True)
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = qualify(args.frontend_image, args.backend_image)
    except (OSError, ValueError, RuntimeError, http.client.HTTPException, subprocess.TimeoutExpired) as error:
        result = {"status": "FAIL/INCOMPLETE", "error_type": type(error).__name__}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)

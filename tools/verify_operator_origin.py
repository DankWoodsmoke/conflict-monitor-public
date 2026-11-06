"""Actual nginx + shipped WS-router regression for custom-port same-origin use.

Uses no host ports, .env, database or provider calls. The legacy config is tested
as a negative control. Isolated fixtures are removed and cleanup is verified.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from verify_public_ingress import docker

ROOT = Path(__file__).resolve().parents[1]
SERVER = '''
from fastapi import FastAPI, Request
from app.routes.ws import router
import uvicorn
app = FastAPI()
app.include_router(router)
@app.get("/origin-proof")
async def proof(request: Request):
    return {"host_preserved": request.headers.get("host") == "fixture.example.invalid:41073",
            "origin_preserved": request.headers.get("origin") == "http://fixture.example.invalid:41073"}
uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False, log_level="warning")
'''
CLIENT = r'''
import http.client, json, socket, time
HOST = "fixture.example.invalid:41073"
ORIGIN = "http://" + HOST
def get(target):
    for attempt in range(30):
        try:
            conn=http.client.HTTPConnection(target,80,timeout=5)
            conn.request("GET","/api/origin-proof",headers={"Host":HOST,"Origin":ORIGIN})
            response=conn.getresponse()
            data=response.read(4096)
            conn.close()
            if response.status==200:return json.loads(data)
        except (OSError,http.client.HTTPException): pass
        time.sleep(.1)
    raise RuntimeError("Fixture unavailable")
def ws(target,origin):
    connection=socket.create_connection((target,80),timeout=5)
    try:
        connection.sendall((f"GET /api/ws/events HTTP/1.1\r\nHost: {HOST}\r\nOrigin: {origin}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        response=bytearray()
        while b"\r\n\r\n" not in response:
            packet=connection.recv(4096)
            if not packet or len(response)+len(packet)>16384:raise RuntimeError("Bad handshake")
            response.extend(packet)
        return int(response.split(b" ",2)[1])
    finally:connection.close()
old=get("legacy")
new=get("fixed")
checks={"legacy_control_drops_custom_port":not old["host_preserved"] and old["origin_preserved"],
        "legacy_same_origin_ws_rejected":ws("legacy",ORIGIN)==403,
        "fixed_host_and_origin_preserved":new["host_preserved"] and new["origin_preserved"],
        "fixed_custom_port_same_origin_ws_accepted":ws("fixed",ORIGIN)==101,
        "cross_origin_ws_rejected":ws("fixed","http://other.example.invalid:41073")==403,
        "wrong_origin_port_rejected":ws("fixed","http://fixture.example.invalid:41074")==403,
        "origin_credentials_rejected":ws("fixed","http://fixture-user:fixture-password@"+HOST)==403,
        "origin_with_path_rejected":ws("fixed",ORIGIN+"/unexpected")==403}
print(json.dumps([{"case":name,"passed":passed} for name,passed in checks.items()]))
'''


def qualify(frontend_image, backend_image):
    prefix = "cm-origin-fixture-" + uuid.uuid4().hex[:12]
    network, backend, legacy, fixed = [prefix + "-" + name for name in ("net", "back", "legacy", "fixed")]
    with tempfile.TemporaryDirectory(prefix="cm-origin-fixture-") as temp:
        temp = Path(temp)
        fixture = temp / "server.py"
        fixture.write_text(SERVER, encoding="utf8")
        config = (ROOT / "frontend/nginx.conf").read_text(encoding="utf8")
        if config.count("proxy_set_header Host $http_host;") != 1:
            raise ValueError("Expected the explicit corrected Host directive")
        legacy_config = temp / "legacy.conf"
        legacy_config.write_text(config.replace("proxy_set_header Host $http_host;", "proxy_set_header Host $host;"), encoding="utf8")
        try:
            images = {label: docker("image", "inspect", image, "--format", "{{.Id}}")
                      for label,image in [("frontend", frontend_image),("backend", backend_image)]}
            docker("network", "create", "--internal", network)
            docker("run", "-d", "--pull=never", "--name", backend, "--network", network,
                   "--network-alias", "backend", "--read-only", "--cap-drop=ALL",
                   "--security-opt", "no-new-privileges:true", "--pids-limit", "64", "--memory", "192m",
                   "--entrypoint", "python", "-e", "PYTHONPATH=/app", "-e", "PUBLIC_READ_ONLY=false",
                   "-e", "CORS_ORIGINS=http://explicitly-unrelated.example.invalid",
                   "--mount", f"type=bind,src={fixture},dst=/tmp/origin_fixture.py,readonly",
                   backend_image, "-B", "/tmp/origin_fixture.py")
            for name, alias, source in [(legacy,"legacy",legacy_config),(fixed,"fixed",ROOT / "frontend/nginx.conf")]:
                docker("run", "-d", "--pull=never", "--name", name, "--network", network, "--network-alias", alias,
                       "--read-only", "--user", "101:101", "--cap-drop=ALL", "--security-opt", "no-new-privileges:true",
                       "--pids-limit", "128", "--memory", "256m", "--tmpfs", "/var/cache/nginx:uid=101,gid=101",
                       "--tmpfs", "/var/run:uid=101,gid=101", "--mount",
                       f"type=bind,src={source},dst=/etc/nginx/conf.d/default.conf,readonly", frontend_image)
                docker("exec", name, "nginx", "-t")
            cases = json.loads(docker("exec", backend, "python", "-B", "-c", CLIENT))
            return {"checked_at":datetime.now(UTC).isoformat(), "status":"PASS" if all(row["passed"] for row in cases) else "FAIL",
                    "scope":"Actual nginx operator config and shipped backend websocket router; custom Host/Origin port; strict origin negatives",
                    "images":images,"nginx_config_sha256":hashlib.sha256((ROOT / "frontend/nginx.conf").read_bytes()).hexdigest(),
                    "cases":cases,"provider_requests":0,"fixture_cleanup_verified":True,
                    "limitations":["Isolated route test, not a full live database pipeline, public deployment or universal CORS audit."]}
        finally:
            for container in [fixed, legacy, backend]:docker("rm", "--force", container, check=False)
            docker("network", "rm", network, check=False)
            if docker("ps", "-aq", "--filter", f"name={prefix}-") or docker("network", "ls", "-q", "--filter", f"name={network}"):
                raise RuntimeError("Fixture cleanup incomplete")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-image",required=True)
    parser.add_argument("--backend-image",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:result=qualify(args.frontend_image,args.backend_image)
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
        result={"status":"FAIL/INCOMPLETE","error_type":type(error).__name__}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["status"]=="PASS" else 2)

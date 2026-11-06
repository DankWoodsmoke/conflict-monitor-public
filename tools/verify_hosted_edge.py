"""Exercise trusted connector identity in real nginx on isolated Docker networks.

Emulates one connector's TCP address; it never runs cloudflared or contacts an
edge. No host ports or actual credentials are used. This is not a live tunnel
qualification. The forged client address cases use documentation-only IPs.
"""
import argparse
import hashlib
import json
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from verify_public_ingress import docker, FIXTURE

ROOT = Path(__file__).resolve().parents[1]
CLIENT = r'''
import concurrent.futures,http.client,json,time
rows=[]
def record(name,passed):rows.append({"case":name,"passed":bool(passed)})
def request(path="/api/health",ip="198.51.100.10",extra=None,hold=False):
    headers={"Host":"monitor.ianmalcolm84.com","X-Forwarded-Proto":"https","CF-Connecting-IP":ip}
    headers.update(extra or {})
    headers={key:value for key,value in headers.items() if value is not None}
    connection=http.client.HTTPConnection("frontend",80,timeout=10)
    connection.request("GET",path,headers=headers)
    response=connection.getresponse()
    if hold:return connection,response
    data=response.read(64000)
    status=response.status
    connection.close()
    return status,data
def trusted_checks():
    for _ in range(40):
        try:
            if request()[0]==200:break
        except (OSError,http.client.HTTPException):pass
        time.sleep(.1)
    else:raise RuntimeError("Hosted fixture not ready")
    record("trusted_connector_with_client_header_accepted",request()[0]==200)
    record("public_publication_endpoint_accepted",request("/api/publication/observations")[0]==200)
    record("private_reports_and_ws_still_denied",request("/api/events")[0]==404 and request("/api/ws/events")[0]==404)
    for name,extra in [("unexpected_host",{"Host":"other.example.invalid"}),("insecure_scheme",{"X-Forwarded-Proto":"http"}),
                       ("missing_scheme",{"X-Forwarded-Proto":None}),("missing_client",{"CF-Connecting-IP":None}),
                       ("invalid_client",{"CF-Connecting-IP":"not-an-address"}),
                       ("multiple_clients",{"CF-Connecting-IP":"198.51.100.1, 198.51.100.2"})]:
        record(name+"_denied",request(extra=extra)[0]==421)
    record("ipv6_client_accepted",request(ip="2001:db8::1234")[0]==200)
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        statuses=list(pool.map(lambda _:request(ip="198.51.100.31")[0],range(65)))
    record("visitor_rate_limit_enforced",429 in statuses and set(statuses)<={200,429})
    record("second_visitor_not_throttled_by_first",request(ip="198.51.100.32")[0]==200)
    spoof=[request(ip="198.51.100.31",extra={"X-Forwarded-For":"198.51.100."+str(i)})[0] for i in range(40,50)]
    record("forged_forwarded_for_cannot_reset_rate_bucket",429 in spoof)
    held=[]
    try:
        for i in range(4):
            connection,response=request("/api/publication/observations/download",ip="198.51.100."+str(100+i),hold=True)
            held.append(connection)
            record("download_slot_"+str(i+1),response.status==200)
        connection,response=request("/api/publication/observations/download",ip="198.51.100.100",hold=True)
        held.append(connection)
        record("one_active_download_per_visitor",response.status==429)
        connection,response=request("/api/publication/observations/download",ip="198.51.100.110",hold=True)
        held.append(connection)
        record("four_downloads_global_cap",response.status==429)
    finally:
        for connection in held:connection.close()
def untrusted_checks():
    record("same_subnet_untrusted_peer_cannot_spoof_connector",request()[0]==421)
    record("untrusted_peer_forged_forwarding_headers_denied",request(extra={"X-Forwarded-For":"172.31.250.2","X-Real-IP":"172.31.250.2"})[0]==421)
    record("external_health_exception_cannot_be_spoofed",request("/",extra={"Host":"127.0.0.1","X-Forwarded-For":"127.0.0.1"})[0]==421)
'''


def qualify(frontend_image,backend_image):
    prefix="cm-edge-fixture-"+uuid.uuid4().hex[:12]
    edge,application,backend,frontend,trusted,untrusted=[prefix+"-"+suffix for suffix in ["edge","app","backend","front","trusted","untrusted"]]
    with tempfile.TemporaryDirectory(prefix="cm-edge-fixture-") as directory:
        fixture=Path(directory)/"fixture.py"
        fixture.write_text(FIXTURE.replace("data = json.dumps(proof).encode()", "data = json.dumps(proof).encode()\n        if '/download' in self.path: data = b'{' + b' ' * 5999998 + b'}'"),encoding="utf8")
        try:
            docker("network","create","--internal","--subnet","172.31.250.0/29",edge)
            docker("network","create","--internal",application)
            docker("run","-d","--pull=never","--name",backend,"--network",application,"--network-alias","backend",
                   "--read-only","--cap-drop=ALL","--security-opt","no-new-privileges:true","--memory","128m","--pids-limit","64",
                   "--entrypoint","python","--mount",f"type=bind,src={fixture},dst=/tmp/fixture.py,readonly",backend_image,"-B","/tmp/fixture.py")
            docker("run","-d","--pull=never","--name",frontend,"--network",edge,"--network-alias","frontend","--ip","172.31.250.3",
                   "--read-only","--user","101:101","--cap-drop=ALL","--security-opt","no-new-privileges:true","--memory","256m","--pids-limit","128",
                   "--tmpfs","/var/cache/nginx:uid=101,gid=101","--tmpfs","/var/run:uid=101,gid=101",
                   "--mount",f"type=bind,src={ROOT/'frontend/nginx-public.conf'},dst=/etc/nginx/conf.d/default.conf,readonly",
                   "--mount",f"type=bind,src={ROOT/'tools/hosting/edge-http.conf'},dst=/etc/nginx/public-edge-http/trusted.conf,readonly",
                   "--mount",f"type=bind,src={ROOT/'tools/hosting/edge-server.conf'},dst=/etc/nginx/public-edge-server/restrict.conf,readonly",
                   "--entrypoint","/bin/sh",frontend_image,"-c","sleep 2; exec nginx -g 'daemon off;'")
            docker("network","connect",application,frontend)
            for name,ip in [(trusted,"172.31.250.2"),(untrusted,"172.31.250.4")]:
                docker("run","-d","--pull=never","--name",name,"--network",edge,"--ip",ip,"--read-only","--cap-drop=ALL",
                       "--security-opt","no-new-privileges:true","--memory","128m","--pids-limit","64","--entrypoint","python",
                       backend_image,"-B","-c","import time;time.sleep(120)")
            docker("exec",frontend,"nginx","-t")
            rows=json.loads(docker("exec",trusted,"python","-B","-c",CLIENT+"\ntrusted_checks();print(json.dumps(rows))"))
            rows.extend(json.loads(docker("exec",untrusted,"python","-B","-c",CLIENT+"\nuntrusted_checks();print(json.dumps(rows))")))
            docker("exec",frontend,"wget","-q","-O","/dev/null","http://127.0.0.1/")
            rows.append({"case":"exact_local_container_healthcheck_allowed","passed":True})
            files=["frontend/nginx-public.conf","tools/hosting/edge-http.conf","tools/hosting/edge-server.conf"]
            return {"checked_at":datetime.now(UTC).isoformat(),"status":"PASS" if all(row["passed"] for row in rows) else "FAIL",
                    "scope":"Real nginx, emulated trusted/untrusted peers, no actual Cloudflare or host ports",
                    "cases":rows,"file_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
                    "tunnel_started":False,"provider_requests":0,"cleanup_verified":True,
                    "limitations":["Does not prove the eventual Cloudflare hostname, TLS, cache rules or real visitor header configuration."]}
        finally:
            for name in [trusted,untrusted,frontend,backend]:docker("rm","--force",name,check=False)
            for name in [edge,application]:docker("network","rm",name,check=False)
            if docker("ps","-aq","--filter",f"name={prefix}-") or docker("network","ls","-q","--filter",f"name={prefix}-"):
                raise RuntimeError("Fixture cleanup incomplete")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-image",required=True)
    parser.add_argument("--backend-image",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=qualify(args.frontend_image,args.backend_image)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["status"]=="PASS" else 2)

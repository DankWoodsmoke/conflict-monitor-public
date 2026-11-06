"""Bounded qualification of an already-running owned publisher fixture, never launch it."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "artifacts/private/release-readiness-20261106"
TABLES = {"public_observation_batches", "public_aircraft_batches"}
SECRETS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "REPLICATE_API_TOKEN", "ADMIN_API_KEY",
           "TELEGRAM_API_HASH", "TELEGRAM_SESSION", "TELEGRAM_BOT_TOKEN", "AISSTREAM_API_KEY", "FIRMS_MAP_KEY",
           "OPENSKY_USERNAME", "OPENSKY_PASSWORD", "TWITTER_BEARER_TOKEN", "TWITTER_AUTH_TOKEN", "TWITTER_CT0",
           "POSTGRES_PASSWORD", "POSTGRES_ADMIN_PASSWORD", "POSTGRES_APP_PASSWORD", "POSTGRES_PUBLIC_PASSWORD", "PGPASSWORD")

SQL_PROBE = r'''
import asyncio,json,os,asyncpg
async def main():
    connection=await asyncpg.connect(os.environ['DATABASE_URL'].replace('postgresql+asyncpg://','postgresql://',1),
        timeout=5,command_timeout=4,server_settings={'statement_timeout':'3000','lock_timeout':'1000'})
    try:
        role=await connection.fetchrow("SELECT current_user AS name,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user")
        rows=await connection.fetch("""SELECT c.relname AS name,
          has_table_privilege(current_user,c.oid,'SELECT') AS read,
          has_table_privilege(current_user,c.oid,'INSERT') AS insert,
          has_table_privilege(current_user,c.oid,'UPDATE') AS update,
          has_table_privilege(current_user,c.oid,'DELETE') AS delete,
          has_table_privilege(current_user,c.oid,'TRUNCATE') AS truncate,
          pg_get_userbyid(c.relowner)=current_user AS owner
          FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relkind IN ('r','v','m','p') ORDER BY c.relname""")
        bounds=await connection.fetchrow("""SELECT has_database_privilege(current_user,current_database(),'CREATE') AS create_db,
          has_database_privilege(current_user,current_database(),'TEMPORARY') AS temporary,
          has_schema_privilege(current_user,'public','CREATE') AS create_schema""")
        denied={}
        if role['name']=='monitor_public':
            statements={
              'private_events_select':'SELECT id FROM public.events LIMIT 0',
              'private_delivery_select':'SELECT * FROM public.event_deliveries LIMIT 0',
              'thermal_update':'UPDATE public.public_observation_batches SET status=status WHERE false',
              'aircraft_delete':'DELETE FROM public.public_aircraft_batches WHERE false',
              'temporary_table':'CREATE TEMP TABLE publication_permission_probe(id integer)',
            }
            for name,statement in statements.items():
                transaction=connection.transaction()
                await transaction.start()
                try:
                    await connection.execute(statement)
                    denied[name]=False
                except asyncpg.InsufficientPrivilegeError:
                    denied[name]=True
                finally:
                    await transaction.rollback()
            for table in ['public_observation_batches','public_aircraft_batches']:
                await connection.fetch('SELECT id FROM public.'+table+' LIMIT 0')
        print(json.dumps({'role':dict(role),'tables':[dict(row) for row in rows],'bounds':dict(bounds),'denied':denied}))
    finally:
        await connection.close()
asyncio.run(main())
'''


def docker(*args, timeout=30):
    result = subprocess.run(["docker",*args],capture_output=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError("Runtime qualification command failed; private output withheld")
    return result.stdout.decode("utf8")


def qualify(folder: Path) -> dict:
    folder=folder.resolve()
    if folder.parent != PRIVATE.resolve() or not re.fullmatch(r"publisher-fixture-\d+T\d+Z",folder.name):
        raise ValueError("Only the owned current publisher fixture is accepted")
    receipt=json.loads((folder/"fixture.json").read_bytes())
    project=receipt["project"]
    if receipt.get("status") != "running" or not re.fullmatch(r"cmonitor-ci-\d+-\d+",project):
        raise ValueError("Fixture must be admitted and running")
    source=Path(receipt["source"]).resolve()
    if source.name != "source" or source.parent.parent != PRIVATE.resolve():
        raise ValueError("Unexpected frozen source location")
    candidate=source.parent/"candidate-receipt.json"
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != receipt["candidate_sha256"]:
        raise ValueError("Candidate binding changed")
    build=json.loads(candidate.read_bytes())
    if build["status"] != "pass" or not all(hashlib.sha256((source/name).read_bytes()).hexdigest()==value for name,value in build["source"].items()):
        raise ValueError("Frozen candidate source changed")
    names=["db","backend","frontend","reader","publicfrontend","migrate"]
    inspected=json.loads(docker("inspect",*[f"{project}-{name}-1" for name in names]))
    services={entry["Config"]["Labels"]["com.docker.compose.service"]:entry for entry in inspected}
    runtime={name:dict(item.split("=",1) for item in services[name]["Config"]["Env"]) for name in ["backend","reader"]}
    writer,reader=runtime["backend"],runtime["reader"]
    # Refuse SQL entirely if ownership/DSN/mounts drift; do not merely record a
    # failed check and continue probes against a possibly non-fixture database.
    for name,user in [("backend","monitor"),("reader","monitor_public")]:
        parsed=urlsplit(runtime[name]["DATABASE_URL"])
        if (parsed.scheme!="postgresql+asyncpg" or parsed.hostname!="db" or parsed.port!=5432
                or parsed.path!="/conflict_monitor_test" or parsed.username!=user or parsed.query or parsed.fragment):
            raise ValueError("SQL probe target is not the isolated fixture database")
    if any(entry["Config"]["Labels"]["com.docker.compose.project"]!=project for entry in inspected):
        raise ValueError("Runtime ownership changed; SQL refused")
    data_mounts=[mount for mount in services["db"]["Mounts"] if mount["Destination"]=="/var/lib/postgresql/data"]
    if len(data_mounts)!=1 or data_mounts[0].get("Name")!=project+"_pgdata17_36_alpine":
        raise ValueError("Database mount is outside the owned fixture; SQL refused")
    checks={
      "container_ownership_matches":all(entry["Config"]["Labels"]["com.docker.compose.project"]==project for entry in inspected),
      "images_match_candidate":all(entry["Image"]==receipt["images"]["backend" if name=="migrate" else name] for name,entry in services.items()),
      "migration_success_on_candidate":services["migrate"]["State"]["Status"]=="exited" and services["migrate"]["State"]["ExitCode"]==0,
      "steady_services_running_healthy":all(services[name]["State"]["Running"] and services[name]["State"].get("Health",{}).get("Status")=="healthy" for name in names if name!="migrate"),
      "no_database_or_api_host_ports":all(not any((services[name]["HostConfig"].get("PortBindings") or {}).values()) for name in ["db","backend","reader","migrate"]),
      "ui_ports_loopback_only":all(binding["HostIp"]=="127.0.0.1" for name in ["frontend","publicfrontend"] for bindings in services[name]["HostConfig"]["PortBindings"].values() for binding in bindings),
      "private_writer_network_only":all(set(services[name]["NetworkSettings"]["Networks"])=={project+"_default"} for name in ["backend","frontend"]),
      "public_reader_network_only":set(services["reader"]["NetworkSettings"]["Networks"])=={project+"_public_reader"},
      "public_nginx_reader_and_ingress_only":set(services["publicfrontend"]["NetworkSettings"]["Networks"])=={project+"_public_reader",project+"_public_ingress"},
      "actual_ui_loopback_bindings_exist":all(bool(services[name]["NetworkSettings"]["Ports"].get("80/tcp")) and all(binding["HostIp"]=="127.0.0.1" and int(binding["HostPort"])>0 for binding in services[name]["NetworkSettings"]["Ports"]["80/tcp"]) for name in ["frontend","publicfrontend"]),
      "database_joins_only_two_app_networks":set(services["db"]["NetworkSettings"]["Networks"])=={project+"_default",project+"_public_reader"},
      "reader_owns_public_backend_dns_alias":"backend" in services["reader"]["NetworkSettings"]["Networks"][project+"_public_reader"]["Aliases"],
      "private_credentials_blank_in_http_workers":all(not environment.get(name) for environment in runtime.values() for name in SECRETS),
      "reader_is_reader_role_only":"//monitor_public:" in reader["DATABASE_URL"] and "//monitor:" in writer["DATABASE_URL"],
      "reader_collectors_and_generators_disabled":reader["PUBLIC_READ_ONLY"]=="true" and all(reader[name]=="false" for name in ["LIVE_INGESTION_ENABLED","DEMO_MODE","PUBLIC_OBSERVATION_PUBLISHER_ENABLED","PUBLIC_AIRCRAFT_PUBLISHER_ENABLED","ENABLE_LOCAL_AI","ENABLE_SITREP_GENERATION","ENABLE_VIDEO_GENERATION"]),
      "one_private_publication_owner":writer["PUBLIC_READ_ONLY"]=="false" and writer["LIVE_INGESTION_ENABLED"]=="true" and writer["PUBLIC_OBSERVATION_PUBLISHER_ENABLED"]=="true" and writer["PUBLIC_AIRCRAFT_PUBLISHER_ENABLED"]=="true",
      "private_publisher_cannot_start_paid_models":writer["RSS_PROCESSING_MODE"]==writer["TELEGRAM_PROCESSING_MODE"]=="reports" and writer["TELEGRAM_TRANSPORT"]=="disabled" and all(writer[name]=="false" for name in ["ENABLE_LOCAL_AI","ENABLE_VIDEO_GENERATION","ENABLE_SITREP_GENERATION","OPENSKY_FALLBACK_ENABLED","X_INGESTION_ENABLED"]),
      "reader_root_readonly_without_artifact_mounts":services["reader"]["HostConfig"]["ReadonlyRootfs"] and not services["reader"]["Mounts"],
      "reader_tmp_bounded_noexec_nosuid":all(part in services["reader"]["HostConfig"]["Tmpfs"]["/tmp"] for part in ["noexec","nosuid","size=64m"]),
      "resource_limits_present":all(entry["HostConfig"]["Memory"]>0 and entry["HostConfig"]["NanoCpus"]>0 and entry["HostConfig"]["PidsLimit"]>0 for entry in inspected),
      "no_gpu_or_docker_socket":all(not entry["HostConfig"].get("DeviceRequests") and not any("docker.sock" in mount.get("Source","") for mount in entry["Mounts"]) for entry in inspected),
      "bounded_log_rotation":all(entry["HostConfig"]["LogConfig"]["Config"].get("max-size")=="10m" and entry["HostConfig"]["LogConfig"]["Config"].get("max-file")=="3" for entry in inspected),
      "owned_database_volume":any(mount.get("Name")==project+"_pgdata17_36_alpine" and mount["Destination"]=="/var/lib/postgresql/data" for mount in services["db"]["Mounts"]),
    }
    network=json.loads(docker("network","inspect",project+"_public_reader"))[0]
    checks["public_network_internal"]=network["Internal"] is True
    probes={name:json.loads(docker("exec",f"{project}-{name}-1","python","-B","-c",SQL_PROBE,timeout=60)) for name in ["reader","backend"]}
    public,private=probes["reader"],probes["backend"]
    checks["reader_actual_sql_identity"]=public["role"]["name"]=="monitor_public" and not any(value for key,value in public["role"].items() if key!="name")
    checks["reader_selects_only_dedicated_tables"]={row["name"] for row in public["tables"] if row["read"]}==TABLES
    checks["reader_no_dml_or_ownership"]=all(not any(row[key] for key in ["insert","update","delete","truncate","owner"]) for row in public["tables"])
    checks["reader_no_schema_temp_or_database_creation"]=not any(public["bounds"].values())
    checks["reader_negative_sql_enforced"]=len(public["denied"])==5 and all(public["denied"].values())
    checks["writer_actual_sql_identity"]=private["role"]["name"]=="monitor" and not any(value for key,value in private["role"].items() if key!="name")
    publication=[row for row in private["tables"] if row["name"] in TABLES]
    checks["writer_publication_select_insert_delete_only"]=len(publication)==2 and all(all(row[key] for key in ["read","insert","delete"]) and not any(row[key] for key in ["update","truncate","owner"]) for row in publication)
    return {"checked_at":datetime.now(UTC).isoformat(),"status":"PASS" if all(checks.values()) else "FAIL",
            "checks":checks,"project":project,"images":receipt["images"],"candidate_sha256":receipt["candidate_sha256"],
            "tool_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope":"Existing owned fixture only; metadata and bounded SQL probes with rollback, no data values or credentials emitted",
            "limitations":["Does not prove source publication freshness, browser rendering, external hosting or long-session behavior."]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=qualify(args.fixture)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["status"]=="PASS" else 2)

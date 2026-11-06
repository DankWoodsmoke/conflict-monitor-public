"""Resolve the publisher and optional tunnel profiles using hostile fixture inputs.

Never starts containers, reads the real .env, authenticates, creates a tunnel or
prints configuration values. A successful check is not public-host readiness.
"""
import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from verify_public_ingress import docker

ROOT = Path(__file__).resolve().parents[1]
PAID_SECRETS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "REPLICATE_API_TOKEN"]


def qualify():
    with tempfile.TemporaryDirectory(prefix="cm-hosting-profile-") as directory:
        directory = Path(directory)
        env_file = directory / "fixture.env"
        env_file.write_text("\n".join([
            "RSS_PROCESSING_MODE=model", "TELEGRAM_PROCESSING_MODE=model", "TELEGRAM_TRANSPORT=session",
            "X_INGESTION_ENABLED=true", "ENABLE_LOCAL_AI=true", "ENABLE_VIDEO_GENERATION=true",
            "ENABLE_SITREP_GENERATION=true", "OPENSKY_FALLBACK_ENABLED=true", "DEMO_MODE=true",
            "PRIVATE_CUSTOM_MODEL_API_TOKEN=fixture-only-private-canary",
            *[name + "=fixture-only-paid-secret" for name in PAID_SECRETS],
            "TELEGRAM_SESSION=fixture-only-private-session", "ADMIN_API_KEY=fixture-only-admin-secret",
        ]) + "\n", encoding="utf8")
        credential = directory / "credential.json"
        credential.write_text("{}", encoding="utf8")
        env = {**os.environ, "CONFLICT_ENV_FILE": str(env_file),
               "POSTGRES_PASSWORD": "fixture-admin-only", "POSTGRES_APP_PASSWORD": "a" * 64,
               "POSTGRES_PUBLIC_PASSWORD": "b" * 64, "FRONTEND_PORT": "5197", "PUBLIC_FRONTEND_PORT": "5198",
               "CONFLICT_TUNNEL_CONFIG": str(ROOT / "tools/hosting/cloudflared.example.yml"),
               "CONFLICT_TUNNEL_CREDENTIALS": str(credential), "PUBLIC_AIRCRAFT_PUBLISHER_ENABLED": "false"}
        args = ["compose", "--env-file", str(env_file), "-f", str(ROOT / "docker-compose.yml"),
                "-f", str(ROOT / "compose.publisher.yml")]
        local = json.loads(docker(*args, "config", "--format", "json", env=env))
        hosted = json.loads(docker(*args, "-f", str(ROOT / "compose.tunnel.yml"),
                                  "--profile", "public-edge", "config", "--format", "json", env=env))
        unresolved = json.loads(docker(*args, "config", "--no-env-resolution", "--format", "json", env=env))
        services, hosting = local["services"], hosted["services"]
        writer, reader = services["backend"]["environment"], services["reader"]["environment"]
        checks = {
            "one_private_writer": writer["PUBLIC_READ_ONLY"] == "false" and writer["LIVE_INGESTION_ENABLED"] == "true"
                and writer["PUBLIC_OBSERVATION_PUBLISHER_ENABLED"] == "true",
            "reader_never_collects": reader["PUBLIC_READ_ONLY"] == "true" and all(reader[name] == "false" for name in
                ["LIVE_INGESTION_ENABLED", "PUBLIC_OBSERVATION_PUBLISHER_ENABLED", "PUBLIC_AIRCRAFT_PUBLISHER_ENABLED"]),
            "legacy_model_modes_cannot_spend": all(writer[name] == "reports" for name in ["RSS_PROCESSING_MODE", "TELEGRAM_PROCESSING_MODE"])
                and all(writer[name] == "false" for name in ["X_INGESTION_ENABLED", "ENABLE_LOCAL_AI", "ENABLE_VIDEO_GENERATION", "ENABLE_SITREP_GENERATION", "OPENSKY_FALLBACK_ENABLED"]),
            "paid_credentials_blank": all(writer.get(name) == "" for name in PAID_SECRETS),
            "telegram_and_admin_credentials_disabled": writer["TELEGRAM_TRANSPORT"] == "disabled"
                and writer["TELEGRAM_SESSION"] == writer["TELEGRAM_BOT_TOKEN"] == writer["ADMIN_API_KEY"] == "",
            "neither_http_process_inherits_operator_env": all(not unresolved["services"][name].get("env_file") for name in ["backend", "reader"])
                and all("PRIVATE_CUSTOM_MODEL_API_TOKEN" not in value for value in [writer,reader]),
            "writer_and_reader_roles_separate": "//monitor:" in writer["DATABASE_URL"] and "//monitor_public:" in reader["DATABASE_URL"]
                and env["POSTGRES_APP_PASSWORD"] not in str(reader) and env["POSTGRES_PASSWORD"] not in str(reader),
            "bootstrap_receives_three_distinct_role_inputs": services["migrate"]["environment"]["POSTGRES_PUBLIC_PASSWORD"] == env["POSTGRES_PUBLIC_PASSWORD"]
                and services["migrate"]["environment"]["POSTGRES_APP_PASSWORD"] == env["POSTGRES_APP_PASSWORD"]
                and env["POSTGRES_PASSWORD"] in services["migrate"]["environment"]["DATABASE_URL"],
            "private_writer_network_separate": set(services["backend"]["networks"]) == set(services["frontend"]["networks"]) == {"default"},
            "reader_is_public_backend_alias": set(services["reader"]["networks"]) == {"public_reader"}
                and services["reader"]["networks"]["public_reader"]["aliases"] == ["backend"],
            "database_joins_both_application_networks": set(services["db"]["networks"]) == {"default","public_reader"},
            "public_reader_network_has_no_external_egress": local["networks"]["public_reader"]["internal"] is True,
            "local_ingress_belongs_only_to_public_nginx": set(services["publicfrontend"]["networks"]) == {"public_reader", "public_ingress"}
                and not local["networks"]["public_ingress"].get("internal", False)
                and [name for name,value in services.items() if "public_ingress" in value.get("networks", {})] == ["publicfrontend"],
            "hosted_ingress_replaces_local_bridge": set(hosting["publicfrontend"]["networks"]) == {"public_reader", "public_edge"},
            "no_db_or_api_host_ports": all(not services[name].get("ports") for name in ["db","backend","reader","migrate"]),
            "local_ui_ports_only_loopback": all(port["host_ip"] == "127.0.0.1" for name in ["frontend","publicfrontend"] for port in services[name]["ports"]),
            "reader_root_and_volumes_restricted": services["reader"]["read_only"] is True and not services["reader"].get("volumes"),
            "all_long_lived_services_resource_bounded": all(services[name].get("mem_limit") and services[name].get("cpus")
                and services[name].get("pids_limit") and services[name].get("restart") == "unless-stopped"
                and services[name].get("logging",{}).get("options",{}).get("max-file") == "3"
                for name in ["db","backend","frontend","reader","publicfrontend"]),
            "no_gpu_or_docker_socket": all(not value.get("gpus") and not value.get("devices")
                and "docker.sock" not in str(value.get("volumes",[])) for value in services.values()),
            "hosted_public_frontend_has_no_host_port": not hosting["publicfrontend"].get("ports"),
            "connector_is_opt_in_pinned_nonroot": hosting["cloudflared"]["profiles"] == ["public-edge"]
                and hosting["cloudflared"]["image"] == "conflict-monitor-cloudflared:2026.10.7-static.1"
                and hosting["cloudflared"]["pull_policy"] == "never" and hosting["cloudflared"]["read_only"] is True
                and hosting["cloudflared"]["user"] == "65532:65532",
            "connector_recipe_pins_official_static_source": "FROM cloudflare/cloudflared:2026.10.7@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba AS upstream" in (ROOT/"tools/hosting/Dockerfile").read_text()
                and "FROM scratch" in (ROOT/"tools/hosting/Dockerfile").read_text()
                and not any(line.startswith("RUN ") for line in (ROOT/"tools/hosting/Dockerfile").read_text().splitlines()),
            "connector_does_not_join_app_or_database_network": set(hosting["cloudflared"]["networks"]) == {"public_edge","tunnel_egress"},
            "edge_bridge_peer_addresses_exact": hosted["networks"]["public_edge"]["internal"] is True
                and hosting["cloudflared"]["networks"]["public_edge"]["ipv4_address"] == "172.31.250.2"
                and hosting["publicfrontend"]["networks"]["public_edge"]["ipv4_address"] == "172.31.250.3",
            "connector_credentials_not_command_or_env": not hosting["cloudflared"].get("environment")
                and "token" not in " ".join(hosting["cloudflared"]["command"])
                and len(hosting["cloudflared"].get("secrets",[])) == 1,
        }
        files = ["docker-compose.yml", "compose.public.yml", "compose.publisher.yml", "compose.tunnel.yml",
                 "frontend/nginx-public.conf", "tools/hosting/edge-http.conf", "tools/hosting/edge-server.conf",
                 "tools/hosting/Dockerfile", "tools/hosting/.dockerignore", "tools/hosting/cloudflared-provenance.json", "tools/hosting/THIRD_PARTY_LICENSES.txt"]
        return {"checked_at":datetime.now(UTC).isoformat(),"status":"PASS" if all(checks.values()) else "FAIL",
                "scope":"Actual Docker Compose resolution with legacy model settings and private credential canaries; no services started",
                "checks":checks,"file_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
                "production_config_printed":False,"tunnel_started":False,"external_state_changed":False}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=qualify()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["status"]=="PASS" else 2)

"""Judge raw observer coverage conservatively, independently of its progress label."""
import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

EXPECTED_ENDPOINTS = {
    "/api/health", "/api/status", "/api/events?limit=50", "/api/tracking/aircraft",
    "/api/tracking/vessels", "/api/tracking/tle", "/api/satellite/hotspots", "/api/sitreps/latest",
}
SQL_INTEGRITY_FIELDS = {
    "pending_receipts_over_5m", "synthetic_events", "invalid_positions", "position_geometry_mismatch",
    "duplicate_channel_message_ids", "checkpoint_behind_stored_message",
}

def percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def load_lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]


def memory_mib(value):
    match = re.fullmatch(r"([0-9.]+)\s*(B|kB|KB|KiB|MB|MiB|GB|GiB)", str(value).split("/", 1)[0].strip())
    if not match:
        return None
    factors = {"B": 1 / 1024**2, "kB": 1000 / 1024**2, "KB": 1000 / 1024**2,
               "KiB": 1 / 1024, "MB": 1_000_000 / 1024**2, "MiB": 1,
               "GB": 1_000_000_000 / 1024**2, "GiB": 1024}
    return float(match[1]) * factors[match[2]]


def database_identity_requirements(progress, samples, segments, sql_samples, elapsed):
    """A stable UI/backend pair cannot stand in for a verified database volume."""
    names = progress.get('expected_containers', {})
    names_valid = (set(names) == {'backend', 'frontend', 'database'}
        and all(isinstance(value, str) and value for value in names.values())
        and len(set(names.values())) == 3)
    observations = [(row['elapsed_seconds'], row['deployment_identity'])
        for row in samples if 'deployment_identity' in row]
    expected_checks = (len(samples) + 1) // 2
    identities, databases = [], []
    valid = names_valid and len(observations) == expected_checks and bool(segments)
    for _, observation in observations:
        containers = observation.get('containers', [])
        if (not isinstance(containers, list) or len(containers) != 3
            or any(not isinstance(row, dict) for row in containers)
            or {row.get('name') for row in containers} != set(names.values())):
            valid = False
            continue
        database = next(row for row in containers if row['name'] == names['database'])
        mounts = database.get('pgdata', [])
        if (len(mounts) != 1 or mounts[0].get('Type') != 'volume'
            or not isinstance(mounts[0].get('Name'), str) or not mounts[0]['Name']
            or mounts[0].get('Destination') != '/var/lib/postgresql/data'
            or any(not isinstance(row.get(key), str) or not row[key]
                for row in containers for key in ('image', 'started_at'))):
            valid = False
            continue
        identities.append(json.dumps(sorted(containers, key=lambda row: row['name']), sort_keys=True))
        databases.append({'image': database['image'], 'volume': mounts[0]['Name']})
    times = [offset for offset, _ in observations]
    cadence = (bool(times) and times[0] <= 90 and elapsed - times[-1] <= 90
        and max((b-a for a,b in zip(times,times[1:])), default=0) <= 90)
    versions = {(row.get('postgresql_version', '').split(' ', 1)[0], row.get('postgis_version', ''))
        for row in sql_samples}
    expected = progress.get('expected_database', {})
    requirements = {
        'database_identity_observed_throughout': bool(valid and cadence and progress.get('observer_version', 0) >= 3),
        'one_three_container_start_and_database_volume_identity': bool(valid and len(set(identities)) == 1),
        'database_versions_and_collation_observed': bool(sql_samples) and len(versions) == 1
            and all(pg and postgis for pg, postgis in versions)
            and all(row.get('collation_version_matches') is True for row in sql_samples),
    }
    if expected.get('postgresql'):
        requirements['expected_postgresql_version'] = all(pg == expected['postgresql'] for pg, _ in versions) and bool(versions)
    if expected.get('postgis'):
        requirements['expected_postgis_version'] = all(postgis == expected['postgis'] for _, postgis in versions) and bool(versions)
    if expected.get('data_volume'):
        requirements['expected_database_volume'] = bool(databases) and all(row['volume'] == expected['data_volume'] for row in databases)
    return requirements, {'database_identities': databases[:1] if len({json.dumps(row,sort_keys=True) for row in databases}) == 1 else databases,
        'sql_versions_observed': [{'postgresql': pg, 'postgis': postgis} for pg, postgis in sorted(versions)],
        'identity_samples': len(observations), 'expected': expected}


def summarize(directory, *, require_single_image=False, require_database_identity=False, require_no_paid_usage=False):
    directory = Path(directory)
    progress = json.loads((directory / "summary.json").read_text(encoding="utf8"))
    samples = load_lines(directory / "samples.jsonl")
    sockets = load_lines(directory / "websocket.jsonl")
    segments = load_lines(directory / "segments.jsonl")
    gaps = []
    finding_counts = Counter()
    endpoints = defaultdict(list)
    http_errors = Counter()
    providers = defaultdict(Counter)
    resources = defaultdict(lambda: {"cpu_percent": [], "memory_mib": [], "pids": []})
    sql_samples, unavailable_sql = [], 0
    previous = None
    for sample in samples:
        elapsed = sample["elapsed_seconds"]
        if previous is not None:
            gaps.append(elapsed - previous)
        previous = elapsed
        for endpoint, request in sample.get("requests", {}).items():
            if request.get("status") != 200:
                http_errors[endpoint] += 1
            if isinstance(request.get("ms"), (float, int)):
                endpoints[endpoint].append(request["ms"])
        for finding in sample.get("findings", []):
            finding_counts[finding["kind"]] += 1
        for provider, data in sample.get("providers", {}).items():
            if isinstance(data, dict) and "status" in data:
                providers[provider][data["status"]] += 1
        for container in sample.get("container_resources", []):
            target = resources[container["Name"]]
            cpu = str(container.get("CPUPerc", "")).removesuffix("%")
            if re.fullmatch(r"[0-9.]+", cpu):
                target["cpu_percent"].append(float(cpu))
            memory = memory_mib(container.get("MemUsage"))
            if memory is not None:
                target["memory_mib"].append(memory)
            if str(container.get("PIDs", "")).isdigit():
                target["pids"].append(int(container["PIDs"]))
        if "sql_integrity" in sample:
            integrity = sample["sql_integrity"]
            if integrity.get("status") == "unavailable":
                unavailable_sql += 1
            else:
                sql_samples.append({"at": sample["at"], **integrity})
    connected = sum(row.get("event") == "connected" for row in sockets)
    elapsed = progress.get("elapsed_seconds", 0)
    requested = progress.get("requested_seconds", 0)
    connected_seconds = 0.0
    socket_opened = None
    for event in sockets:
        if not event.get("at"):
            continue
        clock = datetime.fromisoformat(event["at"])
        if event.get("event") == "connected" and socket_opened is None:
            socket_opened = clock
        elif event.get("event") == "disconnected" and socket_opened is not None:
            connected_seconds += max(0, (clock - socket_opened).total_seconds())
            socket_opened = None
    if socket_opened is not None:
        end_clock = progress.get("ended_at") or progress.get("last_sample_at")
        if end_clock:
            connected_seconds += max(0, (datetime.fromisoformat(end_clock) - socket_opened).total_seconds())
    connected_fraction = min(1.0, connected_seconds / elapsed) if elapsed else 0
    requirements = {
        "observer_finished": bool(progress.get("ended_at")),
        "requested_duration_observed": elapsed >= requested > 0,
        "sample_cadence_bounded": len(samples) >= 2 and max(gaps, default=math.inf) <= 90
            and samples[0]["elapsed_seconds"] <= 90
            and elapsed - samples[-1]["elapsed_seconds"] <= 90,
        "rest_requests_successful": not http_errors and set(endpoints) == EXPECTED_ENDPOINTS
            and all(len(values) == len(samples) for values in endpoints.values()),
        "sampled_integrity_preserved": not finding_counts and not progress.get("source_hash_changes"),
        "sql_checks_available": len(sql_samples) >= 2 and unavailable_sql == 0,
        "sql_integrity_preserved": bool(sql_samples) and all(SQL_INTEGRITY_FIELDS.issubset(row) for row in sql_samples)
            and not any(row[name] for row in sql_samples for name in SQL_INTEGRITY_FIELDS),
        "websocket_connected": connected > 0,
        "websocket_available_over_95_percent": connected_fraction >= .95,
        "websocket_payloads_valid": progress.get("ws_payload_errors", 0) == 0,
    }
    per_segment = []
    for index, segment in enumerate(segments):
        start = segment["elapsed_seconds"]
        end = segments[index + 1]["elapsed_seconds"] if index + 1 < len(segments) else elapsed
        per_segment.append({**segment, "observed_seconds": round(max(0, end-start), 2)})
    image_pairs = {tuple(sorted("|".join(line.split("|")[:2]) for line in segment["identity"].splitlines())) for segment in segments}
    if require_single_image:
        requirements["one_backend_and_frontend_image_pair"] = len(image_pairs) == 1
    database_profile = None
    if require_database_identity:
        extra, database_profile = database_identity_requirements(progress, samples, segments, sql_samples, elapsed)
        requirements.update(extra)
    if require_no_paid_usage:
        requirements['no_recorded_paid_usage']=bool(sql_samples) and all(type(row.get('usage_calls')) is int and row['usage_calls']==0 for row in sql_samples)
    return {
        "scope": "bounded_read_only_local_deployment_soak",
        "started_at": progress.get("started_at"), "ended_at": progress.get("ended_at"),
        "observer_version": progress.get("observer_version", 1), "observer_sha256": progress.get("observer_sha256"),
        "requires_single_image_pair": require_single_image,
        "requires_database_identity": require_database_identity,
        "requires_no_paid_usage": require_no_paid_usage,
        "database_profile": database_profile,
        "elapsed_seconds": elapsed, "requested_seconds": requested, "samples": len(samples),
        "status": "qualified_sample" if all(requirements.values()) else "incomplete_or_findings",
        "requirements": requirements,
        "deployment_segments": per_segment,
        "max_sample_gap_seconds": round(max(gaps), 2) if gaps else None,
        "endpoint_timing_ms": {endpoint: {"samples": len(values), "p50": percentile(values, .5),
            "p95": percentile(values, .95), "max": max(values)} for endpoint, values in endpoints.items()},
        "http_errors": dict(http_errors), "integrity_findings": dict(finding_counts),
        "provider_status_observations": {key: dict(value) for key, value in providers.items()},
        "container_resource_samples": {name: {metric: {"samples": len(values), "first": values[0],
            "last": values[-1], "min": min(values), "max": max(values)} for metric, values in metrics.items()
            if values} for name, metrics in resources.items()},
        "sql_checks": len(sql_samples), "unavailable_sql_checks": unavailable_sql,
        "sql_first": sql_samples[0] if sql_samples else None, "sql_last": sql_samples[-1] if sql_samples else None,
        "websocket": {"connections": connected, "disconnects": progress.get("ws_disconnects", 0),
            "observed_connected_seconds": round(connected_seconds, 2), "connected_fraction": round(connected_fraction, 5),
            "event_messages": progress.get("ws_messages", 0), "payload_errors": progress.get("ws_payload_errors", 0),
            "delivery_observed": progress.get("ws_messages", 0) > 0},
        "limitations": [
            "Provider state and sampled API/SQL behavior do not establish factual truth or global source coverage.",
            "WebSocket connection with no event messages does not qualify event delivery; use the separate real pipeline test.",
            "Deployment segments are distinct; total duration does not imply the final image ran for that duration.",
            "No physical device, every code path, long-term reliability, or sustained-load claim is established.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("--output")
    parser.add_argument("--require-single-image", action="store_true")
    parser.add_argument("--require-database-identity", action="store_true")
    parser.add_argument("--require-no-paid-usage", action="store_true")
    args = parser.parse_args()
    result = summarize(args.directory, require_single_image=args.require_single_image,
        require_database_identity=args.require_database_identity,require_no_paid_usage=args.require_no_paid_usage)
    rendered = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf8")
    else:
        print(rendered)

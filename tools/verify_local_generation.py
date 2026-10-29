"""Explicit, loopback-only qualification of real local AI and video generation.

Reads an operator key from environment/private dotenv, never command arguments
or output. --execute authorizes one analysis and one video job. No retries,
model pulls, service changes, database mutations or synthetic reports are used.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit


class VerificationError(RuntimeError):
    """A controlled check failure, containing no response bodies or credentials."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def utc():
    return datetime.now(UTC)


def local_origin(value, *, api=False):
    parts = urlsplit(value)
    if (
        parts.scheme != "http"
        or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
        or not parts.port
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path.rstrip("/") not in ({"", "/api"} if api else {""})
    ):
        raise VerificationError("A loopback HTTP origin with explicit port is required")
    return value.rstrip("/")


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def load_key(env_file=None):
    import os

    key = os.environ.get("ADMIN_API_KEY", "")
    if env_file:
        from dotenv import dotenv_values

        key = dotenv_values(env_file).get("ADMIN_API_KEY") or key
    if not key:
        raise VerificationError("No operator key is configured")
    return key


class Client:
    def __init__(self, base, key=""):
        self.base = local_origin(base, api=True)
        self.key = key
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect())

    def get(self, path, *, data=None, headers=None, limit=1_500_000):
        if not path.startswith("/") or path.startswith("//"):
            raise VerificationError("Unexpected qualification path")
        supplied = dict(headers or {})
        if data is not None:
            supplied.update(
                {"Content-Type": "application/json", "X-Admin-Key": self.key}
            )
        req = request.Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=supplied,
        )
        try:
            with self.opener.open(req, timeout=30) as response:
                payload = bytearray()
                while block := response.read(65536):
                    if len(payload) + len(block) > limit:
                        raise VerificationError(
                            "Qualification response exceeds byte limit"
                        )
                    payload.extend(block)
                return response.status, dict(response.headers), bytes(payload)
        except error.HTTPError as exc:
            raise VerificationError(
                f"HTTP request failed with status {exc.code}"
            ) from None
        except error.URLError:
            raise VerificationError("Loopback service is unavailable") from None

    def json(self, path, *, data=None):
        status, _, raw = self.get(path, data=data)
        try:
            value = json.loads(raw)
        except (ValueError, RecursionError):
            raise VerificationError("Malformed JSON qualification response") from None
        return status, value


def require(condition, name, receipt):
    receipt.setdefault("checks", {})[name] = "PASS" if condition else "FAIL"
    if not condition:
        raise VerificationError(name)


def database_snapshot(container, event_id):
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}", container)
        or type(event_id) is not int
        or event_id <= 0
    ):
        raise VerificationError("Invalid database qualification identity")
    # Only this fixed statement is executed, with an already validated integer.
    sql = (
        "SELECT json_build_object('event',(SELECT row_to_json(x) FROM "
        "(SELECT id,source,raw_text,summary,source_url,timestamp FROM events WHERE id="
        + str(event_id)
        + ")x),'usage_log_rows',(SELECT count(*) FROM usage_log));"
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "monitor",
            "-d",
            "conflict_monitor",
            "-Atq",
            "-c",
            sql,
        ],
        capture_output=True,
        timeout=20,
        check=False,
    )
    if result.returncode or len(result.stdout) > 100_000:
        raise VerificationError("Read-only database qualification query failed")
    try:
        return json.loads(result.stdout)
    except (ValueError, RecursionError):
        raise VerificationError("Invalid database qualification result") from None


def select_report(events, event_id=None):
    if not isinstance(events, list):
        raise VerificationError("Expected actual event array")
    now = utc()
    for event in events:
        try:
            stamp = datetime.fromisoformat(event["timestamp"])
            eligible = (
                str(event.get("source", "")).startswith("rss_")
                and event.get("classification_status") == "not_requested"
                and event.get("severity") == 0
                and stamp.tzinfo is not None
                and now - timedelta(hours=24) <= stamp <= now
                and isinstance(event.get("raw_text"), str)
                and bool(event["raw_text"].strip())
            )
        except (ValueError, TypeError, KeyError):
            eligible = False
        if eligible and (event_id is None or event.get("id") == event_id):
            return event
    raise VerificationError("No eligible current free RSS source was found")


def poll_job(client, name, previous_attempt, timeout, receipt):
    begin = time.monotonic()
    announced = 0
    while time.monotonic() - begin < timeout:
        _, status = client.json("/briefing/status")
        current = status.get(name, {})
        if (
            current.get("last_attempt_at")
            and current.get("last_attempt_at") != previous_attempt
        ):
            if current.get("state") == "failed":
                receipt.setdefault("job_failures", []).append(
                    {
                        "job": name,
                        "error_type": current.get("error_type"),
                        "last_attempt_at": current.get("last_attempt_at"),
                    }
                )
                raise VerificationError(f"{name} generation was rejected or failed")
            if current.get("state") == "ready":
                return current
        elapsed = time.monotonic() - begin
        if elapsed - announced >= 15:
            print(
                json.dumps(
                    {
                        "phase": name,
                        "state": current.get("state"),
                        "elapsed_seconds": round(elapsed),
                    }
                ),
                flush=True,
            )
            announced = elapsed
        time.sleep(1)
    raise VerificationError(f"{name} generation deadline exceeded; no automatic retry")


def source_binding(row, event):
    # Resolve labels against the reviewed local catalog, independently of the
    # returned manifest. Display spelling may differ from the immutable ID.
    catalog_path = Path(__file__).resolve().parents[1] / "backend/app/services/source_catalog.py"
    tree = ast.parse(catalog_path.read_text(encoding="utf-8"))
    catalog = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "RSS_FEEDS" for target in node.targets)
    )
    source_id = event["source"].removeprefix("rss_")
    feed = next((feed for feed in catalog if feed["source"] == source_id), {})
    label = str(feed.get("display_name") or event.get("channel_name") or event["source"]).replace("_", " ").strip()
    return (
        row.get("id") == event["id"]
        and row.get("source") == label
        and row.get("source_platform") == event["source"]
        and row.get("headline") == str(event.get("summary") or event["raw_text"])[:500]
        and row.get("source_url") == event["source_url"]
        and row.get("original_text_sha256")
        == hashlib.sha256(event["raw_text"].encode()).hexdigest()
        and row.get("text") == event["raw_text"][:2500]
        and datetime.fromisoformat(row["published_at"])
        == datetime.fromisoformat(event["timestamp"])
    )


def execute(args, receipt):
    client = Client(args.base_url, load_key(args.env_file))
    _, health = client.json("/health")
    _, config = client.json("/config")
    require(health.get("status") == "healthy", "core_readiness", receipt)
    require(
        config.get("demo_mode") is False
        and config.get("live_ingestion_enabled") is True,
        "actual_live_mode_without_synthetic_fallback",
        receipt,
    )
    require(
        config.get("local_ai_enabled") is True
        and config.get("video_generation_enabled") is True,
        "local_generation_explicitly_enabled",
        receipt,
    )
    if args.event_id is not None:
        _, selected = client.json(f"/events/{args.event_id}")
        events = [selected]
    else:
        _, events = client.json("/events?limit=20")
    event = select_report(events, args.event_id)
    receipt["source"] = {
        "event_id": event["id"],
        "source": event["source"],
        "published_at": event["timestamp"],
        "original_text_sha256": hashlib.sha256(event["raw_text"].encode()).hexdigest(),
    }
    before = database_snapshot(args.docker_db_container, event["id"])
    stored = before.get("event") or {}
    require(
        stored.get("id") == event["id"]
        and stored.get("source") == event["source"]
        and stored.get("raw_text") == event["raw_text"]
        and stored.get("summary") == event["summary"]
        and stored.get("source_url") == event["source_url"],
        "actual_postgis_source_matches_api",
        receipt,
    )
    receipt["usage_log_rows_before"] = before["usage_log_rows"]
    _, old_status = client.json("/briefing/status")
    require(
        old_status["local_ai"].get("state") != "running"
        and old_status["video"].get("state") != "running",
        "no_other_generation_is_running",
        receipt,
    )
    status, _ = client.json("/briefing/analyze", data={"event_ids": [event["id"]]})
    require(status == 202, "local_ai_job_admitted", receipt)
    ai_status = poll_job(
        client,
        "local_ai",
        old_status["local_ai"].get("last_attempt_at"),
        args.timeout,
        receipt,
    )
    _, analysis = client.json("/briefing/latest")
    reports = analysis.get("reports", [])
    require(
        analysis.get("generated_at") == ai_status.get("last_success_at")
        and len(reports) == 1
        and source_binding(reports[0], event),
        "new_analysis_is_bound_to_actual_source",
        receipt,
    )
    require(
        reports[0].get("coordinates") is None
        and reports[0].get("severity") is None
        and reports[0].get("assessment_status") == "model_generated_unreviewed",
        "no_model_coordinates_or_fact_verdict",
        receipt,
    )
    frozen_fields = {
        "id",
        "source",
        "source_platform",
        "published_at",
        "source_url",
        "text",
        "text_truncated",
        "headline",
        "original_text_sha256",
    }
    require(
        canonical_hash(
            [
                {key: value for key, value in row.items() if key in frozen_fields}
                for row in reports
            ]
        )
        == analysis.get("source_snapshot_sha256"),
        "analysis_snapshot_hash_recomputed",
        receipt,
    )
    text = reports[0]["text"]
    for spans in reports[0].get("mentions", {}).values():
        for span in spans:
            require(
                text[span["start"] : span["end"]] == span["text"]
                and text.encode("utf-16-le")[
                    span["start_utf16"] * 2 : span["end_utf16"] * 2
                ].decode("utf-16-le")
                == span["text"],
                "exact_unicode_and_utf16_source_spans",
                receipt,
            )
    provenance = analysis.get("provenance", {})
    model_client = Client(local_origin(args.ollama_url))
    _, models = model_client.json("/api/tags")
    installed = next(
        (m for m in models.get("models", []) if m.get("name") == args.model), {}
    )
    require(
        provenance.get("model") == args.model
        and provenance.get("model_digest") == installed.get("digest")
        and bool(re.fullmatch(r"[0-9a-f]{64}", str(installed.get("digest", ""))))
        and provenance.get("sampling", {}).get("num_gpu") == 0,
        "actual_owned_local_model_identity_and_cpu_request",
        receipt,
    )
    receipt["local_ai"] = {
        "model": provenance["model"],
        "model_digest": provenance["model_digest"],
        "generated_at": analysis["generated_at"],
        "prompt_eval_count": provenance.get("prompt_eval_count"),
        "eval_count": provenance.get("eval_count"),
        "total_duration_ns": provenance.get("total_duration_ns"),
        "system_sha256": provenance.get("system_sha256"),
        "source_snapshot_sha256": analysis.get("source_snapshot_sha256"),
        "model_calls_qualified": 1,
        "paid_api": False,
    }
    status, _ = client.json("/briefing/video", data={"event_ids": [event["id"]]})
    require(status == 202, "video_job_admitted", receipt)
    video_status = poll_job(
        client,
        "video",
        old_status["video"].get("last_attempt_at"),
        args.timeout,
        receipt,
    )
    _, manifest = client.json("/briefing/video/manifest")
    sources = manifest.get("sources", [])
    require(
        manifest.get("generated_at") == video_status.get("last_success_at")
        and len(sources) == 1
        and source_binding(sources[0], event),
        "new_video_is_bound_to_actual_source",
        receipt,
    )
    require(
        canonical_hash(sources)
        == manifest.get("source_snapshot_sha256")
        == analysis.get("source_snapshot_sha256"),
        "video_snapshot_hash_recomputed_and_matches_analysis",
        receipt,
    )
    digest = manifest.get("sha256", "")
    filename = digest[:32] + ".mp4"
    require(
        bool(re.fullmatch(r"[0-9a-f]{64}", digest))
        and manifest.get("filename") == filename
        and manifest.get("url") == "/api/briefing/video/" + filename,
        "content_addressed_video_name_and_url",
        receipt,
    )
    _, _, mp4 = client.get("/briefing/video/" + filename, limit=40_000_000)
    require(
        len(mp4) == manifest.get("bytes") and hashlib.sha256(mp4).hexdigest() == digest,
        "downloaded_mp4_exact_full_sha256_and_size",
        receipt,
    )
    status, headers, partial = client.get(
        "/briefing/video/" + filename, headers={"Range": "bytes=0-31"}, limit=64
    )
    normalized = {k.lower(): v for k, v in headers.items()}
    require(
        status == 206
        and partial == mp4[:32]
        and normalized.get("content-range") == f"bytes 0-31/{len(mp4)}",
        "actual_http_206_byte_range",
        receipt,
    )
    destination = Path(args.media_dir)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / filename
    path.write_bytes(mp4)
    probe = subprocess.run(
        [
            args.ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels:format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    require(
        probe.returncode == 0 and len(probe.stdout) < 20_000,
        "independent_mp4_probe",
        receipt,
    )
    streams = json.loads(probe.stdout).get("streams", [])
    require(
        len(streams) == 2
        and any(
            s.get("codec_name") == "h264"
            and s.get("width") == 1280
            and s.get("height") == 720
            for s in streams
        )
        and any(
            s.get("codec_name") == "aac" and s.get("channels", 0) >= 1 for s in streams
        ),
        "actual_h264_720p_and_aac_streams",
        receipt,
    )
    decode = subprocess.run(
        [
            args.ffmpeg,
            "-v",
            "error",
            "-nostdin",
            "-xerror",
            "-err_detect",
            "explode",
            "-threads",
            "2",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=180,
        check=False,
    )
    require(
        decode.returncode == 0, "independent_complete_video_and_audio_decode", receipt
    )
    segments = manifest.get("validation", {}).get("audio_segments", [])
    require(
        len(segments) == 3
        and all(
            s.get("rms_pcm16", 0) >= 25 and s.get("clipped_fraction", 1) <= 0.05
            for s in segments
        )
        and manifest.get("validation", {}).get("full_decode") == "passed",
        "server_pcm_energy_and_full_decode_receipts",
        receipt,
    )
    receipt["video"] = {
        "generated_at": manifest["generated_at"],
        "sha256": digest,
        "filename": filename,
        "bytes": len(mp4),
        "duration_seconds": manifest.get("duration_seconds"),
        "source_snapshot_sha256": manifest.get("source_snapshot_sha256"),
        "voice_model_sha256": manifest.get("voice_model_sha256"),
        "download_path": str(path),
        "streams": streams,
    }
    after = database_snapshot(args.docker_db_container, event["id"])
    require(
        after.get("event") == before.get("event"),
        "source_report_not_mutated_by_generation",
        receipt,
    )
    receipt["usage_log_rows_after"] = after["usage_log_rows"]
    require(
        before["usage_log_rows"] == after["usage_log_rows"] == 0,
        "no_recorded_paid_usage_rows_before_or_after",
        receipt,
    )
    _, final_health = client.json("/health")
    require(
        final_health.get("status") == "healthy",
        "core_readiness_after_optional_jobs",
        receipt,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:5190/api")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11502")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--event-id", type=int)
    parser.add_argument("--env-file")
    parser.add_argument("--docker-db-container", default="cmonitor-live-db-1")
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument(
        "--media-dir", default="artifacts/private/generation-qualification"
    )
    parser.add_argument(
        "--output", default="artifacts/local-generation-production.json"
    )
    args = parser.parse_args(argv)
    receipt = {
        "started_at": utc().isoformat(),
        "status": "NOT_EXECUTED",
        "scope": "Actual loopback production API, PostGIS, owned local model and local speech/video generation",
        "limitations": [
            "Source truth, independent corroboration, precise incident locations and model general accuracy remain unverified.",
            "Paid UsageLog rows do not count local inference or electricity. A successful run qualifies one new local inference job.",
            "Successful decoding/PCM checks do not certify listener audibility or pronunciation.",
        ],
    }
    result = 2
    try:
        local_origin(args.base_url, api=True)
        local_origin(args.ollama_url)
        if not 10 <= args.timeout <= 900 or (
            args.event_id is not None and args.event_id <= 0
        ):
            raise VerificationError("Invalid qualification bounds")
        if not args.execute:
            receipt["reason"] = (
                "Pass --execute to authorize one actual local analysis and video job"
            )
        else:
            execute(args, receipt)
            receipt["status"] = "PASS"
            result = 0
    except Exception as exc:  # noqa: BLE001 - sanitize every failure before writing a public receipt
        receipt["status"] = "FAIL"
        receipt["error_type"] = type(exc).__name__
        receipt["reason"] = (
            str(exc)
            if isinstance(exc, VerificationError)
            else "Qualification could not complete; raw exception suppressed"
        )
        result = 1
    finally:
        receipt["ended_at"] = utc().isoformat()
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            previous = output.with_name(
                output.stem
                + "-prior-"
                + utc().strftime("%Y%m%dT%H%M%S%f")
                + output.suffix
            )
            shutil.copyfile(output, previous)
        output.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "status": receipt["status"],
                    "receipt": str(output),
                    "checks": receipt.get("checks", {}),
                    "reason": receipt.get("reason"),
                }
            ),
            flush=True,
        )
    return result


if __name__ == "__main__":
    sys.exit(main())

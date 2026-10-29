"""Review captured synthetic outputs offline; model execution is explicit.

Default: verify bundle hashes, replay all output gates, recompute label metrics.
--execute-model: three bounded requests against an already owned local Ollama;
no service startup, model download, private data, credentials, or app writes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import sys
import time
from pathlib import Path
from urllib import request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def label_metrics(cases, predictions):
    predicted = {row.get("id"): row for row in predictions if isinstance(row, dict)}
    result = {}
    for field, labels in (
        ("relevance", ("relevant", "not_relevant", "uncertain")),
        ("stance", ("reported", "denied", "uncertain")),
    ):
        per_label = {}
        for label in labels:
            tp = sum(
                row[field] == label and predicted.get(row["id"], {}).get(field) == label
                for row in cases
            )
            fp = sum(
                row[field] != label and predicted.get(row["id"], {}).get(field) == label
                for row in cases
            )
            fn = sum(
                row[field] == label and predicted.get(row["id"], {}).get(field) != label
                for row in cases
            )
            per_label[label] = {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
            }
        result[field] = {
            "correct": sum(
                predicted.get(row["id"], {}).get(field) == row[field] for row in cases
            ),
            "total": len(cases),
            "by_label": per_label,
            "abstentions": sum(
                predicted.get(row["id"], {}).get(field) == "uncertain" for row in cases
            ),
        }
    expected = {
        (row["id"], place.casefold())
        for row in cases
        for place in row.get("places", [])
    }
    found = {
        (identity, str(place).casefold())
        for identity, row in predicted.items()
        for place in row.get("place_mentions", [])
    }
    tp = len(expected & found)
    result["places"] = {
        "tp": tp,
        "fp": len(found - expected),
        "fn": len(expected - found),
        "precision": tp / len(found) if found else None,
        "recall": tp / len(expected) if expected else None,
    }
    result["required_actor_cases"] = [
        {
            "id": row["id"],
            "expected": row["required_actor"],
            "found": row["required_actor"]
            in predicted.get(row["id"], {}).get("actor_mentions", []),
        }
        for row in cases
        if "required_actor" in row
    ]
    result["quantity_range_cases"] = [
        {
            "id": row["id"],
            "expected_numbers": row["numbers"],
            "all_found": all(
                number
                in " ".join(predicted.get(row["id"], {}).get("quantity_mentions", []))
                for number in row["numbers"]
            ),
        }
        for row in cases
        if "numbers" in row
    ]
    return result


def snapshot_for(cases, ids):
    by_id = {row["id"]: row for row in cases}
    return [
        {
            "id": identity,
            "text": by_id[identity]["text"],
            "source": "synthetic_heldout_fixture",
        }
        for identity in ids
    ]


def load_validator():
    spec = importlib.util.spec_from_file_location(
        "public_validator_snapshot", ROOT / "validator_snapshot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_extraction


def verify_bundle():
    manifest = load("bundle-manifest.json")
    for row in manifest["files"]:
        path = ROOT / row["path"]
        if (
            path.parent != ROOT
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]
        ):
            raise ValueError("Bundle byte manifest mismatch: " + row["path"])
    provenance, frozen = load("provenance.json"), load("frozen-evaluation.json")
    if (
        hashlib.sha256((ROOT / "fixtures.json").read_bytes()).hexdigest()
        != frozen["fixture_sha256"]
    ):
        raise ValueError("Frozen fixture changed")
    if (
        hashlib.sha256((ROOT / "system-prompt.txt").read_bytes()).hexdigest()
        != frozen["system_sha256"]
    ):
        raise ValueError("Frozen prompt changed")
    validate = load_validator()
    if (
        hashlib.sha256(inspect.getsource(validate).encode()).hexdigest()
        != provenance["current_validator_function_sha256"]
    ):
        raise ValueError("Validator snapshot changed")
    return validate


def replay_saved(validate, cases):
    saved = [("cpu", row) for row in load("cpu-results.json")["results"]]
    saved.append(("gpu", load("gpu-results.json")))
    summary = []
    for profile, result in saved:
        decisions = []
        for batch in result["batches"]:
            try:
                validate(batch["raw_model_content"], snapshot_for(cases, batch["ids"]))
                decision = "accepted"
            except (ValueError, TypeError, RecursionError):
                decision = "rejected"
            if decision != batch["production_gate"]:
                raise ValueError("Stored gate decision changed")
            decisions.append(decision)
        metrics = label_metrics(cases, result["raw_predictions"])
        if metrics != result["metrics"]:
            raise ValueError("Recorded label metric does not recompute")
        summary.append(
            {
                "profile": profile,
                "model": result["model"],
                "model_digest": result["model_digest"],
                "decisions": decisions,
                "accepted_reports": result["accepted_reports"],
                "seconds": result["seconds"],
                "metrics": metrics,
            }
        )
    return summary


def local_endpoint(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or not parsed.port
        or parsed.path.rstrip("/")
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use an owned loopback HTTP origin with an explicit port")
    return value.rstrip("/")


def bounded_json(opener, url, *, body=None, limit=64000):
    req = request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode()
        if body is not None
        else None,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with opener.open(req, timeout=360) as response:
        data = bytearray()
        while block := response.read(8192):
            if len(data) + len(block) > limit:
                raise ValueError("Model response exceeds byte budget")
            data.extend(block)
    return json.loads(data), hashlib.sha256(data).hexdigest(), len(data)


def execute_model(args, validate, cases):
    origin = local_endpoint(args.base_url)
    opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
    inventory, _, _ = bounded_json(opener, origin + "/api/tags", limit=200000)
    installed = next(
        (row for row in inventory.get("models", []) if row.get("name") == args.model),
        None,
    )
    if not installed:
        raise ValueError(
            "Requested model is not installed; this tool never downloads it"
        )
    profile = load("request-profile.json")
    schema = load("request-schema.json")
    system = (ROOT / "system-prompt.txt").read_text(encoding="utf-8")
    result = {
        "model": args.model,
        "model_digest": installed["digest"],
        "num_gpu_request": args.num_gpu,
        "scope": "Repeated execution of the same synthetic sample, not new independent held-out data",
        "batches": [],
        "raw_predictions": [],
    }
    for start in range(0, len(cases), 4):
        ids = [row["id"] for row in cases[start : start + 4]]
        snapshot = snapshot_for(cases, ids)
        options = {**profile["options"], "num_gpu": args.num_gpu}
        body = {
            "model": args.model,
            "stream": False,
            "think": False,
            "keep_alive": 0,
            "format": schema,
            "options": options,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"untrusted_reports": snapshot}, ensure_ascii=False
                    ),
                },
            ],
        }
        batch = {"ids": ids}
        begin = time.monotonic()
        try:
            response, digest, size = bounded_json(
                opener, origin + "/api/chat", body=body
            )
            raw = response.get("message", {}).get("content", "")
            batch.update(
                response_bytes=size,
                response_sha256=digest,
                raw_model_content=raw,
                done=response.get("done"),
                done_reason=response.get("done_reason"),
                eval_count=response.get("eval_count"),
            )
            if (
                response.get("done") is not True
                or response.get("done_reason") != "stop"
            ):
                raise ValueError("Model response is incomplete")
            result["raw_predictions"].extend(json.loads(raw).get("reports", []))
            output = validate(raw, snapshot)
            batch.update(
                production_gate="accepted", accepted_ids=[row["id"] for row in output]
            )
        except Exception as exc:  # noqa: BLE001 - bounded synthetic execution receipt; no credentials are used
            batch.update(production_gate="rejected", error_type=type(exc).__name__)
        batch["seconds"] = round(time.monotonic() - begin, 3)
        result["batches"].append(batch)
        print(
            json.dumps(
                {
                    "batch_ids": ids,
                    "gate": batch["production_gate"],
                    "seconds": batch["seconds"],
                }
            ),
            flush=True,
        )
    result["metrics"] = label_metrics(cases, result["raw_predictions"])
    result["seconds"] = sum(row["seconds"] for row in result["batches"])
    result["accepted_reports"] = sum(
        len(row.get("accepted_ids", [])) for row in result["batches"]
    )
    result["status"] = "COMPLETED_EVALUATION"
    result["output_gate_all_rows_passed"] = result["accepted_reports"] == len(cases)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-model", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--model",
        choices=("qwen3.5:4b", "qwen3:8b", "qwen3:0.6b"),
        default="qwen3.5:4b",
    )
    parser.add_argument("--num-gpu", type=int, choices=(0, 99), default=0)
    parser.add_argument(
        "--output", help="Optional new-run receipt; never modifies the bundled evidence"
    )
    args = parser.parse_args(argv)
    validate = verify_bundle()
    cases = load("fixtures.json")
    summaries = replay_saved(validate, cases)
    if args.execute_model:
        result = execute_model(args, validate, cases)
        if args.output:
            output = Path(args.output)
            if output.resolve().is_relative_to(ROOT):
                raise ValueError("Write new-run receipts outside the immutable bundle")
            if output.exists():
                raise ValueError("New-run receipt already exists; choose a new path")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(
            json.dumps(
                {
                    "model": result["model"],
                    "accepted_reports": result["accepted_reports"],
                    "status": result["status"],
                    "output_gate_all_rows_passed": result[
                        "output_gate_all_rows_passed"
                    ],
                    "seconds": result["seconds"],
                    "metrics": result["metrics"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if result["output_gate_all_rows_passed"] else 1
    else:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "mode": "offline_replay_no_model_calls",
                    "stored_batches_replayed": 12,
                    "case_count": len(cases),
                    "profiles": summaries,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

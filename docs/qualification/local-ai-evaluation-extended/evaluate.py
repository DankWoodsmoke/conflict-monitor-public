"""Review a fresh authored stress set; local CPU execution requires --execute.

Imports only the public synthetic evaluation helpers, not the application or GOOL.
No keys, real reporting, service startup, downloads, retries, or app writes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "local-ai-evaluation"


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def baseline():
    spec = importlib.util.spec_from_file_location(
        "public_baseline_review", BASE / "replay.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_freeze(review):
    frozen = read("frozen.json")
    for relative, expected in frozen["files"].items():
        path = (ROOT / relative).resolve()
        if (
            path not in {ROOT / "fixtures.json", ROOT / "evaluate.py"}
            and path.parent != BASE
        ):
            raise ValueError("Unexpected evaluation dependency")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen evaluation dependency changed: " + relative)
    validate = review.verify_bundle()
    cases = read("fixtures.json")
    if len(cases) != 24 or len({row["id"] for row in cases}) != 24:
        raise ValueError("Expected exactly 24 unique authored cases")
    return validate, cases


def assess(review, validate, cases, result):
    by_id = {row["id"]: row for row in cases}
    predictions = {
        row.get("id"): row for row in result["raw_predictions"] if isinstance(row, dict)
    }
    accepted = set()
    decisions = []
    offsets = []
    rejected = []
    for batch in result["batches"]:
        snapshot = review.snapshot_for(cases, batch["ids"])
        try:
            rows = validate(batch["raw_model_content"], snapshot)
            decision = "accepted"
            accepted.update(row["id"] for row in rows)
            for row in rows:
                if row["coordinates"] is not None or row["severity"] is not None:
                    raise AssertionError("Unsupported model inference escaped the gate")
                for mentions in row["mentions"].values():
                    for span in mentions:
                        text = by_id[row["id"]]["text"]
                        if text[span["start"] : span["end"]] != span["text"]:
                            raise AssertionError("Codepoint span changed source bytes")
                        utf16 = text.encode("utf-16-le")
                        if (
                            utf16[
                                2 * span["start_utf16"] : 2 * span["end_utf16"]
                            ].decode("utf-16-le")
                            != span["text"]
                        ):
                            raise AssertionError("UTF16 span changed source bytes")
                        offsets.append(row["id"])
        except (ValueError, TypeError, RecursionError):
            decision = "rejected"
            rejected.extend(batch["ids"])
        if decision != batch["production_gate"]:
            raise ValueError("Recorded batch decision does not replay")
        decisions.append(decision)
    metrics = review.label_metrics(cases, result["raw_predictions"])
    if metrics != result["metrics"]:
        raise ValueError("Saved metric does not recompute")
    return {
        "case_count": len(cases),
        "raw_metrics": metrics,
        "batch_decisions": decisions,
        "accepted_reports": len(accepted),
        "rejected_ids": rejected,
        "accepted_span_count": len(offsets),
        "accepted_span_units_checked": ["unicode_codepoints", "utf16_code_units"],
        "unsupported_coordinates_or_severity_accepted": 0,
        "case_results": [
            {
                "id": row["id"],
                "category": row["category"],
                "batch_accepted": row["id"] in accepted,
                "expected_relevance": row["relevance"],
                "actual_relevance": predictions.get(row["id"], {}).get("relevance"),
                "expected_stance": row["stance"],
                "actual_stance": predictions.get(row["id"], {}).get("stance"),
            }
            for row in cases
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:11502")
    parser.add_argument("--output", default=str(ROOT / "cpu-results.json"))
    args = parser.parse_args()
    review = baseline()
    validate, cases = verify_freeze(review)
    output = Path(args.output)
    if args.execute:
        if output.exists():
            raise ValueError("Never overwrite a prior model result")
        result = review.execute_model(
            SimpleNamespace(base_url=args.base_url, model="qwen3.5:4b", num_gpu=0),
            validate,
            cases,
        )
        result["scope"] = (
            "Fresh 24-case authored stress set; expectations and unchanged evaluation dependencies frozen before these calls. Not independent human annotation or real-news accuracy."
        )
        result["assessment"] = assess(review, validate, cases, result)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        result = json.loads(output.read_text(encoding="utf-8"))
        if assess(review, validate, cases, result) != result["assessment"]:
            raise ValueError("Saved assessment does not replay")
    print(
        json.dumps(
            {
                "status": "EVALUATION_REPLAY_PASS",
                "mode": "six_new_local_requests"
                if args.execute
                else "offline_no_model_calls",
                "model": result["model"],
                "model_digest": result["model_digest"],
                "seconds": result["seconds"],
                **result["assessment"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    # A successful audit retains failures; it does not claim semantic success.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

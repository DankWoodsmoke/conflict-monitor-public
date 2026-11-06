import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import httpx
import pytest


TOOL = Path(__file__).resolve().parents[2] / "tools" / "run_gool_review.py"
SPEC = importlib.util.spec_from_file_location("operator_gool_review", TOOL)
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)
SNAPSHOT_AT = "2026-11-04T20:10:00Z"


def packet(*, source="Port exercise", platform="authored_fixture", url="https://example.test/one"):
    def row(i, name, source_platform, address, text):
        return {
            "id": i, "source": name, "source_platform": source_platform,
            "published_at": "2026-11-04T20:00:00Z", "source_url": address, "text": text,
            "headline": "Authored exercise", "text_truncated": False,
            "original_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
    rows = [
        row(41, source, platform, url, "🧭 The gate opened. The desk did not claim that ferry service resumed."),
        row(42, "Ferry exercise", "authored_fixture", "https://example.test/two",
            "The ferry operator reported that departures remained suspended."),
    ]
    return runner.build_packet(rows, snapshot_at=SNAPSHOT_AT).model_dump(mode="json")


def endpoint(*, prompt_price="0.000001", provider=runner.PRIMARY.endpoint, status=0, safety_retention=False):
    return {"data": [{
        "tag": provider, "model_id": runner.PRIMARY.model, "context_length": 131072,
        "status": status, "safety_retention": safety_retention,
        "pricing": {"prompt": prompt_price, "completion": "0.000003"},
        "supported_parameters": ["structured_outputs", "response_format", "reasoning", "max_tokens"],
    }]}


def provider_reply(*, choice_text=None, finish="stop", model=runner.PRIMARY.model):
    content = choice_text if choice_text is not None else json.dumps({"candidates": [{
        "kind": "alternative_to_check", "question": "Could gate access and ferry service have separate clocks?",
        "span_ids": ["s1", "s2"],
    }]})
    return {
        "model": model, "provider": "Nebius",
        "choices": [{"finish_reason": finish, "message": {"content": content}}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 35, "total_tokens": 935, "cost": 0.001005},
    }


def test_provider_run_preserves_citations_and_private_boundary(tmp_path):
    value = packet()
    result_dir = tmp_path / "run"
    calls, guards = [], []

    def handler(request):
        calls.append((request.method, str(request.url)))
        assert request.url.host == "openrouter.ai"
        if request.method == "GET":
            assert "authorization" not in request.headers
            assert request.url.path.endswith("/endpoints/zdr")
            return httpx.Response(200, json=endpoint())
        reserved = json.loads((result_dir / "receipt.json").read_text())
        assert reserved["status"] == "reserved" and reserved["inference_attempts"] == 1
        assert reserved["reserved_usd"] == "0.15"
        body = json.loads(request.content)
        assert "tools" not in body and "plugins" not in body and "example.test" not in request.content.decode()
        assert body["provider"]["only"] == ["nebius/fp8"]
        assert body["provider"]["allow_fallbacks"] is False and body["provider"]["zdr"] is True
        assert body["provider"]["max_price"] == {"prompt": 1, "completion": 3, "request": 0}
        assert body["reasoning"] == {"enabled": False}
        return httpx.Response(200, json=provider_reply())

    result = asyncio.run(runner.review(value, value["snapshot_sha256"], result_dir, "fixture-secret-key",
                                       lambda question, citations: guards.append((question, citations)), {},
                                       transport=httpx.MockTransport(handler)))
    assert result["status"] == "validated_private_review" and result["provider_charge"] == "observed"
    assert [method for method, _ in calls] == ["GET", "POST"] and len(guards) == 1
    assert "fixture-secret-key" not in (result_dir / "receipt.json").read_text()
    artifact = json.loads((result_dir / "review.private.json").read_bytes())
    assert artifact["event_mutation_allowed"] is artifact["publication_allowed"] is False
    assert artifact["semantic_usefulness"] == "unverified"
    citation = artifact["candidates"][0]["citations"][0]
    assert citation["quote"] == value["sources"][0]["text"]
    assert citation["end_utf16"] == citation["end"] + 1


def test_azure_route_requires_explicit_selection_without_cascade(tmp_path):
    value = packet()
    route = runner.ROUTES["azure-mini"]
    route_quote = endpoint(prompt_price="0.00000015", provider="azure")
    details = route_quote["data"][0]
    details["model_id"] = route.model
    details["context_length"] = 128000
    details["pricing"]["completion"] = "0.0000006"
    details["supported_parameters"].remove("reasoning")
    details["supported_parameters"].remove("max_tokens")
    details["supported_parameters"].append("max_completion_tokens")
    calls = []
    def handler(request):
        calls.append(request.method)
        if request.method == "GET":
            assert request.url.path.endswith("/endpoints/zdr")
            return httpx.Response(200, json=route_quote)
        request_body = json.loads(request.content)
        assert request_body["model"] == route.model and "reasoning" not in request_body
        assert request_body["max_completion_tokens"] == 1024 and "max_tokens" not in request_body
        assert request_body["provider"]["only"] == ["azure"]
        return httpx.Response(200, json={**provider_reply(model=route.model), "provider": "Azure"})
    receipt = asyncio.run(runner.review(value, value["snapshot_sha256"], tmp_path / "azure", "fixture",
                                        lambda *_: None, {}, route=route, transport=httpx.MockTransport(handler)))
    assert receipt["status"] == "validated_private_review" and receipt["reserved_usd"] == "0.02"
    assert calls == ["GET", "POST"]


@pytest.mark.parametrize("source,platform,url", [
    ("Telegram archive", "authored_fixture", "https://example.test/one"),
    ("Port", "telegram_public", "https://example.test/one"),
    ("Port", "authored_fixture", "https://example.telegram.dog/public/5"),
])
def test_telegram_aliases_are_rejected_before_reservation(source, platform, url, tmp_path):
    value = packet(source=source, platform=platform, url=url)
    with pytest.raises(runner.SourcePermissionRequired):
        asyncio.run(runner.review(value, value["snapshot_sha256"], tmp_path / "run",
                                  "fixture", lambda *_: None, {}))
    assert not list(tmp_path.iterdir())


def test_stale_approval_rejects_before_reservation(tmp_path):
    with pytest.raises(ValueError, match="Approved input hash"):
        asyncio.run(runner.review(packet(), "0" * 64, tmp_path / "run", "fixture", lambda *_: None, {}))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("reply,quote,attempted", [
    (provider_reply(finish="length"), endpoint(), 1),
    (provider_reply(model="different-model"), endpoint(), 1),
    (provider_reply(choice_text='{"candidates":[],"candidates":[]}'), endpoint(), 1),
    (provider_reply(choice_text='{"candidates":[{"kind":"missing_evidence","question":"Where is evidence?","span_ids":["s999"]}]}'),
     endpoint(), 1),
    (provider_reply(), endpoint(prompt_price="0.000002"), 0),
    (provider_reply(), endpoint(provider="another-route"), 0),
    (provider_reply(), endpoint(safety_retention=True), 0),
    (provider_reply(), endpoint(status=-5), 0),
])
def test_failures_never_emit_an_analyst_artifact(tmp_path, reply, quote, attempted):
    def handler(request):
        return httpx.Response(200, json=quote if request.method == "GET" else reply)
    value = packet()
    directory = tmp_path / "run"
    receipt = asyncio.run(runner.review(value, value["snapshot_sha256"], directory, "fixture",
                                        lambda *_: None, {}, transport=httpx.MockTransport(handler)))
    assert receipt["status"] == "failed" and receipt["inference_attempts"] == attempted
    assert not (directory / "review.private.json").exists()


def test_cancelled_request_reserves_unknown_charge_and_has_no_artifact(tmp_path):
    async def exercise():
        accepted = asyncio.Event()
        async def handler(request):
            if request.method == "GET":
                return httpx.Response(200, json=endpoint())
            accepted.set()
            await asyncio.sleep(60)
        value = packet()
        directory = tmp_path / "run"
        task = asyncio.create_task(runner.review(value, value["snapshot_sha256"], directory, "fixture",
                                                  lambda *_: None, {}, transport=httpx.MockTransport(handler)))
        await asyncio.wait_for(accepted.wait(), timeout=3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        receipt = json.loads((directory / "receipt.json").read_bytes())
        assert receipt["status"] == "cancelled" and receipt["provider_charge"] == "unresolved"
        assert receipt["inference_attempts"] == 1 and not (directory / "review.private.json").exists()
    asyncio.run(exercise())

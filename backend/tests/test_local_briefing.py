"""Safety and behavior gates for free local inference and source-card video."""

import asyncio
import hashlib
import json
import math
import struct
import sys
import wave
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from app.services import briefing_video as video
from app.services import local_briefing as local
from fastapi.testclient import TestClient


def snapshot(
    text="Officials denied an airstrike in Beirut. No casualties were confirmed.",
):
    return [
        {
            "id": 17,
            "text": text,
            "headline": text,
            "source": "Publisher",
            "published_at": local.clock().isoformat(),
            "source_url": "https://example.org/report",
            "original_text_sha256": "a" * 64,
            "text_truncated": False,
        }
    ]


def output(**changes):
    row = {
        "id": 17,
        "relevance": "relevant",
        "stance": "denied",
        "place_mentions": ["Beirut"],
        "actor_mentions": ["Officials"],
        "quantity_mentions": [],
    }
    row.update(changes)
    return json.dumps({"reports": [row]})


def test_literal_spans_preserve_full_denial_without_coordinates():
    row = local.validate_extraction(output(), snapshot())[0]
    span = row["mentions"]["place_mentions"][0]
    assert row["text"][span["start"] : span["end"]] == "Beirut"
    assert "denied" in row["text"] and "No casualties" in row["text"]
    assert row["coordinates"] is None and row["severity"] is None


def test_non_bmp_literal_span_offsets_include_explicit_javascript_utf16_units():
    row = local.validate_extraction(
        output(), snapshot("🛰️ Officials denied an airstrike in Beirut.")
    )[0]
    span = row["mentions"]["place_mentions"][0]
    assert (
        span["offset_unit"] == "unicode_codepoints"
        and span["start_utf16"] == span["start"] + 1
    )
    utf16 = row["text"].encode("utf-16-le")
    assert (
        utf16[span["start_utf16"] * 2 : span["end_utf16"] * 2].decode("utf-16-le")
        == "Beirut"
    )


def test_deeply_nested_manifest_returns_controlled_unavailable(monkeypatch, tmp_path):
    from app.routes import briefing

    monkeypatch.setattr(local.settings, "briefing_artifact_dir", str(tmp_path))
    (tmp_path / "analysis.json").write_text("[" * 4000 + "0" + "]" * 4000)
    with pytest.raises(Exception) as error:
        briefing.artifact("analysis.json")
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 18},
        {"stance": "reported"},
        {"place_mentions": ["Tehran"]},
        {"place_mentions": ["Beirut", "Beirut"]},
        {"place_mentions": ["Beir"]},
        {"lat": 33.9},
        {"severity": 9},
        {"relevance": "not_relevant"},
    ],
)
def test_reject_identity_negation_invented_spans_and_model_coordinates(changes):
    with pytest.raises(ValueError):
        local.validate_extraction(output(**changes), snapshot())


@pytest.mark.parametrize(
    "url",
    [
        "https://remote.example:443",
        "http://127.0.0.1:11501/evil",
        "http://user:fixture-password@localhost:11434",
        "http://localhost:11434?model=x",
        "http://127.0.0.1",
    ],
)
def test_model_origin_is_local_explicit_and_cannot_supply_paths_or_credentials(url):
    with pytest.raises(ValueError):
        local.local_url(url)


def test_explicit_docker_desktop_host_alias_and_loopback_are_supported():
    assert (
        local.local_url("http://host.docker.internal:11501/")
        == "http://host.docker.internal:11501"
    )
    assert local.local_url("http://127.0.0.1:11501") == "http://127.0.0.1:11501"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [
        {"done": False},
        {"done_reason": "length"},
        {"model": "private-model"},
        {"message": {"content": output(), "tool_calls": [{}]}},
    ],
)
async def test_incomplete_or_changed_model_response_cannot_be_published(
    monkeypatch, patch
):
    data = {
        "model": "qwen3:8b",
        "done": True,
        "done_reason": "stop",
        "message": {"content": output()},
    }
    data.update(patch)

    def respond(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:8b", "digest": "a" * 64}]}
            )
        body = json.loads(request.content)
        assert (
            body["keep_alive"] == 0
            and body["options"]["num_gpu"] == 0
            and body["stream"] is False
        )
        assert "tools" not in body
        return httpx.Response(200, json=data)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        local.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )
    monkeypatch.setattr(local.settings, "local_ai_model", "qwen3:8b")
    monkeypatch.setattr(local.settings, "local_ai_num_gpu", 0)
    with pytest.raises(ValueError):
        await local.request_extraction(snapshot())


@pytest.mark.asyncio
async def test_failed_analysis_preserves_last_good_artifact_and_records_local_attempt(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(local.settings, "briefing_artifact_dir", str(tmp_path))
    monkeypatch.setattr(local.settings, "enable_local_ai", True)
    monkeypatch.setattr(local.settings, "demo_mode", False)
    old = {
        "status": "available",
        "generated_at": local.clock().isoformat(),
        "reports": [{"id": 99}],
    }
    local.atomic_json(local.artifact_path("analysis.json"), old)
    monkeypatch.setattr(local, "source_snapshot", AsyncMock(return_value=snapshot()))
    monkeypatch.setattr(
        local, "request_extraction", AsyncMock(side_effect=ValueError("reject"))
    )
    with pytest.raises(ValueError):
        await local.analyze()
    assert local.read_artifact("analysis.json") == old
    assert local.get_status()["state"] == "failed"
    line = json.loads((tmp_path / "local-calls.jsonl").read_text())
    assert line["paid_api"] is False and line["inference_attempted"] is True


@pytest.mark.asyncio
async def test_disabled_analysis_never_contacts_model(monkeypatch):
    monkeypatch.setattr(local.settings, "enable_local_ai", False)
    request = AsyncMock()
    monkeypatch.setattr(local, "request_extraction", request)
    with pytest.raises(ValueError):
        await local.analyze()
    request.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_source_fails_before_model_or_published_artifact(monkeypatch):
    row = SimpleNamespace(
        id=17,
        source="rss_test",
        timestamp=local.clock() - timedelta(days=3),
        raw_text="old",
        summary="old",
        source_url="https://example.org",
        channel_name="publisher",
    )
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [row]))

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        execute = AsyncMock(return_value=result)

    monkeypatch.setattr(local, "async_session", Session)
    with pytest.raises(ValueError, match="stale"):
        await local.source_snapshot([17])


def write_wave(path, amplitude):
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        wav.writeframes(
            b"".join(
                struct.pack(
                    "<h", int(amplitude * math.sin(i * 2 * math.pi * 440 / 22050))
                )
                for i in range(22050)
            )
        )


def test_audio_gate_distinguishes_real_energy_from_silence(tmp_path):
    good = tmp_path / "good.wav"
    silent = tmp_path / "silent.wav"
    write_wave(good, 1000)
    write_wave(silent, 0)
    assert video.audio_check(good)["rms_pcm16"] > 500
    with pytest.raises(ValueError, match="silent"):
        video.audio_check(silent)


@pytest.mark.asyncio
async def test_real_media_child_output_flood_is_bounded_and_process_reaped(monkeypatch):
    original = asyncio.create_subprocess_exec
    children = []

    async def capture(*args, **kwargs):
        child = await original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", capture)
    with pytest.raises(ValueError, match="byte budget"):
        await video.run_process(
            [
                sys.executable,
                "-c",
                "import sys,time;sys.stdout.write('x'*3000000);sys.stdout.flush();time.sleep(30)",
            ],
            timeout=5,
        )
    assert children[0].returncode is not None


@pytest.mark.asyncio
async def test_real_media_child_timeout_and_cancellation_reap_owned_process(
    monkeypatch,
):
    original = asyncio.create_subprocess_exec
    children = []

    async def capture(*args, **kwargs):
        child = await original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", capture)
    with pytest.raises(TimeoutError):
        await video.run_process(
            [sys.executable, "-c", "import time;time.sleep(30)"], timeout=0.2
        )
    task = asyncio.create_task(
        video.run_process(
            [sys.executable, "-c", "import time;time.sleep(30)"], timeout=30
        )
    )
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(child.returncode is not None for child in children)


def test_source_cards_preserve_denial_and_dates_and_do_not_invent_footage():
    rows = snapshot()
    segments = video.build_segments(rows, local.clock().isoformat())
    assert segments[1]["body"] == rows[0]["headline"]
    assert "denied" in segments[1]["narration"]
    assert rows[0]["source_url"] in segments[1]["footer"]
    assert "No incident footage" in segments[0]["narration"]


def test_non_english_narration_abstains_instead_of_inventing_translation():
    rows = snapshot("نفت الوزارة وقوع غارة في بيروت.")
    segment = video.build_segments(rows, local.clock().isoformat())[1]
    assert segment["body"] == rows[0]["headline"]
    assert "No translation has been generated" in segment["narration"]


def test_public_artifact_age_and_admin_gate(monkeypatch, tmp_path):
    from app.main import app
    from app.routes import briefing

    monkeypatch.setattr(local.settings, "briefing_artifact_dir", str(tmp_path))
    monkeypatch.setattr(local.settings, "admin_api_key", "")
    local.atomic_json(
        local.artifact_path("analysis.json"),
        {
            "status": "available",
            "generated_at": (local.clock() - timedelta(hours=2)).isoformat(),
            "reports": [],
        },
    )
    assert briefing.artifact("analysis.json")["stale"] is True
    client = TestClient(app)
    assert client.post("/briefing/analyze", json={"event_ids": [17]}).status_code == 503
    assert client.get("/briefing/video/../analysis.json").status_code == 404


def test_video_content_address_integrity_and_byte_range_support(monkeypatch, tmp_path):
    from app.main import app

    monkeypatch.setattr(local.settings, "briefing_artifact_dir", str(tmp_path))
    data = b"fixture-payload-for-range-transport-only"
    digest = hashlib.sha256(data).hexdigest()
    filename = digest[:32] + ".mp4"
    (tmp_path / filename).write_bytes(data)
    manifest = {
        "generated_at": local.clock().isoformat(),
        "filename": filename,
        "url": f"/api/briefing/video/{filename}",
        "bytes": len(data),
        "sha256": digest,
    }
    local.atomic_json(local.artifact_path("video.json"), manifest)
    client = TestClient(app)
    response = client.get(f"/briefing/video/{filename}", headers={"Range": "bytes=2-7"})
    assert response.status_code == 206 and response.content == data[2:8]
    (tmp_path / filename).write_bytes(b"X" + data[1:])
    assert client.get(f"/briefing/video/{filename}").status_code == 503


def test_video_uuid_cannot_masquerade_as_a_content_address(monkeypatch, tmp_path):
    from app.main import app

    monkeypatch.setattr(local.settings, "briefing_artifact_dir", str(tmp_path))
    data = b"transport fixture"
    filename = "0" * 32 + ".mp4"
    (tmp_path / filename).write_bytes(data)
    local.atomic_json(
        local.artifact_path("video.json"),
        {
            "generated_at": local.clock().isoformat(),
            "filename": filename,
            "url": f"/api/briefing/video/{filename}",
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    )
    assert TestClient(app).get(f"/briefing/video/{filename}").status_code == 503


@pytest.mark.asyncio
async def test_failed_video_preserves_previous_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(local.settings, "briefing_artifact_dir", str(tmp_path))
    monkeypatch.setattr(local.settings, "enable_video_generation", True)
    monkeypatch.setattr(local.settings, "demo_mode", False)
    monkeypatch.setattr(local.settings, "piper_model_path", "")
    monkeypatch.setattr(local, "source_snapshot", AsyncMock(return_value=snapshot()))
    previous = {"generated_at": local.clock().isoformat(), "sha256": "a" * 64}
    local.atomic_json(local.artifact_path("video.json"), previous)
    with pytest.raises(ValueError):
        await video.generate()
    assert local.read_artifact("video.json") == previous
    assert video.get_status()["state"] == "failed"


@pytest.mark.asyncio
async def test_queue_creation_failure_closes_unowned_coroutine(monkeypatch):
    import inspect

    from app.routes import briefing

    monkeypatch.setattr(briefing.runtime, "tasks", {})

    def failed(*args):
        raise RuntimeError("creation fixture")

    monkeypatch.setattr(briefing.runtime, "start", failed)

    async def work():
        return None

    coroutine = work()
    with pytest.raises(RuntimeError):
        briefing.queue("local_analysis", coroutine)
    assert inspect.getcoroutinestate(coroutine) == inspect.CORO_CLOSED

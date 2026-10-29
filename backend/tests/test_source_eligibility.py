"""Source-use restrictions precede model/speech work and preserve originals."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.routes import briefing
from app.services import briefing_video as video
from app.services import local_briefing as local
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def restore_worker_status():
    analysis, narration = dict(local._state), dict(video._state)
    yield
    local._state.clear()
    local._state.update(analysis)
    video._state.clear()
    video._state.update(narration)


def test_atomic_json_publishes_exact_destination_without_leftover_temp(tmp_path):
    path = tmp_path / "analysis.json"
    value = {"status": "available", "reports": []}
    local.atomic_json(path, value)
    assert json.loads(path.read_text()) == value
    assert not path.with_suffix(".tmp").exists()


def event(id=1, source="rss_fixture", url="https://example.org/report"):
    return SimpleNamespace(
        id=id,
        source=source,
        source_url=url,
        channel_name="Fixture publisher",
        timestamp=local.clock(),
        raw_text="Preserved original fixture",
        summary="Fixture headline",
    )


def session_rows(monkeypatch, rows):
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        execute = AsyncMock(return_value=result)

    monkeypatch.setattr(local, "async_session", Session)
    return Session


@pytest.mark.parametrize(
    "url",
    [
        "https://t.me/source/1",
        "https://telegram.me/source/1",
        "https://T.ME./s/source/1",
        "https://t%2Eme/source/1",
        "https://www.telegram.me/source/1",
    ],
)
@pytest.mark.asyncio
async def test_telegram_citations_reject_even_when_collector_calls_them_rss(
    monkeypatch, url
):
    session_rows(monkeypatch, [event(url=url)])
    with pytest.raises(
        local.SourcePermissionRequired, match="Telegram source permission"
    ):
        await local.source_snapshot([1])


@pytest.mark.asyncio
async def test_mixed_explicit_selection_rejects_before_ai_or_tts(monkeypatch, tmp_path):
    session_rows(
        monkeypatch, [event(), event(2, "telegram", "https://example.org/mirror")]
    )
    for key in ("enable_local_ai", "enable_video_generation"):
        monkeypatch.setattr(local.settings, key, True)
    monkeypatch.setattr(local.settings, "demo_mode", False)
    monkeypatch.setattr(local.settings, "briefing_artifact_dir", str(tmp_path))
    request, process = AsyncMock(), AsyncMock()
    monkeypatch.setattr(local, "request_extraction", request)
    monkeypatch.setattr(video, "run_process", process)
    for operation in (local.analyze, video.generate):
        with pytest.raises(local.SourcePermissionRequired):
            await operation([1, 2])
    request.assert_not_awaited()
    process.assert_not_awaited()
    assert (
        not (tmp_path / "analysis.json").exists()
        and not (tmp_path / "video.json").exists()
    )
    assert (
        local.get_status()["error_type"]
        == video.get_status()["error_type"]
        == "SourcePermissionRequired"
    )


@pytest.mark.asyncio
async def test_default_skips_telegram_and_canonical_wrappers_for_rss(monkeypatch):
    rows = [event(2, "telegram"), event(3, url="https://t.me/channel/3"), event()]
    session = session_rows(monkeypatch, rows)
    result = await local.source_snapshot(limit=1)
    assert [r["id"] for r in result] == [1] and result[0][
        "source_platform"
    ] == "rss_fixture"
    assert rows[0].raw_text == "Preserved original fixture"
    query = str(
        session.execute.await_args.args[0].compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "!= 'telegram'" in query


@pytest.mark.asyncio
async def test_default_empty_pool_has_eligibility_state_not_model_failure(monkeypatch):
    session_rows(monkeypatch, [event(2, "telegram")])
    with pytest.raises(local.NoEligibleSources):
        await local.source_snapshot()


@pytest.mark.parametrize(
    "platform,channel,label",
    [
        ("rss_bbc_mideast", "bbc_mideast", "BBC News"),
        ("rss_aljazeera", "aljazeera", "Al Jazeera"),
        ("rss_unknown_fixture", "literal_name_fixture", "literal name fixture"),
    ],
)
@pytest.mark.asyncio
async def test_display_label_formats_only_metadata_and_preserves_original_provenance(
    monkeypatch, platform, channel, label
):
    row = event(source=platform)
    row.channel_name = channel
    session_rows(monkeypatch, [row])
    result = (await local.source_snapshot([1]))[0]
    assert result["source"] == label and result["source_platform"] == platform
    assert result["source_url"] == row.source_url and result["id"] == row.id
    assert result["text"] == row.raw_text and result["headline"] == row.summary
    assert (
        result["original_text_sha256"]
        == hashlib.sha256(row.raw_text.encode()).hexdigest()
    )
    assert row.source == platform and row.channel_name == channel


def test_lookalike_host_and_publisher_name_are_not_guessed_as_telegram():
    assert not local.telegram_citation("https://t.me.example.org/report")
    local.ensure_artifact_source_permission(
        {
            "reports": [
                {
                    "source": "Telegram",
                    "source_platform": "rss_fixture",
                    "source_url": "https://example.org/report",
                }
            ]
        }
    )


@pytest.mark.asyncio
async def test_direct_model_and_narration_helpers_cannot_bypass_permission_guard(
    monkeypatch,
):
    rows = [{"id": 1, "source_url": "https://t.me/channel/1", "text": "Fixture"}]
    client = AsyncMock()
    monkeypatch.setattr(local.httpx, "AsyncClient", client)
    with pytest.raises(local.SourcePermissionRequired):
        await local.request_extraction(rows)
    client.assert_not_called()
    with pytest.raises(local.SourcePermissionRequired):
        local.validate_extraction("{}", rows)
    with pytest.raises(local.SourcePermissionRequired):
        video.build_segments(rows, local.clock().isoformat())


@pytest.mark.parametrize(
    "metadata",
    [
        {"source_url": "https://t.me/channel/1"},
        {"source_platform": "telegram"},
        {"platform": "telegram"},
        {"collector_source": "telegram"},
    ],
)
def test_restricted_artifacts_and_media_withheld_without_deleting(
    monkeypatch, tmp_path, metadata
):
    monkeypatch.setattr(local.settings, "briefing_artifact_dir", str(tmp_path))
    generated = local.clock().isoformat()
    local.atomic_json(
        tmp_path / "analysis.json",
        {"status": "available", "generated_at": generated, "reports": [metadata]},
    )
    local.atomic_json(
        tmp_path / "video.json",
        {
            "status": "available",
            "generated_at": generated,
            "filename": "a" * 32 + ".mp4",
            "sources": [metadata],
        },
    )
    media = tmp_path / ("a" * 32 + ".mp4")
    media.write_bytes(b"original file preserved")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    app = FastAPI()
    app.include_router(briefing.router)
    with TestClient(app) as client:
        for url in [
            "/briefing/latest",
            "/briefing/video/manifest",
            "/briefing/video/" + media.name,
        ]:
            response = client.get(url)
            assert (
                response.status_code == 403
                and response.json()["detail"]["code"] == "SourcePermissionRequired"
            )
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_rss_artifacts_keep_bytes_and_status_explains_policy(monkeypatch, tmp_path):
    monkeypatch.setattr(local.settings, "briefing_artifact_dir", str(tmp_path))
    generated = local.clock().isoformat()
    row = {
        "source": "Fixture publisher",
        "source_platform": "rss_fixture",
        "source_url": "https://example.org/report",
    }
    raw = b"RSS media fixture"
    digest = hashlib.sha256(raw).hexdigest()
    filename = digest[:32] + ".mp4"
    (tmp_path / filename).write_bytes(raw)
    local.atomic_json(
        tmp_path / "analysis.json",
        {"status": "available", "generated_at": generated, "reports": [row]},
    )
    local.atomic_json(
        tmp_path / "video.json",
        {
            "status": "available",
            "generated_at": generated,
            "filename": filename,
            "url": "/api/briefing/video/" + filename,
            "sha256": digest,
            "bytes": len(raw),
            "sources": [row],
        },
    )
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    app = FastAPI()
    app.include_router(briefing.router)
    with TestClient(app) as client:
        assert client.get("/briefing/latest").json()["status"] == "available"
        assert client.get("/briefing/video/" + filename).content == raw
        status = client.get("/briefing/status").json()
        assert (
            status["local_ai"]["source_eligibility"]["explicit_selection"]
            == "reject_entire_selection"
        )
        assert status["video"]["source_eligibility"]["telegram_ugc_excluded"] is True
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before

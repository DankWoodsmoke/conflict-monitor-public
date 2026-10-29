"""Opt-in local analysis/video with bounded, authenticated work requests."""

import hashlib
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.config import settings
from app.security import require_admin_key
from app.services import briefing_video, local_briefing
from app.services.runtime import runtime

router = APIRouter(prefix="/briefing", tags=["local briefing"])


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_ids: list[StrictInt] = Field(default_factory=list, max_length=8)


@router.get("/status")
async def status():
    return {
        "local_ai": local_briefing.get_status(),
        "video": briefing_video.get_status(),
    }


def artifact(name):
    try:
        value = local_briefing.read_artifact(name)
        if value:
            value["runtime_state"] = (
                local_briefing.get_status()
                if name == "analysis.json"
                else briefing_video.get_status()
            )
            generated = datetime.fromisoformat(value["generated_at"])
            if generated.tzinfo is None:
                raise ValueError("Unknown artifact clock")
            age = (datetime.now(UTC) - generated).total_seconds()
            value["age_seconds"] = max(0, age)
            value["stale"] = age > 3600 or age < 0
        return value
    except local_briefing.SourcePermissionRequired:
        raise HTTPException(
            403,
            {
                "code": "SourcePermissionRequired",
                "message": local_briefing.SOURCE_PERMISSION_MESSAGE,
            },
        ) from None
    except (ValueError, OSError, KeyError, TypeError, RecursionError):
        raise HTTPException(503, "Briefing artifact is unavailable") from None


@router.get("/latest")
async def latest():
    return artifact("analysis.json") or {"status": "unavailable", "reports": []}


@router.get("/video/manifest")
async def video_manifest():
    return artifact("video.json") or {"status": "unavailable", "url": None}


@router.get("/video/{filename}")
async def video_file(filename: str):
    if not re.fullmatch(r"[a-f0-9]{32}\.mp4", filename):
        raise HTTPException(404, "Video not found")
    manifest = artifact("video.json")
    if not manifest or manifest.get("filename") != filename:
        raise HTTPException(404, "Video not found")
    path = local_briefing.artifact_path("video.json").parent / filename
    if not path.is_file():
        raise HTTPException(404, "Video not found")
    digest = manifest.get("sha256", "")
    if (
        not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or filename != digest[:32] + ".mp4"
        or manifest.get("url") != f"/api/briefing/video/{filename}"
        or path.stat().st_size != manifest.get("bytes")
        or path.stat().st_size > 40_000_000
        or hashlib.sha256(path.read_bytes()).hexdigest() != digest
    ):
        raise HTTPException(503, "Video integrity check failed")
    return FileResponse(
        path, media_type="video/mp4", headers={"Cache-Control": "no-store"}
    )


def queue(name, coroutine):
    current = runtime.tasks.get(name)
    if current and not current.done():
        coroutine.close()
        raise HTTPException(409, "A briefing task is already running")
    try:
        runtime.start(name, coroutine)
    except BaseException:
        coroutine.close()
        raise
    return {"status": "queued", "task": name, "status_url": "/briefing/status"}


@router.post("/analyze", status_code=202, dependencies=[Depends(require_admin_key)])
async def analyze(request: Request):
    if not settings.enable_local_ai or settings.demo_mode:
        raise HTTPException(503, "Local analysis is disabled")
    if any(i <= 0 for i in request.event_ids):
        raise HTTPException(422, "Positive source IDs required")
    return queue("local_analysis", local_briefing.analyze(request.event_ids))


@router.post("/video", status_code=202, dependencies=[Depends(require_admin_key)])
async def generate_video(request: Request):
    if not settings.enable_video_generation or settings.demo_mode:
        raise HTTPException(503, "Local video is disabled")
    if len(request.event_ids) > 4 or any(i <= 0 for i in request.event_ids):
        raise HTTPException(422, "Choose at most four positive source IDs")
    return queue("local_video", briefing_video.generate(request.event_ids))

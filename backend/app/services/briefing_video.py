"""CPU-only narrated source cards, not synthetic incident footage.

Piper is a separately configured local speech engine. No voice or media assets
are downloaded at runtime. A verified, content-addressed MP4 is published only
after full decode, audio-energy, stream, duration and source checks succeed.
"""

import array
import asyncio
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import textwrap
import wave
from pathlib import Path

from app.config import settings
from app.services import local_briefing as local

_lock = asyncio.Lock()
_state = {
    "state": "idle",
    "error_type": None,
    "last_attempt_at": None,
    "last_success_at": None,
}
WIDTH, HEIGHT, FPS = 1280, 720, 24
DISCLAIMER = "Attributed publisher reports. Claims unverified. Publication time is not incident time."


def get_status():
    return {
        **_state,
        "enabled": settings.enable_video_generation,
        "voice_configured": bool(settings.piper_model_path),
        "method": "local_piper_speech_and_editorial_source_cards",
        "interpretation": "Narrated text briefing; no incident footage or causal verification",
        "source_eligibility": local.source_eligibility(),
    }


async def run_process(args, *, timeout=90):
    process = await asyncio.create_subprocess_exec(
        *map(str, args),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2"},
    )
    tasks = []

    async def read_bounded(stream):
        data = bytearray()
        while chunk := await stream.read(8192):
            if len(data) + len(chunk) > 200_000:
                raise ValueError("Media child output exceeds byte budget")
            data.extend(chunk)
        return bytes(data)

    try:
        limit_cores(process.pid)
        tasks = [
            asyncio.create_task(read_bounded(process.stdout)),
            asyncio.create_task(read_bounded(process.stderr)),
            asyncio.create_task(process.wait()),
        ]
        stdout, _stderr, _ = await asyncio.wait_for(asyncio.gather(*tasks), timeout)
        if process.returncode:
            raise RuntimeError("Local media command failed")
        return stdout
    finally:
        if process.returncode is None:
            process.kill()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # A killed process can still have bytes in a paused pipe transport.
        # Discard in constant memory while reaping, rather than deadlocking on
        # process.wait() with an unread full stdout/stderr buffer.
        async def discard(stream):
            while await stream.read(8192):
                pass

        await asyncio.wait_for(
            asyncio.gather(
                discard(process.stdout), discard(process.stderr), process.wait()
            ),
            5,
        )


def limit_cores(pid):
    """Limit only this owned media child to two allowed logical CPU cores."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
        kernel.GetProcessAffinityMask.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x0600, False, pid)
        if not handle:
            raise OSError("Cannot bound media child CPU affinity")
        try:
            allowed, system = ctypes.c_size_t(), ctypes.c_size_t()
            if not kernel.GetProcessAffinityMask(
                handle, ctypes.byref(allowed), ctypes.byref(system)
            ):
                raise OSError("Cannot inspect media child CPU affinity")
            cores = [i for i in range(64) if allowed.value & (1 << i)][:2]
            if not cores or not kernel.SetProcessAffinityMask(
                handle, sum(1 << i for i in cores)
            ):
                raise OSError("Cannot set media child CPU affinity")
        finally:
            kernel.CloseHandle(handle)
    elif hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(pid, sorted(os.sched_getaffinity(pid))[:2])
    else:
        raise RuntimeError("A bounded media worker CPU platform is required")


def audio_check(path):
    with wave.open(str(path), "rb") as audio:
        if (
            audio.getsampwidth() != 2
            or audio.getnchannels() != 1
            or not 16000 <= audio.getframerate() <= 48000
        ):
            raise ValueError("Unexpected narration audio format")
        duration = audio.getnframes() / audio.getframerate()
        if not 0.5 <= duration <= 85:
            raise ValueError("Narration duration outside bounds")
        samples = array.array("h", audio.readframes(audio.getnframes()))
        if sys.byteorder != "little":
            samples.byteswap()
    rms = math.sqrt(sum(float(x) * x for x in samples) / max(1, len(samples)))
    clipping = sum(abs(x) >= 32760 for x in samples) / max(1, len(samples))
    if rms < 25 or clipping > 0.05:
        raise ValueError("Narration is silent or severely clipped")
    return {
        "duration_seconds": duration,
        "rms_pcm16": round(rms, 2),
        "clipped_fraction": clipping,
    }


def draw_card(path, *, title, body, footer, generated_at, index, total):
    from PIL import Image, ImageDraw, ImageFont

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    font_path = next((p for p in candidates if Path(p).is_file()), None)
    if not font_path:
        raise RuntimeError("A Unicode briefing font is required")
    image = Image.new("RGB", (WIDTH, HEIGHT), (7, 15, 25))
    draw = ImageDraw.Draw(image)
    font = lambda size: ImageFont.truetype(font_path, size)
    draw.rectangle((0, 0, 15, HEIGHT), fill=(64, 210, 190))
    draw.text(
        (58, 32),
        "CONFLICT MONITOR  /  SOURCE BRIEFING",
        font=font(21),
        fill=(104, 228, 212),
    )
    draw.text(
        (58, 76),
        f"COMPILED {generated_at[:19].replace('T', ' ')} UTC  ·  {index}/{total}",
        font=font(16),
        fill=(154, 173, 193),
    )
    y = 138
    for line in textwrap.wrap(title, width=53)[:3]:
        draw.text((58, y), line, font=font(36), fill=(238, 245, 250))
        y += 47
    y += 20
    # Wrap long URLs/tokens as well as prose; no arbitrary text enters ffmpeg.
    lines = textwrap.wrap(
        body, width=82, break_long_words=True, replace_whitespace=False
    )
    if len(lines) > 10:
        raise ValueError("Source card text exceeds visual budget")
    for line in lines:
        draw.text((58, y), line, font=font(24), fill=(210, 222, 235))
        y += 34
    footer_lines = textwrap.wrap(footer, width=118)[:3]
    for footer_index, line in enumerate(footer_lines):
        draw.text(
            (58, 574 + footer_index * 22), line, font=font(15), fill=(148, 175, 194)
        )
    draw.rectangle((40, 650, 1240, 652), fill=(40, 75, 90))
    draw.text(
        (58, 669),
        "SOURCE CLAIMS UNVERIFIED  ·  EDITORIAL TEXT CARDS / NO INCIDENT FOOTAGE",
        font=font(17),
        fill=(239, 190, 98),
    )
    image.save(path, "PNG")


def build_segments(snapshot, generated_at):
    local.ensure_artifact_source_permission({"sources": snapshot})
    if not 1 <= len(snapshot) <= 4:
        raise ValueError("Video supports one to four source reports")
    segments = [
        {
            "title": "Reports, sources and open questions",
            "body": DISCLAIMER,
            "footer": "No automated risk assessment. No generated incident imagery. Read the original linked sources.",
            "narration": "Conflict Monitor source briefing. These are attributed publisher reports, not independently verified facts. Publication time is not incident time. No incident footage is shown.",
        }
    ]
    for row in snapshot:
        headline = re.sub(r"[\x00-\x1f]", " ", row["headline"]).strip()
        if not headline:
            raise ValueError("A source headline is required")
        # Retain the complete supplied headline, including denial/uncertainty.
        # Non-English source text is displayed without inventing a translation.
        english = sum(c.isascii() for c in headline) / len(headline) > 0.92
        narration = (
            f"Source report {row['id']}. {row['source']} reports: {headline}"
            if english
            else f"Source report {row['id']}. The original language headline is displayed. No translation has been generated."
        )
        narration = re.sub(r"\[\[|\]\]", " ", narration)
        segments.append(
            {
                "title": f"SOURCE {row['id']}  /  {row['source']}",
                "body": headline,
                "footer": f"Published {row['published_at']}  |  {row['source_url']}",
                "narration": narration,
                "source_id": row["id"],
            }
        )
    segments.append(
        {
            "title": "Evidence limits",
            "body": "Source statements may be mistaken, incomplete, revised or share one origin. Heat detections do not establish a strike. Unknown locations remain unknown.",
            "footer": "Inspect the source links and immutable source hashes in the companion manifest.",
            "narration": "Source statements may be mistaken, incomplete, revised, or share one origin. Heat detections do not establish a strike. Unknown locations remain unknown. Inspect the cited sources and the companion manifest.",
        }
    )
    return segments


async def generate(event_ids=None):
    if not settings.enable_video_generation or settings.demo_mode:
        raise ValueError("Briefing video generation is disabled")
    if _lock.locked():
        raise ValueError("A video generation is already running")
    async with _lock:
        _state.update(
            state="running", error_type=None, last_attempt_at=local.clock().isoformat()
        )
        try:
            snapshot = await local.source_snapshot(event_ids, limit=3)
            if len(snapshot) > 4:
                raise ValueError("Choose at most four sources for video")
            model = Path(settings.piper_model_path)
            if (
                not settings.piper_model_path
                or not model.is_file()
                or not model.with_suffix(model.suffix + ".json").is_file()
            ):
                raise ValueError(
                    "Configure an installed Piper voice and its JSON config"
                )
            if not 1_000_000 <= model.stat().st_size <= 200_000_000:
                raise ValueError("Piper voice size outside budget")
            config_path = model.with_suffix(model.suffix + ".json")
            if config_path.stat().st_size > 100_000:
                raise ValueError("Voice configuration exceeds budget")
            voice_config = json.loads(config_path.read_text(encoding="utf-8"))
            if voice_config.get("phoneme_type") != "espeak" or not str(
                voice_config.get("espeak", {}).get("voice", "")
            ).startswith("en"):
                raise ValueError(
                    "Use an installed English espeak Piper voice; runtime language downloads are disabled"
                )
            root = local.artifact_path("video.json").parent
            root.mkdir(parents=True, exist_ok=True)
            if sum(p.stat().st_size for p in root.glob("*.mp4")) > 160_000_000:
                raise ValueError("Briefing storage budget reached; archive old videos")
            generated = local.clock().isoformat()
            segments = build_segments(snapshot, generated)
            audio_receipts = []
            duration = 0
            async with asyncio.timeout(600):
                with tempfile.TemporaryDirectory(prefix="briefing-", dir=root) as temp:
                    work = Path(temp)
                    for index, segment in enumerate(segments):
                        png, wav, mp4, text = (
                            work / f"{index}.{ext}"
                            for ext in ("png", "wav", "mp4", "txt")
                        )
                        draw_card(
                            png,
                            **{k: segment[k] for k in ("title", "body", "footer")},
                            generated_at=generated,
                            index=index + 1,
                            total=len(segments),
                        )
                        text.write_text(segment["narration"], encoding="utf-8")
                        worker = (
                            Path(__file__).resolve().parents[1]
                            / "workers"
                            / "piper_speech.py"
                        )
                        await run_process(
                            [
                                settings.piper_python or sys.executable,
                                worker,
                                "--model",
                                model,
                                "--output",
                                wav,
                                "--input",
                                text,
                            ]
                        )
                        audio = audio_check(wav)
                        duration += audio["duration_seconds"]
                        if duration > 240:
                            raise ValueError(
                                "Video exceeds four minute duration budget"
                            )
                        audio_receipts.append(
                            {
                                "segment": index,
                                **audio,
                                "narration_sha256": hashlib.sha256(
                                    segment["narration"].encode()
                                ).hexdigest(),
                                "frame_sha256": hashlib.sha256(
                                    png.read_bytes()
                                ).hexdigest(),
                            }
                        )
                        await run_process(
                            [
                                settings.ffmpeg_path,
                                "-v",
                                "error",
                                "-nostdin",
                                "-y",
                                "-loop",
                                "1",
                                "-framerate",
                                FPS,
                                "-i",
                                png,
                                "-i",
                                wav,
                                "-c:v",
                                "libx264",
                                "-threads",
                                "2",
                                "-preset",
                                "fast",
                                "-pix_fmt",
                                "yuv420p",
                                "-c:a",
                                "aac",
                                "-b:a",
                                "128k",
                                "-shortest",
                                "-t",
                                f"{audio['duration_seconds']:.3f}",
                                "-movflags",
                                "+faststart",
                                mp4,
                            ],
                            timeout=100,
                        )
                    concat = work / "list.txt"
                    concat.write_text(
                        "\n".join(f"file '{i}.mp4'" for i in range(len(segments))),
                        encoding="utf-8",
                    )
                    output = work / "result.mp4"
                    await run_process(
                        [
                            settings.ffmpeg_path,
                            "-v",
                            "error",
                            "-nostdin",
                            "-y",
                            "-f",
                            "concat",
                            "-safe",
                            "1",
                            "-i",
                            concat,
                            "-c",
                            "copy",
                            "-movflags",
                            "+faststart",
                            output,
                        ]
                    )
                    raw = await run_process(
                        [
                            settings.ffprobe_path,
                            "-v",
                            "error",
                            "-show_streams",
                            "-show_format",
                            "-of",
                            "json",
                            output,
                        ]
                    )
                    probe = json.loads(raw)
                    streams = probe.get("streams", [])
                    video = next(
                        (s for s in streams if s.get("codec_type") == "video"), {}
                    )
                    audio = next(
                        (s for s in streams if s.get("codec_type") == "audio"), {}
                    )
                    measured = float(probe.get("format", {}).get("duration", 0))
                    if (
                        video.get("codec_name") != "h264"
                        or audio.get("codec_name") != "aac"
                        or video.get("width") != WIDTH
                        or video.get("height") != HEIGHT
                        or not duration - 1 <= measured <= duration + 2
                        or output.stat().st_size > 40_000_000
                    ):
                        raise ValueError(
                            f"Rendered video failed stream or duration checks: measured={measured:.3f}, expected={duration:.3f}, video={video.get('codec_name')}, audio={audio.get('codec_name')}"
                        )
                    await run_process(
                        [
                            settings.ffmpeg_path,
                            "-v",
                            "error",
                            "-nostdin",
                            "-i",
                            output,
                            "-f",
                            "null",
                            "-",
                        ],
                        timeout=100,
                    )
                    digest = hashlib.sha256(output.read_bytes()).hexdigest()
                    filename = digest[:32] + ".mp4"
                    final_path = root / filename
                    if (
                        final_path.exists()
                        and hashlib.sha256(final_path.read_bytes()).hexdigest()
                        != digest
                    ):
                        raise ValueError("Video content-address collision")
                    output.replace(final_path)
                    manifest = {
                        "status": "available",
                        "generated_at": generated,
                        "method": "local_piper_editorial_source_cards",
                        "url": f"/api/briefing/video/{filename}",
                        "filename": filename,
                        "sha256": digest,
                        "bytes": (root / filename).stat().st_size,
                        "duration_seconds": measured,
                        "width": WIDTH,
                        "height": HEIGHT,
                        "fps": FPS,
                        "voice_model_sha256": hashlib.sha256(
                            model.read_bytes()
                        ).hexdigest(),
                        "sources": snapshot,
                        "source_snapshot_sha256": local.canonical_hash(snapshot),
                        "segments": segments,
                        "validation": {
                            "full_decode": "passed",
                            "streams": "h264_and_aac",
                            "audio_segments": audio_receipts,
                        },
                        "limitations": [
                            DISCLAIMER,
                            "Speech is synthesized. Source pronunciation and factual claims require review.",
                            "This is editorial text, not incident footage or live imagery.",
                        ],
                    }
                    local.atomic_json(local.artifact_path("video.json"), manifest)
            _state.update(state="ready", last_success_at=generated)
            return manifest
        except (Exception, asyncio.CancelledError) as exc:
            _state.update(state="failed", error_type=type(exc).__name__)
            raise

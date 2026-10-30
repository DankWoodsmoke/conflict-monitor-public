"""Offline qualification of the narrowly compiled source-card media runtime.

Run inside the candidate backend image with --network none, two CPUs and a
memory limit. A supplied Piper voice is read only; this tool never downloads a
model or calls an API. Outputs describe authored synthetic test material.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app.services import briefing_video as media


async def qualify(output, voice=None):
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "Offline synthetic source-card encoding, concatenation, probing and complete decoding; optional actual CPU Piper speech",
        "status": "running",
        "checks": [],
        "voice_used": voice is not None,
        "limits": [
            "Synthetic fixture, not a real report, DB/API pipeline or listener audibility test.",
            "A restricted codec/protocol inventory is not absence of unknown vulnerabilities.",
            "No network/model download, GOOL service or GPU is used by this tool.",
        ],
    }
    receipt = output / "receipt.json"

    def record(name, **details):
        result["checks"].append({"name": name, "status": "PASS", **details})
        receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")

    async def run(*args, timeout=90):
        return await media.run_process(args, timeout=timeout)

    try:
        protocols = (await run("ffmpeg", "-hide_banner", "-protocols")).decode()
        names = {
            line.strip()
            for line in protocols.splitlines()
            if line.strip()
            and line.strip() not in {"Supported file protocols:", "Input:", "Output:"}
        }
        assert names == {"file", "pipe"}, names
        record("only_local_file_and_pipe_protocols", protocols=sorted(names))
        for option in ["-demuxers", "-decoders", "-encoders"]:
            data = await run("ffmpeg", "-hide_banner", option)
            (output / (option[1:] + ".txt")).write_bytes(data)
        versions = json.loads(
            await run("ffprobe", "-v", "error", "-show_versions", "-of", "json")
        )
        (output / "versions.json").write_text(
            json.dumps(versions, indent=2) + "\n", encoding="utf8"
        )
        assert versions["program_version"]["version"] == "9.0.2"
        record("pinned_ffmpeg_version", version="9.0.2")
        demuxers = {
            line.split(maxsplit=2)[1]
            for line in (output / "demuxers.txt").read_text().splitlines()
            if line.split()[:1] == ["D"] and line.split()[1:2] != ["="]
        }
        assert demuxers == {"concat", "image2", "mov,mp4,m4a,3gp,3g2,mj2", "wav"}, (
            demuxers
        )
        decoders = {
            line.split(maxsplit=2)[1]
            for line in (output / "decoders.txt").read_text().splitlines()
            if len(line.split()) >= 2
            and len(line.split()[0]) == 6
            and line.split()[0][0] in {"V", "A", "S"}
            and line.split()[1] != "="
        }
        assert decoders == {"png", "h264", "aac", "pcm_s16le"}, decoders
        record(
            "only_required_demuxers_and_decoders",
            demuxers=sorted(demuxers),
            decoders=sorted(decoders),
        )
        assert os.getuid() == 10001
        privileged = await run("find", "/usr", "-xdev", "-type", "f", "-perm", "/6000")
        assert not privileged.strip()
        record("nonroot_user_and_no_usr_suid_sgid_files", uid=os.getuid())

        from PIL import Image

        image = output / "card.png"
        media.draw_card(
            image,
            title="SYNTHETIC SECURITY QUALIFICATION",
            body="No real event is described. This authored card tests local media processing.",
            footer="Synthetic fixture. No incident footage or source claim.",
            generated_at=result["started_at"],
            index=1,
            total=1,
        )
        with Image.open(image) as decoded:
            decoded.load()
            assert decoded.size == (media.WIDTH, media.HEIGHT)
        record("actual_source_card_renderer", width=media.WIDTH, height=media.HEIGHT)

        wav = output / "narration.wav"
        if voice:
            text = output / "narration.txt"
            text.write_text(
                "This is a synthetic security qualification briefing. No real event is being described.",
                encoding="utf8",
            )
            await run(
                sys.executable,
                Path(media.__file__).resolve().parents[1] / "workers/piper_speech.py",
                "--model",
                voice,
                "--input",
                text,
                "--output",
                wav,
            )
        else:
            import array
            import math
            import wave

            samples = array.array(
                "h",
                (
                    int(3000 * math.sin(i * math.tau * 440 / 22050))
                    for i in range(22050)
                ),
            )
            with wave.open(str(wav), "wb") as audio:
                audio.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
                audio.writeframes(samples.tobytes())
        audio = media.audio_check(wav)
        record(
            "actual_piper_speech_and_audio_gate"
            if voice
            else "synthetic_tone_audio_gate",
            **audio,
        )

        for number in range(2):
            await run(
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-y",
                "-loop",
                "1",
                "-framerate",
                media.FPS,
                "-i",
                image,
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
                output / f"{number}.mp4",
                timeout=100,
            )
        record("both_local_png_wav_to_h264_aac_segments")
        listing = output / "list.txt"
        listing.write_text("file '0.mp4'\nfile '1.mp4'\n", encoding="utf8")
        final = output / "synthetic-qualification.mp4"
        await run(
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            listing,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            final,
        )
        record("safe_local_concat_and_faststart")
        probe = json.loads(
            await run(
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                final,
            )
        )
        streams = {stream["codec_type"]: stream for stream in probe["streams"]}
        assert streams["video"]["codec_name"] == "h264"
        assert streams["audio"]["codec_name"] == "aac"
        assert (streams["video"]["width"], streams["video"]["height"]) == (
            media.WIDTH,
            media.HEIGHT,
        )
        duration = float(probe["format"]["duration"])
        assert (
            2 * audio["duration_seconds"] - 1
            <= duration
            <= 2 * audio["duration_seconds"] + 2
        )
        record("actual_ffprobe_stream_geometry_duration", duration_seconds=duration)
        await run(
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            final,
            "-f",
            "null",
            "-",
            timeout=100,
        )
        record("complete_video_and_audio_decode")
        for args in [
            ("-i", "https://127.0.0.1:9/no-network", "-f", "null", "-"),
            ("-f", "hls", "-i", str(listing), "-f", "null", "-"),
        ]:
            start = time.monotonic()
            try:
                await run("ffmpeg", "-v", "error", "-nostdin", *args, timeout=5)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Unsupported input unexpectedly accepted")
            assert time.monotonic() - start < 5
        record("https_and_hls_inputs_rejected")
        result.update(
            status="PASS",
            ended_at=datetime.now(UTC).isoformat(),
            video_sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
            video_bytes=final.stat().st_size,
            worker_sha256=hashlib.sha256(Path(media.__file__).read_bytes()).hexdigest(),
        )
    except BaseException as error:
        result.update(status="FAIL", error_type=type(error).__name__)
        raise
    finally:
        receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--voice", type=Path)
    arguments = parser.parse_args()
    asyncio.run(qualify(arguments.output_dir, arguments.voice))

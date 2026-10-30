# Local AI triage and narrated source briefings

These optional features use local computation. They do not call a paid model or
speech API, invent incident footage, or establish the truth of collected reports.
Collection, analysis and video are separate opt-ins. A provider key being present
does not enable paid X collection: that also requires `X_INGESTION_ENABLED=true`.

## Operator workflow

Configure `ENABLE_LOCAL_AI=true`, a local `LOCAL_AI_URL`, and an installed stock
`LOCAL_AI_MODEL`. The evaluated default is `qwen3.5:4b`. No model pull is performed
by the application. Supported stock model names are an explicit allowlist; private
persona models and corpora are not used. The origin must be HTTP loopback with an
explicit port, or the explicit Docker Desktop `host.docker.internal` host alias.
Redirects, user credentials, arbitrary remote hosts and URL paths are rejected.

The Windows qualification used a project-owned server on port11502 with a separate
private model cache. The older cached-model comparison used a different owned
server on11501. Neither shared GOOL services nor its model definitions were
started or altered. Both inference requests explicitly used CPU, four compute
threads, one request at a time, 8,192 context tokens, a 1,400 output-token ceiling,
temperature0, seed42 and immediate model unloading. These settings describe the
request; reproducibility across hardware/runtime changes is not guaranteed.

For portable Linux hosting an optional Ollama sidecar may share the backend's
network namespace and listen on its loopback without publishing an Ollama port.
Use a dedicated stock-only model cache. Do not expose an unauthenticated model
server to the Internet. An operator may instead supply an already owned local
runtime. The application does not start that runtime or download weights.

`POST /briefing/analyze` accepts `{ "event_ids": [1,2] }`, or an empty list for the
latest four eligible source records. It requires the configured `X-Admin-Key` and
returns202 after queuing a single supervised job. Eight IDs is the maximum.
`GET /briefing/status` shows job state and sanitized error type.
`GET /briefing/latest` returns the last validated analysis, its age/stale state,
frozen source text, source hashes, model identity/digest, token counts, instruction
hash and validation scope. Failed work cannot overwrite the last good analysis.

Analysis returns topic relevance, a linguistic reported/denied/uncertain label,
and exact source mentions of places, actors and quantities. Labels remain
**model-generated and unreviewed**. The complete bounded source excerpt remains
visible so a label cannot replace the source's denial or uncertainty. The model
cannot add fields, invent spans, change/miss IDs or produce event coordinates.
An exact span is necessary, not proof of correct entity role or semantic meaning.
Place mentions stay unresolved source mentions, not incident positions.

Spans have Python Unicode-codepoint `start`/`end` plus explicitly named
`start_utf16`/`end_utf16` offsets for JavaScript. A non-BMP regression checks both.
No automatic Event summary, severity, classification or location is changed.
If any row fails the schema/span/identity/negation gate, the whole batch is
rejected; the current contract does not silently discard invalid model rows.

Sources must be dated, not future dated, within the configured24-hour default
window (maximum48hours), have public HTTP(S) citations and fit text budgets.
The request cap is60KB; inventory/model responses are streamed with200KB/64KB
limits. Generation has a deadline and no automatic retries. Model failure does
not become a successful deterministic "AI" result.

Local attempts are recorded separately in the bounded `local-calls.jsonl` ledger,
including whether inference was attempted and whether a validated response was
received. Paid `UsageLog` rows do not count these local jobs. Zero paid API rows
must never be described as zero total model calls or zero electricity cost.

## Measured model sample

Twelve synthetic multilingual/adversarial cases were fixed before the comparison.
The three earlier development probes used to revise instructions are **tuning**,
not held-out validation. The sample includes denial, numeric ranges, missing
input, unrelated material, actor/place ambiguity, Arabic, Spanish and embedded
instruction attempts. Expectations, prompt and validator hashes were frozen.

| CPU model | Relevance correct | Stance correct | Batches accepted | Reports in accepted batches | Total latency |
|---|---:|---:|---:|---:|---:|
| Qwen3.5:4B |11/12|11/12|2/3|8/12|80.6s|
| Qwen3:8B |10/12|9/12|2/3|8/12|166.0s|
| Qwen3:0.6B |2/12|0/12|0/3|0/12|13.2s|

The4B model's relevant-topic precision/recall were1.0/1.0 over ten positive
cases; place-mention precision/recall were0.909/1.0. Its first batch contained a
nonliteral mention and was rejected. One actor/place ambiguity and an empty-input
label failure remained. The8B model's failed batch omitted negation. The0.6B
model changed/omitted source identities in every batch. Failures and raw bounded
synthetic responses were retained. These are sample results, not calibrated
general accuracy or independent factual verification. The4B model was selected
for this unreviewed triage task, not promoted as a general SITREP/world model.

After formatting-only changes, all nine stored raw batch responses were replayed
against the current validator with identical acceptance/rejection decisions.
Local receipts are `artifacts/local-ai-heldout-comparison.json`,
`local-ai-holdout-frozen.json` and `local-ai-validator-replay.json`. Runtime
artifacts and model caches are excluded from the public source export.

An optional follow-up compared the same frozen sample with full GPU offload on
the actual RTX4070. It is a repeated computational comparison, not a new
independent validation set. GPU batches took66.078/5.688/5.531seconds versus
CPU26.703/25.593/28.282seconds. Including the first CUDA initialization, total
speedup was only1.04×; the later two requests were about4.8× faster. Actual
runtime VRAM reached3,176,440,789bytes and the model was absent from `/api/ps`
after automatic unloading. Total GPU memory fell from1,242MiB before to1,131MiB
after. No production settings or shared services were changed.

All three GPU batches passed the output gate, but relevance was10/12 and stance
11/12. GPU output differed from CPU output and did not improve all semantic
metrics. The default remains CPU; a dedicated-GPU operator can evaluate this
tradeoff with cold-start latency, shared GPU ownership and numerical differences
made explicit. The complete raw sample/metrics are in
`artifacts/local-ai-gpu-comparison.json`.

## Real narrated MP4

Configure `ENABLE_VIDEO_GENERATION=true` and `PIPER_MODEL_PATH` pointing to an
installed English espeak Piper voice with its adjacent `.onnx.json` file.
`PIPER_PYTHON` optionally selects the worker interpreter. The RC.2 production image
builds SHA/signature-verified FFmpeg9.0.2 with only required local formats and
`file`/`pipe` protocols, alongside DejaVu fonts and the locked Pillow13, Piper1.8
and ONNX Runtime1.31.1 dependencies. Retained parser advisories and native-library
inventory are in the [OS review](OS_SECURITY_REVIEW.md). Model files are mounted separately, never downloaded by
an incoming generation request. `BRIEFING_ARTIFACT_DIR` must be writable by the
unprivileged backend user and backed by persistent storage for restarts.

`POST /briefing/video` accepts at most four source IDs, or an empty list for the
latest three. It requires the same admin gate, returns202 and runs one supervised
job. `GET /briefing/video/manifest` exposes the validated MP4 URL, exact original
sources, publication clocks, narration/frame hashes, voice hash, audio checks
and evidence limits. The video endpoint serves only the current manifest's
content-addressed filename and verifies URL/size/hash consistency.

The output is1280×720,24fps,H.264 video with AAC narration. It consists of an
introduction, exact attributed publisher headlines with source IDs/URLs/UTC
publication dates, and an evidence-limits card. No source photography, generated
incident footage, cloned voice or synthesized factual claim is used. Non-English
headlines are displayed unchanged. A conservative character-ratio heuristic
abstains from narrating substantially non-ASCII source text and explicitly says
no translation was generated; it is not a validated language detector. Other
headlines are quoted literally using the English voice. Language support and
pronunciation require review; the qualified production example is an English
RSS report.

The separate speech worker sets ONNX intra-op2/inter-op1 threads with spinning
disabled. Every owned media child is restricted to two allowed logical CPU
cores; FFmpeg encoding uses two threads. Child output is read with bounded
streaming readers. Flood, timeout and cancellation kill/reap the owned process
and drain pipe tails in constant memory. Jobs have per-command and overall
deadlines, four-minute/output-file/storage caps, PCM energy/clipping checks,
stream/duration checks and a full FFmpeg decode before publication. A failed or
cancelled job preserves the prior manifest. No subprocess command uses a shell
or interpolates source prose into FFmpeg expressions.

## Captions and exact narration transcript

The frozen 224-test frontend adds native WebVTT captions and a complete narration
transcript for compatible recorded manifests. It validates one to four unique
sources, the opening/source/closing segment order, finite measured audio durations,
bounded safe text and the content filename/full-hash prefix. WebCrypto checks
each exact UTF-8 narration against its manifest hash before either captions or
the transcript become available. Missing metadata, unavailable crypto or a
mismatch leaves the video playable with an explicit caption/transcript limit.
Hash identity does not independently establish spoken content or source truth.

Cue boundaries use cumulative measured audio-segment durations, never stretched
to the video length; they are **not word aligned**. The current real `c39e4447…`
artifact has three segments totaling38.359365seconds against a38.379801-second
container, a20.436ms difference. Captions escape markup, timing delimiters and
newlines; the separate transcript preserves the exact narration as text. It is
keyboard reachable and scrollable. Neither transcript nor captions are a source
translation or independent factual check.

Equivalent manifest polls retain the same video, playback position, caption
selection and Blob resource. Artifact/consumed-metadata changes retire the owned
resource; stale verification cannot attach a revoked URL or an old transcript.
A native track-load failure keeps the verified transcript available and does not
become a false MP4 playback error. These lifecycle and malformed-metadata cases
have focused regressions; viewing or toggling captions starts no generation job.

Development preflight and the exact `b6e6bc17…` Docker frontend at port5196
qualified native playback and exact cue/transcript behavior in three engines,
with a retained limit. Chromium/WebKit passed visible caption on/off/restore.
**Firefox failed immediate repaint when captions were re-enabled on a paused
frame**; cue mode/state alone did not prove visible text. Actual native user
Play/Pause checks restored the caption pixels, kept the same video and one track,
and produced no generation POST or page errors. This is two strict paused-frame
restoration passes and one qualified user-resume recovery, not three paused-repaint passes.
The page conditionally says to resume playback if paused captions do not appear;
the notice clears on actual playback or hiding captions. No browser sniffing,
forced play, seeking or track rebuild workaround is used. The verified transcript
remains an alternative. Failed native-repaint experiments are preserved.

Frontend `b6e6bc17…` is [live-admitted](qualification/2026-10-30-rc2-frontend-build-and-admission.json)
with source/served-byte/header/process checks complete; full final production
mobile/caption checks and the running long-session observations remain pending. Development
results do not qualify the final admitted runtime, physical iOS, screen readers,
every native CC menu, general speech quality or full WCAG conformance. See the
[verification state](VERIFICATION.md) for current phase and exact identities.

## Earlier native media sample

The earlier native Windows qualification fetched one actual production report
over HTTP, froze that source, and generated a33.194-second MP4 in32.734seconds.
It passed H.264/AAC metadata, complete decode and all three non-silent narration
segment checks. A frame was visually inspected for readable attribution/date/
URL/disclaimer. This native helper receipt is **not** the Docker API/database
integration receipt; qualify that deployment separately. An earlier slow/failed
candidate was preserved. Any later production result belongs in the main
verification document; it is not implied by this native run.

An additional offline speech-consistency sample used an already cached public
faster-whisper-medium.en model on CPU/int8 with two threads. It recognized the
native video's two key uncertainty/no-footage disclaimers. Unadjusted word error
rate against the supplied narration was3/69 (4.35%), with21.14seconds recognition
time. This automatic comparison is not listener audibility evidence, a voice
quality score, or proof of correct pronunciation. No ASR model was downloaded
and no shared GOOL service was started.

## Deployment qualification

`tools/verify_local_generation.py` is an explicit execution gate. Supply the
loopback deployment URL, owned local model URL, and an operator dotenv containing
`ADMIN_API_KEY`. For example, after configuring the local services:

```powershell
./.venv/Scripts/python.exe tools/verify_local_generation.py --execute --base-url http://127.0.0.1:5190/api --ollama-url http://127.0.0.1:11502 --env-file .env
```

The script selects a current actual RSS report, verifies its identity/raw text
against a read-only PostGIS query, queues exactly one analysis and one video,
checks frozen source hashes and the actual installed model digest, downloads the
verified MP4, checks HTTP206 seeking and independently decodes both streams.
It checks unchanged source data and zero recorded paid usage before/after.
It never prints the operator key, follows redirects with it, or loads synthetic
source data. `--event-id` selects one eligible actual report. The default Docker
database container name can be overridden for an isolated deployment.

Without `--execute` it produces `NOT_EXECUTED`/exit2 and queues nothing. Failures
produce exit1 and a failed receipt; they do not retry generation. Prior receipts
are preserved when the named output is reused. A PASS/exit0 establishes this
specific executed path and source/model binding, not general factual accuracy.

The [RC.2 execution](qualification/2026-10-30-rc2-local-generation.json) passed
all24 checks on backend `9b094edd…` and database `fc61b564…`, using actual RSS
report1257, one CPU Qwen3.5:4B request, Piper and restricted FFmpeg. The
759,731-byte H.264/AAC720p24fps MP4 is38.379801seconds, fully decoded independently,
with content-addressed filename/hash, HTTP206 and unchanged source data verified.
Paid UsageLog remained zero; that does not erase the local inference job or its
resource cost. A prior explicit Telegram selection was rejected before work,
and no eligibility gate was relaxed. Caption/browser rendering has separate
checks and is not implied by this backend generation pass.

The [earlier upgraded-profile execution](qualification/2026-10-29-postgresql17-local-generation.json)
on October 29 passed all 24 checks through nginx, restricted-role PostGIS,
CPU Qwen3.5:4B and containerized Piper/FFmpeg using actual RSS report 55. Its
650,081-byte H264/AAC MP4 is 33.503 seconds, fully decoded independently and
served with HTTP206 range support. The canonical source ID, reviewed display
name and complete source snapshot hash agree. Paid usage remained zero and the
source report was unchanged. That phase's frontend playback advanced on Chromium,
Firefox and WebKit at 390-pixel width without implicit generation.

A separate offline, cached medium.en CPU/int8 ASR check matched all 70 expected
words, including both uncertainty/no-footage disclaimers. The earlier narrated
artifact and its less accurate ASR result remain preserved; neither was relabeled
as the new result. This is one English source-card example, not multilingual
speech quality, general extraction accuracy or human audibility qualification.
That earlier generation receipt also retains the verifier-only failed attempts and
accounts for the additional local analysis job rather than erasing it.

## Components, weights and licenses

- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
  and its [chat API](https://docs.ollama.com/api/chat) provide the local structured
  transport. Schema conformance alone is not semantic correctness.
- [Qwen3.5:4B](https://ollama.com/library/qwen3.5:4b) is the compared optional
  model. The official [Qwen3.5-4B model card](https://huggingface.co/Qwen/Qwen3.5-4B)
  identifies the selected weights as Apache2.0.
  [Qwen3:8B](https://huggingface.co/Qwen/Qwen3-8B) is also Apache2.0. Ollama
  manifests/digests in the actual execution receipts bind the tested weights.
- The [Piper engine](https://github.com/OHF-Voice/piper1-gpl) is GPLv3. The
  standalone [speech adapter](../backend/app/workers/piper_speech.py) is explicitly
  GPLv3-or-later; its license text is included at
  [licenses/PIPER_GPL_3.txt](licenses/PIPER_GPL_3.txt). The surrounding service
  invokes this separate worker via files/subprocess. Preserve these notices and
  the corresponding engine source/license obligations when distributing it.
- The selected [LJSpeech-high voice model card](https://huggingface.co/rhasspy/piper-voices/blob/5041a7a49ae5b3a0f30e6837769eb03fdbb231bd/en/en_US/ljspeech/high/MODEL_CARD)
  identifies its public-domain dataset. The voice repository declares MIT; the
  [LJ Speech dataset author](https://keithito.com/LJ-Speech-Dataset/) describes
  the US public-domain recordings/text and credits Linda Johnson/Keith Ito.
  Downloaded voice:114,199,011bytes, SHA256
  `5d4f08ba6a2a48c44592eed3ce56bf85e9de3dd4e20df90541ae68a8310c029a`;
  adjacent config SHA256
  `7e1f4634af596d83cca997fb7a931ba80b70f8a316a2655ee69c55365e0ace14`.
  No voice weights are shipped in the source archive.
- [FFmpeg licensing](https://ffmpeg.org/legal.html) depends on build options and
  linked codecs; the installed libx264-enabled build is not blanket MIT content.
  [Pillow](https://github.com/python-pillow/Pillow) and
  [ONNX Runtime](https://github.com/microsoft/onnxruntime) retain their own
  licenses. The dependency inventory is not a replacement for those notices.

## Source eligibility for AI and synthesized narration

This deployment excludes Telegram records from local model and speech work because no context-specific continued creator consent has been supplied. This guard follows [Telegram content-licensing terms](https://telegram.org/tos/content-licensing) and [API terms §1.5](https://core.telegram.org/api/terms). It is not a content/topic filter or an assertion that other publishers permit every use.

Automatic selection skips `Event.source=telegram` and known `t.me`/`telegram.me` citations within a bounded recent candidate scan. Explicit selections are all-or-nothing: one restricted record raises the fixed `SourcePermissionRequired` before model or TTS work. The UI uses automatic eligible selection rather than silently selecting recent mixed-platform rows. There is no operator consent checkbox or general override. Other source rights still require review for the intended processing.

Known restricted analysis/video artifacts are withheld by read and media endpoints with the same fixed reason; files and original reports are preserved. Citation hosts and explicit platform metadata identify these records; publisher display names are not guessed and mutable database lookups are not used for old artifacts. New snapshots retain `source_platform`. Previously qualified RSS artifacts remain readable without rewriting their bytes. Ordinary authorized report viewing and deterministic source digests are unchanged by this AI/speech eligibility guard.

The recovered channel registry, scores and notes are March 2026 unverified historical editorial metadata. They are not calibrated accuracy/speed measurements, independent confirmation, or current identity/funding findings. Registry values remain preserved for review.

Public channel list/detail responses now mark `metadata_status=inherited_unverified`, `reliability_basis=uncalibrated_legacy_editorial_prior`, and `affiliation_status=unverified`. Displayed notes carry a March 2026 historical prefix without mutating registry values; handle lookup is case-insensitive and returns the canonical handle. RSS analysis/narration display labels use exact trusted catalog names, with literal underscore spacing as fallback. Canonical `source_platform`, source ID/URL, original text and its hash remain unchanged.

## Local guard scope and disabled legacy engines

The source-permission guard qualified here applies to the **local structured triage and local narrated-video pipeline**. It is not a universal Telegram guard across every inherited engine. The inherited Telegram model-ingestion branch, paid SITREP engine and standalone paid analysis paths remain unqualified and must stay disabled pending their own source-permission and technical review.

The qualified private profile retains `TELEGRAM_PROCESSING_MODE=reports`, `ENABLE_SITREP_GENERATION=false`, disabled X model ingestion and blank paid-provider credentials. Changing those settings is outside this qualification. Ordinary authorized non-AI viewing and deterministic source digests are separate uses; this boundary grants no general RSS/content license.

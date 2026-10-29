# Public local-AI evaluation evidence

**All report text in this directory is authored synthetic test material. It is
not publisher reporting or evidence that any described incident happened.** No
private persona, corpus, session, environment value, operator key or actual
publisher article body is included. The separate production summary contains
only hashes, counts and execution metadata.

This bundle makes the bounded local linguistic-triage experiment reviewable.
It does not qualify a world model, factual correctness, independent corroboration
or incident geolocation. Original source text stays visible in the application;
generated labels remain unreviewed and never become event coordinates/severity.

## Inspect or replay without running a model

Install the project's locked backend dependencies, then run:

```powershell
./.venv/Scripts/python.exe docs/qualification/local-ai-evaluation/replay.py
```

The default is offline. It verifies the byte manifest, loads only the pure
validator snapshot, recomputes the recorded label metrics and replays all twelve
saved batch decisions: nine CPU batches across three models and three GPU
batches. A PASS means that the stored results reproduce; it does **not** convert
failed recorded model outputs into successful outputs. No application, database,
network, source collector or model service is started by offline replay.

| Profile | Raw relevance | Raw stance | Accepted output batches | Reports in accepted batches | Elapsed |
|---|---:|---:|---:|---:|---:|
| Qwen3.5:4B CPU | 11/12 | 11/12 | 2/3 | 8/12 | 80.578 s |
| Qwen3:8B CPU | 10/12 | 9/12 | 2/3 | 8/12 | 165.985 s |
| Qwen3:0.6B CPU | 2/12 | 0/12 | 0/3 | 0/12 | 13.156 s |
| Qwen3.5:4B RTX 4070 | 10/12 | 11/12 | 3/3 | 12/12 | 77.297 s |

Raw label scores include rejected outputs. They are shown alongside batch
rejection/coverage, rather than presenting accuracy only on the accepted subset.
Precision, recall, abstentions, exact source mentions, required-actor expectations
and quantity-range checks are recorded in the JSON files and recomputed by
offline replay. Missing IDs count as missing predictions, not successful
abstention. Exact spans are necessary but do not prove correct entity roles.

The 4B CPU failure was a nonliteral source mention. The 8B failed batch omitted
visible negation. All 0.6B batches changed/omitted source identities. Those
responses and failure receipts remain visible. No production gate was weakened
to make the sample pass. The GPU requests passed the output gate but had lower
relevance accuracy than the CPU run, so output conformance is clearly distinct
from semantic quality.

## What was frozen, and what the sample means

- `fixtures.json` is an exact-byte copy of the twelve authored cases and golden
  expectations. They include English, Arabic, Spanish, denial, ranges,
  unrelated material, missing text, embedded instructions and role ambiguity.
  Expectations are author judgments, not independent multi-annotator ground
  truth. In particular, the country-as-actor "Jordan" case deliberately tests
  the frozen role expectation; that distinction can be debated and must not be
  treated as calibrated geolocation accuracy.
- `frozen-evaluation.json` records the timestamp and fixture/prompt/validator
  hashes fixed before these model calls. The three prior development probes
  are **prompt tuning**, not held-out evaluation. They are disclosed separately
  in `development-probes.json`; the first 0.6B development rejection did not
  retain its raw invalid response, and no missing bytes are fabricated.
- `system-prompt.txt` is the exact frozen instruction string, not a prose
  paraphrase. `request-schema.json` and `request-profile.json` preserve the
  structure, inference options, batching and source-envelope convention.
  The schema snapshot was recorded when curating this bundle from the unchanged
  definition; it was not separately hash-frozen before the initial calls.
- `validator_snapshot.py` is a pure copy of the current evaluated validator and
  its strict models. CPU evaluation preceded formatting-only changes and an
  equivalent `re.I` → `re.IGNORECASE` alias change. Its old source hash is retained.
  `validator-replay.json` records the nine CPU decisions replayed unchanged
  against the current function. The later GPU experiment used the current hash.
- The GPU run repeated the **same twelve cases after CPU model selection**. It
  is a hardware/profile comparison, not twelve additional independent tests.
  Model digests and all raw synthetic responses are preserved. Temperature zero
  and a fixed seed did not make CPU/GPU output identical.

This small constructed sample is useful for finding failures. It does not
estimate accuracy on a real multilingual news distribution. The selected 4B
model remains an optional unreviewed triage tool; it is not a qualified factual
SITREP generator. Raw model coordinates cannot enter the result, and an invalid
row rejects the complete batch in this contract.

## Explicitly run a new model comparison

Only if you already own an idle loopback Ollama runtime and have installed the
stock model, run for example:

```powershell
./.venv/Scripts/python.exe docs/qualification/local-ai-evaluation/replay.py --execute-model --base-url http://127.0.0.1:11434 --model qwen3.5:4b --num-gpu 0 --output artifacts/my-local-ai-reproduction.json
```

This makes three bounded requests containing only the bundled synthetic inputs.
It does not start services, download models, read application credentials, use
private retrieval data or overwrite bundled evidence. It records the actual
installed digest and raw new responses. New outputs and timing may differ.
The output must be outside this bundle and must not already exist. Model mode
returns exit1 if any batch fails the output gate; exit0 means only that this
output gate accepted all rows, not that semantic labels are correct.

GPU use requires `--num-gpu 99` explicitly. Check current resource ownership and
memory headroom first. The recorded RTX 4070 run requested immediate unloading,
observed 3,176,440,789 bytes of model VRAM, and confirmed the model absent from
Ollama's active-model list afterward. Its first CUDA initialization took
66.078 seconds; later batches took 5.688/5.531 seconds. Including cold start,
total speedup over CPU was only 1.04×; the later two requests were about 4.8×
faster. That is a measured tradeoff, not a universal performance promise.

## File inventory

`bundle-manifest.json` records the exact byte hash and size of every other file.
`cpu-results.json` and `gpu-results.json` contain original raw synthetic outputs,
metrics, errors and timings. `provenance.json` states runtime and curation limits.
The actual live-source generation proof is separately summarized in
[`../local-generation-production-summary.json`](../local-generation-production-summary.json),
without copying the publisher's source body or private runtime artifacts here.

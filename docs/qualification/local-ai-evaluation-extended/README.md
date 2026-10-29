# Additional frozen local AI stress set

This separate evaluation contains 24 newly authored fictional cases. Their text,
expectations, evaluator, and the unchanged baseline prompt/schema/validator were
hashed in `frozen.json` at 2026-10-29 05:51:18 UTC, before these model calls. No
prompt tuning, retries, application changes, private corpus, publisher text,
credentials, speech service, or paid model calls were used. Expectations are
researcher judgments, not independent human annotation or proof of real-news
accuracy. This is distinct from the earlier 12-case comparison.

Six four-report requests used stock Qwen3.5:4B on the already owned local Ollama
runtime, CPU only (`num_gpu=0`, `num_thread=4`, `keep_alive=0`). The observed model
digest was `d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`,
matching the expected digest frozen before execution. During execution the
runtime reported zero model VRAM; it had no active models after completion.

| Measurement | Result |
| --- | --- |
| Total model request time | 211.062 seconds |
| Raw relevance labels | 22/24 match authored expectations |
| Raw stance labels | 21/24 match authored expectations |
| Batch gate acceptance | 4/6 batches; 16/24 reports |
| Place mentions | 22 true positives, 0 extras, 1 missing |
| Required actor exact-string cases | 3/12; includes prefix/granularity mismatches |
| Quantity/range cases | All 3 required numeric cases found |
| Accepted source spans | All 29 replay in Unicode codepoints and UTF16 units |
| Accepted coordinates/severity | None; these fields remain unknown |

Raw label metrics include rejected outputs and are not the accuracy of published
results. No result from this stress test was inserted into the event database.
Batch rejection discards all four analyses, including other correct rows. Saved
raw responses and both rejected batches remain in `cpu-results.json`.

The failures matter:

- The existing token-boundary rule rejects a literal Chinese place within a
  continuous Chinese sentence. It is not a multilingual word segmenter.
- The narrow keyword topic guard rejects the correct unrelated classification
  of a military band concert. Keywords do not establish a security event.
- In case 218, the model extracts the literal number `9000` from an embedded
  malicious instruction and marks the evacuation report unrelated. Its batch
  is rejected because of another row. A separately labeled, no-model-call
  single-row replay shows that literal-span validation alone would accept this
  row. Source text can contain instructions; literal occurrence is not evidence
  that a number is a casualty count or a true claim. These outputs remain
  unreviewed source mentions, with no event severity/location/count mutation.
- The model misses or uses the wrong actor in some cases. Exact-string scoring
  also penalizes `The Red Cross` versus `Red Cross`; a post hoc containment
  diagnostic is recorded separately and does not replace the frozen score.
- Unknown geography and absence of an agreement cause some overcautious stance
  labels. The damaged message does not receive the expected relevance abstention.

The first execution saved all raw results and the assessment, then exited 1
while printing multilingual results to a Windows cp1252 console. This was an
output encoding failure after all six requests, not a model retry or lost
batch. The unchanged frozen evaluator subsequently replayed the saved evidence
offline with UTF8 output and exited 0. `execution-observations.json` preserves
this distinction. An audit replay pass means the recorded decisions and metrics
recompute; it does not mean the semantic model passed every case.

Run offline from the project root, with no model calls:

```powershell
$env:PYTHONIOENCODING='utf-8'
./.venv/Scripts/python.exe docs/qualification/local-ai-evaluation-extended/evaluate.py
```

Explicit new execution requires a caller-owned idle loopback Ollama with the
stock model already installed. The tool never starts it or downloads weights.
Use a new output path; it refuses to overwrite any prior result. Calls are
bounded to the six requests in this fixture, with the original baseline byte
limits and no retry logic. New latency and outputs may differ.

```powershell
$env:PYTHONIOENCODING='utf-8'
./.venv/Scripts/python.exe docs/qualification/local-ai-evaluation-extended/evaluate.py --execute --base-url http://127.0.0.1:11502 --output artifacts/new-24-case-evaluation.json
```

`frozen.json` checks all pre-call dependencies, including sibling files in
`../local-ai-evaluation/`. `bundle-manifest.json` inventories this completed
bundle. `review-notes.json` contains post hoc diagnostics labeled as such. The
application prompt, validator, and operator workflow were not changed in
response to this stress set. The local model remains an optional unreviewed
triage aid requiring human review, not a fact verifier or complete multilingual
conflict classifier.

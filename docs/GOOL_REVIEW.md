# Private GOOL evidence review

The monitor has an operator-run text review through a separately installed
GOOL checkout. It proposes questions about missing evidence, apparently
different accounts and alternatives to check. It shares GOOL's existing
quote and factual-anchor checks and preserves the monitor's private review
contract. The operator path is separate from collection, the browser and
the GOOL voice dispatcher. Its outputs carry no event-edit or publication
authority.

`backend/app/services/gool_review_contract.py` prepares a provider-neutral request
and validates a response without performing inference, retrieval, network
calls, database queries, writes or publication. The operator runner separately
submits a bounded, explicitly approved packet. The model selects immutable
evidence IDs and the runner resolves literal Unicode spans before applying the
existing validator. Full GOOL dispatch and corpus retrieval remain separate.

The input is an existing source snapshot with explicit platform provenance,
permission checks shared with local briefing, original text hashes, exact
provided-text hashes, publication timestamps and a packet hash. The snapshot
rejects duplicate identities, unrecognized fields and invalid citations. Changing
text, metadata, or timestamps invalidates a prior response. Historical snapshots
remain historical. A hash binds supplied bytes; it does not authenticate the
publisher, recover truncated text, or establish source truth or independence.

The response can contain only review questions of three kinds: potential
contradiction, missing evidence within the bundle, and an alternative to check.
Each question requires literal cited spans, matching source IDs/hashes and the
packet hash. Potential contradictions require two distinct reports. Full supplied
source context and both Unicode/codepoint and browser UTF-16 offsets accompany
the citations. Coordinate, severity, classification and verified-status fields
are rejected. All accepted artifacts remain model-generated, unreviewed, private
and unauthorized to change events. Leading questions and wrong interpretations
can still pass a literal-span check; human contextual review is necessary.

## Run a private review

From the monitor checkout, prepare a private source file containing one to
eight rows with the `Source` fields in the contract. Use authored material or
sources for which you can authorize this processing. Review every selected
excerpt and its original hash. Telegram material and known Telegram origins
are excluded. Preparing the packet is offline.

```powershell
.venv/Scripts/python.exe tools/run_gool_review.py prepare --sources private-sources.json --snapshot-at 2026-11-04T20:10:00Z --packet private-packet.json
```

The command returns the packet hash. After inspecting the exact packet,
explicitly approve that hash for submission to OpenRouter. Use a fresh
private run directory and a trusted GOOL checkout containing
`gool/brain/monitor_review.py`. Supply the operator's existing OpenRouter
key through the environment or `--key-file` with a private GOOL dotenv.

```powershell
.venv/Scripts/python.exe tools/run_gool_review.py run --route azure-mini --packet private-packet.json --approve-provider-input-sha256 $approvedPacketHash --gool-checkout C:/Users/NewUser/Desktop/projects/gool --run-directory private-review-run
```

The provider receives the approved text spans, report IDs and source clocks.
The runner uses one explicit model and endpoint, checks the provider's
current ZDR catalog and price limits, and allows at most one 1,024-token
completion under a 30-second total deadline. There is no retry, alternate
route, web tool, private corpus lookup or voice activity. `receipt.json`
records the reservation and observed usage. `review.private.json` exists
only after validation and contains the supplied source context.
[OpenRouter privacy and ZDR policy](https://openrouter.ai/docs/guides/features/zdr)

## Measured scope

One authored exercise completed on the explicitly selected GOOL-configured
GPT-4o-mini/Azure route. The provider reported 399 input tokens, 125 output
tokens and USD 0.00013485 under a USD 0.02 reservation. Three questions
passed the grounding and contract checks. Two questions overlapped, and
the potential-contradiction label paired reports about distinct actions.
One sample cannot establish semantic utility. The separate Hermes primary
attempt timed out and a Mistral attempt returned HTTP 404, with unknown
charges preserved. No private corpus or collected publisher report entered
these probes.

A separate private offline pilot used eight held-out authored cases and
32 authored records in a closed, read-only fixture database. It reused
GOOL's token selector and source-tier functions with a case-bounded FTS5
query and top-three selection. It recovered 13 of 14 relevant records,
with 13 of 15 selected records relevant and no citation-byte mismatches.
It missed a critical indirectly referenced completion record and retained
two distractors. That failure blocks adoption of this retrieval approach.
The pilot made zero hosted inference calls. Comparative semantic quality
remains unmeasured. The shared corpus and ordinary GOOL dispatcher were
outside this fixture's scope.

## Remaining qualification

The existing [analyst boundary](qualification/GOOL_ANALYST_BOUNDARY.md) still
applies. A fresh history list does not isolate GOOL's ordinary dispatcher from
shared memory, transcripts, diagnostics, enrichment, tool execution or cost
records. Its ordinary retrieval connection can initialize/migrate database
schemas. A separate historical archive has a real read-only query pattern, but
it is not a drop-in isolated interface to the main retriever. No private GOOL
corpus belongs in a public monitor artifact.

Private corpus retrieval and hosted use of additional sources require their
own authorization and isolation evidence. A reviewed publication workflow,
a browser operator surface and the larger comparison remain open.

The [frozen synthetic contract benchmark](qualification/gool-review-contract-benchmark.json)
checks schema, hashes, provenance, citations, Unicode and adversarial responses.
Passing it says nothing about GOOL's semantic quality. Its separate held-out plan
asks whether review adds actionable, correctly contextualized questions beyond
the current local baseline, with blinded human adjudication, unsupported-premise
and abstention measurements, repeat-sample disagreement, reviewer time, latency
and actual cost. Thresholds must be fixed before that run. Semantic utility and
full GOOL integration remain **unverified**.

Run `python -m pytest backend/tests/test_gool_review_contract.py backend/tests/test_gool_review_runner.py`
from the monitor checkout. The offline tests use an intercepted provider
transport and require no GOOL service or credential.

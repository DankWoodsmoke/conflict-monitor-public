# GOOL integration handoff — October 30, 2026

The current operator-run adapter and its measured scope are in
[Private GOOL evidence review](GOOL_REVIEW.md). The original handoff below
preserves the broader proposed evaluation and retrieval boundary.

Copy the prompt below into the existing GOOL chat. It requests engineering and
bounded measurement, not a change to GOOL's shared voice service or a public
deployment. This document contains no private corpus, credentials or source bodies.

---

I want you to start a proper, useful integration between my existing GOOL system
and Conflict Monitor. Work from the actual code and current evidence. Do not
equate calling Hermes with using GOOL, and do not stop at another architecture
description when an isolated implementation or offline test can be completed.
Modest inference cost is acceptable when it buys measurable usefulness. Keep
the integration private until its behavior is qualified; hosting on
Ianmalcolm84.com remains undecided.

## Workspaces and first reads

- GOOL: `C:/Users/NewUser/Desktop/projects/gool`.
- Current monitor candidate: `C:/Users/NewUser/Desktop/projects/conflict-monitor-release`.
- Original monitor/history: `C:/Users/NewUser/Desktop/projects/conflict-monitor`.
  This is read-only reference; preserve its dirty worktree and archive.
- Published `v0.2.0-rc.2` is an immutable earlier release. This request does not
  replace its assets, deploy a site or authorize merging legacy data into live data.

Read the cross-project `CLAUDE CODE BRANCH/KNOWLEDGE_BASE.md` by relevant concept,
the project hub, `~/.codex/guidance/OPERATING_GUIDANCE.md`, then GOOL's `AGENTS.md`,
`CLAUDE.md`, the latest dated block of `BRANDON_RETURN.md`, and
`WEB_AGENTIC_SPEC.md` sections 0 and 2. Inspect actual source and applicable
tests before reusing an interface. Preserve existing user changes. Do not treat
dated corpus totals, gate counts or a cold admin endpoint as current readiness.

Read these monitor files before designing the interface:

- `docs/GOOL_REVIEW.md` and `docs/qualification/GOOL_ANALYST_BOUNDARY.md`.
- `backend/app/services/gool_review_contract.py` and its tests.
- `docs/qualification/gool-review-contract-benchmark.json`.
- `backend/app/services/local_briefing.py`, especially the source-permission
  guard and immutable source snapshots; `docs/LOCAL_AI_VIDEO.md`.
- `docs/LOCAL_REVIEW_2026-10-30.md`, `docs/METHODOLOGY.md`,
  `docs/LOCATION_REVIEW.md`, `docs/HISTORICAL_BACKFILL.md`,
  `docs/HISTORICAL_RECOVERY.md` and `docs/CONTEXT_RECONCILIATION.md`.
- Private technical audit, for local inspection only:
  `artifacts/private/gool-value-20261030/AUDIT.md` and `verification.json`.

The source was at GOOL commit `a3fddb7afd88bfc6a6803d130849409f4582805d`
when inspected on October 30. Recheck HEAD and relevant file hashes; this is an
identity pointer, not a claim that a running service uses those bytes.

## The useful job

Start with a private, cited evidence reviewer. Given a small frozen set of
reports, identify a genuinely useful missing source, possible contradiction,
changed account, or alternative explanation a reviewer should check. Distinguish
different times, places, speakers and quoted claims before calling two reports
contradictory. Ask an answerable evidence question and retain the supporting
context. Abstain when the bundle cannot support one.

GOOL's potential advantage is its curated source repository, source lineage,
literal locators, retrieval/reranking, topic/entity lookup and existing integrity
checks—not merely the rented synthesis model. Measure which of those actually
helps this task. The existing `audit_primary_contradictions.py` pattern is useful
because it surfaces incompatible statements for review without resolving them
automatically. Its narrow status regexes are not a general conflict-analysis engine.

Keep GOOL's existing voice/persona policies intact. Build a distinct analyst
boundary rather than injecting voice output into the monitor. A corpus tier,
editorial alignment, persuasive framing or repeated claim is not incident truth,
source independence or a location measurement. Preserve attribution and
uncertainty in this analyst product. Do not import persona instructions as
authority to erase conflicting evidence or to rewrite source records.

Do not build a relationship graph from co-mention counts. The measured negative
Atlas result is in `gool/audit/atlas_usefulness_2026-10-05.md`; source drawers and
locators are more useful starting points than an unqualified network diagram.

## Existing monitor contract: reuse it, do not quietly widen it

`monitor-private-review-v1` already provides:

1. `build_packet(snapshot, snapshot_at=...)`: one to eight permission-eligible
   source rows, at most 2,500 characters per supplied excerpt, publication and
   snapshot clocks, original/provided text hashes and a canonical packet hash.
2. `build_review_request(packet)`: provider-neutral messages, exact JSON schema,
   no tools, and an explicit not-executed status.
3. `validate_review(raw, packet)`: strict schema, matching packet/source hashes,
   exact Unicode spans and browser UTF-16 offsets; at most eight review questions.

Allowed kinds are `potential_contradiction`, `missing_evidence` and
`alternative_to_check`. A contradiction requires two distinct reports; that does
not establish two independent sources. Coordinates, severity, classification,
verified status and unknown fields are rejected. Validated output remains
private, model-generated and unreviewed, with no event mutation or publication
authority. The tests deliberately show that a leading question can pass literal
citation validation; schema success is not semantic usefulness.

The current packet contains monitor source rows only. If GOOL needs additional
repository evidence, propose an explicit versioned extension with source kind,
stable namespaced identity, exact locator, text/version hashes, source and
retrieval clocks, permissions and provenance. Do not fabricate monitor event IDs
for GOOL chunks or insert hidden context that the reviewer cannot inspect.
Keep v1 working unchanged. Return the proposed extension to the monitor owner
before editing monitor-owned contracts or wiring a runtime consumer.

## Stage 1: implement and prove isolation without inference

Audit the call graph first. Earlier source inspection found:

- Ordinary `dispatch_oneshot` / `dispatch_streaming` writes shared memory,
  transcripts, diagnostics and potentially enrichment/tool state.
  `history_override=[]` does not make it isolated.
- Main `gool/brain/rag.py::open_db()` opens writable SQLite and initializes or
  migrates schema. Ordinary `lookup()` is not a read-only boundary.
- `gool/research_archive.py` has a real `mode=ro` plus `query_only=ON` pattern,
  but it is a separate historical archive, not the main retriever.
- `system_prompt.load(build_if_missing=False)` avoids building a missing prompt,
  but does not isolate the rest of dispatch.
- The model client supports an explicit model but shares cost/rate state. Its
  daily preflight is not an atomic budget for this job.
- A one-pager hash attestation is not an existing signed evidence-package API.

Use or build a supported additive text adapter with injected dependencies and a
private run directory. Start with synthetic fixtures. Make it impossible for
the adapter to reach ambient room state, transports, speech, control markers,
enrichment/writeback, shared history, implicit web searches, model judges or
fallback cascades. Do not monkeypatch production guards to manufacture a pass.

Qualify read-only retrieval separately. Any production-derived snapshot must be
transactionally consistent and remain private; copying a live SQLite main file
without its WAL is not that proof. Missing prompt/index/schema inputs must fail
closed, not rebuild shared state. Show allowed reads, attempted writes denied,
bounded queries/results, isolated caches/logs and actual before/after checks.
Do not export the private corpus or persona to a hosted provider. Initially use
synthetic or already permission-eligible monitor evidence; identify exact source
scope before any later repository-content export. Local availability is not a
redistribution or AI-processing license. Reuse the monitor permission guard,
including Telegram restrictions, before cache lookup or inference.

Do not start/stop shared services, change schedules, rebuild corpus/entity
indexes, alter persona/tier policy or launch X/Discord to test this adapter.
Own any disposable CPU/GPU process by exact command, PID and creation time, with
bounded resources and cleanup; do not claim another project's worker. If a
necessary shared boundary is absent, implement the isolated portion and report
the precise remaining dependency instead of using ordinary dispatch as a shortcut.

Test wrong/stale hashes, source revisions, truncation, Unicode, duplicate JSON
keys, malicious source instructions, denied source permission, timeout, partial
response, cancellation after a provider accepted work, and budget exhaustion.
A failing run must not overwrite a prior good artifact or leave hidden work running.

## Stage 2: measure value and cost

Freeze the task, source bundles, adjudication rubric and promotion thresholds
before evaluating. Use the existing 24-bundle held-out plan, stratified across
denials, quotations, changed dates, syndication, ambiguous geography, consistent
accounts and prompt injection. Keep development examples separate.

Compare three arms on the same permitted evidence:

- Current local extraction alone.
- The same pinned hosted model and analyst task, without GOOL retrieval/guards.
- The isolated GOOL adapter with its precisely recorded extra components.

The middle arm separates the value of a larger model from the value GOOL adds.
Use two samples per model arm per held-out bundle if the reserved budget permits;
do not pretend a smaller sample is the full 24-bundle study. A synthetic-only
retrieval experiment qualifies plumbing, not real repository utility.

Capture a dated official provider/model capability and price quote at execution
time. Select one explicit provider/model, bounded context/output and concurrency
one. Set hard call/token/deadline/cost caps in a run manifest before spending,
reserve worst-case remaining cost atomically, and include failures, cancelled
requests and retries. Suggested initial development envelope: at most 24 calls,
1,024 output tokens per call, 30 seconds per request, 20 minutes total and USD1;
reduce the run if current pricing makes that envelope impossible. This is a
proposed ceiling, not a spend receipt or a claim that every model fits it.
The later full 96-call held-out design needs its own explicitly recorded bounded
budget within the user's modest-cost intent. No hidden judge, tool or retry spend.
Unknown charged usage must remain unresolved and consume its reservation.

Measure contextual citation correctness, unsupported factual premises, false
contradictions, useful new evidence questions, justified abstention, differences
between repeated samples, reviewer time, median/tail latency and actual cost.
Keep original failures. Human adjudication must be blind to the arm; if no
independent reviewer is available, prepare the randomized worksheet and report
semantic utility as pending. Do not replace that missing measurement with an
LLM judge, attractive prose or contract-test counts.

## Later capabilities: propose separately, do not mutate events

Useful future work includes source-linked change briefs, detecting revisions and
retractions, comparing known coverage against explicit questions, and proposing
an investigation checklist. GOOL must not grade a source as truthful merely
because it agrees with a preferred view or reports first.

Classification and severity need a separate source-bound proposal contract.
Preserve actor/claimant, reported action, denied/quoted/uncertain stance, literal
quantities and units, event-time versus publication-time, and unknown fields.
Severity is an unreviewed impact estimate under a documented rubric, separate
from confidence, reporting volume and review priority. Never convert no score
into a medium score, a thermal detection into a strike, or an allegation into a
confirmed explosion. The monitor team is currently repairing this legacy path;
coordinate against their final bytes instead of adding a parallel implementation.

Geolocation is its own evidence problem. GOOL may propose a literal place mention
or ask for corroborating evidence; it must not generate accepted coordinates,
equate an actor with headquarters, collapse a broad area to a facility point, or
plot denied/quoted locations as incidents. Acceptance needs a separate durable
review/correction record with source/version binding, role, precision and provenance.

Historical work must retain original rows and correction chains. The April
archive is separate and includes old model assertions and unknown-location
sentinels. Do not feed it wholesale to GOOL, silently merge it with current data,
or label old evidence as current. A read-only historical viewer and per-source
coverage/retention display are useful monitor work, not proof of missing-month
recovery. More feeds and lower polling latency do not prove truth or firstness.

## Deliverables and how the monitor consumes them

Deliver an additive isolated adapter, offline tests, a deterministic synthetic
request/response example, and a private run manifest with source/code/model/prompt
hashes, exact commands, exit codes, resource ownership, all calls/costs and
limitations. Provide a compact compatibility note mapping your output to v1 or
the proposed versioned extension. Include the reproducible command for the
monitor team to run without starting GOOL voice/admin services.

Put the technical handback under a new private dated run directory in GOOL's
`audit/` or existing appropriate private artifact structure. Do not include
credentials or bulk corpus. Identify exact file paths and hashes in your final
response; I will bring that response back to the monitor chat. Do not send
messages to other chats automatically.

The monitor team will independently check the adapter and run its validator
against the frozen packet before considering a manual analyst-only consumer.
Only then should we add a supervised, idempotent job with cancellation, stale
source invalidation, a private review UI, no automatic reruns and explicit
operator demand. Public projection/publication is a later separate decision.

Report separately: implemented, executed, measured useful, and still unverified.
Start with Stage 1 now and continue all work within the established boundaries.

# Optional GOOL analyst boundary

GOOL may be useful as a private analyst that critiques source coverage, proposes
competing explanations, and identifies evidence gaps. Its incremental benefit
and cost for this monitor have **not been measured**. It is not part of the
qualified free ingestion pipeline, and no paid GOOL inference was performed in
this audit. No GOOL service, voice transport, persona, corpus, index, or source
file was changed.

Static inspection of the existing text-dispatch and benchmark paths found that
fresh conversation history alone does not isolate a run. Normal dispatch can
write shared runtime/diagnostic and enrichment state, perform retrieval through
a database-opening helper that creates or migrates schema, and perform further
web/model work. Redirecting a benchmark report or some log settings does not
redirect every side effect. A dry run that skips inference does not qualify an
actual analysis. No gate was monkeypatched to manufacture isolation.

The lower-level model client can accept an explicit prompt, empty history,
explicit model and no tools. That bypasses GOOL's retrieval and dispatch guards;
testing it would be a prompt/model comparison, not a qualification of full GOOL.
It was not invoked as a substitute for the missing isolation boundary.

A supported text analyst adapter must establish these properties before a
usefulness benchmark or product integration:

1. Explicit bounded event IDs and an immutable source-snapshot hash, with
   citation/span IDs. Private retrieval requires separate explicit scope;
   private material cannot automatically enter a public briefing or release.
2. A genuinely read-only retrieval session, no schema migrations, corpus/index
   mutation, enrichment/writeback, shared history or control-marker consumption.
   Missing required prompt/retrieval snapshots must fail closed rather than
   rebuilding shared state. Any caches and diagnostic/cost logs belong to an
   isolated run namespace. Normal relevant reasoning and safety guards remain.
3. No speech, transport startup, ambient room state, publication permission,
   hidden web/tool calls, judges or fallback model cascade. Resource ownership
   and CPU/GPU limits are explicit.
4. An explicit model, bounded input/output and call count, current provider
   pricing, and a conservative caller-approved budget reserved before a run.
   A shared daily-spend preflight alone cannot bound a multi-call request.
   Preserve actual model, token/cost metadata, latency and every failed attempt.
5. A private unreviewed result carrying the source hash, cited factual spans,
   alternative hypotheses, missing corroboration and uncertainty. The monitor's
   underlying reports remain unchanged. Coordinates, severity and incident
   truth cannot be asserted solely by the analyst.
6. A frozen benchmark comparing citation correctness, unsupported assertions,
   false certainty, useful evidence gaps, cost and latency against the current
   local baseline. Preserve failures and require operator review before any
   public result. An analyst's framing is not independent corroboration.

The current release therefore preserves this as a concrete integration design,
with the existing full-GOOL text interface unqualified for isolated use. The
free local triage and narrated source-card workflow has separate execution
evidence and explicit limitations; it does not imply GOOL qualification.

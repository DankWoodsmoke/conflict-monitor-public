# Evidence and analysis methodology

This monitor organizes reports and observations. A marker is a report, not a
verdict. Source diversity, speed, repeated publication, model fluency, and a
satellite observation near a report are not independent confirmation.

## Evidence contract

Each event exposes an `evidence` object. `reported` means a source label is known;
`multiple_reports` means multiple distinct publisher labels are present;
`sensor_observation` identifies a thermal observation; `unassessed` means the
metadata cannot establish even that coverage. These are descriptive states, not
probabilities. `independent_origin_count` is `null`, `independence_status` is
`unassessed`, and `verification_basis` is `none` until an actual claim-level review
and provenance workflow exists. Different networks may repeat a single origin.

Source reliability is an inherited editorial prior about a publisher. It is not
the probability that an incident occurred. Severity describes the reported
impact. Extraction status describes whether the configured model returned valid
structured data. Location precision describes the spatial evidence. These axes
must not be combined into an unexplained confidence percentage.

`reports` retains raw text, source URL, source-scoped message identity, publication
time, extraction status, and a SHA-256 hash of the raw UTF-8 text. Identical replays
do not increase the report count. A changed version of the same message is kept
as another revision without becoming an independent report. Hashes establish
byte identity, not authenticity or truth. Legacy records can lack the individual
reports needed to reconstruct their historical coverage.

Preservation is application behavior checked by execution receipts. The runtime
database role still has modeled-table DML permissions; this release does not
provide an externally witnessed, write-once cryptographic audit log.

For native feeds, the preserved report text is the parsed, trimmed title plus
two line breaks and the feed description/summary, then outer trimming. XML
entity decoding occurs before this UTF-8 text hash. This is attributed publisher
metadata, not a full article, original HTTP/XML byte archive or proof of a
publisher's identity. Network-response hashes in the dated connector probes
describe a different byte layer. Atom entries without a publication field can
retain an explicitly recorded source-updated clock; it must not be used to
claim initial publication or incident time.

Publication time is not necessarily incident time. A repost can describe an old
event. Until incident-time extraction and review are separately qualified, the
timeline must be interpreted as report timing. Unknown coordinates stay unknown;
a city or country centroid is not an impact coordinate. Legacy gazetteer points
have unassessed precision.

## Reports, claims, and analysis

A source can assert, deny, question, quote, or relay a claim. Extraction must
preserve that relationship and the original actor. A government's statement is
evidence that it made the statement, without automatically establishing its
underlying allegation. The same distinction applies to media, eyewitnesses,
independent researchers, and this project's own generated analysis.

An analyst lens may emphasize institutional incentives, independent reporting,
historical patterns, competing hypotheses, or economic dependencies. That lens is
interpretation and should remain labeled as such. It must not rewrite raw source
records, convert a preferred interpretation into a sensor observation, or treat
agreement with an editorial position as corroboration. A model-generated SITREP
does not become an additional source for its own claims.

The public build carries no private GOOL corpus, persona, credentials, or source
rankings. It applies reusable engineering lessons: retain provenance on derived
items, separate source type from assertion, preserve contradictory evidence, make
unknowns explicit, and validate exact artifacts before promoting them.

## Clustering and disagreement

Real-time fuzzy clustering is deliberately conservative: matching event type,
15-minute report window, at most 2 km between available coordinates, at least
eight substantive tokens, and Jaccard similarity at least 0.92. A lexical guard
rejects detected English negation/attribution differences and incompatible
explicit numbers. These parameters are engineering defaults, not validated
incident-identification accuracy. They can miss translated or differently worded
reports and cannot prove that two similar reports describe the same event.

An exact source URL scoped to its publisher can identify a replay when supplied
by ingestion. Clustering retains raw reports and does not raise source
reliability, replace incident coordinates, or promote an alarming severity.
Network pairs never confer confirmation. Unlocated reports do not undergo fuzzy
spatial merging.

The retrospective matcher exposes review candidates from recent reports. It
does not delete records, prefix summaries with merge decisions, or create
confirmations. Contradictory candidates remain visible. A full claim graph,
syndication-lineage resolver, human review UI, and calibrated multilingual
semantic matcher are future work, not completed capabilities.

Administrative geocoding and reclassification stage up to 100 proposals for
review; they do not rewrite published event coordinates or summaries. Live
collection and provider configuration must be enabled before those jobs run.
The inherited bulk text-based deletion endpoint is disabled. The inherited
external wave-dataset importer is also disabled until its licensing, version,
provenance, timestamp, and coordinate handling are qualified. Those operations
return explicit errors; they must not be advertised as completed imports.

## Model extraction

Source text is untrusted data. Batch records have stable input IDs; the entire
response is schema-validated before any result is returned. Missing required
fields, invalid IDs, unsupported event types, missing credentials, and provider
errors cannot turn into a fabricated military event with a default severity.
Failures return an explicit nonpublishable status. Original source reports must
remain available for later reprocessing.

Successful extraction results can be reused for identical raw text, but reuse
does not discard another publisher's report. Flags, nationalities, and the
longest place-name mention do not override an unresolved incident location.
Short reports are not rejected solely for being short. Input framing and schema
validation reduce certain failure modes; they do not demonstrate comprehensive
prompt-injection resistance or factual accuracy.

Model names are configurable. A newer model is a candidate for evaluation, not
an automatic upgrade. Promotion requires the same frozen fixtures plus separate
reviewed multilingual examples, false-merge and missed-merge measures,
attribution/negation checks, source-span fidelity, failure behavior, latency,
and cost. Synthetic examples are not a substitute for a held-out labeled corpus.

## Satellite observations

NASA FIRMS reports active fire and thermal anomaly detections. The pixel center
does not identify a precise strike location, and a thermal detection does not
establish cause, actor, weapon, casualties, or damage. NASA describes several
possible causes and cautions about spatial resolution and viewing geometry.
[NASA FIRMS map explanation](https://firms.modaps.eosdis.nasa.gov/map/)

VIIRS confidence is retained as `low`, `nominal`, `high`, or `unknown`; the
application does not invent 35%, 65%, or 85% probabilities from these categories.
Numeric confidence is preserved only when it is actually supplied. It still
describes a detection attribute, not conflict-event certainty.
[NASA detection-confidence explanation](https://forum.earthdata.nasa.gov/viewtopic.php?t=5182)

The correlation view records distance and time difference between a thermal
observation and a reported event. It never snaps incident coordinates to a
hotspot or boosts reliability. Industrial-zone overlap is context, not proof of
gas flaring. Fire radiative power is not a weapon-yield or damage estimate. High
FRP observations remain `thermal_anomaly` records with cause unassessed.

Missing detections do not establish absence of a fire; acquisition timing and
obscuration can prevent detection. Context imagery links do not prove that the
imagery is contemporaneous with the report. Successful empty API responses clear
the live cache; a failed fetch preserves the age of the last successful data and
exposes an error state.
[NASA fire-alert notes](https://firms2.modaps.eosdis.nasa.gov/alerts/notes.php)

## Verification boundary

WebSocket delivery uses bounded per-client queues and bounded admission. A slow
browser cannot hold the shared publish lock; queue overflow disconnects that
client. Shutdown cancels owned handshakes and sender tasks. These controls protect
service responsiveness and do not prove successful receipt by a remote browser.

Market snapshots retain provider attribution and unknown observation times.
Cache age is the time since successful retrieval, not market observation age.
History refreshes are scoped to the requested range. Refresh work is limited to
four asynchronous tasks and two actual provider jobs, with a 30-second retry
cooldown after failures. Request cancellation cannot free a running provider
job's capacity early. Python cannot forcibly terminate an executing provider
thread: shutdown cancels owned asynchronous work, while running provider I/O may
continue and can delay process exit. Provider isolation or deployment-level
termination remains necessary for a hard process shutdown deadline.

Offline regressions exercise repeated sources, revisions, network diversity,
negation, changed numbers, unlocated reports, input-ID binding, incomplete model
batches, provider absence, invalid satellite data, and noncausal spatial links.
They verify specific software behavior with mocked external dependencies.

They do not certify live connector coverage, field accuracy, source independence,
multilingual model quality, real-world geolocation, or the truth of a SITREP.
Skipped, absent, failed, and unexecuted checks must be reported separately from
passes. Synthetic showcase data is labeled and cannot count as live evidence.

# Local symbol, tracking and assessment review — October 30, 2026

This continues the unreleased candidate after [the earlier local review](LOCAL_REVIEW_2026-10-30.md).
The published RC.2 files and the original project remain separate. The implementation
and bounded tests described here are not a factual validation of every report,
surveyed position, or a public-production qualification.

## Aircraft that looked like boats

The domain mapping was correct: aircraft records reached aircraft symbols and
AIS records reached vessel symbols. The failure was visual. At regional zoom,
the old 32-pixel marker shrank to 16 pixels, leaving a roughly 10-pixel interior;
the unknown-direction aircraft profile could resemble a hull and superstructure.

Aircraft now have stronger wings/tails, vessels have a distinct bow/stern or
side hull, and labels include the track category beside its original identifier.
Track markers render at 36 pixels nearby and at least 24 pixels at regional zoom.
Unknown direction retains a fixed, explicitly non-directional identifier. Ground
emitter categories remain separate. The tradeoff is more overlap in dense areas;
search and selected-position details remain available when markers overlap.

The visual review used equal colors, rotations, fresh/hollow variants and actual
Cesium billboards, including 192 SVG samples and four near/far scenes. Those
synthetic scenes establish readability in their test conditions, not live source
accuracy. Final Google-imagery inspection and exact source/image bindings are
recorded in the private execution receipt.

## Plotting and replay fidelity

Future snapshots preserve the source's coordinates without an additional
five-decimal rounding step, observation and receipt clocks, direction basis,
reported altitude reference, registration and available position-quality codes.
Vessel course and true heading remain separate. Absent vessel speed/direction,
navigation status and aircraft position-source metadata remain unknown rather
than becoming zero. Old rows are not rewritten or given invented metadata.

The ADS-B adapter preserves whether direction came from ground track or reported
true heading; OpenSky track remains course over ground. NIC/NACp appear as raw
provider categories, with no invented error radius. These meanings follow the
[readsb JSON documentation](https://github.com/wiedehopf/readsb/blob/dev/README-json.md).
Coordinate bounds, source age and byte preservation cannot detect every bad
receiver fix, spoof, identity error or provider omission. Aircraft still use
surface projections because a common validated vertical reference is absent.

Timeline counts/ticks now share the report-position admission rule, excluding
nonfinite/out-of-range coordinates and the recovered unknown-location sentinel.
New model classifications cannot geocode an unsupported place name into an
accepted incident position. The separate literal place-review workflow remains
available without changing source bytes or event coordinates.

## Classification, impact and critical alerts

The live baseline sample contained 492 raw unclassified reports and eight thermal
detections among the latest 500 records; all were unscored. RSS was in reports
mode. Local AI availability does not mean automatic report classification is
enabled. These are different pipeline capabilities.

Recovered model/default paths could assign a medium score without evidence,
discard useful model metadata, accept unsupported extracted fields, and turn
raw numeric severity into anomaly or automatic critical/escalation output.
Neutral defaults and source-bound, versioned extraction now replace those paths.
Model snapshots retain the original-text hash, model/prompt/rubric identifiers,
literal evidence excerpt, stance and bounded extraction fields. The excerpt is
preserved as the displayed model summary rather than trusting a new paraphrase
of quantities and units. The source ledger remains separate and unchanged.

Validation rejects malformed/ambiguous structure and checks literal support and
known qualifier omissions. These are limited defenses, including English lexical
checks; they do not establish multilingual semantic correctness. The classifier
has not earned an accuracy claim from mocked model responses or schema tests.
Telegram model processing now applies the existing source-permission boundary
before inference/cache lookup.

The API and interface distinguish unscored reports, sensor observations,
source-bound model estimates, invalid assessments and unreviewed legacy numbers.
Legacy scores remain inspectable, but cannot drive ranking or critical styling.
Earth's scored-layer filter uses the same admission rule as the report feed;
the final manual review caught and removed a leftover raw-score comparison.
Source-bound model scores remain visibly unreviewed. Numeric thresholds are
filtering aids, not confirmed alerts; automatic critical/anomaly/escalation paths
remain unqualified. Synthetic exercises are explicitly separate.

This separation is informed by the [OASIS Common Alerting Protocol](https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2.html),
which treats severity, urgency and certainty as distinct fields. This application
does not claim CAP compliance or a calibrated warning service. A useful public
alert system still needs a versioned impact rubric, source/stance adjudication,
correction handling, held-out evaluation and separately accepted alert criteria.

## Recovered capability gaps and GOOL

The April code already included Google imagery, replay, richer SITREP sections
and video composition. Useful remaining work includes a visible historical-job
and coverage interface, a separate read-only April archive viewer, source-linked
change/thematic briefs, and richer source-card video layouts. Repeated-source
confidence, thermal-as-attack confirmation, guessed ownership and simulated
thermal/orbital displays are not trustworthy capabilities to restore.

Tracking retention remains 30 days; replay excludes some aircraft and ground
contacts, and report display remains bounded at 5,000 loaded records. No change
here reconstructs seven missing months or makes old classifications current.

The [copy/paste GOOL handoff](GOOL_INTEGRATION_HANDOFF.md) requests an additive
isolated adapter, exact source/corpus provenance, no ambient shared-service
effects, and a local/bare-model/GOOL comparison of useful findings, unsupported
claims, latency and cost. Its proposed cost envelope is not a spend receipt.
No GOOL inference, shared-service start or public-site deployment occurred here.

## Execution evidence

The private `artifacts/private/symbol-severity-20261030/` directory retains the
baseline, rejected visual attempts, regression logs, peer findings, image tests,
database-preservation checks and browser observations. Final counts and exact
images belong to the final receipt, not earlier intermediate test runs.

The actual backend application image passed 828 tests and 29 subtests without
mounting application source or the private environment into the test container.
The final frontend passed 305 tests in 24 files with before/after source and
build hashes. Four synthetic browser cases exercise the specific assessment,
layer-filter, identifier, mobile disclosure and horizon regressions; twelve
live Google-imagery cases cover three browser engines and four viewport sizes.
Seven HTTP/cache-policy cases passed. These are bounded checks, not exhaustive
verification of every source report, external stream or production environment.

The application cutover preserved all twelve tables, sequences, indexes,
geometry and extensions against a same-snapshot logical backup. The final
layer-filter correction replaced only the frontend and retained the same
backend/database containers. Actual post-cutover replay snapshots contain the
new observation/direction/quality metadata. A 500-event live API sample
contained 492 unscored reports and eight sensor observations; no record in that
sample qualified a verified critical alert, and report mode still did not
request model classification.

The final Chrome inspection separately checked an AIS vessel's reported
heading/course and an ADS-B aircraft's category/identity/quality fields, then
left the app on real Google 3D imagery. The private final receipt binds the
screenshots, source/image identities, raw observation files and test logs.

Existing OS package findings, the unresolved canonical backend rebuild transport
problem, physical-device coverage and final-image long-session qualification
remain separate gates. The local backend application image retains the prior
qualified runtime layers; application tests do not clear those OS findings.

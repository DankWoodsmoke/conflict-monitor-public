# Regional overview and selected-report review

The user's rejected regional screenshot exposed a gap in the earlier qualification:
correct type mapping and isolated symbol tests did not establish that a crowded
Earth view was usable. Aircraft and vessel positions were overlapping, difficult
to distinguish, and difficult to select. This review is an additional local
candidate; it does not replace the published RC2 archive.

## Changes

- Overlapping tracking positions are partitioned into screen-area groups with
  explicit aircraft, vessel, ground-emitter and obstruction counts. Native buttons
  show the groups, support keyboard activation, and reserve space around the
  workspace controls. A group label is not a shared geographic coordinate.
- The contact index searches all members, including those beyond the first page.
  Selecting a contact restores its individual source marker and exposes its
  original identifier, coordinates, observation clock and direction basis.
- Source entities retain their original coordinates. Horizon and camera-frustum
  checks run before grouping. Reports are not merged into track groups. If no
  display slots remain, the source markers are retained rather than silently lost.
- A real polling/rendering defect was repaired: replaced Cesium graphics could
  leave grouped source glyphs visible underneath badges. Visibility now updates
  before the data-source visualizers, with a bounded settling frame after a
  visibility change. An unchanged scene does not request continuous rendering.
- The globe depth test was clipping the aircraft glyph at its surface anchor.
  Surface annotations now retain complete silhouettes, with separate horizon
  rejection. A first-frame GPU test also exposed delayed visibility consumption;
  the public data-source update now applies it before render commands are built.
- Contact rows keep their identity, height and position across source updates.
  Departed contacts become disabled slots, and selection resolves the current
  source ID. New members require explicit refresh/search, bounding retained slots
  while the panel remains open. This repairs a live selection mismatch without
  freezing current source coordinates or presenting expired positions as current.
- Controls and selected-position cards are compact by default. Additional city,
  imagery, source and evidence details remain available on demand. Tracking
  freshness exposes retained observations separately from successful API receipt.
- [Selected-report local analysis](REPORT_ANALYSIS.md) binds one explicit local
  inference to preserved source text and provenance. It returns review proposals,
  not accepted classifications, severity, incident locations or critical alerts.
- Market quotes retain provider metadata and distinguish unknown observation time
  from retrieval time. Polling is serial, abortable, and explicitly marks an aging
  cached snapshot delayed. A provider refresh cannot prove quote freshness.
  Empty startup snapshots receive at most four short retries, rather than making
  the user wait five minutes after the provider finishes loading.
- Google attribution can wrap after tiles load. The contact controls reserve its
  measured height. Short landscape uses bounded freshness details and compact
  controls so grouped tracks retain display space. The live timeline shows the
  window endpoint explicitly; the full start/end interval remains in its tooltip.
- The running frontend exposes a reproducible source fingerprint in
  `build.json` and Sources & health. This identifies bytes, not release readiness.

## Qualification boundaries

Tests include dense synthetic scenes, a frozen captured distribution of actual
tracking positions, source/type/clock conservation, native group activation and
search, original-coordinate selection, polling refresh, opposite-hemisphere
exclusion, and mobile viewport/touch emulation. Captured tracking fixtures are
explicitly marked recorded; no source clock is rewritten to make them look live.

## November 4 local qualification

Frontend build `dfb5ee2abaff` passed 395 tests, a production build, dense
synthetic and recorded-position browser cases, and 12 live Google layout cases
across Chromium, Firefox and WebKit. The live matrix included 320 px portrait,
390 px portrait, 768 px portrait and short landscape. Review covered 24
screenshots and measured 81–138 px of wrapped provider attribution with
positive separation from the controls and contact bar. The desktop captures
include the regional overview and close, oblique Google detail in Dubai.

The admitted build coalesces panel geometry writes outside ResizeObserver
delivery, resolving the WebKit delivery-loop errors in the previous attempt.
It retains the selected marker and all source members. Dense selected views
at 320 px can still fall back to individual markers when the controls and
detail card leave no space for group badges. A separate layout experiment
recovered group capacity while keeping the selected marker and keyboard
controls accessible. That experiment has its own evidence and remains
outside the admitted build.

The fresh canonical backend build and isolated PostgreSQL/PostGIS execution
both passed. Current backend and database images retain High vulnerability
matches. A separate concurrent transaction test reproduced a report omission
during reconnect. The current local review covers specific code and measured
workloads. Provider-coordinate accuracy, model semantics, complete historical
coverage and physical-phone behavior remain unverified. Public deployment
and a replacement GitHub release remain unqualified.

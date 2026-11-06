# Product comparison and next capabilities

Reviewed November 5, 2026. The baseline is the privately qualified RC.4
source and its recorded live evidence. This review compares actual local
code with publicly documented capabilities. Palantir references below are
public Foundry documentation. They do not establish access to, or parity
with, a deployed Gotham installation. External projects were researched
through their own documentation. Their performance and accuracy were not
independently benchmarked here.

## What the baseline already supplies

The application has a persistent Google Earth canvas, distinct aircraft and
vessel symbols, screen-space contact groups, horizon rejection, source clocks,
historical tracking snapshots, a timeline, immutable source reports, citation
checks, optional local analysis/video, source health and durable reconnect
delivery. These capabilities have different qualification scopes in
[VERIFICATION.md](VERIFICATION.md).

Text search already exists in `LiveFeed`, inside the filter panel. It searches
summary, location and publisher name. It does not search the preserved raw text.
The baseline checks `search.trim()` for emptiness but matches the untrimmed
value. Search, filters and sort are component state, and the Earth-only feed
unmounts when the workspace changes. This is a concrete opportunity to improve
discovery and retain context without introducing a second search engine.
[LiveFeed implementation](../frontend/src/components/LiveFeed.tsx),
[workspace composition](../frontend/src/App.tsx)

The subsequent local candidate implements that first discovery slice. Search
is always visible, trims its query and matches canonically equivalent Unicode
in the original source body and existing fields. Application-owned filter
state survives feed remounts across workspaces and mobile layouts. The feed
shows matched and loaded-window counts, with its existing 600-card limit
stated when reached. Clearing the query restores input focus. Seven new
regression cases and the existing affected tests passed, 40 checks total,
and TypeScript passed. Build, visual and deployment admission belong to the
parent qualification run. Named saved views remain a later capability.

## Ranked gaps

Effort estimates describe implementation scope, with existing privacy and
source-integrity rules retained. They are planning judgments, not measured
completion dates.

| Priority | Useful capability | RC.4 gap and suggested implementation | Value / effort | Required evidence |
| --- | --- | --- | --- | --- |
| 1 | Persistent, discoverable investigation filters | Expose existing report search, trim its input, search appropriate preserved fields, and retain bounded filter state across workspace changes. Follow with named saved views containing time window, camera region and layers. | High / small first slice, medium saved views | Tabs and mobile drawer preserve criteria. Reset is explicit. Loaded coverage and empty results are clear. Stale saved IDs degrade safely. |
| 2 | Reviewed incident locations and assessment decisions | Place mentions and model output are proposals. Add an authenticated review queue with cited source spans, reviewer, time, precision or uncertainty area, decision reason and supersession. Accepting a location must preserve source report bytes. | Very high / large | Competing places, denials, multilingual names, actor headquarters and publication locations stay distinguishable. Audit/retry/concurrency tests prove acceptance history. |
| 3 | Cases that connect evidence and corrections | Source reports and candidate matches exist, but the baseline lacks a complete case workflow linking supporting evidence, disagreements, same-origin reposts and later corrections. Start with an explicit case and relationship table plus a readable evidence list. | High / medium to large | Similarity suggests a link. It never establishes independent corroboration. Revisions and rejected relationships remain auditable. |
| 4 | Geographic questions on the same Earth | Add a bounded region or drawn-area filter, a visible result count, and one selected-object inspector. The current region navigation and contact grouping do not provide a general polygon report query. | High / medium | Latitude/longitude order, antimeridian handling, unknown locations, loaded limits and server bounds are tested. Region filters preserve unresolved report discovery. |
| 5 | Versioned historical conflict context | Add UCDP as a separately labeled research layer, preserving dataset version, native event ID, time precision and geographic precision. Use its release history for backfill and comparisons. | High / medium | Native counts reconcile after import. Updated releases cannot silently rewrite a prior snapshot. Research events and breaking source reports remain identifiable. |
| 6 | Dated imagery discovery | The current imagery endpoint returns research links and a basemap reference with unknown acquisition date. Add bounded STAC discovery around a reviewed location and date, showing acquisition time, footprint, cloud information and provider links. | High / medium | Empty coverage and uncertain metadata remain visible. Alignment and resolution limits are shown before any before/after interpretation. |
| 7 | Shareable evidence packages and reproducible views | Add source links, permitted excerpts, hashes, selected time range and a manifest to a bounded export. A viewer link should restore its declared state and show unavailable records explicitly. | High / medium | Public exports exclude keys, private corpus and unauthorized publisher bodies. Export content matches the selected snapshot. Sharing permissions are enforced at the server. |
| 8 | Source coverage and multilingual use | Surface what each feed contributes by region, language, source role and freshness. Add native-language discovery and RTL presentation from reviewed cases. Existing publisher health does not establish completeness or independent origins. | High / medium to large | Original text is retained alongside labeled translations. Search and geolocation evaluations include Arabic and Hebrew. Coverage metrics avoid interpreting silence as absence of events. |

The reusable patterns are supported by Palantir's saved maps, spatial
intersection search and object relationships. Ushahidi documents saved searches,
collections, review workflows and notifications. These provide useful task
patterns for returning to an investigation and reviewing evidence.
[Palantir saved maps](https://www.palantir.com/docs/foundry/map/create-save-maps),
[Palantir spatial search and relationships](https://www.palantir.com/docs/foundry/map/add-to-map),
[Ushahidi capabilities](https://www.ushahidi.com/features/)

Atlos documents incidents containing multiple source items, review metadata and
a change feed, plus location/status filters and a review queue. Its source-media
workflow includes exact-link and perceptual duplicate detection. That suggests
a useful later media-review capability once this project's permitted media
intake and retention have been qualified. Perceptual similarity requires human
review and cannot authenticate a scene.
[Atlos incidents](https://docs.atlos.org/incidents/incidents/),
[Atlos search and queue](https://docs.atlos.org/investigations/searching-and-visualizing-data/),
[Atlos source material](https://docs.atlos.org/incidents/source-material/)

## Data and code adoption

| Candidate | Verified current condition | Adoption decision |
| --- | --- | --- |
| UCDP | Official downloads list GED 26.1 and monthly candidate data, with CC BY 4.0 and dataset-specific citation requirements. Candidate releases have a reporting lag. | Strong first structured historical connector. Preserve methodology and precision fields, with an explicitly dated layer. [UCDP downloads and terms](https://ucdp.uu.se/downloads/) |
| Copernicus Data Space STAC | The official catalog supports discovery by spatial and temporal criteria. Discovery, asset download and processing are separate operations. | Start with metadata and source links. Check the chosen collection's access and usage terms before download or redistribution. [STAC documentation](https://documentation.dataspace.copernicus.eu/APIs/STAC.html) |
| ReliefWeb | The current API requires a pre-approved appname. Original publishers may retain rights in report content. | Useful humanitarian context after application approval. Retain publisher links and permissions. [Official API documentation](https://apidoc.reliefweb.int/) |
| ACLED | Its data use is governed by an EULA, content usage terms and attribution policy. | Evaluate a deployment-specific entitlement before importing or exposing records publicly. [Official terms](https://acleddata.com/terms-and-conditions) |
| WorldMonitor | The repository documents multilingual/RTL support, native-language feeds, specialized views and cross-stream analysis. Its current code license is AGPL-3.0. | Study task organization and data adapters. Any code reuse needs a file-level license review and a compatible distribution plan. The monitor application's own license is MIT with explicitly listed third-party exceptions. [Official README](https://github.com/koala73/worldmonitor), [license](https://raw.githubusercontent.com/koala73/worldmonitor/main/LICENSE), [local license](../LICENSE) |
| Bellingcat toolkit | The maintained toolkit covers geolocation, dated imagery, verification and archiving, with caveats for individual tools. | Add reviewed outbound research links where they answer a selected-report question. Inclusion in a toolkit does not establish a tool's suitability for every investigation. [Toolkit](https://bellingcat.gitbook.io/toolkit) |

Google's photographic Earth remains the visualization surface. Its Map Tiles
policies restrict extraction, machine interpretation and unauthorized storage.
Any future GOOL image analysis should use separately admitted imagery whose
terms support that use. Provider attribution remains visible.
[Google Map Tiles policies](https://developers.google.com/maps/documentation/tile/policies)

## Visual direction

Use a restrained dark neutral surface, readable text and one accent for active
selection. Reserve alarm colors for assessed states with accompanying text.
Unclassified reports need a neutral visual treatment. Distinguish observation
age, transport status and assessed severity in both wording and shape. Keep
search and the selected object easy to find, and progressively expose detailed
provenance. The existing Earth should remain available across analysis tasks.
These are design recommendations for the separate visual audit, not measured
contrast or usability results from this research pass.

## Fit for ianmalcolm84.com

The site publicly presents a searchable audio/transcript archive. A monitor
could complement that material by linking a dated discussion to its cited
reports and reviewed geographic context. A dedicated Monitor navigation item
and independently operated application would let the archive and monitor
retain separate resource and release lifecycles. This is an architectural
recommendation. Current hosting and production capacity need their own checks.
[Current site](https://ianmalcolm84.com/)

Public admission still requires resolution of the recorded security gate,
publisher display permissions, an approved Google deployment key and budget,
public-load qualification, backup/restore ownership and a correction workflow.
The strongest initial public scope is a clearly dated research tool with
source attribution and coverage limits. Claims of comprehensive coverage,
verified incident positions or enterprise operational parity require evidence
beyond the current local tests.

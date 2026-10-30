# Earth imagery quality review

Research date: **October 29, 2026 UTC**; final independent image checks:
**October 30 UTC (October 29 CDT)**. This document distinguishes the published
release baseline, source-established defects, proposed improvements and subsequent
qualification. It does not assert that all proposals are implemented or deployed.
No shared database was changed for this review.

The goal is a detailed, responsive Earth workspace that makes the limits of its
imagery and observations easy to inspect. A visually sharp building is not evidence
that the building still exists, was recently photographed or was correctly located
by a report.

## Reproducible baseline

The audited baseline is public release `v0.2.0-rc.1`, commit
`f077bdde3a5d6da6791ceab35e1aae331b210b5d`, source ZIP SHA-256
`acf0a1dbf86780388e6270580515a6470eef97b1ab8d473e0ce511b6271a307d`.
Findings below were checked against immutable ZIP bytes while later candidate work
continued separately. Its lockfile pins Cesium **1.139.1**, engine **23.0.1** and
widgets **14.4.1**. Two useful source anchors are:

| Baseline file | SHA-256 |
| --- | --- |
| `frontend/src/components/CesiumView.tsx` | `3b21021a3be864e9ce5bdb652b99cfa59daa3296c6651dc0bd93c354fe674a5b` |
| `frontend/src/lib/earth.ts` | `ee6ae5b555c29a79b7c5abde7d8a9d08af31583119adb82701ae4818d8ac6cf1` |

The release has three different basemap paths. Its explicit synthetic showcase
uses the bundled **NASA Black Marble 2016 night composite**. Its ordinary keyless
live fallback already uses **Esri World Imagery**, which is daytime imagery.
Configured Google mode loads **Photorealistic 3D Tiles through Cesium**. It is not
the Google Earth desktop application or a date-selectable satellite scene archive.
Do not diagnose a showcase screenshot as proof that live Google was unavailable.

Google describes its satellite tiles as orthophotography from both satellite and
aerial cameras, and its photorealistic product as textured 3D geometry. Image
coverage and available detail vary. Google's Earth guidance also explains that
imagery is assembled from acquisitions at different times and is not real time;
the capture-date controls in Google Earth are not automatically metadata supplied
by this application's 3D Tiles integration.
[Map Tiles overview](https://developers.google.com/maps/documentation/tile/overview),
[Google imagery dates](https://support.google.com/earth/answer/6327779?hl=en).

## Source-clock semantics

The final review also found a data-meaning issue outside the basemap: normalized
event timestamps were sometimes captioned as publication times even when they
represented **FIRMS sensor acquisition** or an **RSS/Atom update-time fallback**.
The current UI uses **Source time** in the feed, Evidence details, Earth report
details and local-briefing citations, with an explanation that publication,
update or acquisition depends on the provider. RSS health now says **Newest
source time age**. Telegram's specific publication labels remain appropriate to
its message-publication clock and were retained.

This correction changes captions and explanations, not the timestamp values,
API schema or recorded source data. Some compatible API/property names still use
publication terminology; consumers must not infer a clock's basis from that
legacy name alone. Source acquisition, source publication/update, receipt and
database creation are distinct clocks. None establishes incident time without
additional evidence, and a new fetch does not make an old acquisition current.

## Ranked repairs established from source

| Priority | Finding and consequence | Narrow repair and verification |
| --- | --- | --- |
| P0 | On baseline Google root-load success, the globe is hidden immediately. Later `tileFailed` only changes a status string; it neither restores the raster globe nor removes the failed tileset. Partial/loading/failing imagery can therefore leave a blank or incomplete Earth. | Keep the reference globe until the requested view has usable 3D content; on failure restore a clearly named raster provider. Offer an explicit fresh-root retry. Test initial root failure, child-tile failure after success, empty/no-coverage views and cancellation during a switch. |
| P0 | The exact inherited unresolved-report pair `(-25,80)` is excluded by LiveFeed but admitted by `earthMarkers` and imagery-link construction. `EventRead` preserves the numeric pair: a synthetic serialization check returned it alongside an unresolved-location limitation. | Use one **report-only** position guard for plotting, fly-to and imagery links. The new `reportPosition.ts` helper rejects this exact pair and invalid numbers; four focused tests pass. Wiring and integrated verification belong to the candidate UI change. Generic aircraft/vessel/search coordinates remain unaffected; usable coordinates still do not imply verified geolocation. |
| P1 | `initialTilesLoaded` describes an earlier initial view, not every later camera destination. There is also no timed root renewal in the baseline effect. | Track loading/completion for the current requested view, bounded timeout and observed error. Renew the root on an appropriate bounded lifecycle. Google's root grants at least three hours of subsequent tile requests; this is not an indefinite URL. [Google 3D Tiles](https://developers.google.com/maps/documentation/tile/3d-tiles). |
| P1 | Every baseline track has a directional arrow. Missing/nonfinite heading sets rotation to zero, visually matching an actual reported north heading even though details say unknown. Every nearby marker can also receive a long label, causing overlap at city inspection scale. | Draw a neutral symbol for unknown orientation; preserve a genuine zero-degree heading. Prioritize selected/hovered labels and deterministic decluttering without deleting underlying observations. Test dense colocated reports/tracks, unknown versus zero heading, hit targets and selection recovery. |
| P1 | Baseline Google tiles omit `enableCollision`, while markers use `CLAMP_TO_GROUND`. The pinned engine's `Cesium3DTileset` constructor documents that its default `false` can prevent entity clamping to mesh geometry. `Scene.getHeight` only considers a tileset for this path when collision is enabled. | Enable supported mesh collision/clamping and qualify marker footprints at close urban and elevated-terrain views. A rendered clamp height is a display surface, not a measured aircraft/event altitude. Hiding the globe alone does not prove clamping is unsupported: this engine also registers 3D Tiles height callbacks. |
| P1 | Baseline city presets commonly remain 90–110 km away; a fixed screen-space error of 12 and CSS-pixel rendering can undersell the available detailed data. | Add intentional city inspection camera ranges and bounded render-quality controls. Measure the actual drawing buffer, memory, refinement and responsiveness. Higher render resolution or lower screen-space error improves rendering, not source acquisition date or native ground resolution. |
| P1 | Esri attribution is hardcoded to an older short provider list. The current official service metadata reports **Esri, Vantor, Earthstar Geographics, and the GIS User Community**. | Prefer service/provider attribution supported by the pinned Cesium adapter and keep it visible. The service advertises zoom levels through 23; this does not establish that every location has native detail at that level. Do not raise the existing level-19 cap merely because a higher level is listed. [Service metadata](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer?f=pjson). |

The baseline uses an ellipsoid terrain provider. A Google textured mesh can supply
3D buildings/landscape within its coverage; the raster fallback alone does not add
terrain elevation. Thus “Google off” must not imply equivalent 3D terrain. Reference
infrastructure remains explicitly unverified; track positions are surface
projections, and report camera range follows stated location precision. These
truth boundaries should survive visual improvements.

Cesium documents screen-space error as a refinement/performance tradeoff and
`allTilesLoaded` as completion for the current view. It also documents that the
recommended-resolution default ignores device pixel ratio; `resolutionScale`
changes the rendered buffer. Candidate native-DPR limits, SSE presets and memory
budgets require testing on the pinned runtime, rather than copying arbitrary
“maximum quality” settings.
[Tileset API](https://cesium.com/learn/cesiumjs/ref-doc/Cesium3DTileset.html),
[Viewer API](https://cesium.com/learn/cesiumjs/ref-doc/Viewer.html).

## Imagery choices by useful task

| Task | Recommended data path | Important limits |
| --- | --- | --- |
| Recognize a city, building context and terrain shape | Keep the existing Google Photorealistic 3D integration, repair its lifecycle and inspection controls first. | Coverage, geometry and texture age vary; no scene acquisition date was established for the displayed area in this review. Requires enabled billing/key and applicable usage limits. It cannot establish event timing. |
| Inspect a detailed flat daytime basemap | Optional official Google 2D satellite mode, or a properly attributed Esri imagery adapter with local metadata inspection. | Google 2D requires a session, returned expiry handling and viewport copyright/availability metadata; raw unofficial XYZ scraping is not the integration contract. Satellite mode includes aerial imagery. [2D Tiles](https://developers.google.com/maps/documentation/tile/2d-tiles-overview), [sessions](https://developers.google.com/maps/documentation/tile/session_tokens). |
| Establish what an accessible satellite scene actually observed on a date | Add a bounded, explicit area/date **Sentinel-2 L2A scene discovery and before/after workflow**, initially using the Copernicus STAC catalogue and linked product metadata. | Visible B02/B03/B04 bands are native 10 m, not building/car-scale imagery. Clouds, no-data and actual acquisition times must remain visible. Tile cloud percentages do not prove a small area is clear; resampling to finer pixels does not create new detail. [STAC](https://documentation.dataspace.copernicus.eu/APIs/STAC.html), [L2A bands and selection](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html). |
| Observe broad recent weather/smoke/environment context | Optional explicitly dated NASA GIBS product layers with sensor/product metadata and no-data overlays. | Product-dependent latency and spatial resolution. Many near-real-time visualizations arrive within 3.5 hours; this is not a guarantee for every product or a city-resolution/live incident camera. [GIBS product guidance](https://nasa-gibs.github.io/gibs-api-docs/available-visualizations/). |
| Work without an account, network imagery or provider key; illustrate the open-source app | Small bundled daytime **NASA Blue Marble May 2004** reference, with the larger August file and existing night texture retained separately. | Static 2,048×1,024 global composite; calculated equatorial pixel spacing approximately 20 km. It is orientation context derived from Earth observations, not current or city-scale evidence. [Asset provenance](ASSET_PROVENANCE.md). |

Esri provides acquisition date, resolution and source metadata at particular
locations/scales; a seamless mosaic may change source as one zooms or pans. A
Wayback **map publication date** is not the capture date of each constituent image.
A future inspector should show either the actual available local metadata or
“capture date unknown,” not today's fetch time as image age.
[Esri metadata](https://www.esri.com/arcgis-blog/products/imagery/imagery/learning-more-about-the-world-imagery-basemap),
[Wayback date distinction](https://www.esri.com/arcgis-blog/products/arcgis-living-atlas/imagery/wayback-with-world-imagery-metadata).

Free/open observation data does not mean unlimited free rendering infrastructure.
Copernicus discovery, downloads and processing have separate access/quotas. A
scene feature should cap area, time span, results, transfer and processing; show
coverage/age/cloud failures explicitly; and keep registration credentials on the
server. This review did not download or process a new Sentinel scene or qualify
commercial very-high-resolution imagery. A task that needs recently captured
sub-metre evidence requires a separately licensed, acquisition-identified product
and measured fitness for that task; the present basemaps do not supply that claim.
[Copernicus quotas](https://documentation.dataspace.copernicus.eu/Quotas.html).

## Concrete utility beyond a sharper globe

The next useful analytical feature is a compact **observation inspector**: provider,
source/product ID, actual acquisition time or unknown, fetch time, native resolution
or unknown, displayed resampling, scene footprint, clouds/no-data, processing level,
and report/track time basis. A report pin should expose its geolocation precision
and source evidence independently of the basemap. A precise scene beneath a vague
city report must not imply a precise incident site.

A subsequent dated-scene comparison should keep two explicit acquisition IDs,
consistent area/projection/scale and visible no-data/cloud masks. It should preserve
the source scene links and operator annotations. A visual difference may result
from season, shadows, viewpoint, registration or processing; automatic claims of
damage, actor attribution or confirmed incidents need separate validation. Google
Map Tiles are for visualization under their policies, not an input to image
analysis, machine interpretation or geodata extraction. Keep any future imagery
analysis on separately authorized scene products. [Google policies](https://developers.google.com/maps/documentation/tile/policies).

## Acceptance evidence for the candidate changes

The following are qualification criteria, not results already obtained by this
document:

1. One persistent Cesium canvas through Earth/Media/Brief, provider changes, resize
   and replay; no duplicate viewers, stranded listeners or growing tileset count.
2. Normal 3D, slow network, root failure, partial child failure, unavailable
   coverage, retry and expiry/renewal all leave a navigable correctly named Earth.
   A successful root HTTP response alone does not pass current-view rendering.
3. Record drawing-buffer dimensions, DPR cap, SSE setting, requested-view loading
   duration, tile errors and memory budget at fixed representative camera states.
   Measure interaction/frame latency on the actual target GPU and constrained
   browser profiles; no universal device-performance claim from one desktop run.
4. Inspect close views over at least covered urban, rural/mountain and unavailable
   3D areas. Show active provider and date uncertainty; never substitute a sharp
   raster while continuing to label it Google 3D. Explicitly test coarse NASA
   fallback at city scale and its static-reference warning.
5. Native provider credits remain visible, readable and operable at portrait,
   landscape and desktop sizes and after workspace panels open. Preserve source
   attribution without redistributing Google imagery in public screenshots,
   offline caches or generated briefing videos.
6. Central report-position tests cover null/invalid values, the exact inherited
   sentinel and valid neighbouring/zero/boundary coordinates. Track heading tests
   distinguish missing from true zero. Dense labels, selected markers, age/clock
   labels and geolocation precision remain readable without false precision.
7. Any future scene workflow records acquisition identity, resolution, licensing
   and processing receipts; absent metadata remains unknown. No screenshot,
   basemap sharpness or successful fetch is promoted into report verification.
8. Verify the surrounding Brief/Media/feed workspace with actual loading,
   unavailable, empty and no-link data states. Text scrollers must remain reachable
   without relying on source links eventually appearing. Focused reference cards
   must fit their scrollport and screen at narrow widths; a successful axe scan
   alone does not establish readable layout. Native attribution must be operable
   with keyboard Enter/Space, contained Tab navigation, Escape, restored focus and
   an unobscured pointer close control. Open that native popup during the audit;
   inspecting only the closed provider-credit area misses these interactions.

The two daytime JPEGs and focused report-position helper were added to the candidate
with separate byte/tests evidence during this review. The 2,048-wide May image is
the bounded runtime choice: the 5,400-wide August texture exceeds a 4,096-pixel
texture context and needs approximately 58.3 MB for one RGBA base level, versus
8.4 MB for the small image. These are size calculations, not total GPU-memory
measurements or a claim that physical mobile devices were tested. Both preserve
the original NASA-distributed bytes. Other repairs are owned by
the Earth/UI implementation work. Their final test/build/browser/image receipts
must be added to the next release verification; the published RC's earlier tests
do not automatically qualify these new bytes.

## Independent final candidate source review

At **00:18 UTC on October 30, 2026**, the reviewed frontend was running healthy as
image `sha256:03b08ff49e8c6d78348ec17f66cafebc7767963616732f167328706e927b4b65`.
The [sanitized source and runtime hash manifest](qualification/2026-10-29-earth-quality-source-manifest.json)
records 88 frontend product/configuration/test/asset files (excluding Markdown
documents) and 403 deployed static files. Every one of the **402** current local
build files matched the running container byte-for-byte. The additional deployed
file is the inherited nginx `50x.html` error page. The image ID and healthy state
were checked both before and after reading these hashes. This proves the scoped
byte comparison, not that every displayed scene or device was functionally tested.
This check followed a fresh successful host `npm run build` (TypeScript and Vite).
Earlier `248740…`, `16321b…` and `a61eb0…` receipts remain preserved privately as
prior phases. They do not qualify later bytes. During this final browser run,
product source remained unchanged; **one unimported E2E assertion** was corrected
from the RSS publication-age caption to the new source-time caption. Its file,
`frontend/e2e/workspace.pw.ts`, changed from
`eaacc503da44a9293021ee0c66f6ab1921e747c2eae071282b73d049f2660450`
to `74e8a1b9f5cb42762686cb142923a669558f0cb801a0515f5a421a9fddb0eed7`.
Both source snapshots are retained. The public manifest records the updated test;
its actual E2E execution is a separate check. This is **not** a claim that all 88
frontend files stayed unchanged during the accessibility run.

The final production audit completed the exact **61 planned axe states** across
1536×1000, 390×844, 844×390 and 320×844, with **zero violations at every impact**,
and **54 bounded keyboard scenarios** with zero observed failures. Four native
attribution text-hit/keyboard/pointer scenarios passed. Four additional synthetic
Brief checks at 320/390/768/1536 verified that the disclosure is initially visible
and keyboard End reaches the complete caption while retaining focus. The image
matched before and after the run. Contrast and ambiguous-name checks marked
incomplete by axe remain manual-review limits; they are not counted as passes.
These are scripted browser samples, not WCAG certification or a screen-reader,
speech-control or physical-device qualification. Broader checks and their scopes
are recorded in [verification](VERIFICATION.md).

The final source reread confirms the report-only position guard in the globe,
feed and imagery links; neutral unknown-heading glyphs; tighter track label
distance; the corrected responsive Earth-focus rule; explicit reference-provider
error/retry state; current Esri credit; the May 2004 small NASA texture; and Google
fallback when visible current-view content is unavailable. Mesh collision is
enabled. Native display rendering is capped at 2× and eight million pixels, with
SSE 8/4 presets and a 384 MiB tileset cache plus 256 MiB overflow allowance. Those
are renderer settings, not a total browser/GPU memory ceiling, scene-resolution
measurement or universal device-performance result.

All **five** manifest assets match their declared sizes and SHA-256 hashes. The
three previously published assets and their manifest entries remain unchanged;
both newly added day images match the original provider downloads and passed full
pixel decode and visual inspection as coarse global references. No Google tile
imagery, source article bodies, environment values or credentials are included in
this review's public hash manifest.

**Long-session limitation remains:** the candidate requests a fresh Google root on
an explicit retry, but does not implement automatic authorization renewal.
Google documents at least three hours of access from one root request; exact later
expiry and uninterrupted long-session continuity were not measured here. Do not
describe short successful rendering checks as proof of three-hour-plus operation.
Physical mobile hardware, local image acquisition dates and native ground
resolution also remain outside this independent static/byte review. The broader
scene-inspector and dated-satellite comparison ideas above remain proposed work.


## Expanded accessibility review and retained failures

A subsequent 57-state audit of the `16321b` build found two real serious rule
failures: visible button captions missing from accessible names (23 state
occurrences) and text-only Methods panels without keyboard-scroll focus (six
states). All 38 bounded keyboard scenarios passed, but that did not override the
axe failures. An independent 320-pixel native-credit test also proved that the
floating Feed button intercepted the actual Data attribution text and click.
The 844-pixel wrapped-link bounding-box center was only whitespace; testing its
individual text fragments correctly passed. Document overflow and a bounding-box
union are inadequate substitutes for actual visible-control and hit-target checks.

The repair preserves the button captions while including them in accessible names,
gives Methods content a named keyboard-focusable scroll region, and places the
portrait Feed control in its own bottom-navigation slot. The first 169-test/build
receipt verifies those source changes; the final 03b0 audit above separately
qualifies the measured deployed interactions. Earlier failing results, incomplete
contrast checks and the completed 16321b functional/11-minute observations remain
separate evidence, not an aggregate pass of subsequent bytes.


The native attribution popup also required an actual interaction check: a close
control could be covered by Earth navigation, and Escape did not close it. The
application now integrates native credit controls with its existing modal focus,
inert-background, Escape and restoration behavior; provider text and links are
preserved. Native popup state is exposed as a dialog only while open, because a
hidden dialog role would incorrectly interfere with Media/Brief keyboard handling.
The final audit opened this native popup at all four viewports and checked Enter,
Space, Tab containment, Escape, focus restoration and an unobscured pointer close.
Google's current [Map Tiles policies](https://developers.google.com/maps/documentation/tile/policies)
require visible provider attribution and distinguish visualization from image
analysis or offline extraction. The public repository previews therefore continue
to use the bundled NASA reference; actual Google captures remain local test
artifacts, rather than being included in the application source distribution.


The follow-up Brief geometry check measured a 317-pixel context column ending at
x636.56 on a 390-pixel viewport. Grid min-content sizing had pushed most of the
column offscreen; document-level overflow checks and axe alone did not establish
readability. The repaired grids use zero-minimum tracks, and narrow screens stack
full-width Brief sections in the parent desk's scroll area. Provider/source data
and existing navigation remain unchanged. Geometry and visible-text checks cover
the actual references after loading, as well as explicitly simulated empty,
unavailable and link-free states.

The `a61eb0…` production run also retained one serious Brief scroll-focus finding
among its 61 states. The follow-up identified a Source References viewport only
six pixels high; its 756-pixel contents became axe-focusable after links loaded,
so the post-load rule did not reproduce the initial failure. The repair gives the
right context column a named keyboard-scroll area and lets references retain their
natural height. Sixteen development samples preserved actual held/released source
responses and explicitly simulated empty, unavailable and no-link inputs. The
appropriate scroll owner moved by PageDown in each sample; on narrow screens that
owner is the parent desk. All five loaded reference-card checks at
320/390/768/844/1536 reached the last real link by Tab and kept the whole card inside
the viewport. The 844-pixel card's outer border/padding had a recorded 0.703-pixel
clip excess; the former 246-pixel horizontal overflow was absent. These geometry
checks supplement the final axe audit rather than being inferred from it.

Direction provenance is also explicit: the live AIS adapter can carry either true
heading or course over ground in its direction field. Aircraft adapters and legacy
vessel snapshots did not retain that basis. The frontend now labels these states
conservatively and no longer manufactures replay course from a historical heading
field. This corrects interpretation without moving positions, changing rotations
or rewriting the original observations.

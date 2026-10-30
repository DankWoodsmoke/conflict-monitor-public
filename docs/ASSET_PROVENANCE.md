# Bundled geographic asset provenance

Verified **October 28, 2026 CDT** (October 29 UTC). All three runtime filenames
are preserved. No image was generated, edited, resized or recompressed for this
replacement. Downloaded provider bytes are retained exactly; the original backup
and `recovery-manifest.json` remain unchanged.

The machine-readable record is
[`frontend/public/textures/asset-manifest.json`](../frontend/public/textures/asset-manifest.json).
It records exact URLs, previous and replacement SHA-256 hashes, sizes, feature
counts and image dimensions. These hashes establish byte identity, not geographic
accuracy or a provider's endorsement of this application.

## Countries and coastlines

Both GeoJSON assets come from **Natural Earth v5.1.2**, pinned to release commit
`f1890d9f152c896d250a77557a5751a93d494776`. The repository's pinned
[`VERSION`](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/f1890d9f152c896d250a77557a5751a93d494776/VERSION)
reads `5.1.2`. The current development branch identifies itself as a prerelease;
the bundled files deliberately use the named released snapshot.

| Local asset | Exact provider file | Bytes | Validation |
| --- | --- | --- | --- |
| `countries.json` | [`ne_110m_admin_0_boundary_lines_land.geojson`](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/f1890d9f152c896d250a77557a5751a93d494776/geojson/ne_110m_admin_0_boundary_lines_land.geojson) | 340,010 | 331 features; 3,108 vertices; LineString/MultiLineString |
| `coastlines.json` | [`ne_110m_coastline.geojson`](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/f1890d9f152c896d250a77557a5751a93d494776/geojson/ne_110m_coastline.geojson) | 139,907 | 134 features; 5,128 vertices; LineString |

Both parsed as nonempty GeoJSON FeatureCollections. Every line has at least two
vertices; every vertex has two finite numeric ordinates, longitude within
`[-180,180]` and latitude within `[-90,90]`. Their line geometry matches the
existing Leaflet/Three.js loading contract. The inherited files matched these
official files exactly after removing terminal whitespace. The replacements now
use the original provider bytes, including the provider's original ending.

Natural Earth's [pinned license](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/f1890d9f152c896d250a77557a5751a93d494776/LICENSE.md)
and [official terms](https://www.naturalearthdata.com/about/terms-of-use/)
place its raster/vector datasets in the public domain and permit redistribution
and modification. Attribution is welcome rather than required. Suggested credit:
**Made with Natural Earth.**

These are generalized **1:110 million reference boundaries and coastlines**.
They do not establish a legal border, current territorial control, high-resolution
coastal position or incident location. In particular, `countries.json` is the
land-boundary line dataset, not a new polygon or a claimed live control map.

## Earth night reference texture

`earth-night.jpg` is the original NASA **Black Marble 2016 global color composite**,
downloaded from the 3,600×1,800 JPEG link in NASA's
[Earth at Night/Black Marble: Flat Maps catalog](https://science.nasa.gov/earth/earth-observatory/earth-at-night/maps/).

Exact asset URL:
[BlackMarble_2016_01deg.jpg](https://assets.science.nasa.gov/content/dam/science/esd/eo/images/imagerecords/144000/144898/BlackMarble_2016_01deg.jpg).

- Provider bytes: **779,638**; Content-Type `image/jpeg`.
- SHA-256: `d87de751a264e4f8ff69c68de5dab9606daee87a6f15ae743c93200743bd7ec1`.
- Full decoder verification and pixel decode succeeded: **JPEG, RGB,
  3,600×1,800**, with a 2:1 global map aspect ratio. JPEG start/end markers also
  matched. The file was copied without a re-encode or pixel transformation.
- Recommended credit: **NASA Earth Observatory image by Joshua Stevens, using
  Suomi NPP VIIRS data from Miguel Román, NASA GSFC.** NASA's
  [associated article](https://science.nasa.gov/earth/earth-observatory/night-light-maps-open-up-new-applications-90008/)
  identifies the observations as 2016 and describes the cloud-free compositing.

Reuse follows NASA's [Images and Media Usage Guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/).
Those guidelines describe NASA government content as generally not subject to
United States copyright and allow factual informational use with acknowledgment,
without implying endorsement. They separately protect NASA identifiers and warn
that identified third-party materials retain their own rights. This selected
global map is credited to NASA Earth Observatory/GSFC and contains no identifiable
person or NASA logo. This is a specific provenance/usage basis; it is **not** a
claim that every asset on a NASA website is public domain or licensed under this
repository's MIT software license.

The map is a **static 2016 reference texture**. It must never be described as
current nighttime observation, present electricity availability, live imagery or
evidence of any incident. Enabling Google photorealistic tiles uses the separate
Google provider and its visible attribution; this bundled reference texture does
not replace or relicense Google data.

## Original asset preservation record

The candidate's earlier asset hashes, preserved in the manifest, are:

| Asset | Prior SHA-256 |
| --- | --- |
| `countries.json` | `d8cec72f3b008717f4f42e43809bdd976368f17151216736286917d3f45a5568` |
| `coastlines.json` | `676178907dd5755ec9fe818c983398587b5f3f8748661433c426ddbc0538b189` |
| `earth-night.jpg` | `373e5a08c9f378a2ce6320214a613148e4b1e3946b3f39a516c9093b76cb7124` |

Only the separate release candidate's assets changed. Their original versions
remain in the protected source backup. Final frontend build/browser verification
is performed separately after these replacement bytes are included.

## Current preview and Google provider boundaries

Earlier four-view screenshots are preserved locally with hashes outside the
public export. They are not used to illustrate the current one-Earth workspace.
Public preview images use the explicit synthetic/keyless exercise and bundled
reference assets; their captions distinguish the2016 reference from Google tiles.
Private Google-rendering execution receipts remain separate from redistributable
application code and imagery assets.

Rechecked October29,2026: [Map Tiles API policies](https://developers.google.com/maps/documentation/tile/policies)
require visible provider/data attribution, restrict caching/extraction/offline
uses, and specify separate conditions for promotional video. The application
does not extract Google imagery into AI inputs or narrated source-card MP4s.
Those MP4s contain editorial text cards, not Google tiles. No offline Google
imagery archive or blanket image-redistribution license is included.

## Added daytime global reference (October 29, 2026)

`earth-day.jpg` adds an original NASA **Blue Marble: Next Generation August
2004 monthly composite with shaded topography and bathymetry**. The three assets
documented above, including `earth-night.jpg`, remain unchanged. This addition
does not replace any protected backup or rewrite the night-texture receipts.

The [NASA download catalog](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-topography-bathymetry/)
links the exact [August global JPEG](https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-topography-bathymetry/august/world.topo.bathy.200408.3x5400x2700.jpg).
The download is **2,308,163 bytes**, SHA-256
`f76d7b94445e8975a755c849ddaa93ed07b7e01118fb0b7e6bc5546a68c18d5c`.
Full decoder verification and pixel decode passed: **JPEG, RGB, 5,400×2,700**.
The provider's bytes were copied directly; no image generation, resizing,
recompression, recoloring or sharpening was applied.

NASA lists this particular global download as **8 km/pixel**. The underlying
collection also offers larger products; its 500 m dataset description does not
describe the resolution of this bundled small JPEG. Geographic pixel spacing
also varies with latitude. The [collection description](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/)
identifies monthly 2004 land-surface composites and credits Reto Stöckli at NASA
Earth Observatory/GSFC. The date refers to the land-surface composite; the
shaded relief and bathymetry are ancillary reference layers.

Required displayed acknowledgment for the selected product is **NASA Earth
Observatory**. Recommended descriptive credit: **NASA Earth Observatory · Blue
Marble August 2004 composite · static ~8 km/pixel reference**. Reuse relies on
the [NASA media usage guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)
described above: factual informational use, acknowledgment, no implied NASA
endorsement and no software-license claim over third-party/government imagery.

This is a daylight-colored **global orientation and offline/showcase reference**.
It is not recent satellite coverage, a city-resolution basemap, live imagery,
evidence of damage, present control or a substitute for the separately configured
Google provider. Close inspection should explicitly identify this reference as
coarse and dated. Provider switching and browser/render qualification are separate
from this byte/provenance check; adding the file does not establish deployment.

### Bounded runtime reference: May 2004, 2,048×1,024

`earth-day-2048.jpg` is a separate **original NASA WorldWind-distributed** Blue
Marble image. Its [official layer source](https://worldwind.arc.nasa.gov/autodocs/WebWorldWind/layer_BMNGOneImageLayer.js.html)
identifies `BMNG_world.topo.bathy.200405.3.2048x1024.jpg` as its single-image global
reference. The [pinned provider file](https://raw.githubusercontent.com/NASAWorldWind/WebWorldWind/5ffe2dfc54ab4d744fc9e587af9639c9910db228/images/BMNG_world.topo.bathy.200405.3.2048x1024.jpg)
is **312,383 bytes**, SHA-256
`7405c39a220bc37519474eba54625a0d1a02b6ad954895147c103a1bc8dd61fb`.
Full decode passed: **JPEG, RGB, 2,048×1,024**. This is **May 2004**, a different
month from the retained August image; the two assets must not share one month label.
Original NASA repository bytes are retained without local image editing.

The NASA WorldWind [repository notice](https://github.com/NASAWorldWind/WebWorldWind/blob/5ffe2dfc54ab4d744fc9e587af9639c9910db228/README.md#license)
declares the SDK's United States Government/NASA copyright notice and Apache-2.0
software terms. Its pinned third-party notices concern the accompanying software
libraries; no WorldWind software or those libraries were copied into this project.
This selected NASA Earth-observation image uses the NASA informational-imagery
reuse basis above, with **NASA Earth Observatory** acknowledgment and no implied
NASA endorsement. It is not relicensed as MIT application code.

The small file is intended as the bounded runtime reference on all devices. The
retained 5,400-pixel August file is an additional provenance asset, not the runtime
choice. A 5,400-wide texture can exceed a device's maximum texture size. The small
image requires about **8.4 MB** for one decoded RGBA base level, compared with
58.3 MB for the large image; these calculations exclude mipmaps and other renderer
allocations. They are not measured total GPU memory or universal device support.
Its roughly **20 km equatorial pixel spacing** is calculated from global map width,
not a newly measured native sensor resolution. Use **NASA Earth Observatory · Blue
Marble May 2004 composite · static global reference** as descriptive credit. The
same coarse/dated/no-incident-evidence limits continue to apply.

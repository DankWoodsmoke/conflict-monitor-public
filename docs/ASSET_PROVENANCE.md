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

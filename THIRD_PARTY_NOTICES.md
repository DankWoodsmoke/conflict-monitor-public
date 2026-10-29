# Third-party notices

This candidate preserves the original Conflict Monitor MIT license and copyright. The original repository is attributed in `LICENSE`; the historical backup and recovered-file hashes are recorded in `docs/recovery-manifest.json`.

No World Monitor, God's Eye View, OpenCTI or Bellingcat implementation was copied into this candidate. Those projects informed research and design decisions documented with primary sources in `docs/CURRENT_RESEARCH.md`.

Runtime packages retain their own licenses, including Cesium (Apache-2.0), Leaflet (BSD-2-Clause), React (MIT), Three.js (MIT), satellite.js (MIT), DOMPurify (Apache-2.0 or MPL-2.0), FastAPI (MIT), SQLAlchemy (MIT), Telethon (MIT), and PostGIS (GPL). This list is a summary; the resolved package distributions and lockfiles are authoritative for package versions and individual notices. Docker images and installed dependencies are not vendored in the source ZIP.

The bundled boundary/coastline vectors are exact Natural Earth v5.1.2 source bytes (public-domain vector terms). The night texture is the original NASA 2016 Black Marble image under the documented NASA media-use permission and required credit. These assets are not relicensed as MIT or presented as current imagery. See `docs/ASSET_PROVENANCE.md` and `frontend/public/textures/asset-manifest.json` for exact URLs, hashes, usage terms and limitations.

Google Maps/Photorealistic 3D Tiles, Esri imagery, OpenStreetMap-derived maps, adsb.lol, AISStream, CelesTrak, NASA FIRMS, Yahoo Finance, external media and individual publishers impose their own terms. Preserve provider attribution in the rendered view. A public API or free key does not authorize arbitrary caching or redistribution. Google attribution and tile copyrights remain visible through Cesium's credit display.

ACLED data and World Monitor hosted outputs are excluded from the release. Optional adapters or dataset exports require a separate rights review. The synthetic exercise is authored test data; its labels explicitly distinguish it from observed intelligence.

The optional local speech worker, `backend/app/workers/piper_speech.py`, is explicitly GPL-3.0-or-later. Its corresponding source is included, and the full license is preserved in `docs/licenses/PIPER_GPL_3.txt`. The service invokes it through a separate process and files. The [Piper engine](https://github.com/OHF-Voice/piper1-gpl) and installed FFmpeg/libx264 build retain their own licensing and distribution obligations; they are not relicensed as MIT. The selected LJSpeech voice uses the pinned voice-repository/model-card terms and is downloaded separately. Ollama and the evaluated Qwen3.5 4B model retain their respective licenses. Exact source links, voice hashes, model digests and the limited evaluation are documented in [local AI/video](docs/LOCAL_AI_VIDEO.md).

CesiumJS 1.139.1 / engine 23.0.1 has a reproducible, hash-bound compatibility patch guarding two `OffscreenCanvas` checks when that browser global is absent. The original Apache-2.0 notices are preserved. `frontend/tools/patch-cesium.mjs` records original/patched hashes and the upstream source and rejects unreviewed versions or bytes. Historical Leaflet/Three.js/Resium/satellite components remain reference source outside the active compilation graph; their former runtime dependencies are removed from the Earth application.

# Historical frontend reference

These files are preserved byte-for-byte from the recovered release candidate immediately before the Earth-only consolidation. `manifest.json` records their original paths, SHA-256 hashes and former optional dependencies. They are outside `tsconfig.json` and the application import graph.

The original `src/` folder layout is retained here for context. Shared imports still refer to their original locations in the active `frontend/src/` tree; these files are an archive, not a separately runnable application. Restore the original structure and review current evidence, rendering, dependency and provider contracts before reusing any code.

In particular, the old Leaflet display, Three globe, guessed altitudes, orbital height scaling, depth overrides, reference ownership labels and historical verification badges do not describe qualified current behavior. The original release test is retained to preserve its optional orbital propagation checks; the active test suite covers the Earth workspace and no longer installs an unused orbital rendering package.

All original project license and third-party notices remain applicable. No private environment, credentials or collected dataset is included here.

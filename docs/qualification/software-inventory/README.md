# Software inventory scope

These are observed package/lock metadata, not legal compatibility, redistribution,
security or complete supply-chain clearance. Provider data, map imagery, voice
weights and operating-system packages require their own inventories and terms.

`frontend-full-lock-sbom.cdx.json` is the unfiltered npm 11.12.1 CycloneDX 1.5
output from the exact package lock with SHA256
`43c8ffc1161d38c6b87b7afecda26f350012675ec35529c2677360379e9bc821`.
It contains 174 deduplicated components, including development/build dependencies
and optional platform packages. It is not a claim that all 174 execute in a
browser or are copied into the runtime image.

`frontend-production-lock-graph.json` independently traverses root production,
optional and peer dependencies, excluding development edges. Its 33 reachable
package locations agree with a separate check of Arborist's global `dev=false`
classification. All four direct production dependencies are included. This
describes potential package dependency reachability, not measured JavaScript
tree shaking or exact bundled file inclusion. Cesium's static runtime, workers
and assets ship separately from the main application JavaScript.

The ordinary `npm sbom --omit=dev` output was found incomplete in both lock-only
and installed-tree mode: it emitted React, ReactDOM and scheduler but omitted
direct production dependencies **Cesium and DOMPurify**. Those raw outputs were
preserved privately. They are not presented as a complete production SBOM.
The full official unfiltered output and independent closure are provided
separately instead; no dependency or npm implementation was changed.

`backend-python-license-inventory.json` enumerates the 71 Python distributions
actually installed in production image
`sha256:a57a1426956f1b0ba5cab3452c810b85779928ece8176b93b4df678902b94990`,
including installer tooling. The initial 69-package license-file count covered
`.dist-info` metadata directories. A broader check also finds ONNX Runtime's
`LICENSE` and `ThirdPartyNotices.txt` within its package, bringing that count to
70/71 distributions with registered license/notice files. Flatbuffers 25.12.19
has Apache 2.0 license metadata but no matching registered license file in this
check. Missing files, ambiguous fields and metadata are not interpreted as a
legal conclusion. File hashes record the actual observed bytes; long metadata
license text is represented by its byte length/hash rather than copied.

The [current-image binding](backend-current-image-binding.json) rechecked the
deployed backend `sha256:4202bfc7add922228c024623b1879ccec7eaf617c718d583b69568b440f90788`
on October 29 at 08:29:53 UTC. All 71 distribution names, versions and enumerated
license metadata agree with the original inventory. All 184 previously
inventoried license/notice file records, totaling 1,086,277 bytes, retain their
exact hashes, including the registered package files outside `.dist-info`.
No package metadata or inventoried license file changed. This byte comparison
preserves the same scope and unresolved licensing questions.

`inventory-scope.json` binds these counts and qualifications. The current
[clean reconstruction](../clean-source-reconstruction-cb2.json) used 296 immutable,
scanned public source files with a fresh npm cache/install. All 149 frontend
unit tests, four keyless workspace browser tests, compatibility and production
build checks passed. All 400 application files exactly match deployed image
`sha256:cb2cc67e72d8c1fc67049c6b91d621ee2e31de0be3e3c4ccda4890a791e5422a`.
Four native synthetic/NASA-reference previews received independent and
coordinating-agent visual review. These are separate from live Google/provider
qualification and human usability acceptance.

The earlier `02ee9066...` automated pass was followed by visual review that found
portrait attribution/legend overlap and Media text clipping. Those previews and
the earlier obsolete-selector failure were retained outside the final public
gallery; the [historical receipt](../clean-source-reconstruction-02ee.json)
records the limits. The final source release package may include later
documentation and screenshot additions; its manifest/hash is separate from the
immutable qualification snapshot. Inventory generation is read-only and is not
legal, security or complete supply-chain clearance.

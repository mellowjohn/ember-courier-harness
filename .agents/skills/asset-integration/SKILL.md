---
name: asset-integration
description: Package a Blender prop GLB into a reproducible offline Three.js scene and prepare an exact Ember asset acceptance proposal without applying it.
---

Use [the pipeline guide](../../../docs/ASSET_PIPELINE.md) and the canonical
`ember_harness.asset_workshop` implementation. Reuse `tools/asset_lab.py`; do not
create a parallel asset server, CDN dependency or approval mechanism.

Generated/registered assets are also available through `asset_library`: source
locations, immutable GLB snapshots and conversation references. `prepare` registers
the source automatically. The host discovers compatible exports in its production
folders and workspace `assets/`, `art/` and `models/`. Prefer those verified
references when the user discusses an existing asset; do not ask them to select
the same files again. Unknown locations still need a source, not an invented path.

In chat, `asset:{ref,intent:"discuss"}` records the referent without changing the
project; `intent:"use"` prepares an exact normal proposal. The host retains the
mesh/runtime payloads and includes source provenance in the review. Source metadata
and conversation never grant approval. Distinguish a changed/missing original file
from the saved snapshot, and do not silently substitute a newer export.
For an accepted asset re-exported to its recorded directory, use **Known assets →
Review updated export**. This local action validates fresh bytes and keeps the
approved scene/runtime, brief and gameplay plan. It prepares the normal exact
review; native-only edits need a new GLB export and cannot supply acceptance.

Inspect GLB bytes with `asset_pipeline.inspect_glb` against the source specification.
`asset.js` is a canonical package containing those bytes, the specification and
measurements; the host validates it again when proposing, previewing and exporting.
The original chest packages remain compatible. New props use the declared
`hinged-prop-v1` specification: slug, display name, dimensions, required nodes,
art direction and interaction metadata. Name the exported GLB after its validated
slug. The scene and ZIP derive their identity from that specification; do not add
asset-name branches to the runtime. Unsupported glTF features still need profiles.

Bundle the pinned Three.js runtime and GLTFLoader into `engine.js` using the optional
ignored npm tools. Retain the upstream licence. Both runtime and asset package are
ordinary reviewed files: changing either creates an exact build diff. Preserve
them in code-only revisions unless the requested change requires replacing them.

Prepare a fresh workshop session, or explicitly name an existing workshop session
for revision. The command creates a proposal, brief and gameplay plan; it grants
no approvals. A changed asset requires the UI's explicit **Accept asset & play**
decision, which creates an individual `asset.accept` receipt even under approve_all.

Try the unapplied proposal, verify the collision mesh is hidden, the correct pivot
moves, and the scene uses the supplied socket and proxy. Test exported ZIP files
offline as well: they contain the exact unpacked GLB, specification and report.

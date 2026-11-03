# Blender to a playable Ember asset

For image-generated PNG sprites, backgrounds, tilesets and scripted effects, use
[the 2D asset workflow](ASSETS_2D.md). It shares the asset library and approval
machinery described here, with an offline canvas workshop instead of Three.js.

The implemented workflow produces original props in Blender, exports GLB, packages
those exact bytes into an offline Three.js scene, and uses Ember's existing proposal,
acceptance, gameplay, version and ZIP flows. The original chest and courier waygate
demonstrate different hinges and collision behavior in the same runtime.
Workflow skills live in `.agents/skills/asset-pipeline`, `blender-prop-production`,
`asset-integration` and `asset-playtest`.

**Create chest/gate directions** now connects a selected project task to three
rendered original studies, an explicit direction pick, bounded Blender production,
independent checks and repeatable source refinement. See [production in the app](ASSET_PRODUCTION.md).

## Talk about an existing asset

Ember keeps source locations and verified GLB snapshots for known assets. You can
ask **“Where is the courier gate source?”**, then follow up with **“Put it into
the scene.”** The conversation retains the selected asset reference across
restarts and after older prose leaves the model's context. The **Known assets**
panel shows what is available, which asset is being discussed or proposed, and
the recorded `.blend`, GLB and specification locations.

The host discovers compatible `asset-spec.json`/`ID.glb` pairs in
`.harness/asset-source/`, `.harness/asset-lab-source/`, workspace `assets/`, `art/`
and `models/`, and successful asset-check exports. The preparation command below
also registers its explicitly supplied source. Discovery stays in these roots;
it does not search the whole computer or pretend an unknown asset has been found.

Selecting an asset in conversation prepares a normal playable proposal containing
its actual snapshot bytes. The source locations and hashes are included in the
review. Discussion alone changes no project files and supplies no acceptance.
Matching pending asset requests reuse the existing exact review.
The original source may change or disappear; its status is shown separately from
the immutable exported snapshot. A new export becomes a new record. The host does
not silently replace the version already selected for a conversation.

For an empty session, using a known asset can create the default workshop. For an
existing asset scene, it can swap the recorded asset while retaining scene code.
Integrating an asset into another game needs a concrete scene implementation in
the proposal. Mesh payloads and vendor runtime code stay with the host, so Muse
can edit ordinary scene files without reconstructing those large files. Geometry
changes still use the Blender production and re-export workflow.

The host snapshots known asset metadata with each chat request and accepts only
references supplied in that snapshot. Metadata and source paths are data, never
execution or approval authority. Entries live under ignored `.harness/asset-library/`.

## Review a revised export in the same session

After accepting an asset, open **Known assets** and find its **Approved scene**
card. Edit the Blender source, then re-export the matching `ID.glb` and
`asset-spec.json` to that card's recorded source directory. Choose **Review updated
export**. Ember re-reads and validates those files and prepares an exact proposal
that changes only `asset.js`, retaining your approved scene code, runtime, project
brief and saved gameplay plan. This action runs locally without calling Muse or
launching Blender.

Choose **Try proposed changes** and **Check proposed changes** to compare the
current and revised asset with the same desktop/touch scenarios. **Accept asset &
play** records a separate acceptance for that exact revised package. Until then,
the current game and prior versions retain their approved bytes. The proposal,
source provenance and conversation focus survive a restart. Repeated requests
reuse the pending update; finish that review before checking another export.

An unchanged GLB/specification produces no proposal, even if the `.blend` changed;
export the native changes first. Invalid or missing exports, a changed asset ID,
an unfinished build, a different pending review or externally modified project
files stop the update. A moved source needs explicit registration using the
preparation command below. Ember follows the source bound to the accepted proposal
when identical asset copies exist elsewhere. Native source is provenance only:
valid GLB measurements do not prove that the `.blend` matches the export.

## Produce and review a chest

Use Python 3.12+, a local Blender executable and Node. Three.js and esbuild are
optional development tools, not new Python dependencies. Install the pinned tools
under ignored local storage:

```powershell
npm.cmd install --prefix .harness/asset-tools --no-audit --no-fund --save-exact three@0.187.0 esbuild@0.28.2
py -3.12 tools/asset_lab.py --bundle-runtime --engine .harness/asset-tools/engine.js
& 'PATH_TO_BLENDER.exe' --background --python tools/blender_delivery_chest.py -- --output .harness/asset-source/chest-001
py -3.12 tools/asset_lab.py --source .harness/asset-source/chest-001 --engine .harness/asset-tools/engine.js
py -3.12 -m ember_harness.local_ui
```

Choose fresh output paths; existing sources and runtime bundles are preserved.
The Blender command runs in its own background process, saves the editable
`delivery-chest.blend`, and exports `delivery-chest.glb` and `asset-spec.json`.
It does not touch an artist's open scene. The runtime bundle retains Three.js's
MIT licence. Rebuilding a runtime can use a new output name.

The preparation command prints a saved session ID. Open **Delivery chest · Blender
asset workshop** in Ember, choose **Try proposed changes**, inspect the asset
measurements, and run **Check proposed changes**. Preparation creates a proposal,
project brief and four gameplay scenarios. It applies no project files and records
no owner acceptance. Review the exact asset and choose **Accept asset & play**
when satisfied. That click approves the reviewed contracts and a separate exact
`asset.accept` action; approve_all cannot supply that individual acceptance.

For a refinement, export to a new directory and use the same runtime plus
`--session SESSION_ID` with `tools/asset_lab.py`. Finish the existing proposal
first. Source-only changes preserve the previous asset acceptance; changed asset
packages and restoring a different package require a new individual receipt.
The final playable proposal is reviewable before that decision, as described in
[the build workflow](CHAT_BUILDS.md).

## Specification and supported profile

### Reusable hinged props

Use the same preparation command for the waygate:

```powershell
& 'PATH_TO_BLENDER.exe' --background --python tools/blender_courier_gate.py -- --output .harness/asset-source/gate-001
py -3.12 tools/asset_lab.py --source .harness/asset-source/gate-001 --engine .harness/asset-tools/engine.js
```

The command-line generators are compatibility entry points for the canonical
packaged scripts and shared helpers in `ember_harness/blender/`.
Their scene reset refuses to run in an artist's foreground Blender process.
The gate targets 1.5 × 2.2 × 0.31 metres with the same 0.02 m tolerance. Decorative
post bands account for its small measured width/depth differences. Its Y-axis
hinge moves the leaf and its collision proxy. Separate fixed proxies keep the
frame posts solid. Closing is refused while the actor occupies the closed leaf's
footprint. This is a coarse box/capsule check, not continuous rigid-body physics.

Other hinged props can supply `asset-spec.json` and a GLB named `ID.glb`:

```json
{
  "profile": "hinged-prop-v1",
  "id": "courier-waygate",
  "display_name": "Courier waygate",
  "dimensions_m": [1.5, 2.2, 0.31],
  "dimension_tolerance_m": 0.02,
  "required_nodes": ["AssetRoot", "GateHinge", "COLLISION_Gate", "Socket_Latch", "COLLISION_PostLeft", "COLLISION_PostRight"],
  "art_direction": "Original courier waygate in teal oak and aged brass.",
  "interaction": {
    "pivot_node": "GateHinge",
    "axis": "y",
    "open_angle_rad": 1.8,
    "collision_node": "COLLISION_Gate",
    "socket_node": "Socket_Latch",
    "noun": "gate",
    "success_text": "Passage open",
    "passage": true,
    "static_collision_nodes": ["COLLISION_PostLeft", "COLLISION_PostRight"]
  }
}
```

The slug must be lowercase with optional hyphens, at most 64 characters; it drives
export identity without supplying paths. Hinge axes are local glTF X/Y/Z and angles
are signed radians, 0.25–3 in magnitude. All nodes belong under `AssetRoot`, the
hinge must move visible geometry, and a passage's primary proxy must descend from
that hinge. Keep its interaction socket and optional static proxy meshes outside
the moving subtree. List every declared helper in `required_nodes`; up to eight
additional fixed collision proxies are supported. The scene derives its labels,
camera framing and interaction from the specification, and refreshes proxy bounds
as the hinge moves. No asset-name branch is needed in the scene.

The original chest specification and canonical packages stay compatible. Changed
profiles still use individual asset acceptance, and ZIPs name the unpacked GLB
after the validated asset slug. No rigging, image textures or exported animation
clips have been added by this profile.

### Original chest and common geometry limits

The brief is an original stylized courier chest: teal wood, aged brass, amber seal,
readable at three metres. The closed model targets **1.21 × 0.81 × 0.821 metres**,
in glTF X/Y/Z order (width/height/depth), with a 0.02 m tolerance, a floor origin,
a rear lid hinge, a delivery socket and separate proxy. Blender uses Z up; the
GLB and scene use Y up. The projecting latch explains the front/back asymmetry.
Geometry includes a functional interior and parcel.

`asset_pipeline.inspect_glb` measures actual exported positions and node world
transforms. The `ember-static-prop-v1` profile permits one embedded BIN buffer,
static triangles with normals and material factors, up to 12,000 triangles, eight
materials, 160 nodes and 360,000 GLB bytes. It checks chunk/accessor bounds, finite
geometry, required names, reachable acyclic hierarchy, origin and dimensions. It
rejects external URIs, extensions, image textures, compression, skins, morph targets
and animation clips. These are bounded prop profiles, not a full glTF conformance
validator or general-purpose engine importer. Other asset families need profiles and tests.

`AssetRoot`, `LidPivot`, `COLLISION_Chest` and `Socket_Delivery` survive export.
The scene hides the collision mesh, derives its box from imported geometry, uses
the socket for reach, and rotates the imported hinge. Lid motion is procedural in
the scene rather than an exported clip.

`asset.js` contains a canonical GLB package, specification and measured report.
`engine.js` contains bundled Three.js and GLTFLoader. Both participate in exact
proposal diffs, snapshots, gate decisions, hashes, saved versions and restore.
GLTFLoader parses the supplied ArrayBuffer; no CDN or asset file server is needed.
Existing preview network isolation stays in place. Runtime and asset source are
bounded at 1 MiB and 512 KiB; ordinary files retain 64 KiB/file and 256 KiB total
limits. Projects still have at most eight files.

Game ZIPs include reviewed scene files plus the exact unpacked `ID.glb`,
`asset-spec.json` and `asset-report.json`. Extract and open `index.html` offline.
The editable .blend stays in the production output directory, outside the game ZIP.
Generated sources, npm tools, reports and captures stay under ignored `.harness/`.

## Prove a refinement

```powershell
py -3.12 tools/asset_check.py --blender 'PATH_TO_BLENDER.exe' --engine .harness/asset-tools/engine.js
py -3.12 tools/asset_check.py --asset gate --blender 'PATH_TO_BLENDER.exe' --engine .harness/asset-tools/engine.js
py -3.12 tools/asset_chat_check.py --source .harness/asset-source/gate-001 --engine .harness/asset-tools/engine.js
```

The rehearsal creates two real Blender exports in an isolated fixture. The first
has an oversized collider: desktop and touch opening checks fail because the actor
cannot reach the socket. It changes the collider in Blender, exports again,
compares current and proposed versions with the same saved plan, and verifies the
refinement before synthetic fixture acceptance. It checks current gameplay,
restart history, individual acceptance receipts and exact GLB bytes in the ZIP.

A second Chromium pass observes the actual scene passed to Three.js. It holds real
movement input against imported collision bounds, checks the hidden proxy, verifies
hinge movement and return, and captures closed/open desktop and mobile views. It
also checks layout overflow and absence of HTTP requests. Reports, Blender logs,
screenshots and the game ZIP stay in the printed `.harness/asset-checks/.../`
directory. Fixture decisions never represent human acceptance of a real asset.

The gate rehearsal first exports a deliberately fixed passage collider and verifies
that the host rejects it. The corrected model then passes the unapplied proposal
and saved desktop/touch scenarios. The scene pass additionally checks actual
Y-axis rotation, fixed-post collisions, walking through the open doorway, and
refusing to close on the actor. Both rehearsals use the same packaging, scene,
owner-review, ZIP and evidence implementations.

The asset-chat rehearsal uses synthetic model replies and fixture owner decisions
with real Chromium. It asks for the native source location, reloads the page,
uses a follow-up reference to prepare a playable proposal, checks gameplay before
acceptance, and edits scene code while retaining the exact asset/runtime. It also
verifies ZIP identity and conversation focus after restart. This verifies host
wiring and browser behavior; natural-language interpretation still depends on Muse.
Add `--updated-source PATH_TO_REVISED_EXPORT` with a different valid GLB of the
same asset to rehearse a rejected invalid export, the **Review updated export**
button, preserved scene code, desktop/touch comparison, restart during review,
separate updated-asset acceptance and exact revised bytes in the ZIP. Only copies
under the rehearsal fixture are changed; both supplied source directories remain
intact.

The offline suite covers malformed GLBs, tampering, exact acceptance, interrupted
acceptance recovery, code-only revisions, restore and export without Blender:

```powershell
py -3.12 tools/offline_tests.py --pattern test_asset_pipeline.py
py -3.12 tools/release_check.py
```

Passing DOM assertions and geometry measurements does not establish fun, visual
craftsmanship or human acceptance. Inspect the open/closed views and play the
proposal. Displayed frame time is a sample on the current host, not a performance
guarantee. AI polish can iterate on scene code; Blender source changes use this
explicit production and re-export workflow.

Implementation references: [Three.js GLTFLoader parsing](https://threejs.org/docs/pages/GLTFLoader)
and [Blender glTF export operators](https://docs.blender.org/api/5.1/bpy.ops.export_scene.html).

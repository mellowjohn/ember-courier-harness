# 2D assets: tiles, generated artwork and scripted VFX

Ember accepts PNG sprites, backgrounds, tilesets and VFX atlases through the same
known-asset, exact proposal, asset acceptance, saved-version and ZIP workflow as
its GLB props. The 2D workshop plays the actual PNG at gameplay and inspection
scale with named clips, replay, pause, frame scrubbing, keyboard/touch movement,
action playback and a transparency grid. No 3D runtime
or new dependency is needed; the pipeline uses the existing Pillow dependency.

Use image generation for authored silhouettes, textures, backgrounds and effect
shapes. Use code for precise frame layout, animation timing, seeded particles,
trails, pooling, easing and gameplay triggers. Generated art and code complement
each other. Inspect readability and animation in the game before acceptance.

Chat artwork cards and Known assets show the actual stored PNG atlases with a
transparency grid and a Download PNG link, including reused artwork. Requests
without an asset are labelled **Not generated yet**. A descriptive artwork plan
does not generate images or prepare game changes; use **Generate artwork & prepare
game changes** on the current plan to request that work. Review the resulting
proposal and accept each changed atlas before applying it.

## Bulk artwork generation

Ask for a batch such as “generate four original impact variations” or “create
separate grass, stone and water tiles.” Chat can return `image_requests` with up
to eight complete artwork specifications and unique asset IDs. Each item gets
its own PNG preview, download, preparation report and generation status. Artwork
batches leave the current game unchanged. Choose an individual result for use in
the game, or request a sprite entity plan to integrate several results; normal
proposal review and acceptance of each changed atlas still apply.

The host validates the whole batch before dispatch, then generates sequentially
through the existing shared-credit ledger. Each call reserves its own bounded
amount. Successful items survive failed siblings and interruption. **Generate
remaining artwork** resumes the saved batch without another Spark request or
resending completed images. An uncertain dispatched call keeps its reservation
and is never automatically retried; request a new generation for that item.
Saved batch specifications, credit binding and incremental results live under
the session's ignored `image-batches/` directory. Batch generation and a build
proposal are separate operations; use the existing sprite entity workflow when
generating artwork as part of a multi-asset game implementation.

## Tiles and tilesets

Ask chat for individual terrain tiles or a named tileset, including the art
direction and terrain types. Chat uses the same image-generation, asset review
and game integration workflow as sprites. Tile artwork has static cells rather
than animation clips. A tileset entity uses `role:"tileset"`,
`required_clips:["default"]` and `machine:null`.

For a manual image-tool handoff, prepare a request without making a provider call:

```powershell
py -3.12 tools/asset_2d.py tileset-request --id meadow-terrain --tile grass --tile path --tile water --tile wall --solid water --solid wall --tile-size 32 32 --columns 2 --style "Original top-down pixel art meadow, warm earth and cool water" --output .harness/meadow-request.json
```

`tile-request` is an alias: supply one `--tile` to prepare an individual tile
(`kind:"tile"`, one cell), or repeat it for a tileset (`kind:"tileset"`). Names
follow the same lowercase slug rules as animations. The helper uses nearest
sampling and opaque terrain. `--no-seamless` allows edge/transition artwork;
`--tool image_gen` prepares a host image-tool request instead of the default
`muse_image` handoff. Use the existing `ingest` and `prepare` commands after the
authorized image tool returns the actual PNG.

The saved specification records tile size in `frame_size`, atlas columns/rows
in `grid`, occupied cell count in `frames`, and optional named tile metadata:

```json
"tileset": {
  "seamless": true,
  "tiles": {
    "grass": {"frame": 0, "solid": false},
    "path": {"frame": 1, "solid": false},
    "water": {"frame": 2, "solid": true},
    "wall": {"frame": 3, "solid": true}
  }
}
```

Name each occupied cell exactly once. New tile specifications use `loop:false`,
`pivot:[0,0]` and no animation fields. Legacy tilesets without tile metadata
remain readable, with names `tile-0`, `tile-1`, etc. For mixed opaque terrain and
transparent overlays, a custom specification can use `require_alpha:true`;
the atlas must contain transparency, but individual terrain cells may be opaque.
Empty map cells use `null` rather than a blank PNG cell.

Both image adapters receive the named layout and instructions for edge-to-edge
cells without gutters, margins or perspective. `seamless:true` requests repetition
across opposite edges of each tile. This is generation guidance, not a verified
seamlessness result. Review repeated edges and transitions visually before acceptance.

The tile workshop shows the atlas, a selected tile repeated 4 × 4, and a sample
map. Choose another tile or turn off Repeat tile to inspect an individual cell.
The preview works on desktop and mobile and exports with the exact PNG, tile
metadata and shared runtime.

For side-view platformers, set `tileset.view:"side-view"`. Use `seamless:false`
for a set with exposed caps, surface trim and interior fill. Plan left/middle/right
surface pieces and the needed underside/corners; repeating a complete outlined
block creates visible internal borders. The image adapters now distinguish this
from overhead terrain. Legacy specifications without `view` retain their original
request bytes and guidance.

```powershell
py -3.12 tools/asset_2d.py tileset-request --id jungle-platforms --tile left --tile middle --tile right --tile fill --solid left --solid middle --solid right --solid fill --view side-view --no-seamless --style "Original side-view jungle ruins with matching surface heights and connected edges" --output .harness/jungle-platforms-request.json
```

Drawing and collision must use the same terrain layout and dimensions. When
replacing art on existing platforms, clip partial cells to the existing bounds;
a 48px art cell must not turn a 22px-high collider into a visibly 48px-high ledge.
Platformer review now has separate criteria for connected terrain in desktop/mobile
captures and source evidence of matching drawing/collision geometry. These are
AI judgments with checked evidence references, not a deterministic seam or physics
proof. See [the platformer terrain review](PLATFORMER_TERRAIN_REVIEW.md) for the
observed jungle failure and remaining process work.

The shared runtime renders tilemaps without advancing through terrain cells:

```javascript
const atlas = await EmberSprites.load(EMBER_ASSET);
const rows = [['grass', 'path', 'wall'], ['grass', null, 'water']];
atlas.drawMap(ctx, rows, 0, 0, {scale: 2});
atlas.drawTile(ctx, 'grass', 100, 100, {scale: 2});
const blocked = atlas.solidAt(rows, 2, 0); // column 2, row 0: wall
```

Tile drawing coordinates are top-left positions, independent of sprite pivots.
Maps accept names or zero-based cell indices and `null` empty cells; they must
be rectangular, with at most 256 rows/columns and 16,384 cells. Invalid maps
are rejected before drawing. Draw multiple maps for layers. The `solid` flags
are authored collision hints; game code controls physics and collision response.
With an entity plan, `scene.createEntity("terrain")` exposes `tiles`,
`drawTile`, `drawMap` and `solidAt`, and map draws appear in entity diagnostics.

Run `py -3.12 tools/offline_tests.py --pattern test_tiles.py` for contract,
request, runtime and export checks, or `py -3.12 tools/sprite_check.py --tiles`
for real desktop/mobile PNG rendering and controls in both preview and ZIP games.
The browser rehearsal uses original synthetic fixtures and makes no live model calls.

## Run the scripted VFX path

From the repository, choose a new output directory:

```powershell
py -3.12 tools/asset_2d.py effect --seed 7 --output .harness/asset-source/ember-impact-v1
py -3.12 tools/asset_2d.py prepare --source .harness/asset-source/ember-impact-v1
```

The first command builds a transparent 12-frame impact atlas: ivory flash,
expanding amber ring, seeded ballistic sparks and blurred glow. It saves the
PNG, versioned recipe specification and canonical `asset.js`. Repeating the
same specification with the same Python/Pillow environment reproduces the PNG.
The implementation is `ember_harness/asset_2d.py:render_effect`; edit the recipe
as code when another effect is needed and version its tool identifier. The
runner accepts only the built-in recipe and never executes model-supplied scripts.
This supersampled recipe supports frame sizes from 16 to 256 pixels per side.

The second command prints a saved session ID and prepares an unapplied proposal.
Reopen that session in Ember, choose **Try proposed changes**, scrub frames and
inspect edges, motion and silhouette. **Accept asset & play** records acceptance
of those exact bytes. Preparation never accepts an asset for you.

You can also use a discovered atlas in an existing session: ask Ember to put the
named effect in the game and trigger it on a hit. Chat receives metadata while
the host retains the PNG payload. Scene code is reviewed with the actual atlas.
Code-only revisions preserve the asset without asking for new asset acceptance.
The original `asset.js` workshop remains compatible. Entity-based games can now
bind up to eight independent atlases, each with up to 64 frames, to a saved
artwork plan. See [entity artwork and state machines](#entity-artwork-and-state-machines).

## Prepare an image-generation handoff

Save a specification such as the following under `.harness/`. Use one cell for a
single sprite or background; use a uniform row-major grid for animation or tiles.
Frames are contiguous, starting at the top left. Nonlooping VFX retain their last
frame in the inspection workshop; game code decides when an instance ends.

```json
{
  "profile": "sprite-atlas-v1",
  "id": "arcane-impact",
  "display_name": "Arcane impact",
  "art_direction": "Original hand-painted violet energy, pale gold core, clear silhouette at 96 pixels",
  "kind": "vfx",
  "frame_size": [256, 256],
  "grid": [4, 4],
  "frames": 16,
  "fps": 24,
  "loop": false,
  "pivot": [0.5, 0.5],
  "blend": "lighter",
  "sampling": "smooth",
  "require_alpha": true,
  "production": {
    "method": "generated",
    "tool": "image_gen",
    "prompt": "A coherent magical impact animation: brief anticipation, bright strike, radial fragments, gradual dissipation. Original game art.",
    "seed": null
  }
}
```

```powershell
py -3.12 tools/asset_2d.py request --spec .harness/arcane-spec.json --output .harness/arcane-request.json
```

An authorized host can pass the request's `parameters` to `image_gen`: `prompt`
and `transparent_background`. Other image services can be named in `production.tool`,
but require the host to translate these generic parameters to their own interface.
The prompt includes dimensions, cell layout, transparency, art direction and
consistent scale/pivot constraints. Tool output is source material, not a finished
game asset merely because the provider says it is. If the provider cannot meet
the grid or dimensions, regenerate or prepare a deliberate scripted conversion;
the importer never silently resizes or removes a background.

After the host returns the actual PNG:

```powershell
py -3.12 tools/asset_2d.py ingest --request .harness/arcane-request.json --image .harness/arcane-returned.png --output .harness/asset-source/arcane-impact-v1
py -3.12 tools/asset_2d.py prepare --source .harness/asset-source/arcane-impact-v1
```

The CLI writes new source directories only. It rejects changed request parameters,
invalid PNGs, animated PNGs, dimension mismatches, empty declared frames, opaque
sprite/VFX frames when transparency is required, excessive dimensions or file sizes. A PNG
is limited to 360,000 bytes, either side to 2048 pixels, and its complete reviewed
package to 512 KiB. Optimize a larger source explicitly before importing it.

The generated source retains its exact request; known-asset records pin hashes
of the specification, returned PNG and request. These records establish which
bytes were reviewed, not independent proof of which provider made an image.
Technical checks do not score visual quality, sprite consistency, animation
quality, seamless tiling or painted checkerboards. Review those in context.

### Start from Ember chat

Ask Ember to generate a sprite, background, tileset or effect atlas. When no known
asset matches, Muse returns an `image_request` specification instead of drawing
placeholder shapes or inventing PNG bytes. The host checks dimensions and layout
and saves the same tool-ready request under the session's
`image-requests/<turn-id>.json`. Chat calls **Muse Image directly** using the same
owner-authorized Model API credit budget as Spark. Set generated production's tool to `muse_image` and seed to
null. Returned artwork appears in the conversation with its real PNG preview,
source preparation report and one-cent ledger charge. The source is registered
in the known asset library. A requested scene implementation can be returned in
the same chat response; the host inserts the actual image package. An empty
project gets a playable asset workshop proposal. Artwork-only requests preserve
an existing ordinary game's files. Final asset acceptance still occurs in Ember.

The adapter uses `muse-image-1.0` at the official Meta images endpoint, reusing
`META_API_KEY`, `MODEL_API_KEY`, or Muse Code's existing stored API credential in
memory. It never puts a credential in project files, captures, logs or app state,
and refuses redirects. It requests one PNG with search tools disabled. The
existing request/ingest CLI remains available for manual workflows.

### Free credits and preparation

Muse Image costs **$0.01 per returned image**, verified against
[Meta's pricing](https://dev.meta.ai/docs/pricing-rate-limits) on November 1, 2026.
This shares the same crash-safe $150 ledger as Spark; no new balance, top-up or
paid fallback is created. On November 1 Johnathan confirmed that his Model API
grant already works with Spark and authorized image calls without repeated
billing blockers. Meta's [terms, section 13.3](https://dev.meta.ai/legal/terms-of-service)
describe promotional credits for the Model API Services rather than Spark-only
credits. `use_shared_credit_budget` records that authorization and the credential
fingerprint without inventing an observed billing balance or claiming a card was
removed. Normal chat generation does not require daily confirmations. Changing
the credential or exhausting the shared budget remains a real stop.

The account's billing page is authoritative for actual credit deductions; the
local ledger cannot track use by other apps. The older owner-confirmed balance
policy remains readable for existing installations, but its 24-hour confirmation
gate is not used for this authorized shared-budget connection.

Blocked requests remain saved. Once connected, **Generate with Muse Image**
executes that saved specification without another Spark call. Completed
images replay from hash-checked local captures. Timeouts, malformed replies and
uncertain failures retain their one-cent reservation and never retry on replay.
The returned-image charge is recorded before local preparation, so rejected
artwork does not silently refund a successful provider generation.

[Muse Image](https://dev.meta.ai/docs/image-generation) produces opaque artwork
at its own resolution. The adapter requests a flat magenta matte for sprites and
effects, then explicitly removes it and resizes to the declared atlas dimensions.
An aspect ratio mismatch over 8% is rejected. Oversized PNGs get one explicit
256-color conversion, then still must fit the ordinary package budget. Original
provider PNGs and preparation measurements remain in the session's
`image-captures/`; runtime sources live under `.harness/asset-source/muse-image/`.
Review edges, uniform cells and motion before accepting. The pipeline does not
claim that a model guaranteed perfect transparency or frame consistency.

## Use and revise the actual asset

PNG proposals now bundle **`sprite-player.js`**, a shared offline canvas player,
and retain it in later code revisions, saved versions and ZIP exports. Chat and
task workers receive its API and the actual asset specification, rather than
having to recreate frame slicing and playback for every game. The host inserts
the actual asset package and one synchronous player load before scene scripts,
correcting missing, late or deferred loader tags. Include classic
`script src="asset.js"` before scene code; when writing HTML explicitly, use
`asset.js`, `sprite-player.js`, then the game script. Wait for
`EmberSprites.load(EMBER_ASSET)` before rendering and show a visible load error.

For a character with multiple actions, extend the existing specification with
optional clip definitions such as:

```json
{
  "animations": {
    "idle": {"frames": [0, 1], "fps": 6, "loop": true},
    "walk": {"frames": [2, 3, 4, 5], "fps": 10, "loop": true},
    "attack": {"frames": [6, 7, 8], "fps": 12, "loop": false, "next": "idle"},
    "death": {"frames": [9, 10, 11], "fps": 8, "loop": false}
  },
  "default_animation": "idle"
}
```

This example requires at least 12 occupied cells in the parent specification.
Indices are zero-based and row-major; clips may reuse and reorder cells.
Each clip has its own speed and loop setting. Only nonlooping clips may declare
`next`; without it, the final frame is held. Names, frame bounds and transitions
are validated before generation/import. Both image handoff paths include this
action-to-cell layout in their generation prompt. Existing specifications and
reviewed hashes remain valid: an atlas without clips exposes one `default` clip
using its original frame count, speed and loop setting.
When `default_animation` is omitted, playback starts with `idle` if available,
otherwise the alphabetically first clip name.

```javascript
async function start() {
  const atlas = await EmberSprites.load(EMBER_ASSET);
  const actor = atlas.createPlayer();
  let previous;
  function tick(now) {
    const dt = previous === undefined ? 0 : Math.min((now - previous) / 1000, 0.1);
    previous = now;
    // Bind movement and action input in your game's existing update loop.
    const finishedActions = actor.update(dt);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    actor.draw(ctx, player.x, player.y, {scale: 2, flipX: player.facingLeft});
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
start().catch(error => { document.querySelector('#error').textContent = error.message; });
```

`actor.play('walk')` does not restart an already playing walk cycle.
`actor.play('attack', {restart: true})` explicitly replays an action; ordinary
attack input should wait until the current attack completes. `update(seconds)`
returns the names completed in that tick, carrying remaining time into `next`.
`actor.completed` identifies a held final frame. Every instance has its own clock.
`actor.seek(index)` uses a clip-local frame index; `actor.frame` reports its actual
atlas cell. Use the declared clip names; existing art does not acquire new actions
merely by changing its name or adding a player.

Draw coordinates identify the normalized pivot. Prefer `[0.5, 1]` for a character
standing on the ground. The player handles cells, scaling, mirroring, sampling and
blend, and restores the canvas settings afterward. Use `source-over` for ordinary
sprites and `lighter` for glowing effects. Keep movement, collision, damage and
effect lifetime in gameplay code. When integrating into a game, replace its intended
draw operation and connect clips to its existing state; preserve unrelated mechanics.

The workshop uses the same player as games. It exposes all clips, a clip-local
scrubber, A/D and arrow movement, touch movement buttons and an action button.
When supplied, idle/walk follow movement and the action button plays attack.
Its saved checks cover loading, pause and replay. Custom games keep their own
gameplay plans; they never receive workshop or 3D prop selectors automatically.
Inspect the actual game for correct input transitions, facing and foot alignment.

Discovery uses the existing asset roots described in [the asset pipeline guide](ASSET_PIPELINE.md).
After revising the recorded PNG and its specification, use **Known assets → Review
updated export**. A generated revision must retain a matching `generation-request.json`.
The scene code stays intact, and the updated atlas requires separate acceptance.
Switching between PNG and GLB assets requires an explicit scene implementation.
For an entity-based game, reviewing an updated PNG changes the corresponding
atlas reference and its entity bindings, preserving other sheets, scene code and
the player. Required clips and state markers must still fit the new export.

Saved versions preserve exact packages. ZIP exports include the original accepted
PNG, specification, technical report and playable game. Historical restore uses
the usual exact review. These tools support the local browser-game target and
the documented Muse Image connection; arbitrary engine imports remain separate.

## Entity artwork and state machines

Artwork requested for a game stays in its game plan and complete first playable.
Ember reuses compatible generated assets, prepares any needed scope review, then
integrates the artwork with gameplay. Existing generated batches offer **Use
these assets in the game plan**; individual results offer **Add artwork to game
plan** when a game design exists. Explicit standalone artwork requests still use
the asset library/workshop flow. Chat receives exact package acceptance receipts
so it can acknowledge previously accepted artwork without inventing approval.

When the game brief calls for authored sprite art, chat now receives a structured
inventory and instructions to plan the relevant characters, props, backgrounds,
tiles, interface art and effects. Movement, airborne and combat terms supply
planning hints. Muse must connect those hints to the game's actual mechanics,
reuse compatible library assets and describe why each new sheet is needed.
Hints do not add mechanics, grant authority or guarantee a model's design choices.

Ask, for example, “Give the courier idle, walk, jump, attack, hurt and death
animations, and use a separate impact on a hit. Keep the existing movement and
score.” The artwork inventory appears in chat and Known assets; game code uses
stable entity IDs such as `hero` and `impact`. Each entity records:

- Its role, purpose and required animation names.
- A frozen library reference to reuse, or a complete image-generation request.
- Whether it appears at startup or is activated on demand.
- Its source-file binding and the exact old drawing snippet being replaced.
- Its animation state machine, or a single explicitly selected clip.

The chat response field is `sprite_project:{intent,expected_revision,plan}`.
`intent:"plan"` with `build:null` saves the descriptive inventory without generation
or game writes. `intent:"implement"` requires real game edits and a complete plan.
The host validates reuse, role/kind compatibility, required clips, state graphs,
draw bindings and runtime file/atlas limits before generation. Project artwork
counts are estimates and never block generation or require a plan amendment.
Each supplied replacement snippet must occur exactly once in the old target file
and disappear from the proposed file. The new source must create the declared
entity using a literal ID in that file. Existing entity IDs are retained during
replacements. These are structural checks; the actual render and game behavior
still require browser checks and review.

An implementation must bind every entity, including backgrounds and on-demand
effects. If generated code omits a binding or its declared entity creation,
Ember requests one metered Muse correction before image generation. That
correction may fix bindings and source but must retain every entity, artwork
choice and animation requirement. It passes the same validation and exact-build
review; another invalid correction stops the request. A failed binding reply
offers **Try a new reply** so an older invalid capture does not trap retries.

Missing artwork uses the existing bounded Muse Image adapter and shared credit
ledger. Identical requests within a turn share a generation, and stable request
IDs replay saved provider captures. If later generation is blocked, completed
asset references remain in the saved inventory; the next implementation can
continue with those references. There is no automatic paid fallback or silent
provider retry. Generated sheets have actual PNG previews in the conversation.

The host creates three reviewed game files:

- `sprite-assets.js`: the actual verified PNG packages, keyed by frozen references.
- `sprite-plan.js`: the entity bindings and state definitions as canonical data.
- `sprite-player.js`: the shared renderer and state-machine implementation.

These files load before scene code and are retained in ordinary code revisions.
Game and task workers receive metadata and the API rather than PNG payloads.
Changing the artwork plan goes through `sprite_project`; workers cannot rewrite
the prepared bundles. The normal exact proposal shows the entity plan, state
names and every changed sheet. Multiple sheets have individual acceptance choices
in the UI and separate `asset.accept` receipts. Source-only changes do not request
asset acceptance again. Nothing accepts an asset for the user.

The collection is limited to eight distinct atlases and 4 MiB, with up to 16
entity definitions. Many entities can share one atlas. The existing eight-file
game limit and per-PNG size/dimension limits remain in effect. New project scopes
allow bounded 4 MiB prepared files; an older narrower approved scope may require
a reviewed renewal before it can hold a larger collection.

### Drive states from the game

Create the scene once, wait for its images, then spawn independent instances:

```javascript
const scene = await EmberSprites.createScene(EMBER_SPRITE_PLAN, EMBER_SPRITE_ASSETS);
const hero = scene.createEntity("hero"); // This literal ID belongs in binding.file.

// In the existing game update loop; these signals must be declared in its machine.
const events = hero.update(dtSeconds, {moving: Math.abs(vx) > 0.01, dead: hp <= 0},
  attackPressedThisTick ? ["attack"] : []);
for (const event of events) {
  if (event.name === "hit") applyAttackDamage();
}
hero.draw(ctx, playerX, feetY, {scale: 1, flipX: facingLeft});
```

The plan's machine contains `initial`, typed `signals`, `states` and ordered
`transitions`. This abbreviated combat example uses existing `idle`, `walk`,
`attack` and `death` clips:

```json
{
  "initial": "idle",
  "signals": {
    "moving": {"type": "boolean", "default": false},
    "dead": {"type": "boolean", "default": false}
  },
  "states": {
    "idle": {"clip": "idle", "priority": 0, "interruptible": true, "terminal": false, "on_complete": null, "markers": []},
    "walk": {"clip": "walk", "priority": 1, "interruptible": true, "terminal": false, "on_complete": null, "markers": []},
    "attack": {"clip": "attack", "priority": 50, "interruptible": false, "terminal": false, "on_complete": "idle", "markers": [{"event": "hit", "frame": 1}]},
    "death": {"clip": "death", "priority": 1000, "interruptible": false, "terminal": true, "on_complete": null, "markers": []}
  },
  "transitions": [
    {"from": ["*"], "to": "death", "event": null, "when": [{"signal": "dead", "op": "eq", "value": true}]},
    {"from": ["*"], "to": "attack", "event": "attack", "when": []},
    {"from": ["idle"], "to": "walk", "event": null, "when": [{"signal": "moving", "op": "eq", "value": true}]},
    {"from": ["walk"], "to": "idle", "event": null, "when": [{"signal": "moving", "op": "eq", "value": false}]}
  ]
}
```

Transitions first match their source, optional input event and all conditions.
The highest target priority wins, with declaration order breaking ties. A locked
state can only be interrupted by a higher-priority target. Requests for the
current state do not restart it. A terminal state ignores every transition until
the game explicitly calls `hero.reset()` for a real respawn.

Completion transitions require nonlooping clips and use state names. The machine
owns these transitions and ignores a clip's separate `next` setting. Completion
can resolve current motion/airborne conditions without replaying an input event.
Signals persist until updated and must have the declared boolean or finite-number
type. Conditions use equality or numeric comparisons; there is no model-supplied
JavaScript evaluator. Airborne games can declare `grounded` and vertical velocity
signals to drive jump, fall and landing states. Hurt can use an event with a
priority above ordinary movement and attacks. These rules belong to that game's
declared mechanics.

Markers use clip-local frame indices and emit once per state entry, even if an
update crosses several frames. Repeated input does not deliver another hit during
the same attack; an interrupted attack cannot emit a later marker. Marker output
includes entity/instance identity and state-entry sequence. Input events should
come from input edges; continuously sending a held attack event can begin another
attack after the prior action finishes. Game code owns collision, valid targets,
damage, movement and score. A marker alone does not prove a hit connected.

An entity with `machine:null` explicitly selects one `required_clips` entry. It
plays that clip without following another clip automatically. This supports
static art and disposable one-shot effects. Animated characters with multiple
required actions must supply a machine. Reuse instances for pools or call
`dispose()` when finished; a scene permits up to 256 live instances.

### Check bindings and behavior

`scene.diagnostics()` and `EmberSprites.diagnostics()` expose entity/reference,
state, actual frame, updates and draw counts. The production browser driver now
records these observations. A `startup` entity that never draws its bound atlas
adds a browser issue, which blocks automatic candidate recommendation. Mark
offscreen enemies, later-level entities and triggered effects `on_demand`, then
exercise their activation in targeted gameplay checks. Diagnostics are observable
game data and are not approval authority or proof of every game rule.

Versions preserve all exact bundles and state definitions. ZIPs include the
playable scripts, `sprite-plan.json`, and original PNG/specification/report files
under `sprites/<frozen-reference>/`, allowing different versions with the same
asset slug. Project handoffs include entity bindings and the asset inventory.
Updating a selected source sheet validates the affected state graph and retains
other sheets and game code. Approval and historical restore synchronize the
saved inventory with the actual approved game.

## Verify

```powershell
py -3.12 tools/offline_tests.py --pattern test_asset_2d.py
py -3.12 tools/offline_tests.py --pattern test_sprite_player.py
py -3.12 tools/offline_tests.py --pattern test_sprite_project.py
py -3.12 tools/sprite_check.py
py -3.12 tools/sprite_scene_check.py
```

The tests use real generated PNGs and synthetic owner decisions confined to
temporary fixture sessions. They check request integrity, alpha and bounds,
deterministic seeds, known-asset chat, separate acceptance, updates, restore and
PNG ZIP exports. They make no live model calls and invent no human acceptance.
The named-player tests also check transition timing, independent instances,
canvas drawing and runtime retention. Node is optional for those JavaScript
checks. The browser rehearsal uses the existing optional Playwright tooling
(see [browser setup](CHAT_BUILDS.md#browser-smoke-checks)); set
`EMBER_BROWSER_EXECUTABLE` if your Chromium-based browser is installed elsewhere.
It uses original synthetic fixture art and fixture-only approval decisions, and
checks real PNG pixels, keyboard/touch state transitions, mirroring and final-frame
holds in the sandboxed preview and exported ZIP game. Captures and the report stay
under `.harness/sprite-checks/`. This verifies integration behavior, not generated
art quality or a live model's implementation choices. Arbitrary games still need
their own gameplay checks and human asset acceptance.
The entity rehearsal also checks per-sheet acceptance in the real UI, replaces
the intended drawing in an existing fixture game, preserves its movement and
score, and exercises jump/fall, locked attacks, one damage event, hurt interruption,
terminal death, respawn and a separate impact atlas on desktop and touch. It tests
the real production browser driver against both a visible startup entity and an
intentionally undrawn one. Reports stay under `.harness/sprite-scene-checks/`.

# Platformer terrain review

Reviewed November 2, 2026 against the saved Jungle Vally project, its actual
generated terrain PNG, current game source and saved desktop verification capture.
No artwork was regenerated and no saved game, proposal or acceptance was changed.

## What the current process does

Muse describes a named atlas; Muse Image generates it; the host sizes the PNG
and validates dimensions, visible cells and transparency. `sprite-player.js`
draws named cells or a rectangular map and exposes authored `solid` hints.
The game code still decides platform geometry, tile placement and collision.
The tile workshop repeats one cell and displays an arbitrary sample map.
Separate proposal review examines game screenshots and available gameplay checks.

This is an atlas generation and rendering path. It does not yet author or
validate a connected platformer terrain layout, choose tiles by their neighbors,
or enforce a common map for visuals and collisions.

## Observed failures

1. **Wrong viewpoint.** The jungle platform atlas explicitly requested
   "overhead top-down platform textures" for a side-view game. The shared tile
   prompt also mandated a top-down view. This was an upstream generation problem.
2. **Missing connection roles.** Its four cells were grass, dirt, stone and ruins,
   with no left/right caps, middle sections, corners or underside roles. The PNG
   contains conspicuous borders and corner details. Repeating it repeats those
   borders between every pair of cells.
3. **Artwork and physics disagree.** The game has floating platforms 22px high
   but draws whole 64px tiles at 0.75 scale (48px high). It rounds platform widths
   up to full tile counts without clipping. Both height and partial end cells can
   extend beyond their collision rectangles. Integer positioning cannot repair
   either mismatched geometry or painted borders.
4. **The seam repair was insufficient.** The saved repair added a backing fill,
   integer positions and disabled smoothing. Its actual desktop capture still
   shows strong repeated grid borders. The separate review correctly recorded
   `needs_changes`; the assistant's proposed explanation was not proof of repair.
5. **Validation is narrower than the claim.** `seamless:true` is an instruction,
   not a measured result. PNG validation checks structure rather than adjacency.
   The recorded jump check only tested canvas visibility, so it could not prove
   jumping, landing alignment or traversability.

Evidence remains in the ignored local session
`.harness/ui/sessions/d849aaa0e86fc0657e712edb/`: the tile request in chat,
the source and candidate files, and `proposal-quality/1480ad75adb119798998fcc45d2431f652df3e76e046a16e86ab7c61f8e57251/`.
The terrain library reference is
`01d3a70fc930fe4a4c8c50709c0c22d80a1275b7736ca9c09ce6199f4d53a816`.

## Changes made in this pass

- Added optional `tileset.view` and CLI `--view`, with side-view generation
  guidance in both image adapters. Existing saved specifications and image
  request hashes remain reconstructible without modification.
- Added platformer planning guidance for caps, middles, fill, undersides and
  matching drawing/collision bounds. Side-view edge sets use `seamless:false`;
  sets explicitly marked seamless are treated as repeating fill textures.
- Added dedicated visual terrain and source geometry review criteria when the
  task or saved design describes a platformer. A nice screenshot alone cannot
  satisfy the source geometry criterion, and a source assertion alone cannot
  satisfy the visual joins criterion.

These changes guide future generation and review. They do not turn the existing
jungle PNG into a connected platformer tileset or implement automatic tile selection.

## Recommended next work, in order

1. **One terrain layout shared by rendering and collision.** Introduce a saved
   grid/layer description with tile size, origin, solid cells and decorative cells.
   For existing irregular rectangles, preserve gameplay bounds and clip partial
   tiles. Decide explicitly whether floating platforms are solid or one-way.
2. **Neighbor-aware tile selection.** Define a small surface/edge/corner/fill
   vocabulary and select atlas pieces from exposed neighbors. Treat grass edges,
   stone interiors and decorative ruins as different roles. Avoid a larger
   all-purpose atlas until the basic joins work.
3. **Review a connected strip before game integration.** Show several center
   tiles joined between left/right caps, thick ground with fill, thin ledges,
   exposed undersides and corners, plus a collider overlay. The current arbitrary
   sample map is insufficient for this review. Add a zoomed view at actual game
   scale and at the intended pixel sampling.
4. **Reject unsupported seam claims.** Record intended neighbor pairs and inspect
   their joins. Color/alpha discontinuity measurements can flag suspicious seams,
   but textured terrain still needs contextual visual review. Do not treat an
   edge metric alone as proof of good art.
5. **Exercise the actual terrain.** Walk across a tile join, land on a narrow
   ledge, collide with an exposed end and traverse the intended route. Assert
   positions, grounded state and collision bounds rather than page visibility.

For the jungle game, the first artwork repair should be a new reviewed side-view
edge/fill set and an unapplied integration proposal with matching geometry. Keep
the current accepted artwork and game available until the replacement is reviewed.

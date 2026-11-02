---
name: blender-prop-production
description: Produce and refine editable Blender props for Ember, with measured scale, exportable materials, deliberate pivots and separate collision geometry.
---

Use [the asset specification and commands](../../../docs/ASSET_PIPELINE.md).
Run `tools/blender_delivery_chest.py` or `tools/blender_courier_gate.py` in a new
background Blender process with a fresh ignored output directory. They share the
construction/export helpers in `tools/blender_prop_support.py`. Never run the
scene reset inside an artist's open working scene. Keep prior exports and .blend
files for comparison; do not overwrite an accepted source.

Start with the brief's dimensions and game camera. Build silhouette and functional
structure before decorative detail. A container needs an interior; a hinged lid
needs its origin at the hinge. Apply mesh scale before beveling, retain meaningful
object names, and use glTF-exportable material factors in this initial profile.

Keep all prop nodes under `AssetRoot`. For `hinged-prop-v1`, declare the exact hinge,
collision and socket names and local rotation axis in the specification. Passage
proxies must be children of the hinge; keep the interaction socket outside that
moving subtree. Declare frame posts or other fixed parts in `static_collision_nodes`
and keep their proxy meshes outside the hinge. The old chest names remain supported
for existing packages. Collision
must describe the intended playable footprint without sealing off the interaction
point. Keep the proxy separate from visible geometry and exclude it from beauty
bounds. Blender uses Z up; the exported specification uses glTF Y up, metres.

Save the editable .blend and export a GLB with named nodes, normals, materials and
custom properties. The current profile has no image textures, external resources,
compression, skins or clips. Check the host's measured GLB bounds against the
brief; do not replace expected dimensions with measured values to hide a mismatch.

Inspect actual closed and open views in the harness after export. Fix edge softness,
intersections, hinge sweep, visible collision, readability and material balance at
the source. Check passages by moving through them, and test closing while the
actor occupies the opening. A successful exporter exit is not proof of delivery.

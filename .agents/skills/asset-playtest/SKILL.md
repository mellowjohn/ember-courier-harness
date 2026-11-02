---
name: asset-playtest
description: Test an Ember asset in its gameplay scene, compare a proposed refinement with the current version, and turn observed failures into precise source changes.
---

Use the existing saved gameplay and proposal-comparison workflows documented in
[ASSET_PIPELINE.md](../../../docs/ASSET_PIPELINE.md). Reuse `asset_workshop.plan(spec)`
for a declared prop; keep desktop keyboard and mobile touch coverage.

Observe a fresh scene for each scenario. Check unreachable interactions, opening,
closing, delivery count, reset and collision. Keep visible state selectors stable.
DOM state is behavioral evidence only; also inspect screenshots or a live scene
for actual mesh motion, clipping, silhouette, materials, scale and camera framing.

For a refinement, capture the current and proposed versions with the same saved
plan before acceptance. Bind reports to their exact manifests and specification.
Investigate a failed collision/reach scenario in Blender before changing interaction
distance. Change controls or camera in the scene source when that is the cause.
Do not substitute an unrelated procedural mesh for a failed imported asset.

Run `tools/asset_check.py --asset chest` and `--asset gate` for the reproducible
Blender-to-browser rehearsals. The gate check must observe its actual moving
proxy, keyboard passage, and refusal to close on the actor. Their
owner decisions are explicitly synthetic inside a generated fixture; never apply
those decisions to a real session or describe them as human acceptance.

Report measured results separately from visual judgments and performance samples.
An observed frame interval is host-dependent, not a performance guarantee. Finish
with the remaining human review step and retained evidence locations.

---
name: asset-pipeline
description: Take a game asset from a production brief through Blender, an offline Ember scene, playtest evidence and source refinement. Use for complete asset workflows in this repository.
---

Read [the working pipeline guide](../../../docs/ASSET_PIPELINE.md) before selecting
tools. The implemented profiles cover the original chest and reusable hinged
props, demonstrated by the courier waygate. Characters, texture pipelines and
arbitrary engine imports need further implementation.

For 2D sprites, tilesets, backgrounds and VFX, use
[the PNG and scripted VFX workflow](../../../docs/ASSETS_2D.md). Prepare a saved
image-tool request and ingest the returned PNG, or use the seeded local effect
recipe. Image generation makes the artwork; scene code controls animation,
particles and gameplay triggers. The image request itself makes no provider
call. Do not invent generated pixels or treat request metadata as execution
authority. PNG atlases use the same library, exact acceptance and version flows.

Keep one asset specification through the workflow: gameplay purpose, real dimensions,
style, target camera, pivot, collision, attachment nodes, budgets and acceptance
scenarios. State that brief before modeling. Obtain missing decisions only when
they materially affect the result; use the approved project direction.

Route production through [blender-prop-production](../blender-prop-production/SKILL.md),
packaging through [asset-integration](../asset-integration/SKILL.md), and validation
and refinement through [asset-playtest](../asset-playtest/SKILL.md).

Treat a handoff as complete only when the next stage consumes the actual artifact.
Carry the GLB hash, specification and observed bounds into the scene and retained
reports. Judge silhouette and materials at gameplay distance as well as close up.
Technical measurements cannot establish visual quality, playability or acceptance.

When a check fails, locate the responsible source: geometry/pivot/collision in
Blender; controls/camera/rendering in the scene. Change that source, export again
when needed, and repeat the same scenarios. Do not weaken the scenario to pass.
Finish with the editable source, exact export, playable proposal, evidence and
remaining limitations. Leave the real asset acceptance to the user's review UI.

# Original prop production in the app

In **Plan**, approve a project plan with an asset budget and select its production task.
Choose **Create chest directions** or **Create gate directions** in that card.
In **Build**, read the producer/verifier permissions and choose **Approve task run**. Older
project scopes need a reviewed amendment/renewal for the new `asset.produce` and
direction-selection actions. Preparing a run starts no model calls or Blender.

This first production profile supports an empty project or the matching existing
prop workshop. Integration into other games uses the existing known-asset chat
workflow after production. Characters, arbitrary meshes, texture/animation
pipelines and engine imports remain separate work.

Install Blender and the existing optional [offline Three.js/browser tools](ASSET_PIPELINE.md).
The app detects Blender on PATH, the standard Windows installation or common
Steam locations; `EMBER_BLENDER` can specify its executable. New workshops use
`.harness/asset-tools/engine.js`. Existing workshops retain their exact runtime.
No Python dependency or paid asset service has been added.

The [orchestrator](ORCHESTRATION.md) assigns concept work, native production and
verification to distinct agents with separately reviewed contracts and write
areas. An explicit native chest/waygate task can select this adapter automatically
through **Run task with Muse**. The direction pick remains a human checkpoint.

## Choose a direction

Muse proposes exactly three bounded original designs. The host produces real
Blender studies with closed hero and open/impact views, palette swatches, notes
and a retained comparison sheet. These are procedural 3D concept studies, not
general painted concept art or image-model generation. Notes are AI suggestions.
Slat count, trim width, edge softness, material factors and proxy padding are
the editable controls; scripts and paths cannot be supplied by the model.

Open **Rendered concept directions**, inspect the views and source design,
then choose one. This click creates an explicit, exact direction-selection
approval in the existing gate; `approve_all` cannot choose for you. Reloading
does not change the pick or silently start production of an unchosen direction.
The project art direction is inherited. When the project declares a palette,
design colors must come from it; use explicit hex colors for this profile.

The chosen identity, dimensions, tolerance, required nodes, interaction structure,
project direction and palette remain locked during refinement. Unsupported
changes need another reviewed scope/run. Each direction is a preview for the
same asset task; none supplies individual asset acceptance.

## Produce, verify and refine

After the pick, a dedicated background Blender process consumes the bounded
parametric source, saves an editable `.blend`, exports its GLB and renders both
views. It starts with factory settings and automatic script execution disabled;
the host supplies only a pinned, packaged generator. It never resets an artist's
open scene or overwrites a previous production directory.

A separate verifier checks the exported specification against the lock, measures
the actual GLB and tests the actual package with the frozen desktop/touch plan.
Muse sees the native views and browser captures in a separate request. Its
positive judgment cannot override failing gameplay, malformed exports or changed
evidence. These checks do not prove arbitrary game quality or human acceptance.

Use **Refine Blender source** with concrete feedback about silhouette, trim,
softness, materials or collision. Muse edits the bounded `production-design.json`
parameters; the fixed generator builds a new native source and export, and the
same independent checks repeat. This is parametric source refinement; it does
not interpret arbitrary edits to an artist's existing `.blend`.

There are at most three production/refinement allocations and $30 in Muse
promotional credits per run, within the existing shared $150 ceiling. Failed or
stopped allocations cannot be reset by a restart or a new run for the same task.
The existing explicit one-extra-attempt decision permits a newly reviewed run;
it does not widen the old generator permissions. Uncertain model usage retains
the existing conservative credit hold. Partial Blender output stops for
inspection and is retained instead of being overwritten.

When checks qualify, choose **Review exact asset changes**, play the unapplied
proposal and then separately **Accept asset & play**. The exact GLB still needs
its own acceptance receipt. Finally inspect the applied game and **Accept task
outcome**. Neither a direction pick nor a passing model assessment accepts the
asset or task. New workshops receive the matching gameplay plan on promotion;
existing scene code, runtime, brief and saved checks remain in place.

Native sources and evidence are under
`.harness/ui/sessions/SESSION/task-runs/RUN/production/ATTEMPT/export/`;
concept studies are alongside them in `concepts/`. Source design, `.blend`, GLB,
specification, both renders and their hashes are retained for each attempt.
Managed run artifacts must remain unchanged for replay or promotion. To make
external artist edits, work from a separate copy and use the existing explicit
[re-export review](ASSET_PIPELINE.md#review-a-revised-export-in-the-same-session).
Game ZIPs contain the accepted GLB and scene; native source stays in production.

## Rehearse the workflow

`tests/test_asset_run.py` uses synthetic model/Blender/owner fixtures to cover
role boundaries, explicit picking, source retention, tampering and acceptance.
Run `py -3.12 tools/asset_production_check.py` for real Blender exports/renders and
Chromium operated through the actual app controls. Its synthetic model first
uses an oversized collision proxy; real keyboard/touch failures block promotion
despite a positive AI judgment. A source refinement then repairs the proxy,
re-exports and passes the same checks before synthetic fixture acceptance.
Reports, screenshots and ZIPs stay under `.harness/asset-production-checks/`.
Live Muse quality and real human artistic acceptance remain delivery gates.

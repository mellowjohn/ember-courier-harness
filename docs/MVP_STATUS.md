# Ember MVP implementation checklist

The baseline is the approved architecture, especially Part 11's tiers and Part
12's owner decisions, plus the later browser workspace, overnight polish and
Blender workflow requests. A working browser demo is one product slice. Passing
the implemented test suite does not establish completion of this checklist.

Status vocabulary: **usable** means available in the app; **library/demo** means
executable code exists but the general product workflow is incomplete;
**partial** names the working boundary; **missing** means no implementation was
found; **paused** preserves an explicit owner restriction. These are capability
assessments, not percentages.

| Requirement | Evidence / working boundary | Remaining work |
|---|---|---|
| A0: approved project scope before work; descendants remain subsets | **Usable/partial:** opt-in persistent project plans, ordered tasks, scope-bound exact builds and isolated worker/verifier contracts, inherited art direction, reviewed amendments and version-bound human task acceptance (`project_plan.py`, [guide](PROJECT_PLAN.md)) | Complete plan-first onboarding and broader project workers; legacy sessions retain per-build behavior until adopting a plan |
| A1: schema, hash-locked approvals, deny-by-default gate, evidence, audit, amendments | **Library/demo and usable:** core, amendments, owner review and app exact-build approvals | Keep new workers behind the existing gate; no parallel permission mechanism |
| A2: iteration, C0–C3 checkpoints, one amendment, three-attempt escalation | **Usable/partial:** browser task allocations and canonical finding attempts, frozen baseline/candidate/applied/owner-closure witnesses, three-attempt breaker, explicit extra allowance and resumable evidence ([findings](FINDINGS.md)); generated Git repairs retain the same task/bug allocation through source and Git stages and connect canonical browser findings to a clean Git witness and explicit C3 closure ([guide](GIT_TASKS.md)) | Expanded Git lifecycle, canonical closure and handoff checks pass in the clean installed release and browser rehearsals. General failure-driven Git scope amendments remain separate; ordinary task/Git runs do not manufacture findings, and S0/S1 closure remains Johnathan-only |
| A3: orchestrator → coding worker → independent verifier, sequential | **Usable/partial:** approved Muse coding → separate source verifier → exact generated-source Git permission review → clean named baseline/head verifier → exact application; both Git stages reuse the existing scope, gate and attempts ([Git repairs](GIT_TASKS.md)); ordinary browser task execution remains available ([task runs](TASK_RUNS.md)) | Expanded end-to-end and clean installation checks pass; live Muse quality remains pending; autonomous arbitrary-project/native Git coding, repository test commands and engine work remain separate |
| A4: observed statuses, evidence labels, report, AI judgment vs owner acceptance | **Usable/partial:** activity, audit, browser reports, proposal comparisons, polish and independent task reports, scope-bound task outcome cards and a verified project handoff spanning asset steps and findings ([guide](PROJECT_HANDOFF.md)) | Broader pipeline evidence and live quality review remain separate |
| A5: concept directions and B1 ingest | **Usable/partial:** three generated procedural Blender directions with hero/open views, palette, notes and comparison sheet, explicit hash-bound human pick; supplied PNG ingest remains available (`assets.py`, [production guide](ASSET_PRODUCTION.md)) | General painted/image-model concepts, pre-pick concept refinement and broader art-direction scoring remain separate work; the current generated studies use bounded original prop geometry |
| A6: Git layout, trailers and local contract-lock | **Usable/partial:** approved browser repairs create fresh private local repositories, named baseline/head commits, contract/round trailers and Git-aware contract-lock; retained source, commits and captures are rechecked before review/export ([guide](GIT_TASKS.md)) | General repository workers and original-history integration remain separate; source repositories are unchanged; hosted CI is not an MVP prerequisite |
| B7: concept/specification lock and validation | **Usable/partial:** app direction pick locks identity, dimensions, interaction, art direction and palette; packaged Blender producer retains editable source, independent GLB inspection and fixed desktop/touch checks | Broader asset families, arbitrary artist-mesh editing and general production specifications remain separate work |
| B7b: cached pipeline steps, invalidation, forced failure, amendment and retry | **Partial:** durable producer/verifier checkpoints, retained native/export versions, audit-backed task attempts and real collision-failure/source-refinement rehearsal; reviewed re-exports remain available | Original planner/step-key invalidation and failure-as-amendment across general pipeline workers remain separate from bounded parameter refinement |
| B8: attach an existing workspace, read-only scan, rendered scaffold plan | **Usable/partial:** read-only inventory with passive Git branch/commit metadata and asset filename hints; rendered setup/import contents, hashes and conflicts; separate reviewed create-only setup or flat browser-source copy, followed by normal scoped exact-build adoption ([guide](WORKSPACE.md)) | Git dirty/remotes and full engine/asset dependency inventories, nested/arbitrary source import, general templates and original-project editing remain separate work |
| Triage intake, deduplication, severity/repro/routing, verified closure/reopening | **Usable/partial:** build-bound human reports, reviewed intake/QA routing, scoped browser fixes, frozen failing baseline and passing candidate, exact apply, explicit closure/reopening and retained limits ([guide](FINDINGS.md)); the generated browser-Git adapter adds clean commit/capture witnesses to canonical finding closure | Expanded Git closure/lifecycle checks pass; live Muse fix quality remains pending; automatic imported findings, late duplicate reconciliation and arbitrary-project Git fixes remain separate; S0/S1 closure stays owner-only |
| One integrated sample: approved scope → assets → playable game → finding → amendment/fix → verify/report | **Partial:** one-session browser rehearsal and handoff across approved scope, real Blender production/refinement, exact asset acceptance, reviewed scope amendment, finding, scoped fix, independent verification, explicit closure and version-bound task acceptance ([guide](PROJECT_HANDOFF.md)); model replies and owner responses are fixtures | Live model output and human playtesting remain outstanding; failure-driven Git amendments remain separate |
| Later request: saved conversations, briefs and project locations | **Usable/partial:** persistent sessions, brief snapshots, remembered locations, reviewed Save as, bounded workspace scan/setup and exact flat browser-source import/adoption ([guide](WORKSPACE.md)) | Nested imports, arbitrary-project editing and original-repository writes remain separate work |
| Later request: gameplay comparisons, history, safe restore and ZIP | **Usable:** fixed desktop/touch plans, version-bound reports, exact restored/exported bytes | Broader human gameplay coverage; DOM checks do not establish arbitrary game quality |
| Later request: overnight detailed polish | **Usable/partial:** isolated candidates, captures, critiques, limits, recovery and final review | Live Muse quality rehearsal; general asset-source/modeling tasks are not part of the polish worker |
| Later request: Blender creation → integration → playtest → refinement | **Usable/partial:** selected-task producer, human concept pick, bounded Muse source-parameter edits, real Blender exports, independent geometry/gameplay checks and screenshot judgment, exact acceptance | Live Muse artistic-quality rehearsal, arbitrary existing-game integration, broader props/characters/textures and arbitrary native-source edits remain separate work |
| Later request: reusable mechanic improvements | **Usable/partial:** Lantern Trail movement/jumps and the expanded Lantern Vale camera, hit-stop/protection, sentinel states and seeded-layout recipes; scoped full-profile migration, configuration-only retuning, twelve fixed observation groups and existing comparison/restore/handoff paths ([guide](MECHANICS.md)) | Sixteen focused runtime/integration cases, seven expanded evidence cases, the complete expanded browser rehearsal and the final installed gate pass. Human feel/comfort, automatic chat routing and arbitrary-game integration remain open |
| Reproducible installation and handoff | **Usable/partial:** the current `fbf5` snapshot passes all 772 tests and twelve demos from a fresh installed wheel in a clean clone, plus desktop/mobile recovery and nine source-bound browser/feature rehearsals ([installation checks](PRODUCT_DEMO.md#clean-installation-check)) | The 230-file implementation manifest matches the verified delivery source; all 88 packaged files match the wheel. The verification checkout stays clean. Live Muse quality and the complete real-user demonstration remain outstanding |

## Delivery order

1. Persistent project planning (implemented first slice): approved scope, explicit exclusions/asset budget,
   ordered tasks, active-task context, scope-bound exact builds, reviewed
   amendments and separate human task acceptance.
2. Bounded task execution (implemented browser slice): one Muse coding worker
   followed by a separate verifier, using the existing gate, attempt module,
   evidence/checkpoint executor and browser driver. Generated browser Git repairs
   now hand source-verifier-qualified bytes to separately approved private Git
   work and clean named before/head checks, sharing one allocation. Canonical
   browser findings retain explicit C3 closure backed by that Git witness.
   General native/repository workers, failure-driven Git scope amendments and
   live model quality remain boundaries. See [Git browser repairs](GIT_TASKS.md).
3. Concept and Blender production (implemented chest/waygate slice): generated
   original procedural directions, explicit human pick, bounded parametric source
   edits, editable native source, export, independent geometry/gameplay/visual
   review and a repeatable refinement loop. General image concepts and arbitrary
   artist-mesh editing remain outside this first profile.
4. Findings and iteration (implemented browser slice): connect human playtest
   findings to reviewed intake, scoped fixes, frozen failing baseline, separate
   candidate verification, exact apply, explicit closure, escalation and recurrence.
   The bounded generated-browser Git adapter now joins that canonical closure
   path. General failure-driven Git amendments and live fix quality remain
   explicit boundaries; the expanded lifecycle and canonical closure checks pass.
5. Existing workspace onboarding (implemented bounded slice): reviewed read-only
   inventory, passive Git metadata, asset filename hints, full setup/import
   contents and conflicts, and separate exact create-only copies. Supported flat
   browser sources can enter the current game only through its normal scoped
   exact-build review. Nested source trees, full Git/engine dependencies and
   original-project editing remain outside this slice. See [workspace onboarding](WORKSPACE.md).
6. Mechanic recipes (implemented bounded references): versioned movement/jumps
   in Lantern Trail plus Lantern Vale camera, impact/protection, sentinel states
   and seeded layouts. The first v2 use reviews a full reference migration;
   subsequent edits change configuration only. Focused timing, viewport,
   actual-route and forged-evidence checks pass, as do the complete expanded
   browser rehearsal and installed gate; human feel, automatic chat recipe
   routing and arbitrary-game integration remain open. See [mechanics](MECHANICS.md).

The integrated sample and verified handoff connect the browser slices. The
earlier Git/import/movement snapshot passed clean installation, launcher,
recovery and the offline gate. The current automated Git/expanded recipe
snapshot also passes its full installed release and product rehearsals. Live model quality and human playtesting
remain separate gates.

Implement one complete stage at a time and update this checklist with the exact
working boundary. Design choices requiring user input should be resolved against
the original decisions; completion criteria must not be silently reduced to the
features already implemented.

## Workflow quality backlog

The [workflow quality tickets](WORKFLOW_QUALITY_TICKETS.md) track the November 1
request to improve output quality through better handoffs, evidence-backed
reviews, useful revision feedback and representative live rehearsals. WQ-01
passes the complete frozen approved design and brief to every browser-task
specialist and independent verifier, including retries. This repairs missing
context; live output quality remains unverified. WQ-02 now freezes visible
task-quality criteria for new ordinary browser-task runs and blocks qualification
on missing, unsupported or unmet evidence. Human experience remains pending;
finding and asset adapters retain their existing specialized reviews. WQ-03 now
carries bounded criticism and browser/gameplay failures from rejected polish
attempts into the next revision while retaining the strongest editing base and
identical recovery context. WQ-04 now compares new ordinary task runs against
the frozen starting experience; WQ-05 exposes blockers, losses and retained
playable attempts; WQ-06 shows advisory interaction-coverage gaps before dispatch.
The reviewed run freezes those inputs and all configured failures remain
blocking. WQ-07's representative live Muse rehearsal and human playtesting remain
open. These tickets preserve the existing delivery gates.

## Mechanic recipe backlog

The [MVP mechanic tickets](MECHANIC_TICKETS.md) document the October 31 request
for reusable, reviewable game improvements. MR-01 through MR-04 are implemented
for the bounded [Lantern Trail reference profile](MECHANICS.md): versioned
settings, reproducible observations, acceleration/friction and forgiving jumps.
The integration retains exact build/manifest/plan bindings and rejects missing,
forged, stale or failed mechanic evidence even when DOM checks or AI judgments
are positive. MR-05's guarded automated product rehearsal and final
installed-release validation passed; Johnathan's own playtest remains pending.
MR-01's verified entry is the Plan recipe UI; automatic chat recipe/task routing
remains a follow-up. MR-06 through MR-09 are now implemented for the bounded
Lantern Vale profile: camera follow/reduced motion, hit pause/protection,
sentinel states and versioned seeded layouts. Sixteen runtime/integration cases
and seven expanded evidence cases pass, together with the complete expanded
product rehearsal and final installed gate. None replaces Johnathan's human
comfort, impact-feel or overall gameplay judgment.

## Current expanded verification — November 3

The automated browser-Git and Lantern Vale implementation passes **772 tests
and twelve demos** from a fresh installed wheel in a clean Git checkout. The
230-file implementation manifest matches the delivery source; all 88 packaged
implementation/resource files match the wheel. Desktop/mobile launch and restart,
nine source-bound browser/feature rehearsals and both Git handoff exports pass.
The checkout stays clean and the shared credit ledger is unchanged. No runtime
package dependency was added.

Local verification snapshot: `de404a8ae8142f1d1e65e6b33a92f01b97ec056f`.
Reports: `.harness/v/fbf5/DELIVERY.md`, `.harness/v/fbf5/REPORT.md` and
`.harness/v/fbf5/c/.harness/clean-installs/b2af738e/REPORT.md`. This local commit
exists only in the ignored verification repository; the original working patch
is uncommitted. Model replies and owner choices are fixtures; installation,
Git, captures, browser input and file checks are real. Live Muse output quality
and Johnathan's own integrated playtest remain open.

## Earlier verified checkpoint — November 3

The earlier local delivery snapshot passes **735 tests and twelve demos** from a
fresh installed wheel, plus installed imports/resources/dependencies, command
entry points and real Windows desktop/mobile launch/restart. The clean Git
checkout remained clean and its 217 implementation hashes matched that delivery
source before the later automated Git/expanded recipe changes. Its local verification commit is
`5005b73e2df567c6e999365b39f9a1cd4b918e6d`; it does not commit or push the original
working patch. Parent report: `.harness/v/bdf9/REPORT.md`; installation:
`.harness/v/bdf9/c/.harness/clean-installs/4bd1798c/REPORT.md`.

The same frozen checkout passes the complete Chromium workflow, import/adoption,
both Git review routes, the movement/jump product rehearsal, guarded quality
repair and overnight polish. `.harness/v/bdf9/DELIVERY.md` indexes those reports,
the playable sample ZIP and source additions. Model replies and owner choices
are fixtures; browser input, Git commits, captures, installation and file checks
are real. The shared credit ledger remained byte-for-byte unchanged. No new
runtime package dependency was added. Live Muse quality, Johnathan's acceptance
and the broader remaining MVP integrations stay open.

## Earlier validation checkpoints

The retained reports below describe earlier frozen snapshots. Their counts,
source manifests and remaining-work statements apply to those checkpoints;
the current capability table and guides above describe the later bounded
Git/import/mechanic implementation. They are not final validation of this slice.

The earlier November 3 delivery checkpoint implements WQ-04 through WQ-06 and verifies
the exact implementation in a clean Git clone of a local source snapshot. Its
fresh installed wheel passes all **680 tests and twelve demos**, installed
imports/resources, dependencies, entry points and Windows desktop/mobile
launch/restart checks. The checkout stays clean and the implementation manifest
matches the working delivery source. Parent report:
`.harness/v/e67a/REPORT.md`; installed report:
`.harness/v/e67a/c/.harness/clean-installs/3ada4d32/REPORT.md`.

The same frozen checkout passes the complete Chromium workflow, guarded quality
repair and overnight polish rehearsals. Reports are in its
`.harness/browser-checks/20261103T140407Z-29369bba/`,
`.harness/quality-checks/20261103T140538Z-a2eb9d/` and
`.harness/polish-checks/20261103T141309Z-6f627ab7/` directories. Model replies and
owner choices in these successful rehearsals are fixtures; browser interactions,
captures, installation and file evidence are real. The release test runner
disables host Muse discovery; browser fixture tools deny unstubbed reservations.
This checkpoint establishes the bounded implementation and automated delivery
checks at that time, not live output quality, human acceptance or upstream
publication. It predates the bounded Git/import/mechanic slice described above.

The live Muse rehearsal now has a repeatable preparation command,
`tools/prepare_live_task.py`, described in [task execution](TASK_RUNS.md#prepare-the-live-mvp-rehearsal).
It creates a dedicated one-task courier session, saved keyboard/touch checks
and an exact pending scope packet after checking local tooling and shared
credit availability. Three focused tests cover missing prerequisites, credit
denial and preparation without dispatch, approval or game writes. This is
preparation only; live output quality and human gameplay acceptance remain open.

The November 1 installed desktop checkpoint uses the actual `Start Ember.cmd`
with a fresh installed wheel and a desktop workspace containing no package
source. Chromium passes desktop session creation and brief saving, desktop/mobile
workflow navigation, restart, exact session/brief recovery and remembered project location.
Missing and retired private-link tokens are refused. A real Muse request reaches
the zero-credit gate and is denied before dispatch; its ledger remains byte-for-byte
unchanged and no model reply is captured. The launcher also retains argument and
failure-exit behavior across project, active and global Python environments.
The retained desktop report and four captures are in
`.harness/clean-installs/9c3a1e01/validation/.harness/desktop-launch-checks/83ff9391/`.
The same clean-install gate passes all 510 Python tests and twelve demos, installed
imports/resources, dependency checks and command entry points. Its parent report
is `.harness/clean-installs/9c3a1e01/REPORT.md`; parent and nested source manifests
remain unchanged, and the parent binds the installed wheel and dependency hashes.
This is installed-source-snapshot evidence, not an actual clean Git checkout,
live model quality, contract approval or human gameplay acceptance.

The workflow UI and handoff checkpoint has isolated installed coverage of 506
unique Python cases: the full 505-case baseline completed successfully, then a
fresh final wheel reran all 15 task cases, including the added large-runtime
regression. Only `task_run.py` and its tests changed between those Python runs.
The final wheel, all packaged resource hashes, dependency check, CLI and twelve
demos passed in `.harness/installed-final/529df21e/`. The original full-suite
wrapper timed out before collecting the completed successful log; its retained
log is linked by that report. The offline watchdog now allows 30 minutes.
The desktop/mobile browser and polish reports in
`.harness/v/05a9/.harness/browser-checks/20261101T005521Z-2d8459e6/` and
`.harness/v/05a9/.harness/polish-checks/20261101T005521Z-ee5c2d91/` pass and bind
the exact final UI resource. They cover workflow navigation, keyboard access,
draft and live-frame retention, the missing gameplay-plan/revision regression
and the existing review, planning, finding and workspace controls. The later
task-runtime prompt changes have separate installed regression coverage.

The same integrated session completed the real Blender-to-browser workflow,
scope amendment, failing regression, scoped fix, exact application, explicit
closure, separate task acceptance, current keyboard/touch checks and mobile
handoff download. The handoff's nested game matches the independently verified
export, repeat downloads are identical and changed native production evidence
blocks export. Evidence is retained in
`.harness/v/2bd2/.harness/integrated-sample-checks/20261101T013302Z-06b5e0c1/continuation/`.
The initial browser driver timed out just before the worker reached exact review;
that failure report is retained in the parent folder. The continuation resumed
the saved qualified candidate with identical product sources and no further
model calls. The driver now allows five minutes for that worker wait and expects
two browser images for the ordinary finding verifier (the asset verifier also
receives two native renders). Provider replies and owner decisions remain
synthetic; Blender, Chromium, files and evidence assertions are real. This
establishes the bounded sample/handoff connection, not live model quality or
Johnathan's human artistic/gameplay acceptance.

The existing-workspace checkpoint passed 491 tests and twelve demos from a
freshly built, offline-installed wheel, plus 18 focused workspace regressions
from the checkout. The final Chromium rehearsal exercised the actual scan,
inventory, setup diff/conflicts, separate contract/action approvals, pending
review reload, mobile layout, exact sandbox files, retained completion and
unchanged source hashes. The existing browser gameplay, project planning,
finding/fix, closure, recurrence and escalation flows also passed. Both final
reports bind the same finished implementation manifest and report unchanged
source: `.harness/clean-installs/1ee8f851/` (nested full release:
`validation/.harness/release-checks/20261031T232613Z-46ca159b/`) and
`.harness/browser-checks/20261031T232548Z-8ab64106/`. Workspace and finding
contract-lock checks passed. Owner responses and provider replies are synthetic;
file evidence and Chromium observations are real. No live Muse calls, credits or
human quality acceptance are claimed. Source import and broader inventories
were still pending at this earlier checkpoint; the current bounded import path
is described in [workspace onboarding](WORKSPACE.md). Complete engine/asset
dependency inventories, the integrated human demonstration and live model
quality remain separate delivery work.

The browser-findings checkpoint passed 473 tests and twelve demos from both the
checkout and a clean-installed wheel. The final Chromium rehearsal exercised
actual intake/review controls, a frozen failing baseline, an independently checked
passing fix, exact application, explicit closure, reload, reopening, two stopped
non-reproducing attempts without additional model calls and an owner decision
allowing exactly one extra attempt. Its closure evidence passes contract-lock
after recurrence. This checkpoint's reports match the finished source manifest:
`.harness/release-checks/20261031T223658Z-4bbe49f7/`,
`.harness/clean-installs/4fec65cf/` and
`.harness/browser-checks/20261031T223658Z-55b8e698/`.
Provider replies and owner decisions are synthetic; browser observations and file
evidence are real. No live Muse calls, credits or human quality acceptance are
claimed. General Git rounds/amendments, automatic finding imports, live fix
quality, workspace onboarding and the full integrated human demonstration remain
separate delivery work.

The bounded original-prop checkpoint passed 459 tests and twelve demos from the
checkout and a clean-installed wheel. Real Blender/Chromium production exercised
three rendered directions, a human-fixture pick, an oversized collider rejected
despite positive AI judgment, source refinement, independent checks, exact asset
acceptance and separate task acceptance. The waygate, browser and overnight
rehearsals also passed. All retained reports match the finished source manifest:
`.harness/release-checks/20261031T214230Z-a4538be3/`,
`.harness/clean-installs/0d9b852a/`,
`.harness/asset-production-checks/20261031T213800Z-90173f31/`,
`.harness/asset-checks/20261031T213800Z-e1e3d1be/`,
`.harness/browser-checks/20261031T214230Z-49cd6577/` and
`.harness/polish-checks/20261031T214230Z-7a99c95c/`. A real native/export/render
smoke check using the installed wheel's packaged generator is retained in
`.harness/production-dev/installed-177395d0/`. Provider replies and owner
decisions remain synthetic. No live Muse calls, credit use or human artistic
acceptance is claimed; clean-checkout launch, live quality and human playtesting
remain delivery gates.

The bounded browser-task checkpoint passed 450 tests and twelve demos, plus the
browser QA/restore/project-plan/task-execution and overnight-polish Chromium
rehearsals. All three reports match the finished implementation manifest:
`.harness/release-checks/20261031T205900Z-56afd2c2/`,
`.harness/browser-checks/20261031T205900Z-5477a1b3/` and
`.harness/polish-checks/20261031T205900Z-446dc79c/`. The task rehearsal operates
the real controls, runs frozen desktop/touch checks, reloads independent
evidence, promotes an exact proposal and separately accepts the applied outcome.
Provider replies and owner decisions are synthetic; no live Muse calls, credit
use or human quality acceptance is claimed. Latest-wheel installation, live
model quality and human playtesting remain delivery gates.

The first planning integration checkpoint passed 438 tests and twelve demos,
plus the browser QA/restore/project-plan and overnight-polish Chromium rehearsals.
Retained reports bind the finished implementation in
`.harness/release-checks/20261031T195210Z-b3a7e15b/`,
`.harness/browser-checks/20261031T195211Z-75d326a7/` and
`.harness/polish-checks/20261031T195211Z-58520c72/`. Provider replies and owner
decisions in those rehearsals are synthetic; no live Muse calls or human quality
acceptance is claimed. The app's sample Ember Courier plan remains unapproved.

Wrathful Conquest engine edits and editor bake/import remain paused. OPA is
excluded. Hosted CI, LFS setup, two parallel workers and automatic scaffolding
are not prerequisites for the original sequential MVP. Animation/sound and
arbitrary asset families need further implementation. PR execution is not
implemented; the registry's approval request is not a created PR. Publishing,
deployment, submission, force pushes and PR merges remain denied. Muse calls
remain subject to the shared authorized promotional-credit ledger.

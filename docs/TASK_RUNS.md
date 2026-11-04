# Run a selected browser task with Muse

Approve a **Project plan**, select **Work on this task**, and save a nonempty
**Gameplay checks** plan with observable expectations for the intended result.
Node, Playwright and Chromium use the existing [browser setup](CHAT_BUILDS.md#browser-smoke-checks).
Muse installation and the shared promotional-credit rules are described in
[models and credits](MODELS_AND_CREDITS.md).

Choose **Run task with Muse**, read the exact coding-worker and verifier
permissions, then **Approve task run**. Preparing the review starts no inference.
Older approved project scopes need **Amend or renew project plan** to include
the isolated task workspace, model and fixed-browser permissions. They cannot
silently gain these permissions. The root is a permission ceiling; the two
separately reviewed child contracts are strict subsets and inherit its art direction.

The host [automatically delegates to specialists](ORCHESTRATION.md) based on the
selected task. A compound gameplay/interface/effects task can use two workers
with separate identities and candidate folders. The run review shows the ordered
assignments, and the verifier checks their combined result. Other tasks retain
one implementation worker. The host runs the roles sequentially:

For a first browser game without an explicit artwork exclusion, an artwork specialist
runs first. It requests missing character/environment sheets through Muse Image
or reuses compatible library art, and binds the actual atlases into a scene. The
implementation specialist then receives that scene and the protected artwork.
The exact run review includes the bounded image allowance. Images and their
checkpoints are reused across coding repairs and resumes; a blocked image call
leaves work incomplete. This route uses up to two coding/verifier attempts within
the same $30 ceiling. See [orchestration](ORCHESTRATION.md).

1. The coding worker receives the selected task, complete approved design,
   editable source, brief and frozen gameplay expectations. The same frozen
   approved design reaches every specialist and the verifier, including its
   core loop, exclusions, artwork estimates and completion criteria. Other planned
   features provide context; only the selected task is assigned work. Later
   brief edits do not redirect a reviewed run or retry. Protected `asset.js`
   and `engine.js` bundles are supplied as verified hashes and sizes, with the
   asset specification, rather than duplicating their contents in the bounded
   prompt. The host carries their exact bytes into every candidate and rejects
   edits to them. Muse returns complete
   HTML/CSS/classic JavaScript or targeted edits, preferring focused changes to
   existing systems. The host reconstructs the complete candidate, validates it
   and gates each isolated write. Later attempts repair the previous candidate
   with its checked feedback; they retain the original approved source for
   comparison instead of starting the implementation over each time.
2. The verifier has a separate agent identity and request, reads the exact
   candidate and original approved source, runs the fixed Chromium driver and receives real desktop/mobile
   screenshots. It judges task completion and preservation of the approved scope.
   It receives no coder narrative and cannot write candidate or current-project files.
   Captures also include a movement pose while Right is held. New comparison
   runs attach a labeled contact sheet per viewport, retaining initial, gameplay,
   movement and any open help/settings panel views within the four-image limit
   for the original/candidate comparison. Each original image and the sheet are
   hash-checked; evidence references use the labeled original filenames.
   Failed candidates'
   desktop/mobile images and open-panel captures (or movement poses when no
   panel is captured) reach the coding specialists on the next permitted repair,
   together with the failed assertions and visual feedback. Movement poses remain
   retained even when panel images use the bounded review attachments.
   Visual review explicitly checks the requested artwork, silhouettes, palette,
   readability and feedback; one captured pose cannot establish smooth animation.
3. Every required gameplay scenario must pass, browser startup must succeed,
   browser observations and overflow must be clean, and the independent AI
   assessment must report completion, preservation and no remaining issues.
   A model's positive judgment cannot override failing gameplay checks.
4. A qualifying result enables **Review exact task changes**. This prepares the
   ordinary previewable exact diff under the existing project scope. Choose
   **Approve & play** to apply it, then play and separately **Accept task outcome**.

New ordinary browser-task runs show **Quality criteria** before permission
approval: the selected task in its approved core-loop/brief context, preservation
of exclusions and assets, readable presentation and feedback, every frozen
gameplay scenario, and pending human experience. The same checklist reaches all
specialists, the verifier and repair attempts. It adds no model call.
The [game UI criteria](GAME_UI.md) separately check that changed HUD/menu layers
belong inside the game stage and match the game's art direction at both sizes.

The independent verifier assesses each ID exactly once as `met`, `not_met` or
`not_observed`, with a reason and evidence. Task/preservation judgments quote
actual candidate source; visual judgments reference both attached desktop/mobile
captures; gameplay judgments reference the matching passing scenario. Unknown,
duplicate or missing IDs and unsupported references block qualification, as do
unmet/unobserved required criteria. Blockers travel into repair feedback and
remain visible with the retained report. A valid reference supports inspection;
it does not prove that the AI interpretation is correct.

Human experience stays `not_observed` with no AI evidence. Project completion
criteria guide that separate review without requiring unrelated planned work in
this task. Existing finding and native asset adapters keep their specialized
verification. Older reviewed runs retain their original packet rather than
silently gaining a new checklist. See [workflow quality](WORKFLOW_QUALITY_TICKETS.md).

New ordinary task runs also freeze a **Starting experience comparison**. Before
coding, the verifier captures the exact original game with the same saved
gameplay scenarios and fixed desktop/mobile input protocol used for each
candidate. The verifier receives both sets of captures, their observations and
the original/candidate source. It must identify the requested improvement and
any losses, citing actual source, both viewport captures and relevant checks on
each available side. A failed original scenario remains visible as before
evidence. A blank first project is explicitly labeled **No playable comparison
baseline**, with no invented before evidence.

Missing or unsupported comparison evidence, no observed improvement and reported
regressions block qualification even when the model says the task is complete.
Changed source alone cannot establish an improved interaction: that conclusion
is still an AI judgment, followed by your separate playtest. Comparison blockers
reach the next permitted repair. The original source and capture checkpoint are
retained across retries and verified again before review, preview or promotion;
changed source, screenshots, reports or saved check plans invalidate the evidence.
The starting capture adds no Muse call and stays inside the existing reviewed
verifier action allowance. Finding/native asset runs and older reviewed runs
retain their original specialized evidence rather than acquiring new permissions.

The same review shows a frozen coverage inventory for the selected task:
configured discoverability, success, failure, reset, replay and input paths,
with suggested check additions where observations are missing. These labels are
the check author's declared intent, not verification that the game implements
it. All configured scenarios remain required. DOM values are influenced by game
code and cannot independently establish scoring, physics, accessibility or fun.
Use the existing gameplay editor to review additions before preparing a new run.

One-worker runs use at most three attempts and two model calls per attempt.
Two-worker runs use at most two attempts and three model calls per attempt.
Both have a $30 bound in
promotional credits, inside the existing shared $150 ceiling. Each model call
uses the existing bounded reservation and conservative interrupted-call rules.

New runs freeze their execution allowances in the permission review. Implementation
and independent verification use high reasoning effort and up to fifteen minutes
per call. Compound assignments or at least 48 KiB of editable source receive up
to thirty minutes; repairs after failed task verification receive thirty minutes.
The next attempt retains the candidate and concrete failure feedback. Time limits
are ceilings, not estimates or quality scores. Progress shows the active call's
allowance and elapsed time, and failed evidence leaves the work incomplete.
The full run can span several calls and attempts within the reviewed window and
credit/attempt bounds. See [execution and credits](MODELS_AND_CREDITS.md).
There is no cash fallback. Task preparation checks available credit but does not
promise that all three attempts can be funded.

Failed candidates retain their source, captures, observations and AI judgment.
The audit-backed attempt ledger lives in `attempts.py`, separately from bug
closure. Starting another run or renewing the same task's scope does not reset
its count. At the limit, review the evidence and choose **Authorize one extra
attempt**, then prepare and approve another run. That decision grants exactly
one allocation and does not approve its contracts or final build.

**Resume same task attempt** validates pinned source, authority, candidate writes,
provider captures and browser evidence before continuing. Completed phases replay
without another call. An uncertain provider outcome remains subject to the
existing credit hold and inspected-retry policy. Validation failures and damaged
partial browser captures stop for inspection; they are not silently retried with
different inputs. **Stop task run** retains evidence and consumes a started
attempt, allowing a new reviewed run only when the ledger has capacity.

Scope revocation, expiry, supersession, changed project bytes, changed gameplay
plans or changed reviewed runtime inputs stop further work or promotion. Changing
the selected card does not redirect an existing run. The current game remains
unchanged until the final exact approval.

This worker supports the existing flat browser-game target. It preserves prepared
`engine.js`, `asset.js` and prepared sprite bundles exactly. Source modeling, arbitrary
commands and Git commits/worktrees retain their separate workflows. The
[findings workflow](FINDINGS.md) adapts this same executor to one approved bug
attempt with a frozen failing baseline and explicit closure; ordinary planned
tasks still cannot manufacture or close bug identities. General Git C0–C3 rounds
remain separate. A separate AI request is independent
of the coding request, but it still uses the same configured Muse model. Its
judgment and fixed DOM checks do not establish arbitrary game quality or human
acceptance. Live model quality rehearsal remains a delivery gate.

The separate [asset-production task](ASSET_PRODUCTION.md) adds bounded original
chest/waygate concepts, source-parameter edits and native Blender exports. It
shares the gate, ledger and checkpoint executor; ordinary coding tasks still
preserve prepared assets exactly.

`tests/test_task_run.py` covers gates, role separation, retries, explicit
escalation, recovery, tampering, changed authority and HTTP authorization with
synthetic provider/owner fixtures. A large-runtime regression checks bounded
prompts, exact host retention for complete editable-file replies and rejection
of protected-runtime edits. The existing `tools/browser_check.py` rehearsal
also operates the actual task controls, executes real Chromium checks, reloads
the retained report, reviews the final proposal and separately accepts its
applied outcome. No live credits are used by these rehearsals.

## Prepare the live MVP rehearsal

```powershell
py -3.12 tools/prepare_live_task.py
```

This checks the existing Muse installation, browser tooling and shared credit
availability, then creates a dedicated **Live Muse MVP rehearsal** session with
one original courier-game task and saved keyboard/touch checks. Both scenarios
fit the gameplay action budget. Each checks pickup, three moves,
delivery and reset; game-reported state remains an observation, not independent
proof of the rules.

The command prepares a normal pending project-scope review. It starts no model
call, reserves no credit, approves no contract and writes no game source. Its
`REVIEW.md` and `preparation.json` under `.harness/live-task-checks/SESSION/`
retain the exact review reference, task, checks, implementation hashes, tooling
identities and initial ledger summary. Each invocation creates a new session;
reopen the saved session to continue an existing rehearsal.

Open that session through History, review and approve its project plan, then
choose **Run task with Muse** and review the narrower worker/verifier contracts.
The existing executor and limits above apply. Retain the real replies, browser
reports and captures. After exact build review and a human playtest, record the
feedback and separately accept the task outcome. Export the project handoff
through the existing Handoff view. A preparation packet is not live-quality
evidence or human approval; update the MVP checklist only with observed results.

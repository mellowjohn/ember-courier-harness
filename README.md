# Ember

**Ember is a local game-development workspace:** describe a browser game, review the proposed changes, play it, and iterate with Muse. Its contract-driven harness keeps file writes, approvals, evidence and recovery tied to the exact work you reviewed. **Ember Courier** is the separate sample workflow demonstrating the contract library.

## Quick start on Windows

1. Install [Python 3.12 or newer](https://www.python.org/downloads/).
   Python 3.12 is the tested setup version. If you use the Python install manager,
   run `py install 3.12` once.
2. [Download Ember](https://github.com/mellowjohn/ember-courier-harness/archive/refs/heads/main.zip),
   choose **Extract all**, and open the extracted folder containing **Start Ember.cmd**.
3. Double-click **Start Ember.cmd**. First launch installs Ember into its own
   private environment, then opens your browser. Leave the launcher window open
   while you use the app. If the browser stays closed, open the complete private
   link printed in that window.
4. Choose **New session**, name your project and choose a projects folder.

The first installation needs internet access. Later launches reuse the setup.
No administrator access, terminal commands or environment activation are needed
after Python is installed. **Setup Ember.cmd** also works on its own for setup
or repairs.

**AI chat uses your own Muse Code account.** Install Muse Code on Windows, sign
in with your subscribed Meta account, then open **Muse settings** in Ember to
check your subscription. If you have your own Model API promotional credits,
you can select that connection separately. You can open Ember and inspect local
work before connecting. See the [setup guide](docs/INSTALL.md#enable-ai-chat).

**Automated gameplay checks are optional:** install [Node.js LTS](https://nodejs.org/en/download),
then run `& ".\Setup Ember.cmd" --browser` from PowerShell in the Ember folder to
add Playwright and Chromium. Manual previews need only your browser. Git is needed
for Git repair verification, the contract sample's commits and contributor workflows; Blender is needed
only for 3D prop production.

See **[installation, updates and troubleshooting](docs/INSTALL.md)** for the
complete setup guide, Muse detection, diagnostics, backups and manual installation.

## What you can build

This repository contains the local app, Python contract library, regression tests, browser rehearsals and architecture. Browser games and a bounded Blender-to-Three.js prop workflow are supported; private engine code is not included. The broader engine and asset-production pipeline remain specifications.

**Blender asset workshop:** create an editable delivery chest or courier waygate, export and validate its GLB, and try it in an offline Three.js scene. Reusable hinged-prop specifications drive the identity, pivot, interaction and moving/fixed collision checks. The exact asset requires your acceptance and travels with saved versions and ZIP exports. See [the asset pipeline guide](docs/ASSET_PIPELINE.md).

**Asset-aware chat:** Ember remembers known assets, their source/export locations
and the asset being discussed. Ask where the gate source is, then say “put it in
the scene” to prepare a proposal from its verified GLB. Scene revisions retain
the asset and runtime automatically; source locations appear in the review.
After re-exporting an accepted asset from Blender, **Known assets → Review updated
export** prepares the revised asset in the same scene for preview, gameplay checks
and separate acceptance, preserving your scene edits.

**2D art and VFX:** prepare image-generation requests, import and validate actual
PNG atlases, or build reproducible impact effects with scripts. Preview animation
and transparency in the canvas workshop, use named idle/walk/action clips through
the shared sprite player, generate individual tiles or named tilesets with
repeated-edge previews, draw layered tilemaps with authored collision hints,
plan and bind entity artwork with guarded animation
states and up to eight separately accepted atlases, and retain
exact acceptance, versions and PNG exports. Live image calls use an external
authorized host handoff. See [2D assets and scripted VFX](docs/ASSETS_2D.md).

**Bulk work:** request up to 64 targeted code edits across project files in one
reviewed proposal, or generate up to eight independent artwork assets in one chat
request. Artwork batches retain per-item results and resume without resending
completed generations; each asset still needs acceptance when used in a game.
See [bulk artwork generation](docs/ASSETS_2D.md#bulk-artwork-generation).

**Game audio:** add original synthesized gameplay cues, looping music and ambience
with separate volume and mute controls. The shared offline player travels with
reviewed builds, previews, saved versions and ZIP exports. Try the standalone
sound demo and see [game audio](docs/GAME_AUDIO.md).

## Run Ember

Double-click **Start Ember.cmd** to reopen Ember, then create or reopen a named
session and describe an original browser game. For manual launch and contributor
commands, see [installation](docs/INSTALL.md#manual-and-contributor-setup).

1. Save a **Project brief** with the goal, controls, visual direction and constraints.
2. Review the proposal and choose **Try proposed changes** to play it beside the current game. With a saved gameplay plan, **Check proposed changes** compares both versions before approval; a failed proposal can be sent back for a reviewed fix.
3. Choose **Approve & play** to apply those exact changes, or **Request changes** to send feedback.
4. Revisit saved versions, review a restore, or download a verified game ZIP.

Revisions focus on improving the existing game. Targeted edits carry untouched
code forward exactly; broader rewrites remain available when requested or needed.

See [the local app guide](docs/LOCAL_UI.md) and [builds, previews and versions](docs/CHAT_BUILDS.md).

The workspace keeps **chat on the left and the playable game on the right**.
Describe your idea, review changes in the conversation, and refine the game as you
play. Proposed changes also open on the right, beside your conversation. Use
**Fullscreen** for the current play session or **Open in new window** for a fresh,
full-window game. **Project tools** holds planning, versions, downloads and audit
details; **Checks & advanced refinement** sits below the game. Opening tools
preserves your live game state. **Download project handoff**
bundles the approved game with its scope, tasks, asset, findings and checked
evidence report. See [project handoff and the integrated sample](docs/PROJECT_HANDOFF.md).

**Existing workspace · scan & setup** inventories a selected project folder,
shows setup/import contents and conflicts, and copies reviewed setup files or
supported flat browser sources into an isolated location after exact approval.
Imported games need the normal scoped build review before replacing the current
game; original files stay unchanged. See [workspace onboarding](docs/WORKSPACE.md).

**Git browser repairs** can use an approved coding worker and independent source
review, then separately reviewed clean Git verification, or start from an exact
edit. Both retain baseline/head commits and the same saved regression before
normal build approval. Canonical findings retain separate verified closure;
source repositories stay unchanged. See [reviewed Git repairs](docs/GIT_TASKS.md).

**Gameplay recipes** provide versioned movement/jump settings in Lantern Trail,
plus camera, hit protection, enemy states and seeded layouts in the expanded
Lantern Vale reference. The first expanded recipe needs a complete reviewed
profile upgrade; subsequent tuning changes its configuration. Compare
keyboard/touch play and separately accept the result. See
[mechanic recipes](docs/MECHANICS.md).

## Gameplay checks and overnight polish

**Project plan & tasks** adds a persistent approved game scope with the complete
feature list, exclusions, artwork estimates, completion criteria and art direction.
Select a task, review its exact build within that scope, and separately accept
the outcome against the saved version. Scope amendments and renewals use the
existing review and widening-acknowledgement rules. See [project planning](docs/PROJECT_PLAN.md)
and the [original MVP implementation checklist](docs/MVP_STATUS.md) for remaining work.

**Run task with Muse** adds a separately reviewed coding worker and independent
verifier for the selected browser task. Candidate files stay isolated while real
desktop/mobile gameplay checks and a separate Muse assessment run. Bounded attempts,
shared credit limits and durable recovery bound the work. A qualified candidate
still needs exact build approval and separate human task acceptance. See
[task execution](docs/TASK_RUNS.md).

**Automatic specialist delegation** routes approved tasks to gameplay, interface
or VFX agents, using two workers for compound tasks and a separate final verifier.
Prop production separates concept, Blender production and verification agents.
Assignments appear in the run review and progress. See
[orchestration](docs/ORCHESTRATION.md).

First visual browser tasks start with an artwork
specialist using Muse Image or compatible library assets, followed by game
implementation and independent verification. Accepting a task automatically
selects the next unfinished task and prepares its run review. Each new run and
generated asset retains its existing approval.

**Create chest/gate directions** adds original rendered concept studies, an
explicit human pick, editable Blender production, independent export/gameplay
checks and bounded parametric source refinement. The final asset and task still
need separate acceptance. See [asset production](docs/ASSET_PRODUCTION.md).

**Playtest notes → Find & fix bug** investigates the source and proposes a repair
from your notes, with visible investigation, code, review and file-application
states. **Dictate** adds editable speech input to chat and notes in supporting
browsers. No finding form or saved gameplay plan is required to request a fix.
**Findings & fixes** keeps the optional formal workflow connecting problem playtests to reviewed intake,
reproduction details, routing and duplicate/severity review. A scoped fix uses
the existing bug-attempt ledger, a failing frozen baseline, a separate candidate
verifier, exact build approval and explicit owner closure. Reopening preserves
the history and attempt allowance. See [findings and verified fixes](docs/FINDINGS.md).

**Gameplay checks** saves a per-session plan of clicks, key presses, touch taps and observable expectations. Check visible states, text and numeric scores; reports bind to the game version and saved plan. Each scenario starts a fresh isolated game. Canvas-only scores need a visible score element before they can be asserted. See [saved gameplay checks](docs/GAMEPLAY_CHECKS.md).

**Overnight polish** freezes the game, brief and saved test plan inside an upfront-reviewed scope. Ember builds isolated candidates, captures real desktop/mobile browser screenshots, obtains AI critiques, and keeps the strongest qualifying result. Failed required gameplay checks block automatic recommendation even when startup is clean. You review the playable candidates and exact final diff before the current game changes. See [overnight polish](docs/OVERNIGHT_POLISH.md).

These features use optional Node, Playwright and Chromium tooling; [setup instructions](docs/CHAT_BUILDS.md#browser-smoke-checks) describe the developer installation. The Python library and offline release suite do not require Chromium. Browser observations and AI judgments cover their stated checks; human gameplay review is still needed.

## Local data and credit limits

Choose a projects folder when creating a session; Ember remembers it after restart. **Project folder → Save approved project as…** prepares a reviewed copy in another location. Sessions, approvals, captures and evidence stay under ignored **`.harness/`** paths; project files use their saved location. See [local project locations](docs/LOCAL_UI.md). Game previews isolate project scripts from the app and its private API. ZIP exports contain verified game files and a source manifest, without private session history or credentials. See [preview restrictions](docs/CHAT_BUILDS.md).

Live requests use the connection selected in **Muse settings**. Ember keeps a shared local $150 safety ceiling with bounded reservations and conservative holds for uncertain usage. Your subscription allowance and promotional balance are managed by Meta. Running saved gameplay checks, trying proposals, restoring versions and exporting ZIPs do not call Muse. See [models and credits](docs/MODELS_AND_CREDITS.md).

## Verify the project

```powershell
.\.venv\Scripts\python.exe tools/release_check.py
.\.venv\Scripts\python.exe tools/clean_install_check.py --wheelhouse .harness/clean-install-wheelhouse
.\.venv\Scripts\python.exe tools/browser_check.py --playwright-module PATH_TO_PLAYWRIGHT --browser-executable PATH_TO_CHROMIUM
.\.venv\Scripts\python.exe tools/polish_check.py
.\.venv\Scripts\python.exe tools/asset_production_check.py --integrated
```

On Windows, add `--desktop-launch` to the clean-install command to check the real
launcher, private link, desktop/mobile UI and saved-session restart using the
installed wheel. It requires the existing optional Chromium tooling and makes no
live model call. See [installation checks](docs/PRODUCT_DEMO.md#clean-installation-check).

The offline gate runs the full test suite and twelve demos. The clean-install gate builds and tests an installed wheel without checkout package source; prepare its dependency wheelhouse using [these instructions](docs/PRODUCT_DEMO.md#clean-installation-check). Chromium rehearsals use synthetic model replies and approval decisions with real browser input, captures and assertions; they consume no Muse credits. Logs and source hashes stay under `.harness/`. See [the current release plan](docs/RELEASE_PLAN.md) for the latest verified checkpoint and remaining work.

## Contract library and demonstrations

Run the tests with `.\.venv\Scripts\python.exe tools/offline_tests.py` after installing with `.\.venv\Scripts\python.exe -m pip install -e .`. This runner disables discovery of your installed Muse so an unstubbed fixture cannot call it. Provider-adapter tests retain their explicit synthetic binaries. See [the implementation guide](docs/contracts/IMPLEMENTATION.md) for setup, approval flow, coverage and current limits.

Run `.\.venv\Scripts\python.exe examples/contract_demo.py` to demonstrate contract approval, allowed and denied actions, and evidence checks that detect a changed file.

Run `.\.venv\Scripts\python.exe examples/amendment_demo.py` to demonstrate draft amendments, separate widening acknowledgement, supersession, evidence carry-forward, and forward rollback. See [the amendment workflow](docs/contracts/AMENDMENTS.md).

Run `.\.venv\Scripts\python.exe examples/staged_fix_demo.py` for a real failing regression, gated fix, local Git commit, read-only automated review and verified closure. Use `.\.venv\Scripts\python.exe -m ember_harness --store PATH contract-lock` to check saved contract history. See [contract-lock and the staged workflow](docs/contracts/CONTRACT_LOCK.md).

Run `.\.venv\Scripts\python.exe examples/round_demo.py` to add C0–C3 round checkpoints, clean pre-fix/fixed verification checkouts, overlapping-round protection, and an audit-backed report. See [rounds and reports](docs/triage/ROUNDS_AND_REPORTS.md).

Run `.\.venv\Scripts\python.exe examples/attempt_demo.py` for three failed fix attempts, blocked escalation, and a recorded owner decision allowing exactly one extra attempt. See [attempt limits and escalation](docs/triage/ATTEMPTS_AND_ESCALATION.md).

Run `.\.venv\Scripts\python.exe examples/intake_demo.py` for bug intake, missing-repro checks, QA-confirmed deduplication, severity review, routing and frozen snapshots. See [intake, deduplication and routing](docs/triage/INTAKE_DEDUP_AND_ROUTING.md).

Run `.\.venv\Scripts\python.exe examples/reconciliation_demo.py` for owner-approved late duplicate merges, preserved attempt history, blocked retries and a separate one-attempt escalation decision. See [owner reconciliation](docs/triage/OWNER_RECONCILIATION.md).

Run `.\.venv\Scripts\python.exe examples/reopening_demo.py` for a real closed → reopened → triaged → closed cycle, preserved attempt counts, stale-evidence rejection and a second verified local fix. See [reopening closed bugs](docs/triage/REOPENING.md).

Run `.\.venv\Scripts\python.exe examples/muse_review_demo.py` for optional review imports and gated intake, or add `--binary PATH_TO_MUSE_EXE` to exercise the installed Muse CLI in no-cost echo mode. This review-capture adapter remains no-cost-only; live chat and overnight polish use the separate credit controls described above. See [Muse review captures](docs/triage/MUSE_REVIEWS.md).

## Start here

- **Local workflow app:** run `.\.venv\Scripts\python.exe -m ember_harness.local_ui`, then open the printed private link. Chat with Muse using your own connection, reopen named sessions, resume checkpointed workflows after a stopped worker, request browser prototypes with inline diff approval, and review sample-workflow approvals in chat. See [`docs/LOCAL_UI.md`](docs/LOCAL_UI.md).

- **Complete product demonstration:** [`docs/PRODUCT_DEMO.md`](docs/PRODUCT_DEMO.md). Run `.\.venv\Scripts\python.exe examples/product_demo.py` for one shared scope, selected and accepted asset, intake, amended fix, actual regression, local commit and clean verification.
- **Concept selection and asset ingest:** [`docs/concepts/SELECTION_AND_INGEST.md`](docs/concepts/SELECTION_AND_INGEST.md). Run `.\.venv\Scripts\python.exe examples/asset_demo.py` for the CLI end-to-end demonstration with original PNG fixtures and simulated owner approvals.
- **Intent to scope:** [`docs/contracts/SCOPE_WORKFLOW.md`](docs/contracts/SCOPE_WORKFLOW.md). Use `scope-propose` and `scope-review`, then the existing separate approval command. Run `.\.venv\Scripts\python.exe examples/scope_demo.py` for the CLI end-to-end demonstration.
- **November 4 priorities and release check:** [`docs/RELEASE_PLAN.md`](docs/RELEASE_PLAN.md). Run `.\.venv\Scripts\python.exe tools/release_check.py` for the full offline suite and all twelve demo entry points, with retained logs and source hashes.
- **Agents & hard rules:** [`AGENTS.md`](AGENTS.md)
- **Architecture (merged source of truth):** [`docs/architecture/ARCHITECTURE_DRAFT_v4.md`](docs/architecture/ARCHITECTURE_DRAFT_v4.md)
- **Contracts (reading order):** [`docs/contracts/README.md`](docs/contracts/README.md)

Optional area skills (stubs): `.agents/skills/{contracts,pipeline,concepts,triage}/`.

## Documentation tree

| Path | Contents |
|------|----------|
| `docs/architecture/` | Architecture draft v4 |
| `docs/contracts/` | Contract system, schema decisions, fixes, addenda, approval/PR notes |
| `docs/pipeline/` | Pipeline subsystem and iteration addenda |
| `docs/concepts/` | Concept step spec and art direction |
| `docs/triage/` | Triage and code step specs |

## Conventions

- Doc headers that mention `/workspace/...` are historical authoring paths, not paths in this repo.
- Technical content is unchanged from the sanitized docs pack; `[UNVERIFIED]` markers are kept where present (e.g. Meta model or rules claims until checked against official event materials).
- Contract tests use prefixes: `CT-` contracts · `CS-T` concept · `PL-` pipeline · `TR-` triage.

## License

Ember is released under the [MIT License](LICENSE).

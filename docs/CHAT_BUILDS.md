# Build from chat

Create a named Muse session and describe what you want to build. Muse can propose
a complete **browser prototype or game** with up to eight HTML, CSS and JavaScript
files, including `index.html`. Use flat lowercase names such as `style.css` and
`app.js`, linked with ordinary script `src` and stylesheet `href` references.
Inline code still works. Limits are 64 KiB per file and 256 KiB per project. Ordinary questions remain conversation turns. The
current implementation does not edit arbitrary repositories, run package
installations or commands, or build engine projects.

Prepared [Blender asset workshops](ASSET_PIPELINE.md) can additionally include
`engine.js` (up to 1 MiB) and canonical `asset.js` (up to 512 KiB). Ordinary source
keeps the limits above. The asset package includes validated GLB bytes and requires
individual owner acceptance when changed. It uses the same offline preview flow.

Known asset references and their recorded Blender/GLB/specification paths are
included in chat. Ask about an asset by name and use follow-ups such as “put it
in the scene”; the host selects the verified snapshot and prepares the same
normal review. Discussion does not accept an asset. The host retains `asset.js`
and `engine.js` during source-only revisions, without asking Muse to copy their
large payloads. See [asset-aware conversation](ASSET_PIPELINE.md#talk-about-an-existing-asset).

The latest 20 conversation messages, saved project brief and complete current
session project are supplied to Muse, together with the approved project plan and
selected task when configured. The brief preserves design guidance across
long conversations; it never grants action authority. See [the local workspace guide](LOCAL_UI.md#project-brief-and-preview-workspace). A
structured reply contains a message and either a concrete build proposal or
`null`. The host validates the proposed path, file count, size, HTML structure,
and all current source hashes. Duplicate names, missing or external script/style
references, and JavaScript modules are rejected. Model output cannot grant permissions or select
another directory. Asking for an unsupported target should produce an explanation
rather than an unrelated implementation.

Bulk edits use one build proposal with up to 64 exact, non-overlapping replacements
across the current project's files. Every replacement matches the original
source, so one edit cannot depend on another edit's output. The combined diff
receives one build review; untouched bytes remain intact. For bulk artwork,
ask for up to eight independent image requests; see [bulk artwork generation](ASSETS_2D.md#bulk-artwork-generation).

## Inline approval

Game UI follows the [integrated game-view process](GAME_UI.md): HUD and menus
belong inside the playfield's stage and use the game's own visual language.
Desktop/mobile review checks integration and style as separate required criteria.

New chat build proposals automatically run a read-only verification stage before
the reply finishes. Muse supplies bounded `gameplay_checks` for the actual
interaction and visible result. The host retains existing saved checks, runs
the exact candidate and current source in Chromium, and captures actual
desktop/mobile screenshots plus poses while movement input is held. A separate
Muse review receives the two game views plus open help/settings panels when
discoverable, otherwise movement poses, within its four-image allowance. All
captures remain available as evidence. Spark supports image input; the installed CLI's repeatable
`--image` option carries the PNG bytes. See [Meta's multimodal input documentation](https://dev.meta.ai/docs/quickstart).

**Game verification** shows gameplay outcomes separately from the AI visual
judgment, concrete issues, and the saved screenshots. The reviewer compares
the user request, brief and approved design with source, checks and pixels;
it must assess coverage as well as appearance. A positive model response cannot
override failed assertions, runtime errors, missing artwork, overflow or missing
evidence. No assertions, unavailable browser/model tooling or credit exhaustion
leave verification incomplete. Old saved proposals are not silently rechecked.

**Fix verification issues** sends the exact proposed source, original request,
retained results and actual screenshots into a revision, then checks that revision
again. It does not apply the candidate. This stage uses one additional bounded
Muse request (a $5 maximum reservation) within the existing shared promotional
ceiling; screenshots and reports stay under the ignored session directory.
Matching files, checks, reports and images are verified before evidence can be
reused. Changed bytes make the report stale. Human playtesting and exact approval
remain separate; screenshots do not establish animation smoothness or game feel.

Run the offline rehearsal with `py -3.12 tools/quality_check.py`. It exercises
real browser input, PNG capture and UI repair with synthetic model responses,
without live provider calls or credits.

The chat shows a compact proposal with its title, summary and changed files.
**Approve & play** records your click as approval of the exact file changes,
applies them, and opens the preview. **View code changes** and **Permissions and
checks** reveal the full diff, checks and contracts when needed. The diff covers each changed file; the reviewed manifest also binds
unchanged files. **Discard** records a decline and leaves the project untouched.
A prompt, model answer, or ordinary chat message saying "approved" never grants
authority by itself.

**Request changes** lets you describe a revision in the same card. **Send changes
to Muse** discards that exact proposal and requests its replacement in one action.
It never approves the old proposal or writes its files. If the reply fails, the
saved request can be retried from chat without another discard. The replacement
still requires its own **Approve & play** decision.

In a session with an approved [project plan](PROJECT_PLAN.md), approval uses the
existing owner-review host to approve one exact coding child of the persistent
root, retaining the plan version, task and inherited art direction. Legacy
sessions approve a per-build root scope and one child coding contract until they
adopt a plan. The exact coding contracts permit only the reviewed `fs.write` paths and
contents. Each changed file has a separate gated action and evidence check. Changed
inputs require a fresh proposal. The prior source is preserved as an immutable
input snapshot so new output evidence can verify without treating an intentional
revision as input corruption. The output hash, human receipts, gate decision,
and completion are recorded in the build audit.

Files are saved in the session's assigned **Project folder**, initially
`.harness/projects/SESSION_ID/`. New sessions can select a parent folder with the
native picker or an absolute path. The preference and each session's exact
destination survive restart and are supplied with project context to Muse.
**Save approved project as…** prepares a separately reviewed copy at a new location.
See [project locations](LOCAL_UI.md) for the flow and backup behavior.
Contracts, review packets, before snapshots and evidence remain under the
session's ignored `build-authority` folder.

Choose **Try proposed changes** to play the pending revision before approving it.
The card labels this **Proposal preview · not applied**. Your current game stays
in the adjacent workspace, so both versions can be tried independently. Hiding
and reopening the proposal preserves its game state while the card remains open.
This also works for first builds, restoration proposals and final polish proposals.

The preview reconstructs the exact reviewed project, including unchanged files,
and uses the same opaque-origin sandbox and blocked-network policy as saved builds.
It makes no Muse call, writes no project files, records no approval or playtest,
and adds no saved version. A changed project, decided proposal or damaged review
packet stops a new preview. An already open frame is a snapshot; approval still
rechecks the current project. Use **Request changes** for feedback or **Approve &
play** to apply the reviewed bytes.

With a saved gameplay plan, **Check proposed changes** compares the current and
proposed files before approval and shows preserved behavior, regressions and
fixes. **Ask Muse to fix proposed gameplay** sends a failed proposal back with its
complete source and checked observations, retaining the intended improvements
for a new review. See [proposal gameplay comparisons](GAMEPLAY_CHECKS.md#check-proposed-changes-before-approval).

## Preview and revision

After approval and completion, **Open prototype preview** renders the verified
`index.html` in an iframe with scripts allowed, an opaque origin, and a restrictive
content policy blocking network access and external resources. Previewing does
not expose the parent chat or its private API token to generated code. Reviewed
local scripts and styles are embedded as data URLs; no file server is exposed.
The preview opens the index page only. Modules, dynamic imports, local fetches,
CSS imports, multipage navigation and packages are outside this build target.

Describe the next revision in chat; Muse receives the complete project and is
instructed to improve it in place, preserving unrelated systems, controls,
visuals and file organization. Revisions prefer targeted source edits. Each edit
must match exactly once in the supplied source; overlapping, ambiguous or missing
matches stop the request. The host carries untouched code and files forward byte
for byte, reconstructs the complete candidate, and uses the existing validation,
preview, exact-diff approval, saved versions and export flow. New files can accompany
targeted edits. These checks preserve bytes outside edits; they do not prove that
the edited behavior is correct or that an edit is necessary.

First builds and requested or necessary rewrites can still return complete files.
Muse is instructed to explain necessary broader changes in the proposal summary;
this remains model guidance, not a semantic guarantee. File deletion is not supported.
Retries retain their original project snapshot and stop if the project changes.
Finish pending reviews and resume approved interrupted builds before another build.
Results shows the project and its files. **Verify current evidence** refreshes every file,
receipt, HTML and evidence checks. These static checks do not establish JavaScript
correctness or playability; inspect behavior in the preview.

## Saved versions and game downloads

Each completed approved build appears in **Saved versions**, including existing
single-file builds. The panel lists the latest 20 versions; their numbering stays
bound to the full completion history. **Preview version N** opens a read-only
preview of that saved version. **Download game ZIP** exports the latest completed
version; individual history rows can download an older version. These actions do
not call Muse or change project files, and do not publish or deploy anything.

Archives include the reviewed HTML/CSS/JavaScript files, a short README and
`ember-build.json` with source hashes. Extract the ZIP and open `index.html` in a
browser. Preview and export reconstruct source from approved review packets and
check the historical gate decisions, file evidence, and complete manifest.
Unchanged files are carried forward from earlier versions. Current unapproved
file edits are never substituted for saved approved bytes; damaged packets,
evidence or audit records stop export. This historical check does not attest to
current workspace bytes or automatically establish correct gameplay.

Exports exclude conversation history, credentials, launch tokens, private host
paths, approval packets and audit logs. The private authenticated local API is
required for preview and download. Old versions do not overwrite the current
project. **Review restore of version N** prepares an exact diff against the current
project, using verified historical approved files. Review it, then choose
**Approve restore & play** to apply it as a new version. **Discard** leaves the
current project unchanged. Restoration does not call Muse or consume credits.

Restores preserve every completed version, approval and report. They reuse the
same gated writes and interruption recovery as other builds. A pending proposal,
unfinished approved build, active Muse request, changed project or stale selected
session stops a new restore. If restoring would require deleting files introduced
in a later version, it is refused with the file names; preview or download the
older version instead. File deletion remains outside the approved write target.

## Browser smoke checks

For game-specific scoring, restart and touch expectations, use
[saved gameplay checks](GAMEPLAY_CHECKS.md). These run through the host's fixed
Chromium actions and also constrain future overnight polish candidates.

Choose **Run browser smoke check** for a fresh, isolated preview of the current
approved build. The fixed `startup-inputs-v1` plan waits for document load and an
animation frame, clicks the first enabled button if present, sends arrow-key and
space keydown/keyup events, and observes a short settling window. These are
synthetic events; games requiring trusted input or other controls need a human
playtest. The player's existing preview and notes stay in place.

The report records each completed step and up to five browser errors, rejected
promises, blocked-resource policy events or runner errors. It shows **issues
observed**, **incomplete**, or **no errors observed**. A missing completion message
times out after eight seconds and cannot produce a clean result. Reports bind to
the exact completed build and manifest; stale builds, changed files and switched
sessions cannot receive a new report. Saving is idempotent, and reports persist
across restarts in the build audit.

Browser messages are untrusted observations, even when all steps complete. They
cannot approve changes, establish correct gameplay, or close bugs. **Ask Muse to
fix browser issues** explicitly sends the current report for investigation and a
normal reviewed proposal. Running and saving checks does not call Muse. Reports
for older builds remain in history but are not supplied as current observations.

For repeatable application QA, run `py -3.12 tools/browser_check.py` with Node and
Playwright available. Optional flags are `--node`, `--playwright-module` (an
installed module directory), and `--browser-executable` (a Chromium executable).
On Windows, the [setup helper](INSTALL.md#optional-browser-checks) installs these
tools with `& ".\Setup Ember.cmd" --browser`. For a manual developer installation
under the ignored workspace:

```powershell
npm install --prefix .harness/browser-tools playwright
.harness/browser-tools/node_modules/.bin/playwright.cmd install chromium
py -3.12 tools/browser_check.py --playwright-module .harness/browser-tools/node_modules/playwright
```

This separate browser gate exercises an original synthetic fixture: startup
failure → report → reviewed fix → clean check → reviewed restoration → clean
check. It also checks real button/keyboard input, preservation of preview state,
message isolation, all four saved versions, responsive layout and ZIP download.
It uses deterministic model fixtures and synthetic decisions, never live Muse
calls or genuine owner approvals. Logs, screenshots, source hashes and the
export stay under `.harness/browser-checks/`. Playwright is optional developer
tooling; the app and offline Python gate need no new runtime dependency.

## Playtest and request a fix

Open the prototype preview and try its controls and gameplay. **Works as expected**
records your observation. To report a bug, enter what you tried, what happened,
and what you expected, then choose **Send feedback & fix**. The host saves the report
against the exact approved build and file manifest. Reports survive restarts;
stale previews or changed project bytes cannot create a report for a newer build.

The preview collects up to five browser errors or unhandled promise rejections.
These are untrusted diagnostic clues: generated code can influence them, and an
absence of errors does not establish correct gameplay. The host accepts messages
only from the current preview frame and its current channel. Observations cannot
approve changes, close bugs, or execute actions.

**Send feedback & fix** saves the report and explicitly sends a chat request
to Muse in one action. **Works as expected** only saves your observation and does
not call Muse. Previously saved problems still offer **Ask Muse to fix this**
for retry or follow-up.
Muse receives reports for the current build and proposes a normal reviewed diff.
Approve the fix, reopen the preview and test it again. Old reports remain in the
audit but are not supplied as observations of a later build. This is human
playtesting with browser diagnostics, rather than automated gameplay testing.

## Restart and interrupted application

Pending proposals and decisions survive an app restart. If approval was recorded
but application did not finish, **Resume approved build** reconciles the saved
gate decisions and file hashes. Writes are atomic per file, rather than across
the project. Recovery checks every file before continuing; preview is blocked
until completion. A file already written with the exact approved
bytes is verified without another write or gate call. An unchanged original file
can still be written under its existing valid authority. Unexpected bytes, an
expired approval, a damaged packet or an interrupted audit write stop recovery
for inspection. Completed older proposals cannot overwrite later revisions.

The original Ember Courier sample remains available through **Start sample
workflow**; it is a separate demonstration from builds requested through chat.
Both review types appear in the same inbox, with separate audit streams in
Activity & audit. Muse calls use the existing shared credit ledger.

`tests/test_chat_build.py` covers proposal-only behavior, explicit approval,
decline, source changes, disallowed paths, revisions, restarted sessions, and an
interruption immediately after atomic file replacement. Multi-file coverage checks
partial-write recovery, dependency tampering and unchanged-file preservation. Test responses are
explicit synthetic fixtures, never actual owner approvals.

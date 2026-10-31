# Build from chat

Create a named Muse session and describe what you want to build. Muse can propose
a complete **browser prototype or game** with up to eight HTML, CSS and JavaScript
files, including `index.html`. Use flat lowercase names such as `style.css` and
`app.js`, linked with ordinary script `src` and stylesheet `href` references.
Inline code still works. Limits are 64 KiB per file and 256 KiB per project. Ordinary questions remain conversation turns. The
current implementation does not edit arbitrary repositories, run package
installations or commands, or build engine projects.

The latest 20 conversation messages, saved project brief and complete current
session project are supplied to Muse. The brief preserves design guidance across
long conversations; it never grants action authority. See [the local workspace guide](LOCAL_UI.md#project-brief-and-preview-workspace). A
structured reply contains a message and either a concrete build proposal or
`null`. The host validates the proposed path, file count, size, HTML structure,
and all current source hashes. Duplicate names, missing or external script/style
references, and JavaScript modules are rejected. Model output cannot grant permissions or select
another directory. Asking for an unsupported target should produce an explanation
rather than an unrelated implementation.

## Inline approval

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

Approval uses the existing owner-review host to approve an exact root scope and
one child coding contract. Each permits only the reviewed `fs.write` paths and
contents. Each changed file has a separate gated action and evidence check. Changed
inputs require a fresh proposal. The prior source is preserved as an immutable
input snapshot so new output evidence can verify without treating an intentional
revision as input corruption. The output hash, human receipts, gate decision,
and completion are recorded in the build audit.

Files are saved under `.harness/projects/SESSION_ID/`. Contracts,
review packets, before snapshots and evidence are saved under the session's
`build-authority` folder. These are ignored local artifacts. No changes are
written into the Ember source checkout.

## Preview and revision

After approval and completion, **Open prototype preview** renders the verified
`index.html` in an iframe with scripts allowed, an opaque origin, and a restrictive
content policy blocking network access and external resources. Previewing does
not expose the parent chat or its private API token to generated code. Reviewed
local scripts and styles are embedded as data URLs; no file server is exposed.
The preview opens the index page only. Modules, dynamic imports, local fetches,
CSS imports, multipage navigation and packages are outside this build target.

Describe the next revision in chat; Muse receives the complete project and proposes
another exact diff. Proposals include unchanged files; deletion is not supported.
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
For example, install developer tooling under the ignored workspace:

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

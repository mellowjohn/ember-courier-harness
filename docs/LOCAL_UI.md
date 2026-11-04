# Local workflow app

On Windows, double-click `Start Ember.cmd` in the repository folder. Leave its
window open while using Ember. The first launch runs setup if needed and opens
the private link in your default browser; you can also open the printed link
manually. Each launch
chooses an available port and a fresh private link; use the new link after a
restart. Closing the launcher stops the server, while saved sessions remain on
disk. This launcher runs directly on your desktop rather than in a temporary
agent command session.

The launcher prefers `.venv\Scripts\python.exe` in the repository, then the
activated `%VIRTUAL_ENV%`, then `py -3.12`. If the selected environment is missing
Python 3.12+ or required modules, it runs **Setup Ember.cmd** to prepare a private
`.venv` before launching. See [installation and troubleshooting](INSTALL.md).
Launch failures retain
their exit code and print a setup reminder before the window pauses. Command-line
arguments, such as `--port 8765`, are passed to the existing local host. Automated
rehearsals may set `EMBER_NO_PAUSE=1`; ordinary double-click launches still pause
after the app stops.

From the repository folder, run:

```powershell
.\.venv\Scripts\python.exe -m ember_harness.local_ui --open-browser
```

Open the private loopback link printed by the launcher in a browser or the Codex
browser panel. Keep the launcher running. After installation, `.\.venv\Scripts\ember-ui.exe --root
"D:\Ember Harness\ember-courier-harness"` provides the same launcher. The source
checkout is required because the app reuses the existing product example.

Choose **New session** and enter a name. Ember uses **Muse only**; it does not
auto-detect or start Ollama or another local model. The main view is a chat: type
a prompt and send it to Muse Spark 1.3. New sessions start as conversations;
**Start sample workflow** explicitly starts the bounded product workflow. Review
packets appear inline in the chat. Model text cannot approve a contract or execute
an action. The workspace keeps one conversation on the left and **Play & refine**
on the right. Plan your game and request improvements in chat; exact approvals
stay in the conversation. **Try proposed changes** opens a clearly marked preview
on the right, above the current approved game. **Return to approved game** brings
you back without resetting either preview.

After **Approve & play**, the game panel shows **Applying your changes…** and
then **Opening your updated game…**. It prevents interaction with the old game
until the updated preview loads. An application or preview error clears the
loading screen and displays the error so you can retry.

The game opens automatically after approval. **Restart game** starts it over;
**Fullscreen** enlarges the current play session. **Open in new window** opens the
approved version in a fresh, isolated game window (or browser tab, depending on
your browser settings). It starts a separate play session and stays on that
version until you open a newer one from Ember. Return to the chat to request
changes. Playtest notes and feedback sit below the game; saved gameplay checks,
findings and overnight polish are under **Checks & advanced refinement**.

Press **Enter** to send a message or **Shift+Enter** to add a new line.

**Project tools** opens a side panel containing **Plan & project**, **Known assets**,
**Versions & downloads**, **Activity & audit**, and **Typography & icons**.
The live [typography and iconography library](UI_LIBRARY.md) provides the shared
type scale, original line icons and friendly messages for observed work stages.
It holds the design, tasks, brief, folder
setup, saved versions, handoff and detailed evidence. Close it with **Back to
game** or Escape. Opening these tools preserves game state and unsaved check
edits. On smaller screens, the conversation and preview stack vertically; use
**Go to game** to jump to the preview.

In **New session**, use **Save projects in** to enter an existing folder or
**Choose folder…** to open the native folder picker. Ember creates a dedicated
subfolder for the project and remembers the parent for future sessions, including
after restart. At the top of **Project tools**, **Project folder** shows the
selected session’s name and exact project destination, above the expandable
sections. It updates when you switch sessions; chat also receives the destination.
The folder is created when a reviewed build is applied.
If the native picker is unavailable, entering the absolute path works.

For an existing build, choose **Project tools → Project folder → Save approved project
as…**. Pick a name and parent folder to create a separate saved session with the
latest approved game, project brief and gameplay plan. Review and approve the
copy to write its files. This local operation makes no model call. The original
project and its history remain available. Unapproved proposals and manual file
edits are not part of the approved copy. Native Blender sources stay at their
recorded locations; this copies the browser project, not its source art directory.

Existing sessions retain their assigned locations. A location is fixed for that
session because contracts name exact file paths; use **Save approved project as…**
for another location. Conversations, versions and evidence stay under
`.harness/ui/sessions/`, even when project files live elsewhere. Back up the
session history and selected project folders together to retain the full workspace.

**Existing workspace · scan & setup** adds a reviewed read-only inventory of a
selected folder, passive Git metadata, asset filename hints, a setup diff and a
separately approved create-only copy. Supported flat browser sources have their
own full import review and then the normal scoped exact-build review before
becoming the current game. Original source files stay unchanged. See
[workspace onboarding](WORKSPACE.md) for limits, exclusions and recovery, and
[Git browser repairs](GIT_TASKS.md) for clean named baseline/head verification
inside fresh private repositories.

**Review automated Git repair** in Plan uses the selected task and saved failing
checks. Approve its coding worker and independent reviewer first, then review
the generated exact Git permissions separately. A passing clean head still
needs the normal exact game approval. **Review Git repair agent** offers the
same sequence for a canonical finding, followed by separate verified closure.
Source and Git stages share one existing task/finding attempt. See
[Git browser repairs](GIT_TASKS.md) for cancellation, recovery and limits.

**Project plan & tasks** lets you adopt a persistent approved game scope and
ordered task list. Exact builds then reuse that root and inherit its art
direction; task outcomes need their own version-bound human acceptance. See
[project planning](PROJECT_PLAN.md) for amendments, expiry, recovery and the
explicit legacy-session compatibility boundary.

The active card's **Run task with Muse** prepares a separate worker/verifier
permission review. It requires saved gameplay expectations and browser tooling.
See [bounded task execution](TASK_RUNS.md) for retries, recovery, independent
evidence and the final exact review.

**Gameplay recipes** in Plan prepares the original Lantern Trail platformer and
reviewed movement/jump settings. Camera, impact protection, enemy states and
seeded layouts use the expanded Lantern Vale profile: include that expansion
in the approved scope, then review its full source upgrade before tuning.
Fixed-step observations complement keyboard/touch checks; human comfort, feel
and task acceptance remain separate. See [mechanic recipes](MECHANICS.md).

**Create chest/gate directions** adds the selected-task [asset-production loop](ASSET_PRODUCTION.md):
three real rendered studies, explicit human pick, bounded Blender source edits,
independent checks, retained native versions and separate exact asset acceptance.

**Findings & fixes** turns a recorded problem into a reviewed, build-bound bug.
Supply reproducible details, select a saved regression scenario, review a scoped
fix and its independent evidence, then apply the exact proposal and separately
approve closure. See [findings and verified fixes](FINDINGS.md) for classification,
three-attempt escalation, critical closure and recurrence.

Muse Code must be installed and signed in. The Windows installation is detected
from its version marker. Each chat request runs one model step using the empty
preset, with shell, writes, web tools, reminders and user-input tools disabled.
No workspace or personal-context attachment is requested. Standard mode is
explicit; contributor mode is off for the call. Conversation context is supplied
from the saved session. Chat can propose concrete browser builds with up to eight HTML/CSS/JavaScript files, with an exact diff and
inline approval before any file write. See [Build from chat](CHAT_BUILDS.md) for
the supported target, preview, revisions and recovery.

Open **Muse settings** from Home or any session to choose how Ember connects.
The default uses your own signed-in Muse Code subscription and requires available
allowance before each new model call. If you have your own Model API promotional
credits, choose that connection and confirm that a payment method cannot be
charged. See [models and credits](MODELS_AND_CREDITS.md).

Each prompt is saved before inference. Completed replies and the provider choice
survive app restarts and reboots. A pending reply is never automatically resent;
use **Retry reply** explicitly after an interrupted request. Repeated completed
message IDs return the saved reply without another model call.

The chat shows an activity panel immediately after sending. Saved checkpoints
show context preparation, Muse startup, observed provider start, response
streaming, reply validation and proposal preparation. The panel shows elapsed
time, the actual current step with a plain-language explanation, and the five
latest timestamped steps without expanding anything. Game verification distinguishes
testing the current game, trying the proposed version on desktop and mobile,
Muse reviewing actual captured screenshots, and the saved review result (including
issues or an incomplete review). During a quiet period the message describes the
step that is still running; it does not invent completion percentages or infer
success from advancing to another step. **Request activity · full history** expands
all recorded steps, their explanations and received response character counts.
The history is also available under **Activity & audit**.

Progress survives a refresh or reopening the same session. A pending request is
shown as running only while its OS-held chat lock is active; an abandoned request
is marked interrupted and offers an explicit retry. Active requests do not show a
retry button. Provider output is reduced to observed event types and counts for
this display; prompts and raw provider event text are not echoed into the activity
panel. Builds still wait for your exact approval before changing project files.

The app runs the bounded integrated Ember Courier sample described in
[PRODUCT_DEMO.md](PRODUCT_DEMO.md). It is not yet a general project editor or
arbitrary workflow designer. Default fixes and concept images are deterministic
fixtures; intake is a fixture and the verifier is deterministic. The local app keeps the sample fix deterministic in Muse-only mode. The separate
local-agent example adapter remains available for offline regression coverage;
the app does not launch it, including for older saved sessions.

**Project tools → Activity & audit** shows execution output and the latest 100
audit entries. **Versions & downloads** shows the current game and [project handoff download](PROJECT_HANDOFF.md), plus saved
versions. **Inspect verification evidence → Verify current evidence** refreshes the manifest and
current file checks rather than relying on the saved PASS. Run logs remain in
`.harness/ui/sessions/`; projects, review receipts and evidence remain in the normal
`.harness/demos/` folders.

Sessions save their name, model choice, timestamps, conversation, worker status
and logs under `.harness/ui/sessions/`. Conversations save automatically. **Rename session** opens the name field;
**Save changes** updates the name and timestamp. The sidebar highlights the selected session and
shows its status. Selecting another session leaves its worker running.

Workflows started in this version keep a versioned JSON step journal, saved with
atomic replacement and a disk flush. Completed steps are restored, so recovery
skips prior asset ingests, attempts, approvals, tests and commits. Each pending
review reopens the same hash-bound packet. An OS-held worker lock is released by
process death and reboot; concurrent resume requests cannot launch two workers.
After a reboot or stopped worker, select the session and choose **Resume workflow**.
The journal validates its source version, workspace file hashes, audit prefix,
contract bytes and owner receipts before continuing. Chat history remains
accessible independently of workflow recovery.

Recovery is conservative at a partial side effect: a stop during an unfinished
write, ingest, test execution, commit or audit write requires inspection, rather
than repeating work whose outcome is uncertain. Modified inputs, damaged journals
or changed workflow code also stop recovery. Completed checkpoints can resume,
including immediately after a recorded commit. Expired or revoked authority is
not extended by recovery. Declined and completed workflows cannot be restarted
through Resume. Sessions created before this version retain their history but
have no execution checkpoint to recover after their worker dies.


The server binds only to `127.0.0.1` on an automatically selected port. The
private launch link supplies a session token, kept in browser session storage;
API requests require that token and enforce the loopback Host and same-origin
policy. Keep the link private. This is a local trusted human host, not multiuser
authentication. Review data is rendered as text. Images are limited to PNGs from
the current workflow's reviewed paths; no arbitrary file browser is exposed.

Audit writers wait up to two seconds to acquire their store lock when a live
worker is briefly busy. This applies to both owner decisions and worker writes;
operations execute only after acquiring the lock. Persistent locks remain in
place and fail closed. The host never deletes another writer's lock, replays an
action to force it through, or retries unrelated file errors.

Run `py -3.12 tools/offline_tests.py --pattern test_local_ui.py` for the HTTP
boundary and seven-checkpoint integration test. Recovery checks are in
`tests/test_session_recovery.py`; conversation durability checks are in
`tests/test_session_chat.py`. All decisions in that test are
explicit synthetic test responses, not owner approvals.

## Project brief and preview workspace

Plan in chat: describe the idea and Ember drafts an initial plan in its reply,
using known answers and clearly labeled suggested defaults. Ask questions or
request changes to refine the draft. Ember asks for a brief idea if none is
available; it does not require a design questionnaire before proposing a plan.
The welcome suggestions and **Plan together in chat** start this draft-first flow.
It returns partial brief
updates for explicit user decisions; the host validates and saves them without
a separate form or Save gesture. A **Remembered** receipt appears on the reply.
The read-only **Project brief** in Plan shows the game goal, controls, visual
direction and constraints, with up to 2000 characters each. **Continue planning
in chat** returns to the conversation. Missing answers do not force a setup wizard.

Answers persist per session across restarts and are included independently of
the latest 20 conversation messages in every new Muse request. Each request keeps
its original brief snapshot on retry; a retry cannot overwrite newer answers.
Interrupted saves use a turn marker to avoid duplicate revisions. Chat drafts
stay with their session while switching within this browser page. The retained
local brief API supports existing integrations with revision and lock checks.
Brief updates remain guidance; they cannot approve builds or amend approved scope.
Discuss plan changes in chat to revise the draft. Ask to prepare the plan for
approval, or to implement it, to open the existing inline project-plan review.
Approving that plan keeps chat open and starts preparing its selected task.
The progress card shows **Plan approved**, one shortened task title, stage and
file activity, with **Building** in the header. Expand **Activity & details** for
the full task and history. Finished builds still need exact review.

On wide screens chat and **Play & refine** appear side by side. Smaller screens
stack the preview below chat. The latest completed build opens automatically after
its source is verified; its version is labeled above the game. Opening previews
does not call Muse. Game state and playtest notes remain in place during normal
polling and when a playtest observation is saved. Opening a different session,
completing a new build, or explicitly reopening the preview starts a fresh game.
The existing preview isolation, version downloads and exact build approvals apply.

**Run browser smoke check** records bounded startup and synthetic-input diagnostics
without resetting the current game. **Saved versions → Review restore of version
N** prepares a new approval before restoring historical files. See
[browser checks and restoration](CHAT_BUILDS.md#browser-smoke-checks) for behavior,
limits and the repeatable Chromium rehearsal.

Under **Checks & advanced refinement**, **Overnight polish** adds upfront-approved autonomous iterations in an
isolated copy, real browser screenshots, an AI critique loop and a morning review.
The current game changes only after a separate exact-diff approval. See
[overnight polish](OVERNIGHT_POLISH.md) for setup, budgets, stopping and recovery.

Local source checkpoint before this polish pass: `235f31b`. Generated projects,
private sessions, approvals and release logs remain under ignored `.harness/`;
the Git checkpoint contains application source and documentation.

## Review task quality

Task cards show the requested outcome, the independent AI assessment and the
completed attempt count. A blocked result separates failed gameplay, visual
concerns, missing observations and unsupported evidence, then names the first
change to discuss. Exhausted allowances remain visible; another attempt still
requires the existing owner decision and credit limits. Passing checks leave
human playtesting pending and do not accept the task.

Open **Play and inspect retained attempts** to play a verified candidate without
applying it. **View task screenshots** shows the starting and proposed game with
matching desktop/mobile evidence when the run has a playable baseline. Changed
or unavailable evidence produces an error instead of displaying unchecked files.
Older runs and first builds identify their available comparison boundary.

Before starting, **Interaction coverage** lists missing paths and suggestions
against the selected task. **Review saved gameplay checks** opens the existing
editor. Mark a scenario's intended success, failure, restart or repeated-play
path, then supply its actual input actions and expectations. Labels describe
intent; they do not prove coverage. Saving changes applies to future reviews;
an already reviewed task keeps its frozen plan. Game-reported values and DOM
checks remain bounded observations, separate from independent measurements and
your judgment of feel.

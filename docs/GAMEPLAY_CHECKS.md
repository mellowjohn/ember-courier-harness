# Saved gameplay checks

Open a saved game and choose **Playtest → Edit gameplay checks**. Give
the plan a name, add desktop or mobile scenarios, then add the actions and
expectations that describe behavior you want to preserve. **Save gameplay plan**
keeps it with this session. **Use saved plan** reloads the saved version if your
draft conflicts with an edit in another window. Unsaved drafts survive session
switches in the current browser window; saved plans survive app restarts.

Each scenario starts a fresh isolated game. Useful sequences include clicking
Start, pressing a movement key, checking the score, waiting for a loss screen,
and clicking Restart. Mobile scenarios use a real Chromium touch tap. Choose
elements by tag (`button`, `canvas`), ID (`#start`, `#score`), or test target
(`[data-testid="restart"]`). Targets must be unambiguous. Arbitrary selectors,
JavaScript, shell commands, network requests and model instructions are not
supported test steps.

Available steps:

| Step | Observation |
|---|---|
| Click / Touch tap | Activate one visible target; touch needs a mobile scenario. |
| Press key | Arrow keys, Space, Enter, Escape, A/D/W/S or R. |
| Wait | Pause for 1–2000 milliseconds. |
| Visible | The target becomes visible. |
| Hidden or absent | The target is hidden or absent. |
| Text equals / Text contains | Check the visible target's trimmed text. |
| Number at least | Check a visible, number-only score against a minimum. |
| Sprite state and drawn frames | Check that the named sprite draws the expected state or clip. Require two distinct frames to check playback. |

Every scenario needs an expectation. Plans allow at most four scenarios and
32 steps per scenario. The whole plan has a 90-second action budget:
most actions and assertions count as one second, plus explicit waits. A
two-frame sprite check counts as two seconds. Assertions poll for up to
800 milliseconds, or 1800 milliseconds for two drawn frames. Place sprite
checks immediately after the input or trigger to observe jump, impact, landing
and restart during gameplay. After a failed step, the remaining steps in that
scenario are skipped; other scenarios still run. Duplicate, missing or hidden
targets fail actions and text checks. **Hidden or absent** deliberately accepts
a missing target.

## Player visibility at launch

For games with a packaged startup player sprite, Ember opens the exact proposal
in Chromium on desktop and mobile. It activates the Start button when present,
then checks that the bound sprite paints visible pixels inside the playfield.
An off-screen spawn, a transparent draw, or a sprite that is immediately erased
fails this check even when the animation reports successful draw calls.
**Approve & play** requires passing evidence for both viewports. This check uses
no Muse credits and is separate from saved gameplay scenarios.

## Review interaction coverage

In the scenario editor, optionally label the purpose of a check: discovering how
to start, success, failure, restart, or repeated play. These labels are declarations
by the plan author. They do not establish that the steps test that behavior;
scenario names and selector names are never treated as coverage evidence.
For repeated play, include the restart and second interaction in the same
scenario, because each scenario starts a fresh game.

The task review maps the selected task to these declared scenarios and shows
paths that have no declared check. Keyboard and touch paths are listed separately
only when their corresponding input action has a later observable expectation;
this still does not prove that the input caused the reported state. Review which
paths apply to the selected task and improve checks using this same editor.
Suggestions stay within the four-scenario, 32-step and action-budget
limits. Saving changed coverage labels changes the plan hash, just like editing
its steps; previously frozen runs keep their reviewed plan.

Missing coverage is a review prompt, not an added feature requirement or an
automatic failure. Every configured scenario remains required by task workers,
including failing restart, second-playthrough and mobile paths. A passing first
playthrough cannot override any of those failures. DOM observations influenced
by game code do not independently verify physics, scoring, accessibility or fun;
unsupported measurements and human experience remain unobserved.

## Run and understand the report

Choose **Run gameplay checks** with a saved plan and a completed approved game.
Ember uses its existing optional Node/Playwright/Chromium tooling; see
[browser setup](CHAT_BUILDS.md#browser-smoke-checks). This host inspection runs
fixed browser actions, makes no Muse call, consumes no promotional credits, and
does not approve or change the game. Each scenario gets its own browser context
with an opaque-origin frame and blocked network access. It does not disturb the
game you are playing in the workspace.

The report records each step, observed text, browser errors, skipped steps, the
game version, complete file manifest and saved-plan hash/revision. A failed
expectation or browser error fails its scenario. A stopped runner, missing
result or changed game/plan cannot produce a new passing report. Completed
reports persist in the build audit; captures and logs remain in the session's
ignored `gameplay-runs/` directory. Repeating the same report ID is idempotent.

The current summary only uses reports matching both the latest completed build
and the current saved plan. Previous reports remain in **Saved gameplay reports**.
A new build or edited plan needs a fresh run. A game or plan changed during
inspection makes that result stale; its captures remain available for inspection.

These are finite observations, not proof of all game rules or human acceptance.
Generated code can influence DOM and error text. A canvas-only score or player
position is not asserted: expose important state in visible accessible elements
in a separately reviewed build. Muse receives the saved plan and current reports
as data when you explicitly request a reply, with a frozen snapshot for retries.
There is no automatic model call or fix when a check fails.

## Check proposed changes before approval

Every pending build review now has **Test before approval**. With a saved plan,
choose **Check proposed changes** to run the same frozen scenarios against fresh,
isolated copies of both the current files and the complete proposed project.
This also works for restores and final polish proposals. It does not write game
files, change approvals, add a completed version, or call Muse. The existing
workspace preview keeps its game state while the comparison runs.

The scenario table distinguishes **Preserved**, **Regressed**, **Fixed** and
**Still failing**. A first build has no current game to compare; it is labeled
**First build** and only the proposed project is tested. No baseline pass is
invented. Expand **Gameplay steps and observations** for the actual expectations,
observed text, browser errors and skipped steps on each side.

Reports bind to the exact pending review reference, complete before/proposed
manifests, saved-plan hash/revision, runner inputs and capture hashes. Changed
files, a changed plan, a decided proposal or damaged captures cannot receive a
new current result. Previous comparisons become stale and cannot supply a fix
request until a fresh valid comparison exists. Captures and reports remain under
the session's ignored `proposal-checks/` directory and in its build audit.

For a failing proposal, **Ask Muse to fix proposed gameplay** explicitly discards
that exact proposal and requests a replacement. Muse receives the complete
unapplied proposal, frozen plan and before/after observations, so it can preserve
the intended improvements while repairing the failure. This is a normal bounded
Muse request using the existing credit ledger. It never approves the proposal.
A saved request can be retried after interruption with the same source, report
context and stable prompt serialization. Run a fresh comparison on the replacement;
applying it still requires your own exact-diff approval.

These comparisons inform your review; they do not automatically apply changes or
remove your ability to approve a proposal after inspecting its results. Overnight
automatic recommendations continue to require the frozen gameplay checks to
pass. With no saved plan, the review offers **Set up gameplay checks** instead
of claiming the proposal passed.

## Overnight polish

Preparing an overnight scope freezes the saved gameplay plan in both reviewed
contracts. Changing the session plan later does not change that run. The host
code and runner are also bound to the approval. The same frozen scenarios run
against the original and every candidate, independently of the screenshot smoke
inputs. A candidate that fails a required scenario cannot become the automatic
recommendation, even with a higher AI visual rating and no startup errors.
Missing, altered or incomplete results stop the worker for inspection.

The morning report separates gameplay assertions from AI assessments and shows
the frozen plan, step observations and failures. With an empty plan it explicitly
says no gameplay plan was configured. A failed original can remain the fallback
when no candidate passes; it is not labeled a passing result. Final application
still requires the existing exact-diff approval.

Run `py -3.12 tools/browser_check.py` with the tooling flags from
[browser setup](CHAT_BUILDS.md#browser-smoke-checks) for the proposal comparison
rehearsal: a healthy current game, an unapplied scoring regression, explicit
repair preserving the proposal's visual changes, a passing replacement, and a
checked restoration. It also checks that the player's preview keeps its state
and the comparison table fits mobile screens. Deterministic model replies and
synthetic owner decisions are separate from the real Chromium observations.

Run `py -3.12 tools/polish_check.py` for the extended real-Chromium rehearsal. It
edits and saves desktop/touch checks through the UI, tests scoring, retains them
across a reload, and rejects a higher-rated candidate with a broken keyboard
scoring path despite clean startup, then checks the final proposal before exact
approval. Owner decisions and model replies are
synthetic; browser input and assertions are real. Evidence stays under ignored
`.harness/polish-checks/`. Unit tests separately cover validation, stale reports,
session binding, frozen scopes and missing/tampered results.

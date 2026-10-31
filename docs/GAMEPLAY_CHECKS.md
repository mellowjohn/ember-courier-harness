# Saved gameplay checks

Open a saved game and expand **Gameplay checks** below its project brief. Give
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

Every scenario needs an expectation. Plans allow at most four scenarios and
sixteen steps per scenario. The whole plan has a twenty-second action budget:
each action/assertion counts as one second, plus explicit waits. Assertions poll
for up to 800 milliseconds. After a failed step, the remaining steps in that
scenario are skipped; other scenarios still run. Duplicate, missing or hidden
targets fail actions and text checks. **Hidden or absent** deliberately accepts
a missing target.

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

Run `py -3.12 tools/polish_check.py` for the extended real-Chromium rehearsal. It
edits and saves desktop/touch checks through the UI, tests scoring, retains them
across a reload, and rejects a higher-rated candidate with a broken keyboard
scoring path despite clean startup. Owner decisions and model replies are
synthetic; browser input and assertions are real. Evidence stays under ignored
`.harness/polish-checks/`. Unit tests separately cover validation, stale reports,
session binding, frozen scopes and missing/tampered results.

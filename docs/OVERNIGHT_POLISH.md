# Overnight polish

Open a saved session with an approved browser game, then choose the **Overnight
polish** tab. Give Ember a concrete direction: what should feel better, what it
must preserve, and the details you care about. The saved project brief is included
as design guidance. Changes to the brief after preparation do not change this run.

1. Set the maximum rounds, hours and promotional-credit cap. Defaults are two
   rounds, eight hours and $25 of free credits, with at most five Muse calls.
2. Choose **Review overnight scope**. Review the goal, frozen starting game,
   variable-content write permissions, limits, and both contracts. This creates
   drafts and makes no Muse call.
3. Choose **Approve scope & start polish**. This records your approval of the
   exact scope and worker contracts and starts a separate local worker. Keep the
   computer awake. The browser and Ember launcher may close while it works.
4. Return to **Overnight polish · Ready** for the strongest completed candidate,
   before/after screenshots, playable candidates, AI assessment and remaining
   issues. You can retain the original if no candidate qualifies.
5. **Review exact changes** prepares an ordinary build proposal. Only your later
   **Approve & play** applies those exact bytes to the current game and adds a
   saved version. The existing ZIP export is then available. Discarding that final
   proposal leaves the game unchanged. **Try proposed changes** in the final
   review plays the exact proposed result alongside the current game before
   approval, without a Muse call or another saved version.

## What the worker does

The original game is reconstructed from its approved version and frozen in the
run's input snapshot. The host captures actual Chromium desktop and mobile
screenshots before and after button/keyboard input. Muse receives screenshots,
source, browser observations, the goal and brief for a critique. Each round
generates a complete candidate from the current best, checks its source, runs the
same browser inspection and requests a new screenshot-based critique. Candidate
comparisons attach both candidate and current-best screenshots.

The original and every completed candidate remain available. A candidate with
browser errors or horizontal overflow cannot become the recommendation. The
[saved gameplay checks](GAMEPLAY_CHECKS.md), frozen into the scope at preparation,
must also pass. Failed gameplay assertions block recommendation even when the
browser reports no startup errors. Empty plans are labeled unconfigured. The AI
must also judge the core preserved; a clean candidate must receive a stronger
assessment and explicit preference to replace an already clean best version.
An equal or weaker latest attempt does not replace an earlier stronger candidate.
These are conservative selection rules, not an objective guarantee of quality.

The UI separates real browser observations from AI ratings. Input dispatch and
screenshots cannot establish correct scoring, a full game loop, accessibility,
fun, or human acceptance. Play the result before approving it. Source, browser
text and prior AI output are treated as untrusted data, never permissions.

## Authority and limits

Johnathan approves one scope and one worker contract upfront. They authorize
bounded variable contents only under this run's `candidates/`, `calls/` and
`captures/` directories. Every candidate/context write, model step and browser
inspection goes through the existing gate and records file-hash evidence. The
worker never creates or approves additional contracts or amendments. Its approval
mode remains `each`; the approved write/compute classes do not require a separate
decision for every iteration. Asset acceptance, bug closure, arbitrary shell
commands, deletion, Git operations, publishing and engine work are not granted.
Generated game code runs inside an opaque frame with blocked network access.

Run settings, source snapshot, host workflow code, art direction and runtime identities are bound to
the reviewed packet. Existing project file names are preserved; new files and
deletions are outside the polish target. Current game files are never writable
under the polish contracts. A change to the current game during a run is allowed,
but blocks promotion from that frozen starting version. Start a new pass from the
updated game to prepare a matching final review.

The time window is fixed when the scope is prepared. An expired scope must be
discarded and prepared again. Rounds are 1–6, hours 1–12 and the run credit cap is
$5–$50. Work finishes as soon as its rounds are complete; it does not spend the
whole time allowance unnecessarily. There is one open run per session.

The run cap is enforced atomically in the existing shared ledger, including
concurrent sessions, restarts and uncertain calls. Each call needs a full $5
reservation under both the run cap and the shared $150 promotional ceiling.
Reported usage settles at the existing pinned rates; missing usage stays held.
There is no cash fallback, automatic top-up or automatic provider retry. A small
remaining balance may be insufficient for the next reservation. See
[models and credits](MODELS_AND_CREDITS.md).

**Stop polish run** stops at the next cancellation check and retains completed
candidates. A model call interrupted by cancellation may retain its reservation.
Closing the UI is not cancellation. After an interrupted worker, **Resume polish
run** reuses verified checkpoints and saved model replies. Screenshot bytes,
prompt, schema and budget are bound to cached replies. Changed artifacts, expired
or revoked authority, uncertain uncaptured model usage, and partial browser
captures stop for inspection. Stopping a run finishes it; it cannot be restarted
under the old approval. Previously completed candidates remain reviewable.

## Browser tooling and retained evidence

Python dependencies are unchanged. This feature also needs Node, Playwright and
Chromium. The local app detects installed Codex bundled tooling and the workspace
developer install described in [chat builds](CHAT_BUILDS.md#browser-smoke-checks).
On other hosts, set `EMBER_NODE`, `EMBER_PLAYWRIGHT_MODULE` and
`EMBER_BROWSER_EXECUTABLE` to installed paths before launching Ember. No browser
or runtime is downloaded automatically. Tooling is checked before a run can be
prepared and its identity is checked again before use.

Run data lives under `.harness/ui/sessions/SESSION_ID/polish/RUN_ID/`: reviewed
contracts and audit evidence in `authority/`, immutable inputs, candidate files,
screenshots, browser logs, model captures and progress. These private artifacts
stay ignored by Git. The UI shows the latest five runs; older evidence is retained.

Run `py -3.12 tools/polish_check.py` for the separate Chromium rehearsal. It uses
original fixtures, synthetic decisions and deterministic model responses, with
real browser captures and no live Muse calls or credits. It checks upfront review,
two autonomous rounds, image comparisons, rejection of a higher-rated broken
candidate, playable preview, final exact approval and report persistence. Reports
and screenshots stay under `.harness/polish-checks/`. The ordinary offline release
and clean-wheel gates cover the contract, ledger, checkpoint and API boundaries;
they do not require Chromium or make AI-quality claims.

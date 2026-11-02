# MVP mechanic recipe tickets

Created October 31, 2026, from Johnathan's request to document the mechanic
concepts discussed for Ember's MVP. All tickets are **documented / unimplemented**;
priorities and defaults below are proposed implementation choices. This backlog
does not approve runtime contracts or mark existing MVP requirements complete.

Reference: [Game Development Cheat Sheet](https://gamedev-cheatsheet.com/).
The concept selection is inspired by that reference; the tickets, product flow,
defaults and acceptance criteria below are Ember-specific proposals.

## Goal and first delivery

Let a user say “make movement smoother” or “make jumping more forgiving,” review
the proposed settings and exact changes, compare playable versions, and retain
checks for the behavior they accepted.

The first slice is one original, offline 2D browser platformer with movement and
jumping recipes. Reuse the existing project plan, selected task, proposal,
gameplay comparison, task worker and human acceptance paths. These tickets add
bounded guidance and verification to those paths; they do not create another
build or approval system. General integration into arbitrary games is later work.

| ID | Priority | Ticket | Depends on |
|---|---|---|---|
| MR-01 | P0 | Versioned recipe definitions and request preparation | None |
| MR-02 | P0 | Reproducible mechanic checks and observations | MR-01 |
| MR-03 | P0 | Acceleration and friction recipe | MR-01, MR-02 |
| MR-04 | P0 | Coyote time and input buffering recipe | MR-03 |
| MR-05 | P0 | Complete the movement/jumping product rehearsal | MR-03, MR-04 |
| MR-06 | P1 | Camera deadzone and easing recipe | MR-05 |
| MR-07 | P1 | Hit stop and invincibility recipe | MR-05 |
| MR-08 | P1 | Patrol/chase/attack state-machine recipe | MR-05 |
| MR-09 | P1 | Seeded level-generation recipe | MR-05 |

P0 is the first mechanic milestone. P1 preserves the other requested concepts
as follow-up tickets; it does not block the movement/jumping milestone. This
ordering adds a feature backlog to the [MVP checklist](MVP_STATUS.md) and does
not replace its existing delivery gates.

## MR-01 — Versioned recipe definitions and request preparation

**User outcome:** choose an improvement, understand its settings, and prepare a
normal scoped task without needing game-development vocabulary.

**Scope:** initially two recipes: acceleration/friction and forgiving jumps.
Each definition records an ID/version, plain-language purpose, supported target,
prerequisites, settings with units/defaults/bounds, implementation guidance,
suggested checks and limitations. Use one small local registry, without a new
dependency or generic plugin framework. Expose recipe selection and settings
through the existing Plan/Build workflow. Chat can suggest a recipe; the user
reviews the resolved choice and values before preparing work.

**Acceptance criteria:**

- “Make movement less abrupt” and “make jumping more forgiving” can each prepare
  the appropriate recipe-backed task with all resolved settings visible.
- Invalid, nonfinite, unknown or out-of-range settings cannot prepare a run.
  Unsupported games show missing prerequisites instead of promising compatibility.
- The request and retry snapshot retain the exact recipe version and values;
  later registry or draft edits cannot redirect an existing proposal or run.
- Selection alone starts no model call or file mutation. Proposed changes reuse
  the approved scope and exact build review; task acceptance remains separate.

**Implementation starting points:** `project_plan.py`, `session_chat.py`,
`chat_build.py`, `task_run.py`, `local_ui.py`, `ui.html`.

## MR-02 — Reproducible mechanic checks and observations

**User outcome:** see what changed and which observations support the result.

**Scope:** an original reference platformer with repeatable start/reset state,
visible accessible position/velocity/grounded/jump-count observations, and
bounded scenarios for timing-sensitive checks. The current saved driver offers
press/tap/wait and DOM assertions; it does not provide precise simulation time
or held-key sequences. Add only the fixed actions or reference-sample controls
needed for this slice, with validated limits. Separate simulation checks from
real-browser input checks and human feel judgments.

**Acceptance criteria:**

- Simulation checks can start from a known state and advance an explicit bounded
  number of steps. Real-browser rehearsals also exercise keyboard and touch
  controls in the playable sample. A script-only simulation pass cannot stand in
  for browser input evidence.
- Timing boundaries are checked on simulation steps, with declared tolerances;
  wall-clock sleeps alone cannot establish a 100 ms jump window.
- Reports bind recipe ID/version/settings, scenario configuration, source
  manifest, build and plan revision. Changed inputs invalidate recommendation
  evidence using the existing report-binding behavior.
- At least one deliberately broken mechanic fails despite a clean startup and
  positive model assessment. Missing/incomplete observations cannot pass.
- Preserve the current plan limits unless a separately scoped implementation
  requires changing them; split scenario plans/reports when necessary. No
  arbitrary JavaScript or model-provided commands become saved test steps.
- Label game-reported values as observations influenced by game code; pair them
  with browser captures and human playtesting. They are not independent proof.

**Implementation starting points:** `gameplay.py`, the existing Chromium driver
and `tools/browser_check.py`; see [saved gameplay checks](GAMEPLAY_CHECKS.md).
Reusable sample generators belong in source; generated games, captures and
reports stay under ignored `.harness/` paths.

## MR-03 — Acceleration and friction recipe

**User request:** “Make movement feel less abrupt.”

**Scope:** horizontal movement in the reference platformer. Proposed defaults:
maximum speed 240 px/s, time to full speed 200 ms, stopping time 100 ms and
reversal braking multiplier 2. Settings expose these units and bounds.
Use time-based movement and fixed simulation steps; do not alter level layout,
jump rules or art as part of this recipe.

**Acceptance criteria:**

- Holding a direction ramps velocity to the configured cap within one simulation
  step of the configured acceleration time; release stops without reversing drift.
- Reversal brakes using the configured multiplier before accelerating the other
  way. Simultaneous opposite directions have an explicit, checked neutral rule.
- Equivalent one-second inputs rendered at 30, 60 and 120 fps produce horizontal
  displacement within a declared 2 px tolerance in the reference sample.
- Keyboard and touch controls use the same movement rules. Restart, blur and
  release clear held input so the player cannot remain stuck moving.
- Compare current and proposed movement with matching inputs; retain observations
  and captures. Human playtesting separately decides whether it feels better.

## MR-04 — Coyote time and input buffering recipe

**User request:** “Make jumping more forgiving.”

**Scope:** proposed defaults of 100 ms coyote time and 100 ms jump buffer,
individually adjustable from 0–200 ms. This extends the existing jump action;
it does not add double jump or change jump height.

**Acceptance criteria:**

- An unconsumed jump press within the coyote window after walking off a ledge
  triggers exactly one jump; a press at least one simulation step outside fails.
  Specify and check inclusive window-boundary behavior.
- A jump pressed within the buffer window before landing triggers once on
  landing. An expired press does not trigger a delayed jump.
- A successful jump consumes both eligibility and buffered input. Holding jump,
  repeated input events or falling after a jump cannot manufacture extra jumps.
- Setting either window to zero disables that assistance. Restart clears timers;
  keyboard and touch use the same rules.
- The before/after comparison includes a formerly missed jump that now succeeds,
  an outside-window failure and an unchanged ordinary jump trajectory.

## MR-05 — Complete the movement/jumping product rehearsal

**User outcome:** experience the complete “request → review → play → accept” loop
with an original sample and reproducible evidence.

**Scope:** connect MR-01 through MR-04 in a named session using the existing
[project plan](PROJECT_PLAN.md), [task run](TASK_RUNS.md) and proposal comparison
workflows. Bundle both recipes in one playable platformer, but allow selecting
and tuning either separately.

**Acceptance criteria:**

- Prepare a scoped task, review values, generate an isolated candidate, compare
  gameplay, review the exact diff, apply it and separately accept the outcome.
- Failed required checks prevent recommendation. Requesting changes retains the
  candidate for a reviewed repair; it never silently overwrites the current game.
- Reload preserves the reviewed recipe/settings, pending proposal and matching
  evidence. Modified source, settings or plan cannot reuse stale passing results.
- Repeat the product rehearsal with real desktop input and mobile touch, without
  horizontal overflow. Recipe selection and checks make no live model call.
- Keep automated fixture-provider rehearsal evidence distinct from live Muse
  quality and Johnathan's human playtest. Record both remaining gates honestly.
- Existing restore, ZIP and project handoff preserve the reviewed game through
  their current paths; include recipe identity/settings in appropriate handoff
  context without exporting private approval history.

**Done for the first slice:** MR-01–MR-05 criteria pass, the focused regression
and real-Chromium rehearsal pass, existing required release gates pass, and
Johnathan separately accepts the played result. Do not mark the broader MVP done.

## MR-06 — Camera deadzone and easing recipe

**User request:** “Make the camera smoother.”

**Scope:** a following camera for the reference sample, tunable deadzone size and
follow smoothing, level bounds and a reduced-motion setting.

**Acceptance criteria:**

- Movement inside the deadzone leaves the camera stationary; crossing an edge
  produces bounded follow movement without jitter or exposing outside the level.
- Restart/teleport resets follow state. Render-rate changes preserve the intended
  response within a declared positional tolerance.
- A repeated route has before/after captures and checked camera positions;
  reduced motion removes optional motion effects. Human review assesses comfort.

## MR-07 — Hit stop and invincibility recipe

**User request:** “Make hits feel stronger and prevent repeated damage.”

**Scope:** one original attack/hazard interaction, tunable hit-stop duration and
post-damage invincibility, visible health and accessible damage feedback.
Proposed defaults: 60 ms hit stop and 750 ms invincibility. Screen shake is optional
later work, not a prerequisite for this ticket.

**Acceptance criteria:**

- A continuous overlap deals one hit during the invincibility window; damage is
  possible after expiry. Restart clears invincibility and pending hit stop.
- Hit stop affects the declared gameplay actors while pause/menu controls and
  feedback remain responsive. Define which timers advance during hit stop and
  check that overlapping hits cannot prolong it without a bound.
- Check health and timing boundaries against a broken baseline; reduced-motion
  feedback stays readable without rapid flashing. Separately playtest impact feel.

## MR-08 — Patrol/chase/attack state-machine recipe

**User request:** “Give enemies patrol, chase, and attack behavior.”

**Scope:** one enemy in a simple unobstructed arena, explicit transition rules,
detection/attack ranges and cooldown. Pathfinding and crowds are deferred.

**Acceptance criteria:**

- Exactly one state is active. Entering detection range starts chase; entering
  attack range permits attacks only at the configured cooldown.
- Leaving range returns to the specified state with boundary hysteresis so an
  enemy near an edge does not switch every frame. Reset restores initial state.
- A repeated player route checks transitions, attack counts and range boundaries;
  captures confirm readable behavior. Impossible state combinations fail checks.

## MR-09 — Seeded level-generation recipe

**User request:** “Generate a level I can reproduce.”

**Scope:** small bounded 2D layouts, explicit seed, generator version and settings.
Constrain the reference generator to reachable starts/goals and safe spawn areas;
world streaming and general procedural worlds are deferred.

**Acceptance criteria:**

- The same seed, generator version and settings produce identical layout data
  across reloads. Record all three with the build; a seed alone is insufficient.
- Chosen fixture seeds produce distinct layouts; each passes explicit spawn and
  start-to-goal reachability checks. Invalid seeds/settings fail before generation.
- Gameplay comparisons reuse the same generated layout and initial state;
  restart reconstructs it. Saving/handoff retains the reproducibility settings.

## Shared delivery boundaries

All tickets retain the existing scope, exact-build approval, separate human
acceptance, sandbox, attempt and promotional-credit limits. See [task runs](TASK_RUNS.md)
and [models and credits](MODELS_AND_CREDITS.md) rather than introducing another
permission or budget mechanism. No new provider, engine import, paid service,
publication or deployment is required by this backlog.

Performance recipes (pooling, instancing, spatial grids, LOD), shaders and broader
asset families remain outside this first mechanic milestone. Add them only with
a concrete user scenario and measured need. Deterministic checks establish the
declared behavior; improvement in feel and overall game quality requires play.

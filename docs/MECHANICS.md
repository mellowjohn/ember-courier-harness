# Reference platformer and mechanic recipes

The first recipe profile is **Lantern Trail**, an original offline browser
platformer. This bounded profile supports two independently adjustable recipes:
**Smoother movement** and **More forgiving jumps**. Existing project scope, exact
build approval and separate human task acceptance still apply. Choosing settings
does not approve work or dispatch a model.

Open **Project tools → Plan → Gameplay recipes**. In an empty session,
review the reference platformer under an approved selected task, then use the
normal **Approve & play** review. Choose an improvement and its values, then
**Review recipe changes**. The pending review shows the exact recipe version
and resolved units/values; reloading retains that packet. Applying a recipe
keeps the other recipe's settings and changes only `mechanic-config.js`.
**Use reference gameplay checks** explicitly replaces the editable saved check
plan. It does not change a reviewed run's frozen checks.

Movement settings expose maximum speed in pixels per second, acceleration and
stopping times in milliseconds, and a reversal braking multiplier. Opposite
directions together are neutral. Reversal first brakes to zero, then accelerates
the other way. Release, restart, lost pointer capture and blur clear held input;
stopping still follows the selected friction time. The jump recipe exposes
0–200 ms coyote and buffer windows. Zero disables the corresponding assistance.
Successful jumps consume eligibility and buffered input, so holding or repeating
jump does not add a double jump or change ordinary jump height.

Recipes are versioned definitions with purpose, units, defaults, bounds,
prerequisites and limitations. Resolved values and the full definition are
hash-bound snapshots. Unknown, nonfinite, boolean or out-of-range values are
rejected. Reference compatibility requires the canonical HTML, game adapter and
physics runtime; an arbitrary game's name or marker cannot establish support.
Changing an existing game's runtime requires its own implementation and review.
Recipe application changes only the configuration file and preserves the other
reviewed source bytes. Styling may vary, but remains in the source manifest and
must pass the existing browser/layout checks.

## Play and compare

Use Arrow keys or A/D to move and Space to jump. Touch buttons drive the same
physics. **Restart trail** clears movement, timers and jump counts. The trail
contains a gap and a destination lantern; the sample does not claim to be a
complete game or a proof of game quality.

**Run configured checks** runs eight fixed simulation observations: acceleration,
friction, reversal/neutral input, render-rate equivalence, coyote time, input
buffering, single-jump consumption/reset and unchanged ordinary trajectory.
The result stays available in the configured-mechanic report. The expandable
observations also offer fixed edge and landing scenarios and buttons advancing
exactly 1, 6 or 12 steps. Those modes pause wall-clock advancement; **Play normally**
or **Restart trail** restores real-time play. There are no arbitrary saved
JavaScript commands or model-provided simulation programs.

Physics uses 120 fixed steps per second. Jump window boundaries are inclusive;
an input at the exact 100 ms boundary is accepted, while one step later is not.
Timing checks use simulation ticks, not browser sleeps. The reference verifies
matching one-second horizontal input at 30, 60 and 120 rendered frames per second
within 2 px, and reports the actual positions. Browser keyboard/touch checks are
separate and use the existing bounded gameplay plans.

Reports bind recipe IDs, versions, settings, scenario version, source manifest,
build reference, saved plan revision and, when supplied, the saved plan hash.
The host checks complete observation fields and derives support for positive
claims from the configured numeric expectations; a bare positive status or
three matching but incorrect positions cannot pass. Runtime/source changes also
invalidate the supported reference profile and existing report bindings.

These remain game-reported simulation observations, influenced by the checked
game code. Pair them with retained browser input/captures and a human playtest.
Whether movement feels better, interaction is comfortable and the game meets
the intended experience remains a separate human judgment. Live Muse quality
and Johnathan's acceptance are not established by these fixture checks.

## Implementation and validation

`ember_harness/mechanic_recipes.py` owns the small registry, frozen settings,
compatibility checks, source generation and report validation. Packaged resources
under `ember_harness/mechanics/` hold the shared reference runtime and interface.
`reference_files([])` creates the explicit legacy baseline: instant movement and
disabled jump assistance. `reference_files()` enables both default recipes.

Run `py -3.12 tools/offline_tests.py --pattern test_mechanic_recipes.py` for settings,
source preservation, deterministic physics, timing boundaries, frame-rate checks,
input/reset rules and rejection of broken or forged positive results. The
deterministic JavaScript checks use the existing optional Node runtime. They do
not call Muse, install dependencies or change a project. See [mechanic tickets](MECHANIC_TICKETS.md)
for the broader milestone, remaining integration and separate human acceptance.

`py -3.12 tools/offline_tests.py --pattern test_mechanic_workflow.py` covers the
scoped preparation, exact application, reload, stale inputs, export, handoff and
forward-restore boundaries. With the existing optional Chromium tooling,
`py -3.12 tools/mechanic_check.py` rehearses those real UI paths, a failed
zero-window proposal followed by a checked 100 ms repair, keyboard/touch input,
ZIP/handoff and separate synthetic owner acceptance. It denies unstubbed Muse
reservations. Successful fixture acceptance is not Johnathan's own playtest.

## Expanded profile: Lantern Vale

The second supported profile, `ember-platformer-v2`, adds the four remaining
recipe families to an original small trail: camera follow, ground-hazard impact,
one sentinel and reproducible layouts. It retains the two movement/jump recipe
snapshots. Existing Lantern Trail source and saved versions remain unchanged.

**The first expanded recipe is a full reference upgrade.** Review its complete
source, layout, camera, hazard and sentinel scaffold under a task that includes
those changes. It is not a camera-only edit to an arbitrary game. The normal
exact-build proposal and separate task acceptance still apply. Subsequent
recipe edits inside the expanded profile change only `mechanic-config.js` and
preserve the other reviewed settings. Returning to older settings within the
expanded profile uses the normal reviewed forward-restore workflow; it does not
rewrite old evidence. V1 history remains available, but a v2-to-v1 runtime
downgrade is outside automatic mechanic qualification and is reported as a source
blocker. It is not silently presented as another configuration-only edit.

| Recipe | Default settings | Supported limits |
|---|---|---|
| Smoother camera | 96 px quiet window, 200 ms follow time, reduced motion off | Window 0–240 px; follow time 0–600 ms; reduced motion 0/1 |
| Clearer hits and damage protection | 60 ms hit pause, 750 ms protection | Pause 0–120 ms; protection 0–2000 ms; zero disables that assistance |
| Patrol, chase and attack | Notice 260 px; attack 50 px; return margin 40 px; cooldown 700 ms | Notice 120–400 px; attack 24–90 px; margin 10–80 px; cooldown 200–2000 ms |
| Reproducible trail layouts | Seed 1729; 10 sections; generator version 1 | Integer seed 1–2147483647; 6–12 sections |

Every value is finite and bounded; these new settings use whole units. Settings,
immutable definitions, source manifest, build, plan revision/hash and generator
version remain bound to each report. Unsupported source changes prevent a
mechanic-qualified recommendation even if an AI assessment is positive.

### Camera, motion and reset

The 400 px world viewport follows beyond a centered quiet window and eases
toward its target at 120 fixed steps per second. It remains within the 1000 px
level. Ordinary play also clamps the courier inside the visible viewport: high
speed, a large quiet window and slow easing cannot leave the player offscreen.
Restart and **Travel to lantern** reset follow state rather than sweeping from
the old location. The fixed **Camera route** starts with the courier visible in
both versions; its first step is 140 px with legacy instant follow and 3.833 px
with the default camera recipe.

Configured reduced motion removes camera easing and optional lantern glow
animation, while preserving the quiet window and bounds. The local accessibility
checkbox and the browser's reduced-motion preference also remove optional
motion during play without rewriting the reviewed configuration. The configured
simulation report remains distinct from these live browser preference checks.
There is no screen shake or rapid flashing. Human review still assesses comfort.

### Health, hit pause and sentinel timing

The courier starts with five health. Coral stakes damage **grounded contact**;
jumping avoids that ground contact zone, including at the slowest supported
movement speed. A hit consumes one health and records readable text. A successful
hit protects all ticks before the declared expiry; another hit is possible
exactly at expiry. Durations round up to the next 120 Hz step: the proposed
60 ms hit pause occupies eight steps (66.667 ms), and 750 ms protection occupies
90 steps. Zero protection allows damage on successive ticks, while still
preventing duplicate hits within one tick.

Hit pause stops player and sentinel actors. Protection and hit-pause timers use
unpaused simulation time; sentinel movement and attack cooldown use actor time.
One continuous contact episode starts at most one hit pause, so repeated overlap
cannot extend it indefinitely. **Pause game** freezes all simulation timers and
clears held input. Pause/resume, accessibility controls and restart remain
responsive during hit pause or after health reaches zero. Restart resets health,
timers, attacks and held input. Human playtesting separately assesses impact feel.

One sentinel patrols an unobstructed interval. Inside notice range it chases;
inside attack range it attacks at its configured cooldown. Leaving either range
requires the additional return margin, preventing boundary chatter. Exactly one
state is active. Restart restores patrol and zero attacks. This profile supplies
neither pathfinding nor crowds. A generated goal is free of generated ground
hazards at creation; an active sentinel can subsequently pursue the courier, so
the goal is not an enemy-exclusion zone.

### Seeded layouts and bounded observations

Generator version one uses an integer PRNG. It produces contiguous platforms
with at most 32 px adjacent height changes, plus bounded ground-hazard sections.
The first and last two sections are flat and free of generated hazards. The
seed, generator version, section count, actual platform/hazard data and layout
fingerprint are retained. The same values reproduce the same geometry across
restart and reload; a seed alone is not a complete reproduction record.

Checks compare actual geometry as well as hashes for fixture seeds 17 and 29.
Host validation independently reconstructs the expected layout; a positive
status or a seed-bearing hash cannot stand in for the declared geometry. The
focused suite also drives the actual slowest supported player through generated
trails, jumping over their ground hazards and reaching the goal with full
health. This complements bounded platform connectivity checks; it does not prove
arbitrary generated worlds, optimal routes, every enemy interaction or overall
game quality.

The expanded reference retains the original eight movement/jump scenarios and
adds four fixed observation groups: camera response/rates/reset, damage expiry
and actor pause, sentinel transitions/cooldown, and layout reproduction/safety.
**Fixed-step mechanic observations** offers explicit camera, hazard and sentinel
scenarios with 1/6/12/60-step advances. No arbitrary JavaScript or model-provided
program becomes a saved gameplay action.

Run `py -3.12 tools/offline_tests.py --pattern test_mechanic_expansions.py` for
the deterministic runtime/host checks. The module
`ember_harness/mechanic_expansions.py` owns the v2 definitions and expectations;
the four `advanced-*` resources are packaged beside the unchanged v1 runtime.
The real-browser expanded recipe rehearsal and evidence tests use the existing
scope, proposal, capture, restore, ZIP, handoff and synthetic-owner paths. Live
Muse quality and Johnathan's own playtest remain separate gates.

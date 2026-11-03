# Workflow quality tickets

Created November 1, 2026, from Johnathan's request to polish the workflows so
the harness produces quality work. These tickets improve planning, execution,
review and revision across supported games. They reuse the existing contracts,
specialists, browser checks, attempts, evidence and exact build review.

The goal is a result that satisfies the intended experience, preserves what
already works and gets better through useful criticism. A generated build,
clean console, passing DOM assertions or positive AI verdict alone cannot
establish that outcome. AI assessments and human acceptance remain distinct.

## Order and status

| ID | Priority | Outcome | Status |
|---|---|---|---|
| WQ-01 | P0 | Carry the full approved intent into every task handoff | Implemented; synthetic regression coverage, live quality unverified |
| WQ-02 | P0 | Review explicit quality criteria with supporting evidence | Implemented for new ordinary browser-task runs; live quality unverified |
| WQ-03 | P0 | Learn from rejected polish attempts | Implemented; synthetic recovery coverage, live quality unverified |
| WQ-04 | P0 | Compare improvement against the starting experience | Implemented for new ordinary task runs; live quality unverified |
| WQ-05 | P1 | Expose actionable quality blockers in the review | Implemented for task review and polish history; live usefulness unverified |
| WQ-06 | P1 | Expose missing behavior and interaction coverage | Implemented as advisory coverage review; semantic coverage requires owner review |
| WQ-07 | P0 release gate | Rehearse quality on representative real tasks | Partial: guarded fixture rehearsals pass; representative live set and owner playtest remain open |

WQ-01 through WQ-04 are the first implementation sequence. WQ-07 evaluates
those changes before claiming an improvement in live output quality. The
[mechanic tickets](MECHANIC_TICKETS.md) remain a separate feature backlog;
the [MVP checklist](MVP_STATUS.md) retains its existing delivery gates.

## WQ-01 — Preserve approved intent through handoffs

**Observed gap:** `task_run.py` freezes `project_plan.document` in the reviewed
run, but previously sent the task title, brief and art direction to coding
workers and only the title/art direction to the verifier. The approved core
loop, explicit exclusions, asset budget and completion criteria were absent
from those model requests. A specialist could implement the title while missing
the intended experience.

**Change:** send the complete frozen approved design to the first worker,
second specialist when present, and independent verifier. Send the frozen brief
to the verifier too. Explain that other planned features provide context;
only the selected task is assigned work. This uses the existing reviewed
snapshot and does not add calls, permissions or a separate approval path.

**Acceptance criteria:**

- Core loop, exclusions, asset budget, completion criteria and art direction
  reach each implementation stage and the verifier unchanged.
- Every retry receives the same reviewed design and brief. Later brief edits
  cannot silently redirect a run; scope changes retain the existing binding gate.
- The verifier still receives no coder narrative, and final build approval and
  task acceptance remain separate.
- Regressions exercise actual task execution, a failed first verdict and repair,
  and the two-specialist handoff with synthetic provider replies.

This fixes missing context. It does not establish that Muse follows that
context or that the resulting game is good. WQ-02 and WQ-07 address those gaps.

Validation: all 16 task-run tests, 6 specialist-orchestration tests and 16
finding/fix tests pass with synthetic provider replies and owner decisions.
No live Muse calls or new dependencies were used for this change.

## WQ-02 — Evidence-backed quality criteria

Implemented November 2 for newly prepared ordinary browser-task runs. The host
freezes task intent, preservation, presentation, each saved gameplay scenario
and pending human experience in the existing permission packet. Its UI shows
criteria before approval and retains criterion assessments and blockers after
execution. Finding and native asset adapters retain their specialized reviews;
older runs keep the criteria, if any, in their original reviewed packet.

Source evidence must quote actual candidate bytes; visual judgments reference
both attached desktop/mobile captures; gameplay evidence references the matching
passing scenario. The host checks references and coverage, not the truth of an
AI interpretation. Required `not_met`/`not_observed` assessments block review;
human experience must remain unobserved until the owner's separate playtest.
Project-wide completion criteria remain human review guidance so unrelated
future features cannot silently become work for the selected task.

No new model calls, dependencies, permissions or automatic human acceptance.
WQ-03 continues the implementation sequence. WQ-07 remains the live quality gate.

Validation: 17 task-run, 6 quality-evidence, 6 orchestration and 16 finding/fix
tests pass. The real Chrome rehearsal passes the visible pre-approval checklist,
retained criterion evidence, exact promotion, separate acceptance and existing
finding/workspace flows. Its report is retained under
`.harness/browser-checks/20261102T131254Z-7c97d86a/REPORT.md`, with unchanged
implementation source. Provider replies and owner decisions are synthetic;
Chromium interactions and captures are real. No live quality claim follows.

**Observed gap:** the ordinary task verdict has `meets_task`, `preserves_scope`,
`summary` and free-text `issues`. It has no required accounting of what was
reviewed, what supports the judgment, or what could not be observed.

**Scope:** prepare a short, task-specific checklist from the approved design,
selected task, brief and existing checks. Show it in the existing run review,
freeze it with that run and give it to every worker. Cover intended behavior,
readability, interaction feedback, applicable art direction and preservation.
Criteria must stay within the selected task rather than adding project features.
Avoid inventing a universal numerical score or equating taste with a test pass.

**Acceptance criteria:**

- Each frozen criterion has a stable ID, expectation and evidence method.
  Distinguish required observed behavior, AI visual judgment and human-only feel.
- The independent verifier returns one assessment per criterion, supporting
  observations/source locations/captures, and `met`, `not_met` or `not_observed`.
- The host rejects missing, duplicate or unknown criterion IDs. Missing evidence
  for a required automated/AI criterion blocks qualification despite a positive
  overall verdict. Human-only criteria remain visibly pending for owner review.
- Browser/gameplay failures remain blocking regardless of the AI judgment.
  A criterion review cannot weaken checks or grant permissions.
- Repair attempts receive the unmet criteria and concrete suggested fixes;
  replay retains the original criteria and completed evidence.
- Regressions include a clean-looking but incomplete game, empty positive
  verdict, unsupported evidence, unavailable observations and a qualified repair.

**Starting points:** `task_run.py`, `project_plan.py`, `local_ui.py`, `ui.html`,
`tests/test_task_run.py`, `tests/test_orchestration.py` and the existing browser
rehearsal. Preserve finding and asset adapters' separate review requirements.

## WQ-03 — Keep useful criticism from rejected attempts

Implemented November 2. The next generator receives bounded AI criticism and
host/browser failure observations from the preceding rejected attempt, while
editing the strongest selected source. The summary names both round IDs and
keeps AI opinions separate from browser/gameplay evidence. It is cleared when
an improvement is selected. No rejected source is supplied as an editing base.

Replay selects the best only from candidates available at that round. This
prevents later saved candidates from changing earlier prompts on recovery.
The regression exercises a high-rated broken attempt, a successful repair,
an interruption after the second captured generation, and another interruption
after its candidate is retained. All model replies replay with identical
feedback; earlier candidates and the current approved game remain intact.
No new calls, dependencies, permissions or automatic acceptance were added.
WQ-04 is next; live output quality still requires WQ-07.

Validation: all 19 polish tests and 17 shared task-run tests pass. The existing
real Chrome polish rehearsal passes with unchanged implementation source,
including desktop/touch assertions, rejection of a higher-rated regression,
best selection, separate exact approval and restart persistence. Its retained
report is `.harness/polish-checks/20261102T132325Z-a3506a87/REPORT.md`.
Provider replies and owner decisions are fixtures; no live Muse credits were used.

**Observed gap:** overnight generation receives the current best candidate and
its critique. If a newer candidate is rejected, its problems and next changes
are retained in evidence but are not explicitly supplied to the next generator.
The worker can repeat the same mistake while starting from the earlier best.

**Acceptance criteria:**

- Keep generating from the strongest eligible candidate while supplying a
  bounded summary of the last rejected attempt's concrete failures and tradeoffs.
- Separate observations from AI opinions and preserve useful changes without
  reintroducing a failed interaction or discarded approach.
- Feedback remains untrusted design data and cannot expand the approved task.
- Two-round tests demonstrate a visually attractive broken attempt being
  rejected, its failure reaching the next request and the earlier working
  candidate remaining available. Resume must replay identical feedback.

**Starting points:** `polish.Worker.run`, `critique`, `choose_best` and
`tests/test_polish.py`. Ordinary task runs already carry the last verdict and
browser observations forward; reuse that approach where appropriate.

## WQ-04 — Judge improvement against the starting experience

Implemented November 3 for new ordinary browser-task runs. The reviewed packet
freezes the starting manifest, saved checks and comparison protocol; the same
bounded Chromium interactions capture both versions. The independent verifier
must identify the improvement and losses using supported source, capture and
scenario references. Missing evidence, unchanged source, a negative improvement
assessment or reported losses block qualification despite a positive overall
verdict. A blank project explicitly has no playable starting baseline.

Capture inputs, images and reports are checked again on recovery, preview,
promotion and handoff. Historical runs keep their original reviewed protocol;
finding and asset adapters retain their specialized evidence. The host validates
evidence references, not whether an AI interpretation is true. Whether a cosmetic
change satisfies the intended interaction still requires judgment and play.
See [task runs](TASK_RUNS.md) for the current boundary and evidence layout.

**Observed gap:** ordinary task verification reads baseline source but attaches
only candidate desktop/mobile captures. It does not have the same visual
before/after comparison available to overnight polish.

**Acceptance criteria:**

- Freeze and capture the starting game's relevant states and the candidate
  using the same bounded interactions, viewports and checks.
- The independent review identifies the requested improvement and any losses
  against that baseline, with clearly identified before/after evidence.
- A cosmetic change alone cannot satisfy an interaction task. An unchanged
  experience cannot satisfy a requested improvement merely through a new verdict.
- A blank initial project is labeled as having no playable comparison baseline.
- Current game files remain unchanged; capture permissions and inputs stay
  inside the existing reviewed contracts and resource limits.

**Starting points:** `task_run.py`, `polish.py`, `polish_runtime.py` and the
existing proposal comparison and gameplay evidence flows.

## WQ-05 — Make quality blockers useful to the owner

Implemented November 3 in the existing task cards. Requested outcome, observed
result, failed behavior, visual concerns, unavailable evidence, comparison losses
and the next suggested change are visible alongside the retained reports.
Each completed attempt can be played in an isolated preview and its verified
before/after screenshots opened without applying it. Failed/exhausted histories
retain the attempt counts and owner-decision boundary. Human playtesting remains
pending. Polish history also exposes review concerns and suggested revisions.
See [the local app guide](LOCAL_UI.md).

**Acceptance criteria:**

- The existing task/review card shows the requested outcome, observed result,
  unmet criteria and the most useful next change in plain language.
- Separate broken behavior, visual judgment, unavailable evidence and pending
  human playtesting. Retain links to the bound captures and playable candidate.
- Failed or exhausted runs summarize what was tried and what remains weak;
  requesting another attempt never promises an improvement or silently resets
  the budget. A positive model verdict is never labeled human acceptance.

**Starting points:** task/polish history, `ui.html`, `PROJECT_HANDOFF.md` and
the existing attempt/evidence report. Reuse the current workflow surfaces.

## WQ-06 — Make coverage gaps visible

Implemented November 3. The existing gameplay editor supports optional bounded
purpose labels. A preflight inventory maps the selected expectation to configured
scenarios and flags missing discoverability, success, failure, reset, repeated
play, keyboard and touch paths. Labels are author-declared intent; names cannot
prove coverage. Keyboard/touch entries require a configured input followed by an
assertion, and even those observations do not establish causal correctness.
The exact inventory is frozen in the reviewed run and supplied to every role
and retry; editing the saved plan requires a new review. Missing categories are
advisory, since their relevance requires judgment. Every configured scenario
remains blocking, including reset, repeated play and touch. No action or timing
limits were widened. See [saved gameplay checks](GAMEPLAY_CHECKS.md).

**Acceptance criteria:**

- Map task expectations to configured observable scenarios and identify missing
  interaction paths before dispatch: discoverability, success, failure, reset,
  repeated play and touch/keyboard behavior where relevant.
- Flag DOM assertions that merely echo a game-reported state; do not present
  them as independent physics, scoring, accessibility or fun verification.
- Offer bounded check improvements through the existing reviewed workflow.
  Unsupported measurements remain explicitly unobserved.
- A passing happy path cannot hide a failing reset, second playthrough or touch
  interaction. Tests include each of those regressions.

**Starting points:** `gameplay.py`, `polish_browser.js`, `task_run.py` and
the existing gameplay-plan editor. Reuse mechanic verification when available.

## WQ-07 — Representative live quality rehearsal

November 3 checkpoint: the final implementation passes 680 installed Python
cases and twelve demos from a clean Git checkout of the local delivery snapshot.
Real Chromium rehearsals cover paired task evidence and exact promotion, a weak
and broken proposal repaired using screenshots, secondary-path regressions,
polish rejection and recovery. Successful rehearsals use synthetic replies and
owner choices, with guarded provider dispatch. The retained evidence is listed
in [MVP status](MVP_STATUS.md#explicit-boundaries-retained). These are fixture
gate checks; the representative live task set and Johnathan's judgments below
still need to be completed.

**Scope:** a small retained set of original tasks: a clearer first-play loop,
a responsive readable HUD, a more satisfying interaction, and a scoped repair
that preserves an existing game. Include both one-worker and two-specialist
routes. Use fixed reviewed designs and starting versions for comparisons.

**Acceptance criteria:**

- First use deterministic weak, broken and improved fixtures to verify that
  the gates distinguish them for the stated reasons.
- Then run real Muse worker/verifier requests through normal approved scopes
  and the existing shared credit cap. No synthetic owner decisions in live runs.
- Retain criteria, exact source, captures, observed checks, rejected attempts,
  model judgments and actual credit usage/holds for each run.
- Johnathan plays the compared versions and records whether the intended
  experience improved and what still feels weak. Keep that judgment separate
  from automated evidence and record mixed/failed outcomes as well as successes.
- Report the sample size and limitations. A successful example does not prove
  quality for arbitrary games; a larger score alone does not close this ticket.

**Starting points:** existing task preparation, browser/polish rehearsals and
project handoff. Extend those entry points instead of copying a new pipeline.

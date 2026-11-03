# Game UI creation and review

Generated game interfaces should belong to the game view and share the game's
art direction. A game squeezed between a web heading/scoreboard and a footer of
instructions or buttons is a layout defect unless the approved design asks for it.
The Ember workspace theme is not the game's design system.

## Design before implementation

For a first build or a requested UI change, the coding prompt asks the worker to
choose essential player information, anchors within the game viewport and a small
visual vocabulary from the approved art: palette, type, shapes, borders and icons.
The build summary briefly explains those choices for review. This is guidance
within the existing coding call, not a separate design call or approval step.

The renderer and DOM interface share a game-stage wrapper. HUD elements anchor
to that wrapper; pause, help and result views appear inside it. The playfield
remains dominant, with contextual prompts and secondary instructions in help or
pause rather than persistent page furniture. Keep the action area clear.

Mobile layouts adapt to the stage dimensions and safe areas, keeping text legible
and touch targets at least 44 CSS pixels. Decorative overlays pass input through;
interactive controls use semantic buttons, visible focus and accessible names.
Counters and controls reserve separate space on narrow stages; compact named icon
buttons or a menu avoid overlapping desktop labels. Help/settings panels use
stage-bounded dimensions and internal scrolling with a reachable close control.
Use the states needed by the mechanic, preserving saved selectors and controls.
Explicit approved layouts take precedence. Unrelated existing UI is preserved.

The **game itself** fills its iframe viewport, including the embedded preview,
fullscreen and standalone play. Avoid small fixed-width wrappers and width-only
canvases. Observe stage size, update the renderer resolution and camera, and map
pointer input to game coordinates without resetting play. Scale artwork uniformly;
when a fixed playfield ratio is required, use the largest centered proportional
fit with deliberate letterboxing. Mark the stage with `data-ember-game-stage`.

## Review the actual game view

Chat proposal and ordinary task verification now have separate required
`game-viewport-fit`, `game-ui-integration` and `game-ui-style` visual criteria. Each requires evidence
from both actual desktop and mobile captures. A positive global verdict or passing
gameplay assertions cannot override an unmet UI criterion. Task failures feed the
specific issue and retained screenshots into the next permitted repair; chat uses
the existing **Fix verification issues** flow. Reports and exact approval remain
in the existing workflow.

Reviewers inspect stage integration, visual fit, hierarchy, playfield visibility
and control placement, consulting source for anchors and input behavior. They
should name the offending element, viewport and repair. Required states absent
from the available evidence remain unobserved; static captures do not prove
interaction quality. Tasks with no UI changes assess preservation, not a forced
redesign. Existing reviewed packets retain their frozen criteria.
Being inside the stage does not excuse overlapping counters or clipped panels:
those fail integration. Source evidence must be one verbatim contiguous candidate
excerpt; abbreviations and explanations belong in the judgment's reason field.
New browser inspections resize the same game document through these saved sizes:

| Layout | Size |
| --- | --- |
| 16:9 | 1280 × 720 |
| 16:10 | 1280 × 800 |
| 4:3 | 1024 × 768 |
| 21:9 | 1680 × 720 |
| 9:16 | 360 × 640 |
| Tall phone | 390 × 844 |
| Phone landscape | 844 × 390 |

Each size retains its screenshot, stage/renderer bounds, overflow, off-screen
controls and whether the document survived resizing. Missing or changed evidence
is rejected. `game-viewport-fit` requires every supplied ratio; a positive AI
verdict cannot override observed overflow, clipped controls or a replaced game
document. Stage fit, distorted artwork, pointer mapping and preservation of the
actual gameplay state still require source, visual review and gameplay assertions.
The document witness alone does not prove game-state preservation.

The fixed browser driver also opens a discoverable Help/Settings/Pause button
whose `aria-controls` points to a panel and captures that state. When available,
the panel, movement and aspect-ratio images are included in labeled desktop/mobile
contact sheets, retaining the four-image allowance for before/after review. Original
captures remain individually accessible. Panel bytes are checked
against the recorded hashes before evidence or repair feedback can be reused.

The same implementation and review guidance reaches polish calls. Polish retains
its existing comparative scores and best-candidate selection rather than the task
criterion gate. The canonical prompts live in `chat_build.py`; required criteria
live in `task_quality.py`. No additional dependency or provider call is introduced.

Automated review is still a model's judgment. Offline tests verify routing,
evidence requirements and repair behavior using synthetic judgments; they do not
establish that a live generated UI looks good. Human preview and playtesting
remain necessary to judge the result.

For a local browser project, run `python tools/viewport_check.py --project PATH`
with the normal optional browser tooling installed. It saves read-only Chromium
evidence under `.harness/viewport-checks/`, makes no model calls and does not alter
or approve the project. Retained older runs keep their original capture protocol.

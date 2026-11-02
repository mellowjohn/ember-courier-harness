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

## Review the actual game view

Chat proposal and ordinary task verification now have separate required
`game-ui-integration` and `game-ui-style` visual criteria. Each requires evidence
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
The fixed browser driver also opens a discoverable Help/Settings/Pause button
whose `aria-controls` points to a panel and captures that state. When available,
the two panel images accompany the desktop/mobile game views in the bounded
four-image review; movement captures are still retained. Panel bytes are checked
against the recorded hashes before evidence or repair feedback can be reused.

The same implementation and review guidance reaches polish calls. Polish retains
its existing comparative scores and best-candidate selection rather than the task
criterion gate. The canonical prompts live in `chat_build.py`; required criteria
live in `task_quality.py`. No additional dependency or provider call is introduced.

Automated review is still a model's judgment. Offline tests verify routing,
evidence requirements and repair behavior using synthetic judgments; they do not
establish that a live generated UI looks good. Human preview and playtesting
remain necessary to judge the result.

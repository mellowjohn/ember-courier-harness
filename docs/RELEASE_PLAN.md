# November 4 delivery plan

Target: November 4, 2026, 9:00 p.m. America/New_York (EST, UTC−05:00).
This is Johnathan's delivery target. Official event eligibility, rules, dates and
submission requirements remain unverified. This plan does not authorize
submission, deployment, publishing, paid fallback or cash spending.

## Product status — October 30

Ember now builds browser games through a saved Muse conversation. Johnathan
reported that the first generated game was playable. This is a human playtest
report, not a claim that arbitrary generated games pass automated gameplay tests.

Implemented in the local app:

- Saved named sessions and durable conversation turns.
- Persistent per-session project briefs and a responsive chat/preview workspace.
  Brief snapshots remain bound to requests and retries; previews retain game state
  during polling and recorded playtest updates.
- One reviewed proposal for up to eight HTML/CSS/JavaScript files; exact gated
  writes, file evidence, changed-input rejection and interrupted-build recovery.
- Compact review, Approve & play, direct revision requests, and feedback-to-fix.
- Playable pending-proposal previews alongside the current game, before exact
  approval, including restoration and final polish proposals.
- Opaque-origin game previews with blocked network access, browser diagnostics,
  version-bound playtest reports and proposed fixes that still need approval.
- Observed agent activity: context preparation, provider startup and output
  streaming, elapsed time, validation, review readiness and interrupted requests.
- A shared $150 promotional-credit ceiling, $5 reservations, disabled provider
  retries, conservative holds for uncertain usage and saved-response replay.
- Completed-build version history, historical previews and verified ZIP exports
  containing reviewed game files and a source manifest. No publishing or deploys.
- Repeatable browser smoke observations, version-bound reports and explicitly
  requested reviewed fixes. Saved versions can be restored through a new exact
  approval while preserving history; restores requiring file deletion are refused.
- Overnight polish for existing browser games: an upfront-approved scope/worker
  pair, isolated candidates, real desktop/mobile captures, screenshot critiques,
  bounded rounds and credits, checkpoint recovery and a separate final exact diff.
  AI recommendations are judgments, and require a human playtest and acceptance.

The contract library also implements scope proposals, approvals, amendments,
asset selection/ingest, intake, real local fixes, separate verification, rounds,
attempt limits, reconciliation and reopening. These are demonstrated separately
in the bounded integrated sample. Engine work remains paused. See
[the product demonstration](PRODUCT_DEMO.md), [the local app](LOCAL_UI.md),
[chat builds and versions](CHAT_BUILDS.md), and
[models and credits](MODELS_AND_CREDITS.md) for exact behavior and limitations.

## Remaining priorities

1. **Reproducible checkpoint and clean installation — verified October 30.**
   The current proposal-preview source passed all 370 tests and twelve demos
   from a clean-installed wheel, plus the browser QA/restore and overnight-polish
   Chromium rehearsals. A separate Chromium rehearsal also passed against the
   installed wheel without checkout package source. Retained reports bind the
   source and wheel hashes; source remained unchanged during the final gates.
   Model replies and owner decisions were synthetic, with no live Muse calls.
   Repeat these gates after code changes; the clean-checkout launch rehearsal
   below remains outstanding. A harness PASS does not establish generated-game
   quality.
2. **Browser QA and safe restoration (October 31–November 1).** Implemented:
   bounded browser smoke checks, clearly labeled observations, user-requested
   reviewed fixes and exact approved restoration as a new version. Run the
   separate Chromium rehearsal in [chat builds](CHAT_BUILDS.md#browser-smoke-checks)
   alongside the offline and clean-install gates. Broaden human gameplay
   rehearsal; no automated claim of arbitrary generated-game quality follows.
3. **Project guidance and presentation (November 2).** Keep the game brief and
   constraints useful across longer conversations; rehearse idea → proposal →
   approve/play → feedback → revised version → ZIP export. Distinguish synthetic
   fixture decisions, genuine owner decisions, model output, static evidence and
   human playtest reports. Verify official event requirements, especially required
   Meta execution and whether the entry must contain a playable game.
4. **Feature freeze and clean rehearsal (November 3, by 9 p.m. Eastern).** Install
   from a clean checkout, run the complete gate and exact demonstration, log every
   blocker with reproduction, and defer optional features. Retest startup using
   Start Ember.cmd, the private launch link, saved sessions and credit enforcement.
5. **Final verification and handoff (November 4).** Finish blocker fixes by 3 p.m.
   EST. After the last source edit, retain final gate logs, source manifest,
   installation evidence, exported sample game, demo instructions and limitations
   by 6 p.m. Leave three hours for Johnathan's review and submission. Johnathan
   still owns submission; closing S0/S1 bugs requires his own approval.

These are work targets, not scheduled automations. If a priority slips, reduce
optional scope before consuming the final verification buffer.

## Run the offline release gate

```powershell
py tools/release_check.py
```

Run from the repository with Python 3.12+, Git and project dependencies installed
(`py -m pip install -e .`). The gate runs the full test suite and all twelve demo
entry points with assertions enabled and retains a unique directory under
`.harness/release-checks/`: REPORT.md, report.json, progress and individual logs.
All checks must pass and the source manifest must remain unchanged. Timeouts,
empty discovery and missing executables fail. Collection continues after a
failure; nested demo repositories and synthetic approvals remain isolated.

Clean wheel installation is covered by
`tools/clean_install_check.py --wheelhouse PATH`; see PRODUCT_DEMO.md for setup.
Release reports are local evidence, not signed or externally anchored attestations.
No official event eligibility or complete-game claim follows from a harness PASS.

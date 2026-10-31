# ember-courier-harness

**Ember is a local game-development workspace:** describe a browser game, review the proposed changes, play it, and iterate with Muse. Its contract-driven harness keeps file writes, approvals, evidence and recovery tied to the exact work you reviewed. **Ember Courier** is the separate sample workflow demonstrating the contract library.

This repository contains the local app, Python contract library, regression tests, browser rehearsals and architecture. Browser games are supported; private engine code and production assets are not included. The broader engine and asset-production pipeline remain specifications.

## Run Ember

Requires Python 3.12+ and Git. From this repository:

```powershell
py -3.12 -m pip install -e .
py -3.12 -m ember_harness.local_ui
```

On Windows, you can also run **Start Ember.cmd**. Open the printed private launch link, create or reopen a named session, and describe an original browser game. Muse chat requires an installed, signed-in Muse CLI and the configured promotional-credit allowance.

1. Save a **Project brief** with the goal, controls, visual direction and constraints.
2. Review the proposal and choose **Try proposed changes** to play it beside the current game.
3. Choose **Approve & play** to apply those exact changes, or **Request changes** to send feedback.
4. Revisit saved versions, review a restore, or download a verified game ZIP.

See [the local app guide](docs/LOCAL_UI.md) and [builds, previews and versions](docs/CHAT_BUILDS.md).

## Gameplay checks and overnight polish

**Gameplay checks** saves a per-session plan of clicks, key presses, touch taps and observable expectations. Check visible states, text and numeric scores; reports bind to the game version and saved plan. Each scenario starts a fresh isolated game. Canvas-only scores need a visible score element before they can be asserted. See [saved gameplay checks](docs/GAMEPLAY_CHECKS.md).

**Overnight polish** freezes the game, brief and saved test plan inside an upfront-reviewed scope. Ember builds isolated candidates, captures real desktop/mobile browser screenshots, obtains AI critiques, and keeps the strongest qualifying result. Failed required gameplay checks block automatic recommendation even when startup is clean. You review the playable candidates and exact final diff before the current game changes. See [overnight polish](docs/OVERNIGHT_POLISH.md).

These features use optional Node, Playwright and Chromium tooling; [setup instructions](docs/CHAT_BUILDS.md#browser-smoke-checks) describe the developer installation. The Python library and offline release suite do not require Chromium. Browser observations and AI judgments cover their stated checks; human gameplay review is still needed.

## Local data and credit limits

Sessions, generated projects, approvals, captures, reports and exports live under ignored **`.harness/`** paths. They are not included in Git pushes. Game previews use an opaque-origin frame with blocked network access. ZIP exports contain verified game files and a source manifest, without private session history or credentials.

Live Muse requests share Johnathan's authorized **$150 total promotional-credit ceiling**, with bounded reservations, conservative holds for uncertain usage, and no cash fallback or automatic top-up. Running saved gameplay checks, trying proposals, restoring versions and exporting ZIPs do not call Muse. See [models and credits](docs/MODELS_AND_CREDITS.md).

## Verify the project

```powershell
py -3.12 tools/release_check.py
py -3.12 tools/clean_install_check.py --wheelhouse .harness/clean-install-wheelhouse
py -3.12 tools/browser_check.py --playwright-module PATH_TO_PLAYWRIGHT --browser-executable PATH_TO_CHROMIUM
py -3.12 tools/polish_check.py
```

The offline gate runs the full test suite and twelve demos. The clean-install gate builds and tests an installed wheel without checkout package source; prepare its dependency wheelhouse using [these instructions](docs/PRODUCT_DEMO.md#clean-installation-check). Chromium rehearsals use synthetic model replies and approval decisions with real browser input, captures and assertions; they consume no Muse credits. Logs and source hashes stay under `.harness/`. See [the current release plan](docs/RELEASE_PLAN.md) for the latest verified checkpoint and remaining work.

## Contract library and demonstrations

Run the contract tests with `py -m unittest discover -s tests -v` after installing with `py -m pip install -e .`. See [the implementation guide](docs/contracts/IMPLEMENTATION.md) for setup, approval flow, coverage and current limits.

Run `py examples/contract_demo.py` to demonstrate contract approval, allowed and denied actions, and evidence checks that detect a changed file.

Run `py examples/amendment_demo.py` to demonstrate draft amendments, separate widening acknowledgement, supersession, evidence carry-forward, and forward rollback. See [the amendment workflow](docs/contracts/AMENDMENTS.md).

Run `py examples/staged_fix_demo.py` for a real failing regression, gated fix, local Git commit, read-only automated review and verified closure. Use `py -m ember_harness --store PATH contract-lock` to check saved contract history. See [contract-lock and the staged workflow](docs/contracts/CONTRACT_LOCK.md).

Run `py examples/round_demo.py` to add C0–C3 round checkpoints, clean pre-fix/fixed verification checkouts, overlapping-round protection, and an audit-backed report. See [rounds and reports](docs/triage/ROUNDS_AND_REPORTS.md).

Run `py examples/attempt_demo.py` for three failed fix attempts, blocked escalation, and a recorded owner decision allowing exactly one extra attempt. See [attempt limits and escalation](docs/triage/ATTEMPTS_AND_ESCALATION.md).

Run `py examples/intake_demo.py` for bug intake, missing-repro checks, QA-confirmed deduplication, severity review, routing and frozen snapshots. See [intake, deduplication and routing](docs/triage/INTAKE_DEDUP_AND_ROUTING.md).

Run `py examples/reconciliation_demo.py` for owner-approved late duplicate merges, preserved attempt history, blocked retries and a separate one-attempt escalation decision. See [owner reconciliation](docs/triage/OWNER_RECONCILIATION.md).

Run `py examples/reopening_demo.py` for a real closed → reopened → triaged → closed cycle, preserved attempt counts, stale-evidence rejection and a second verified local fix. See [reopening closed bugs](docs/triage/REOPENING.md).

Run `py examples/muse_review_demo.py` for optional review imports and gated intake, or add `--binary PATH_TO_MUSE_EXE` to exercise the installed Muse CLI in no-cost echo mode. This review-capture adapter remains no-cost-only; live chat and overnight polish use the separate credit controls described above. See [Muse review captures](docs/triage/MUSE_REVIEWS.md).

## Start here

- **Local workflow app:** run `py -3.12 -m ember_harness.local_ui`, then open the printed private link. Chat with Muse using the authorized hackathon credits, reopen named sessions, resume checkpointed workflows after a stopped worker, request browser prototypes with inline diff approval, and review sample-workflow approvals in chat. See [`docs/LOCAL_UI.md`](docs/LOCAL_UI.md).

- **Complete product demonstration:** [`docs/PRODUCT_DEMO.md`](docs/PRODUCT_DEMO.md). Run `py examples/product_demo.py` for one shared scope, selected and accepted asset, intake, amended fix, actual regression, local commit and clean verification.
- **Concept selection and asset ingest:** [`docs/concepts/SELECTION_AND_INGEST.md`](docs/concepts/SELECTION_AND_INGEST.md). Run `py examples/asset_demo.py` for the CLI end-to-end demonstration with original PNG fixtures and simulated owner approvals.
- **Intent to scope:** [`docs/contracts/SCOPE_WORKFLOW.md`](docs/contracts/SCOPE_WORKFLOW.md). Use `scope-propose` and `scope-review`, then the existing separate approval command. Run `py examples/scope_demo.py` for the CLI end-to-end demonstration.
- **November 4 priorities and release check:** [`docs/RELEASE_PLAN.md`](docs/RELEASE_PLAN.md). Run `py tools/release_check.py` for the full offline suite and all twelve demo entry points, with retained logs and source hashes.
- **Agents & hard rules:** [`AGENTS.md`](AGENTS.md)
- **Architecture (merged source of truth):** [`docs/architecture/ARCHITECTURE_DRAFT_v4.md`](docs/architecture/ARCHITECTURE_DRAFT_v4.md)
- **Contracts (reading order):** [`docs/contracts/README.md`](docs/contracts/README.md)

Optional area skills (stubs): `.agents/skills/{contracts,pipeline,concepts,triage}/`.

## Documentation tree

| Path | Contents |
|------|----------|
| `docs/architecture/` | Architecture draft v4 |
| `docs/contracts/` | Contract system, schema decisions, fixes, addenda, approval/PR notes |
| `docs/pipeline/` | Pipeline subsystem and iteration addenda |
| `docs/concepts/` | Concept step spec and art direction |
| `docs/triage/` | Triage and code step specs |

## Conventions

- Doc headers that mention `/workspace/...` are historical authoring paths, not paths in this repo.
- Technical content is unchanged from the sanitized docs pack; `[UNVERIFIED]` markers are kept where present (e.g. Meta model or rules claims until checked against official event materials).
- Contract tests use prefixes: `CT-` contracts · `CS-T` concept · `PL-` pipeline · `TR-` triage.

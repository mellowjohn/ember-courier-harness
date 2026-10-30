# ember-courier-harness

Public documentation for a **contract-driven game development harness**, demonstrated on the sample game **Ember Courier**. Prepared for Johnathan Rossi's Meta Global AI Developer Hackathon entry (Track 1, indie, solo).

This repository contains the public architecture and a local Python implementation of the contract schema, approval gate, evidence verification, versioned amendments, local triage workflows, and manual concept selection and asset ingest. It does not include private engine code or production game assets. The broader concept generation and production pipeline remain specifications.

Run the contract tests with `py -m unittest discover -s tests -v` after installing with `py -m pip install -e .`. See [the implementation guide](docs/contracts/IMPLEMENTATION.md) for setup, approval flow, coverage and current limits.

Run `py examples/contract_demo.py` to demonstrate contract approval, allowed and denied actions, and evidence checks that detect a changed file.

Run `py examples/amendment_demo.py` to demonstrate draft amendments, separate widening acknowledgement, supersession, evidence carry-forward, and forward rollback. See [the amendment workflow](docs/contracts/AMENDMENTS.md).

Run `py examples/staged_fix_demo.py` for a real failing regression, gated fix, local Git commit, read-only automated review and verified closure. Use `py -m ember_harness --store PATH contract-lock` to check saved contract history. See [contract-lock and the staged workflow](docs/contracts/CONTRACT_LOCK.md).

Run `py examples/round_demo.py` to add C0–C3 round checkpoints, clean pre-fix/fixed verification checkouts, overlapping-round protection, and an audit-backed report. See [rounds and reports](docs/triage/ROUNDS_AND_REPORTS.md).

Run `py examples/attempt_demo.py` for three failed fix attempts, blocked escalation, and a recorded owner decision allowing exactly one extra attempt. See [attempt limits and escalation](docs/triage/ATTEMPTS_AND_ESCALATION.md).

Run `py examples/intake_demo.py` for bug intake, missing-repro checks, QA-confirmed deduplication, severity review, routing and frozen snapshots. See [intake, deduplication and routing](docs/triage/INTAKE_DEDUP_AND_ROUTING.md).

Run `py examples/reconciliation_demo.py` for owner-approved late duplicate merges, preserved attempt history, blocked retries and a separate one-attempt escalation decision. See [owner reconciliation](docs/triage/OWNER_RECONCILIATION.md).

Run `py examples/reopening_demo.py` for a real closed → reopened → triaged → closed cycle, preserved attempt counts, stale-evidence rejection and a second verified local fix. See [reopening closed bugs](docs/triage/REOPENING.md).

Run `py examples/muse_review_demo.py` for optional review imports and gated intake, or add `--binary PATH_TO_MUSE_EXE` to exercise the installed Muse CLI in no-cost echo mode. Live credit-consuming runs are blocked pending enforceable budget controls. See [Muse review captures](docs/triage/MUSE_REVIEWS.md).

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

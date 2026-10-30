# AGENTS.md — ember-courier-harness

Contract-driven game-dev harness; demo sample game **Ember Courier**. Read `docs/architecture/ARCHITECTURE_DRAFT_v4.md` first.

## Hard rules
- **Deny by default.** The gate rejects any action not allowed by the active, approved contract.
- **Johnathan approves** every contract and amendment (and accepts each asset, even under `approve_all`).
- **Muse credit budget (Johnathan, Oct 30 2026):** Muse may use up to **$150 total in free promotional credits**, shared across all sessions and restarts. No out-of-pocket charges, paid fallback, automatic top-up, or spending beyond that ceiling. Verify and track credit usage before enabling live Muse calls; reserve a bounded maximum per call so concurrent or interrupted runs cannot exceed the budget. Ordinary cash `spend_usd` remains 0. This exception supersedes earlier blanket $0/no-credit-use prose only for Muse free credits; contract and action approvals still apply.
- **No publish, no submit, no deploy, no force push, no merging PRs.** Denied in both approval modes.
- **D44:** closing S0/S1 bugs still needs Johnathan's own approval under `approve_all` (his decision, Oct 23 2026).
- `git.open_pr` only when the coding contract template lists it (contract's own branch, non-force). Pipeline contracts never list `git.push` or `git.open_pr`.
- `art_direction` is inherited from the approved scope contract; every build contract is a subset of the scope contract.
- No secrets, keys, or tokens in the repo. No copyrighted or trademarked material.
- Meta model and rules claims marked [UNVERIFIED] stay so until checked against the official event page.

## Status
Concept, pipeline, and triage docs are documentation-only until Meta agents build them.

## Test ID prefixes
`CT-` contracts · `CS-T` concept step · `PL-` pipeline · `TR-` triage.

## Docs
`docs/contracts/` · `docs/pipeline/` · `docs/concepts/` · `docs/triage/` · `docs/architecture/`

## Repository hygiene

For workflow, demo, test and dependency changes, follow `.agents/skills/repo-hygiene/SKILL.md`. Reuse existing implementations and keep generated artifacts under ignored `.harness/` paths.

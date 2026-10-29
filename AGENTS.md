# AGENTS.md — ember-courier-harness

Contract-driven game-dev harness; demo sample game **Ember Courier**. Read `docs/architecture/ARCHITECTURE_DRAFT_v4.md` first.

## Hard rules
- **Deny by default.** The gate rejects any action not allowed by the active, approved contract.
- **Johnathan approves** every contract and amendment (and accepts each asset, even under `approve_all`).
- **Spend $0.** `spend_usd` is 0; any spending call is `deny`.
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

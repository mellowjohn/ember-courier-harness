# AGENTS.md — contracts

Scope: contract schema, compiler, gate, evidence, audit, approval. Parent: [`../../AGENTS.md`](../../AGENTS.md).

## Reading order

Follow [`README.md`](README.md) in this folder:

1. `CONTRACT_SYSTEM.md` — base spec (schema, gate, evidence, audit)
2. `SCHEMA_DECISIONS_v0.2.md` — wins over Part 1 of the held spec where they differ
3. `CONTRACT_FIXES_v0.3.md`
4. `CONTRACT_ADDENDUM_v0.4.md` — scope contract, `art_direction`, `art_score`, CT-46..49
5. Notes: `APPROVAL_MODE_AND_PR_NOTE.md`, `TOOL_REGISTRY_NOTE_pipeline.md`

Architecture merge: `../architecture/ARCHITECTURE_DRAFT_v4.md` Part 1 + Appendices 1A–1C.

## Agent role

- **Propose drafts only.** Agents do not approve contracts, compute canonical hashes for approval, or write **approved** files under runtime `contracts/**` (D35). Approved bytes are hash-locked; edits require a new version via the harness compiler/amend flow.
- **Deny by default.** If an action is not in `allowed_actions` / `allowed_paths` for the active approved contract, assume **deny**.

## Approval modes

- Field: `approval_mode` — `each` (default) or `approve_all` (hashed, shown in summary).
- Under `approve_all`, listed `needs_approval` actions may auto-resolve to `allow` with audit entries — **except** contract approve/amend, widening, **S0/S1 bug closes (D44)**, and all baseline denies (publish, submit, spend at $0, force push, deploy, unlisted actions).
- Full rules: `APPROVAL_MODE_AND_PR_NOTE.md`.

## Git actions

- **`git.open_pr`:** Coding template only; non-force push of the contract branch + open PR; evidence includes PR URL and commit id.
- **Bare `git.push`:** Unlisted → deny unless explicitly listed (unusual).
- **`git.merge_pr`:** Not in scope → deny.
- **Pipeline contracts:** Must **not** list `git.push` or `git.open_pr` (root hard rule).

## Evidence and gate

- Gate order and steps: `CONTRACT_SYSTEM.md` + schema addendum tests **CT-13–CT-25**.
- Every call (including deny) appends audit; audit write failure → deny (fail closed).
- Step done = required evidence satisfied; see `required_evidence` per action.

## Verification

Acceptance tests use prefix **`CT-`** (CT-1 through CT-45 across addenda). Run or implement against those ids when building the contract subsystem.

## Do not

- Store secrets, API keys, or tokens in contract JSON or this repo.
- Remove **[UNVERIFIED]** from Meta or hackathon-dependent requirements without official confirmation.

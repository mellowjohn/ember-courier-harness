# AGENTS.md — ember-courier-harness

Entry point for coding agents working in this repository. Cursor merges this file with nested `AGENTS.md` files under `docs/`; **the closest file to your working directory wins on conflict**.

## Project overview

- **What this is:** A **contract-driven game development harness** — deny-by-default gate, hash-locked contracts, evidence per step, hash-chained audit — demonstrated on the sample game **Ember Courier** (public docs use that name; architecture text may still say Wrathful Conquest for the full-game context).
- **What this repo is:** **Documentation only** until Johnathan builds the harness with Meta's agents. There is no runtime gate, compiler, or engine code here — only specs under `docs/`.
- **Who approves:** **Johnathan** approves every contract and amendment and accepts each asset (even under `approve_all`).

## Read order

1. **Always first:** `docs/architecture/ARCHITECTURE_DRAFT_v4.md` — merged source of truth (decisions D1–D45, Parts 1–11, open questions Part C, UNVERIFIED register Part D).
2. **Then the subsystem** that matches the **active contract** you are implementing or reviewing:
   - Contract system → `docs/contracts/` (see `docs/contracts/README.md` for file order)
   - Concept step → `docs/concepts/`
   - Production pipeline → `docs/pipeline/`
   - Triage / coding → `docs/triage/`
3. **Nested agent guides** (scope-specific rules): see [Nested AGENTS.md](#nested-agentsmd) below.

Do not paste or duplicate whole architecture chapters into issues or PRs; **cite paths and section names** instead.

## Hard rules

These apply in every subsystem. The gate enforces them at runtime; in this repo, treat them as non-negotiable design law.

- **Deny by default.** The gate rejects any action not allowed by the active, approved contract.
- **Johnathan approves** every contract and amendment (and accepts each asset, even under `approve_all`).
- **Spend $0.** `spend_usd` is 0; any spending call is `deny`.
- **No publish, no submit, no deploy, no force push, no merging PRs.** Denied in both approval modes.
- **D44:** closing **S0/S1** bugs still needs Johnathan's own approval under `approve_all` (his decision, Oct 23 2026).
- **`git.open_pr`** only when the **coding** contract template lists it (contract's own branch, non-force). **Pipeline contracts never list `git.push` or `git.open_pr`.**
- **`art_direction`** is inherited from the approved scope contract; every build contract is a subset of the scope contract.
- **No secrets, keys, or tokens** in the repo. No copyrighted or trademarked material.
- **Meta model and rules claims** marked **[UNVERIFIED]** stay so until checked against the official event page.

Details: `docs/contracts/APPROVAL_MODE_AND_PR_NOTE.md`, `docs/contracts/CONTRACT_SYSTEM.md`, architecture Part 12 (D32–D45).

## Approved contracts (runtime layout)

When the harness exists, approved contract versions live as **system files** under `contracts/` (see architecture D35, Part 7). Agents **never write approved bytes** under `contracts/**` — listing that path in `allowed_paths.write` is invalid; attempts are **deny** (CT-42, GT-10).

Agents may produce **drafts and proposals** only (for example compiler input, amendment proposals under paths like `triage/amendments/` as specified in the triage/contract docs). Approval, hash lock, and promotion to `approved` are harness steps, not agent tools.

This public repo holds **specs in `docs/`**, not live `contracts/` JSON.

## Verification and done criteria

Work is not "done" on intent alone:

1. **Gate first:** Every action goes through `check(action)` against the active approved contract before side effects.
2. **Evidence:** A step completes only when **`required_evidence`** for that action exists and passes verification (`verify_evidence`); missing or failing evidence → **`incomplete`**, never silently passed.
3. **Audit:** Decisions and evidence attach to the hash-chained audit log (fail closed if the log write fails).
4. **Tests:** Use the subsystem's acceptance tests as done criteria (`CT-*`, `CS-T*`, `PL-*`, `TR-*`, plus `IT-`, `GT-`, `WS-`, `OR-`, `TP-` where architecture Parts 6–10 apply).

Pointers: `docs/contracts/CONTRACT_SYSTEM.md` (gate, evidence, audit); architecture "Decisions made" and Part B for cross-spec consistency.

## Test ID prefixes

| Prefix | Subsystem |
|--------|-----------|
| `CT-` | Contract system |
| `CS-T` | Concept step |
| `PL-` | Pipeline (including `PL-R` iteration tests) |
| `TR-` | Triage and coding |
| `IT-`, `GT-`, `WS-`, `OR-`, `TP-` | Architecture Parts 6–10 (iteration, git, workspace, orchestration, transparency) |

## Nested AGENTS.md

| Path | When to read |
|------|----------------|
| [`docs/architecture/AGENTS.md`](docs/architecture/AGENTS.md) | Architecture-wide context, decisions vs open questions |
| [`docs/contracts/AGENTS.md`](docs/contracts/AGENTS.md) | Schema, gate, approval modes, proposing contracts |
| [`docs/pipeline/AGENTS.md`](docs/pipeline/AGENTS.md) | Pipeline steps, worker/verifier contracts |
| [`docs/concepts/AGENTS.md`](docs/concepts/AGENTS.md) | Step A, art direction, Johnathan picks |
| [`docs/triage/AGENTS.md`](docs/triage/AGENTS.md) | Bugs, fix contracts, closure, D44 |

## Status

Concept, pipeline, and triage docs are documentation-only until Meta agents build them.

## Docs map

`docs/architecture/` · `docs/contracts/` · `docs/pipeline/` · `docs/concepts/` · `docs/triage/`

Human-readable index: root [`README.md`](README.md).

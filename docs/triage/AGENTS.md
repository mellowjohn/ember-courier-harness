# AGENTS.md — triage

Scope: bug triage + **coding under contract**. Parent: [`../../AGENTS.md`](../../AGENTS.md).

## Primary docs

| File | Role |
|------|------|
| `TRIAGE_AND_CODE_SPEC.md` | Held triage + fix-contract spec |
| `TRIAGE_ADDENDUM_ITERATION.md` | Rounds, amendments, iteration |
| `TRIAGE_PROPOSED_FIXES.md` | Proposed fixes |

Merged: `../architecture/ARCHITECTURE_DRAFT_v4.md` Part 4 + Appendix 4A.

## Flow (summary)

Intake → dedupe → severity **S0–S3** (+ demo-impact) → repro gate → routing → **fix contract** draft → coding agent (allowed paths only) → **reviewer ≠ author** → local commits → **closure gate** + regression index.

## D44 — S0/S1 closure (critical)

**Closing S0 or S1 bugs always requires Johnathan's approval**, even when the active contract uses **`approve_all`**. This is decision **D44** (Oct 23 2026). Do not auto-close or treat severity downgrade as substituting for his sign-off on S0/S1.

Other severities follow the contract's `approval_mode` and `requires_approval` as defined in `../contracts/APPROVAL_MODE_AND_PR_NOTE.md`.

## Coding under contract

- Edits only inside an **approved fix contract** (paths, tests, lint).
- **Local commits only** on the contract branch; **`git.open_pr`** only if the **coding** template lists it (see root `AGENTS.md`).
- **No push, deploy, publish, submit** without Johnathan (deny in both approval modes).

## Amendments and proposals

- Agents propose amendments via paths/tools defined in architecture Part 6/7 (e.g. `triage/amendments/*.json` proposals) — not direct writes to approved `contracts/**`.
- Compiler `amend()` is a harness step; agents supply untrusted proposal input only.

## Verification

Acceptance tests: prefix **`TR-`** (TR-1–TR-43). Contract tests **`CT-`** apply where triage touches gate behavior (e.g. CT-42 contracts not agent-writable).

## Agents in this folder

- This public repo has **no** `triage/` runtime tree — specs only.
- No secrets in bug snapshots, logs, or repro artifacts committed to git.

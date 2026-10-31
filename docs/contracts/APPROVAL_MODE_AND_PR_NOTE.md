> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Approval mode and PR-implies-push (Contract Smith, 2026-10-23)
Documentation only. Held specs untouched. Gate order (9 steps, first match wins) unchanged.
Source: Johnathan's decisions relayed by Ultralord via Hack Lead, Oct 23 7:00 PM ET (approval-mode setting; git-based rollback; contracts as harness-stored system files; harness may create scaffold files, commits and PRs; OPA no-go).

## 1. `approval_mode`: `each` (default) | `approve_all`
- **Where it lives:** a contract field `approval_mode`, hashed into `content_hash` and shown in the approval summary. Johnathan sets it when he approves a version. Changing it means a new version (an amendment), and moving from `each` to `approve_all` counts as a widening, so it needs his separate widening acknowledgement.
- **What it changes:** only gate step "needs_approval". Under `approve_all`, a `needs_approval` result for an action that is **listed in the approved, active version's `allowed_actions` and `requires_approval`** auto-resolves to `allow`.
- **What it never changes (still deny):** baseline forbidden actions, `deploy.*`, `network.*`, publish, submit, any spend while the limit is $0, actions not in `allowed_actions`, paths outside `allowed_paths`, exceeded limits, and any action checked against a `draft`, `revoked` or `superseded` version. Drafts have no authority.
- **Never auto-resolved (always prompt):** approving or amending a contract, any widening (including switching to `approve_all`), and S0/S1 bug closes. Publish, submit, spend at $0, force push and `deploy.*` stay `deny` in both modes.
- **Audit log:** each auto-resolution writes `kind: decision` with `outcome: allow`, `resolved_by: approve_all`, `contract_id`, `version`, `content_hash`, and the action, plus a `kind: approval` entry citing the version's original approval record (who, when, quoted words). The transparency viewer marks these "auto-approved under approve_all", separate from "approved by Johnathan".
- **Revocation:** revoking the version, or a new version with `approval_mode: each`, ends auto-resolution at once, with no grace period.

## 2. `git.open_pr` implies push
- Confirmed with one addition. There is one action, `git.open_pr`, class `push`. It performs a **non-force** push of the contract's own branch only (`branch` constrained with `equals` to the contract's branch name, `force: false`), then opens a PR against a target named in the contract (`base` `equals`).
- It's listed only in the coding template. Under `approval_mode: each` it is `needs_approval`. Under `approve_all` it auto-resolves to `allow` when the approved, active version lists it (per Ultralord's correction, Oct 23 7:01 PM ET, following Johnathan's decision that the harness may create commits and PRs). Force push, `deploy.*`, publish, submit and any spend deny in both modes.
- Bare `git.push` stays unlisted: `deny` unless a contract lists it. The harness never pushes outside `git.open_pr`. Merging (`git.merge_pr`) is not covered here, so it's `deny`.
- **Evidence:** `output_snippet` with the PR URL, the head commit id and the `Contract-Version` trailer.
- **Audit log:** every resolution writes a `kind: decision` record with `approval_mode` (`each` or `approve_all`) and `resolved_by` (Johnathan's quoted yes, or `approve_all` plus a link to the version's approval record).
- **Rollback (git-based):** a revert commit or PR on the contract branch under a new amendment version. Contracts are stored by the harness as system files under `contracts/`.

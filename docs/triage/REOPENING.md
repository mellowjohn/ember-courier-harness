# Reopening closed bugs

Implements the merged architecture Part 4 lifecycle and Appendix A transition `closed -> reopened -> triaged` (architecture lines around 1884). Attempt counts remain governed by D18 / IT-11, and every S0/S1 closure remains subject to D44. The architecture names the transition but does not specify its request format; the QA permission, state-hash checks and fresh snapshot rule below are implementation choices.

## Flow

1. Use an intake-managed canonical bug whose latest audited state and attempt ledger are both closed. A duplicate alias, open bug or repeated reopen request is refused.
2. A distinct QA reviewer needs an active approved verifier contract with `extensions.triage.review_role: QA` and a `triage.reopen` write permission for that bug path. The reviewer must differ from both the intake author and the latest fix author. Supply the current bug record hash, attempt state hash and a nonblank recurrence reason describing the reported recurrence/build.
3. One durable `state_transition` records the reopened bug, prior closure sequence, recurrence note, incremented reopen count and attempt-state link. Bug state becomes `reopened`, assigned to QA. The note is labeled `self_reported`; this action records QA's attestation and does not claim an automated reproduction ran.
4. Submit a fresh finding through `bug-ingest --update` against the reopened record hash. Complete, eligible findings return to `triaged`; incomplete findings remain with QA as `needs_repro`, and severity/routing restrictions still apply. Severity review or duplicate merging cannot substitute for this fresh intake step.
5. Freeze a new current bug snapshot and approve a new fix contract. Snapshots from before the latest reopening, or snapshots superseded by subsequent intake changes before a new approval, cannot authorize the new attempt. Existing frozen files and approved contracts are not rewritten.
6. Close again through the normal closure gate with a newly allocated fix attempt, fresh reproduction, fix, review and verification evidence after reopening, and named pre-fix/fixed commits. A previous fix or old closure evidence cannot close the new cycle. S0/S1 still requires Johnathan even under `approve_all`.

## Preserved history and limits

Reopening retains the previous closure entry, its successful attempt and all earlier failed or abandoned attempts. It records `last_reopened_seq` without changing any original attempt status or number. New attempts continue at the next ordinal. At three spent attempts, reopening leaves the budget `awaiting_decision`: Johnathan must separately authorize exactly one extra attempt with `attempt-decide`. Reopening is not a retry permission.

Attempt-budget status may be `ready` while the intake bug is `reopened`; that only means slots remain. Fresh intake and a fresh snapshot are still mandatory for approval. Reopened and retriaged bugs can participate in owner reconciliation; their successful history remains part of the combined budget. Bugs still awaiting fresh intake cannot be merged. Repeated close/reopen cycles retain the latest closure and accumulated reopen count.

The audit is authoritative. Audit-write failure accepts neither the bug-state nor budget transition. A cache-write failure reports a warning after durable acceptance. Contract-lock reconstructs reopening from the historical closed record, checks reviewer authority, gate arguments, recurrence note, exact resulting record and attempt hash, and checks new fix snapshots at their historical approval point. Reports include reopening provenance and show `awaiting_fresh_triage` until intake resumes.

This flow applies to bugs already managed by the local intake adapter. Importing legacy standalone closed records is not included. QA and owner attribution comes from the trusted local host; the audit does not authenticate a person's identity.

## Commands

```powershell
py -m ember_harness --store STORE bug-show BUG-0001 --root TRIAGE_ROOT
py -m ember_harness --store STORE attempt-status BUG-0001
py -m ember_harness --store STORE bug-reopen BUG-0001 --root TRIAGE_ROOT --contract QA_CONTRACT --expected-hash BUG_HASH --state-hash ATTEMPT_STATE_HASH --reason "QA reports the reward regression on build BUILD"
py -m ember_harness --store STORE bug-ingest recurrence.json --root TRIAGE_ROOT --contract INTAKE_CONTRACT --update BUG-0001 --expected-hash REOPENED_RECORD_HASH
py -m ember_harness --store STORE bug-snapshot BUG-0001 ct-fix-reopened-0002 --root TRIAGE_ROOT
py -m ember_harness --store STORE attempt-report BUG-0001
py -m ember_harness --store STORE contract-lock
py examples/reopening_demo.py
```

The demo uses explicit fixture approvals and a fixture bootstrap to introduce a later recurrence on an untested coin count. Both fix cycles actually execute failing and passing regressions, run a distinct read-only structural checker, and create local commits. The second closure runs both the registered original regression and the expanded regression. It demonstrates refusal before retriage, refusal of the old fix/evidence and a second closure at attempt two. No human or independent AI review is claimed.

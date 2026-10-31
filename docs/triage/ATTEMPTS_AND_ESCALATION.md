# Three-attempt limit and owner escalation

This implements the **per-bug triage** circuit breaker in merged architecture
Part 6 sections 2.1/2.5, IT-11, D18 and OR-11. The later architecture decisions
override the older TR-33 wording: **Johnathan**, not Hack Lead, decides whether
to continue after the limit. Pipeline per-step/slug limits remain a separate
adapter slice; no pipeline execution exists in this implementation.

## Run the demo

```powershell
py examples/attempt_demo.py
```

The isolated demo runs actual failing Python regressions for three approved
candidate fixes. It shows attempt 1 amended from v1 to v2 without allocating
another attempt, attempt 4 refused under `approve_all`, the same count after
restart, a failed contract denied further actions, an agent's escalation request
refused, and owner STOP/RETRY decisions recorded as explicit demo fixtures.
RETRY authorizes just attempt 4. After that candidate fails, attempt 5 is refused
until a fresh owner decision. The ending state is `awaiting_decision`, not closed.
No failure count is erased. Its report links the audit-derived attempt history.

## Identity, allocation and outcomes

A fix attempt is one coding/worker contract for one canonical `BUG-NNNN` ID.
At approval the harness resolves that identity from a frozen `bug_snapshot`
input with a non-null SHA-256. If `extensions.triage.bug_id` is present, it must
match. The approval entry receives harness-computed `bug_attempt` metadata:
`bug_id`, ordinal `number`, and an optional owner `escalation_ref`.
Agents cannot pick or reset those numbers through extension fields or filenames.

The counter comes from the audit across all contract IDs and versions for the
same bug. New rounds and restarts do not reset it. An amendment retains the
same attempt; changing/removing the bug identity is refused. A `derived_from`
successor cannot claim a different bug to escape its ancestor's limit. Distinct
canonical bug IDs have distinct budgets. [Intake candidate detection and QA confirmation](INTAKE_DEDUP_AND_ROUTING.md)
now supplies canonical aliases; confirmed duplicates cannot obtain a separate
budget. Late merges with allocated histories require owner reconciliation.

At most one unfinished attempt is allocated for a bug. A new attempt needs its
own contract approval and an outcome for the previous attempt. Successful
verified closure marks its fix attempt `succeeded` and the bug `closed`.
Revoking an unfinished attempt marks it `abandoned` and consumes its ordinal;
repeated revocation is not a way to reserve fresh free attempts. Consequently,
three allocated attempts with no success require an owner decision even if
some were abandoned rather than failed. Reports show started and failed counts
separately.

The gate denies work under a failed, abandoned or succeeded attempt regardless
of `approve_all` or an old one-time action approval. A finished attempt cannot
be reactivated by approving an amendment, even after owner escalation. Continued
work uses a new fix contract ID. Round planning rejects finished fix attempts.
Contracts retain their ordinary contract status for history; their separate
attempt outcome removes work authority.

## Recording a failed attempt

Test reruns are not automatically whole failed fix attempts. The architecture
allows cheap reruns under one approved contract, and the baseline reproduction
must fail without consuming a completed-failure verdict. The trusted host
explicitly finalizes a candidate after a captured regression failure:

```powershell
py -m ember_harness --store PATH attempt-fail CONTRACT_ID --execution-seq 12 --reason "Candidate still fails the regression"
py -m ember_harness --store PATH attempt-status BUG-0042
```

`Attempts.fail()` requires an active tracked fix version, a captured assertion
failure from its approved pinned test script, and earlier complete file-hash
evidence for its allowed UTF-8 `fs.write` edit. The captured regression input
must match both that edited path and its approved written bytes. A baseline
repro, passing test, stale version, another contract's execution, duplicate
verdict or tampered evidence cannot finalize a failure. A retry under the same
running contract remains possible until it is finalized or exhausts its call
budget. After finalization, a fresh fix contract is required.

This initial adapter finalizes assertion-based Python regression failures and
verified text edits. It does not infer a whole-attempt failure from a timeout,
syntax error, arbitrary command output or human review. Other failure providers
need their own trusted evidence adapter. Revocation is available to abandon a
candidate without fabricating a failed-regression verdict.

## Owner escalation

After the third allocated attempt finishes without success, the bug status is
`awaiting_decision`. Approval of another fix contract is refused. Drafting a
fourth contract does not grant rights, and the prior finished contracts remain
denied. Only the trusted human-facing approval interface can record the owner
decision; it is never an automatically resolved gate action.

`attempt-status` returns a `state_hash` of the current attempt state. Johnathan
reviews that state and chooses **retry** (one additional new attempt) or **stop**:

```powershell
py -m ember_harness --store PATH attempt-decide BUG-0042 --choice retry --state-hash HASH --quote "Recorded owner decision"
py -m ember_harness --store PATH attempt-decide BUG-0042 --choice stop --state-hash HASH --quote "Recorded owner decision"
```

The corresponding API is
`Attempts.decide(bug_id, choice=..., expected_state_hash=..., approver="johnathan", quote=...)`.
It records a distinct human `approval` entry with scope `attempt_escalation`
and a content-addressed `reviewer_note`. The note is labeled `self_reported`.
The entry binds bug ID, decision-state hash and the next attempt number. Agent
actors, blanket `approve_all`, blank wording, stale hashes and duplicate decisions
are rejected. Incidental audit entries do not invalidate an otherwise unchanged
decision state.

RETRY supplies one credit consumed atomically by the next successful contract
approval. It does not approve that contract, widen its scope, revive old attempts,
change `max_calls`, erase history, or permit paid/publish actions. If the extra
attempt fails or is abandoned, another decision is required. STOP leaves work
blocked; Johnathan may later reconsider using a fresh hash-bound RETRY decision.
Failed audit writes grant no credit, allocate no attempt and record no failure.

The interface records the trusted host's attribution; it does not authenticate
human identity or send a message through Ultralord. A relay would need to pass
the actual owner decision through this host interface. Demo owner decisions are
explicit fixtures, not permissions for production work.

## Reports and verification

```powershell
py -m ember_harness --store PATH attempt-report BUG-0042
py -m ember_harness --store PATH contract-lock
```

`attempt-report` writes `triage/report/BUG-NNNN-attempts.md` with attempt outcomes,
contract versions, audit bases and owner decisions. Round reports also include
attempt counts as of the round checkpoint. `contract-lock` now verifies allocation
order, failure witnesses, owner-note references, actor/version/hash binding and
one-credit consumption. Broken proof yields an integrity error rather than a
verified escalation history.

Existing stores with pre-feature bug-fix approvals lack attempt bindings. Their
fix actions fail closed with `attempt_tracking_required`, and `contract-lock`
requires explicit migration. They are not silently assigned a reset budget.
Newly generated demos and stores enroll automatically. No migration command is
included in this slice.

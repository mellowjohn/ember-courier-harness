# Rounds, clean verification and audit-backed reports

This slice implements the merged architecture's Part 6 section 2.6 and the
round/report portions of the triage iteration addendum. Checkpoints are trusted
host operations, not agent tools that can assert completion.

## Demo

```powershell
py examples/round_demo.py
```

The demo runs the staged bug fix inside round 1, with real detached Git worktrees
for the broken baseline and fixed commit. Both checkout locations and their
scripts are explicitly covered by the approved verifier contract. The verifier
has a distinct fixture identity and no write paths. Its scripts and frozen bug
snapshot are pinned inputs. Review remains a deterministic automated structural
check, not human or independent AI peer review.

The demo rejects an overlapping round and premature C3, then completes C0–C3.
It produces both the execution summary and a generated report under
`sample/control/triage/report/round-1.md`. Approval entries apply only to the
isolated demonstration authorized by the user. The fixed source is committed
locally; nothing is pushed or published.

## Plan and checkpoints

`Rounds(harness)` provides these trusted host APIs:

| Operation | Conditions and recorded proof |
|---|---|
| `start(tasks)` / C0 | One or two tasks; unique bug, worker and branch; active approved versions; distinct read-only verifier; fixed worker branch; pinned bug snapshot/severity; task-list SHA-256. |
| `reviewed(round, bug_id, build, review_seq)` / C1 | Captured passing review under the planned verifier; complete review evidence; reviewed Git commit; passing Git-aware contract-lock; clean fixed checkout whose input bytes match that build. |
| `verified(round, bug_id, repro_seq, verify_seq)` / C2 | C1 exists; verifier runs after planning/C1 in order; the same regression script fails with an assertion on the clean baseline and passes on the clean fixed commit; both evidence steps complete. |
| `close(round, next_round=[])` / C3 | Every task has C1/C2 and a matching later verified bug closure; current worker source/build and verification checkouts still match; S0/S1 closure must cite Johnathan's own action approval. Records closure references, next-round bugs and push decision `not_requested`. |
| `abandon(round, reason)` | Open round and nonempty reason; records terminal abandonment without closing its bugs. |
| `status(round)` | Reconstructs status, checkpoint sequences and task plan from the verified audit log; ignores editable round cache. |

Statuses are `planned`, `in_progress`, `awaiting_approval`, `complete`, or
`abandoned`, always with an audit `status_basis`. A task's C2 is not a closed
bug or a completed round. Duplicate/out-of-order checkpoints are refused. New
rounds cannot start until the previous round is complete or abandoned. A later
round needs contracts pinned to its own branch. Revoking, superseding or expiring
a planned contract blocks further checkpoints; abandon the old plan and prepare
fresh approved contracts rather than silently replacing its versions.

The audit is authoritative. `triage/rounds/round-NNNN.json` is a derived cache.
After a durable checkpoint, cache-write errors are returned as `cache_warning`;
the checkpoint remains recorded. Audit-write failure never records completion.
C3 also saves its audit head to `audit/anchors/round-N.txt`; retain that head
outside the store if external anchoring is required. The local anchor alone does
not authenticate the log against replacement of the entire store.

## Task shape

`round-start` accepts a JSON array of objects with exactly these fields:

```json
[
  {
    "bug_id": "BUG-0001",
    "severity": "S2",
    "fix_contract_id": "ct-fix-0001",
    "fix_version": 1,
    "verifier_contract_id": "ct-verifier-0001",
    "verifier_version": 1,
    "source_path": "D:/demo/sample/src/reward.py",
    "repo": "D:/demo/sample",
    "base": "<baseline commit>",
    "branch": "round/1/ct-fix-0001",
    "repro_repo": "D:/demo/verify-before",
    "verification_repo": "D:/demo/verify-fixed"
  }
]
```

The host creates the detached checkouts. Checkpoint APIs inspect their clean
status, HEAD, captured input hashes and named Git blobs. They do not accept
caller-supplied "pass" strings as witnesses. This initial adapter uses verifier
action IDs `reproduce`, `review`, and `verify`. The verifier's approved
`extensions.triage` carries `repro_repo` and `verification_repo`, and its inputs
pin the scripts at those concrete paths. The usual closure gate validates both
named source commits and the unchanged regression. It now supports verifier
reproduction on the baseline checkout as well as the earlier worker repro.

## CLI

```powershell
py -m ember_harness --store PATH round-start tasks.json
py -m ember_harness --store PATH round-reviewed 1 BUG-0001 --build COMMIT --review-seq 20
py -m ember_harness --store PATH round-verified 1 BUG-0001 --repro-seq 10 --verify-seq 25
py -m ember_harness --store PATH round-close 1 --next-round BUG-0002
py -m ember_harness --store PATH round-status 1
py -m ember_harness --store PATH round-report 1
py -m ember_harness --store PATH round-abandon 1 --reason "Revise the plan after feedback"
```

Sequence numbers above are examples; use actual captured execution sequences.
Report output defaults to `triage/report/round-N.md`. `--output PATH` writes a
copy elsewhere, with protection against overwriting authority/evidence files.

## Report provenance and current limits

The generated report lists audit-backed checkpoints, contract/version approvals,
allowed and denied decisions, automatic approval versus recorded human action
approval, and machine-checked versus self-reported evidence. Reviewer notes stay
`self_reported`. A damaged evidence payload is `unverified`; integrity failure
prevents a report from labeling the round complete. A broken audit chain refuses
report generation. Editing the round cache cannot promote a planned round.

Checkpoint status is historical at its audit sequence. Reports do not silently
rerun completed work; use `step-status` for current file bytes. They record the
trusted host's approval attribution, not cryptographic proof of a human identity.

This is a sequential local checkpoint runner and report generator. It does not
launch autonomous workers or schedule rounds. [Per-bug attempt caps and owner escalation](ATTEMPTS_AND_ESCALATION.md)
are now enforced across rounds. [Intake, deduplication and routing](INTAKE_DEDUP_AND_ROUTING.md)
now supplies canonical frozen snapshots. Automatic plan amendment, broader review providers,
and actual push/PR decisions remain later slices. The current C3 path explicitly
records `not_requested` for pushes. Test scripts are trusted code, not OS-isolated.

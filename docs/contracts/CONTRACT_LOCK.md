# Local contract-lock and staged fix workflow

This implements the local verifier from merged architecture Part 7 section 2.3
and a small staged closure slice from Part 4. It needs no remote or hosted CI.
The command is read-only: it does not stage, commit, install hooks, push or repair
contract files.

## Commands

```powershell
py -m ember_harness --store PATH contract-lock
py -m ember_harness --store PATH contract-lock --repo REPO --base BASE_COMMIT
py -m ember_harness --store PATH contract-lock --repo REPO --base BASE_COMMIT --message-file commit-message.txt
```

After installing the package, `contract-lock --store PATH` is also available.
All forms report `name: contract-lock`, `ok`, `errors`, and completed checks.
Failure returns exit code 1. Use an explicit base commit for Git checks.
`--message-file` checks staged paths and the prospective commit message; without
it, Git checks inspect commits in `BASE..HEAD`. Bootstrap/setup commits belong
before the chosen base. Run this check manually before a local commit; hooks
and hosted jobs are not installed by this implementation.

## Checks

- Every saved contract validates, its filename matches its identity, and every
  non-draft hash matches its approved content. Historical files retain audit-backed
  status. Approved versions require both the human approval audit entry and the
  matching `approvals/ID-vN.json` record. Missing approved files fail.
- Version numbers have no gaps and at most one approved head exists. Amendment
  records match the audit, retained proposal hash, computed diff, predecessor
  hash, new version, lineage, affected actions and new content hash. Rollbacks
  reconstruct the historical terms. Widening requires a separate, earlier human
  acknowledgement matching the widening and reviewed draft hashes.
- Child scope and inherited art direction match their approval-time parent.
  Evidence payloads and captured execution outputs resolve and match their
  content-addressed references. Optional audit anchors must name a chain entry.
- Git base comparison permits only legal status transitions in previously
  tracked non-draft versions; other edits or deletion fail, including edits to
  approval metadata excluded from the contract content hash.
- A worker commit needs all five trailers: `Round`, `Contract-Id`,
  `Contract-Version`, `Contract-Hash`, `Subsystem`. The version/hash must match
  an approved contract. Its branch is `round/N/ID`; changed paths (including both
  sides of renames) must fit that contract's write paths. Fix metadata also
  requires the bug, author and reviewer in the message; author and reviewer differ.
- Amendment branches use `contract/ID/vN`, with changes limited to that ID's
  contract directory and `approvals/` under the selected store. Similar nested
  folder names cannot bypass this rule. Merge commits are rejected by this
  worker-commit verifier.
- Staged store bytes must match the files just verified, preventing a different
  staged version from hiding behind a valid working copy. Worker file sizes
  are checked from staged/committed blobs against
  `extensions.git.thresholds.max_plain_file_bytes`, default 1 MiB.
- Optional `assets/manifest.json` accepts an array (or `{files: [...]}`) of
  `{path, sha256, size}`. Local bytes are checked; a standard LFS pointer is
  matched by its OID and declared size and labeled `basis: lfs_pointer`,
  `label: self_reported`. It never claims that the underlying asset bytes were
  fetched or verified. Manifest paths must stay within the selected root.

Git checks require the store to be tracked inside the specified repository for
base comparison of contract files. If the store is outside it, its current
history is still verified, but no Git base immutability comparison of that store
is possible. Working copies are checked in their current local path context;
contracts contain absolute paths. Relocating a store is not a portable replay.

The verifier does not authenticate human identities, prevent a trusted host from
replacing the entire unanchored log, or enforce that callers run it before a
commit. Automatic LFS setup, `.gitattributes` generation, hosted checks and remote
repository rules remain out of scope. It does not re-run every historical test
or require old output files to remain unchanged after a later approved fix;
`step-status` provides current-byte evidence checks.

## Staged bug-fix demo

```powershell
py examples/staged_fix_demo.py
```

Each run creates a fresh local Git repository under `.harness/demos/staged-fix-*`
and a Markdown report. It does the following with actual scripts and files:

1. Freeze a BUG-0001/S2 snapshot and approve fixture scope, coding and read-only
   verifier contracts. Regression and review scripts are pinned by SHA-256.
2. Commit the intentionally broken reward function and regression as the local
   bootstrap, then create the contract's own worker branch.
3. Run the regression through the gate; it fails on the pre-fix commit.
4. Reject an edit outside the fix contract. Allow the exact source fix, verify
   its hash, and run the regression again; four input cases pass.
5. Stage the single approved source file, pass `contract-lock`, and make one local
   commit carrying all five trailers plus bug/author/reviewer metadata.
6. Run an automated AST review and the regression under the distinct read-only
   verifier identity. Capture real stdout, stderr, exit status and input hashes.
   A named reviewer note is recorded as self-reported alongside the machine check.
7. Register the regression for the named fix build and pass the closure gate.
   Edited approved contract bytes then demonstrate lock failure; restoring them
   restores a passing lock result.

Closure requires an active fix and distinct read-only verifier, the approved bug
snapshot/severity, an assertion failure before the fix, passing regression/review
after it, the same regression script on both named commits, evidence matching
the current fixed source, a regression index record, complete required evidence,
and a passing Git-aware lock check. Duplicate closure is rejected. Closure calls
the ordinary approval gate, so S0/S1 can never auto-resolve under `approve_all`.

This is a deterministic **automated structural review**, not a human or independent
AI peer review. Demo identities and approval records are fixtures confined to the
user-authorized demonstration. The test runner executes only an approved pinned
script, but trusted test code can access the host: it is not an OS sandbox.

This slice demonstrates a staged bug through closure; it is not the full triage
service. [Intake, deduplication, routing and severity review](../triage/INTAKE_DEDUP_AND_ROUTING.md)
now handles the front of this workflow, including canonical frozen snapshots.
[Attempt limits and escalation](../triage/ATTEMPTS_AND_ESCALATION.md) now tracks fix budgets and owner decisions;
contract-lock verifies those histories and their captured failure proofs.
[Rounds and reports](../triage/ROUNDS_AND_REPORTS.md) now adds
C0–C3 checkpoints and explicit clean verification checkouts. No real
engine code, paid service, push, publish or deployment is involved.

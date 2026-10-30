# Owner reconciliation for late duplicate merges

Implements the architecture's oldest-canonical rule (Part 4 section 2.2) and the per-bug three-attempt limit (D18, Part 6 section 2.5). The architecture does not specify a late-merge transaction; the hash-bound proposal and atomic owner approval below are implementation choices that preserve those rules.

An ordinary QA duplicate confirmation still refuses bugs with allocated attempts. A QA reviewer with an active approved `triage.confirm_duplicate` contract can instead propose reconciliation. The reviewer must differ from both intake authors. This uses the existing duplicate tool permission; proposing a plan consumes a gate call but does not merge records.

The proposal is a content-addressed JSON file under `STORE/triage/reconciliations/HASH.json`, with an audited copy. It includes both current record hashes, both complete attempt states, original contract identities, combined spent count, unused retry permissions to cancel, stop decisions to retain, and the resulting bug records. Johnathan approves that exact hash through the trusted local host. Current bug hashes, attempt states, evidence, QA contract version and authority are checked again at approval. Any change requires a fresh proposal.

One durable audit entry commits the duplicate alias, evidence union, duplicate count and ledger reconciliation together. The oldest bug remains canonical. Attempts are ordered by their allocation entries; the combined projection numbers them sequentially and retains `origin_bug_id` and `origin_number`. Approved contract files, original bindings, captured executions and frozen bug snapshots remain intact. Historical retry decisions are replayed at their original audit position; merging does not reinterpret their hashes.

Both IDs resolve to the combined ledger. Spent slots include failed and revoked/abandoned attempts. A merge cancels all unused retry permissions and preserves any stop decision. At three or more spent attempts, Johnathan must make a separate current-state retry decision before another contract can start. That decision grants exactly one attempt. Merge approval never grants retry authority.

Running attempts must finish or be explicitly revoked before proposing or approving reconciliation. Revocation spends the allocated slot. Closed bugs must use the [reopening flow](REOPENING.md) and fresh intake first. Their historical successes remain counted during reconciliation. Conflicting routes require explicit classification before merging; an engine or non-code route cannot silently gain code-fix authority. Higher severity, pending severity review and demo impact are retained. S0/S1 closure rules are unchanged.

Bug caches are projections: cache-write failure yields warnings after the durable commit. Audit-write failure accepts neither half of a merge. Contract-lock verifies the proposal hash/file, historical QA authority, gate links, current source hashes, exact resulting records and combined attempt history. Attempt reports display original identities and reconciliation provenance.

## Commands

```powershell
py -m ember_harness --store STORE bug-reconcile-propose BUG-0002 BUG-0001 --root TRIAGE_ROOT --contract QA_CONTRACT --bug-hash HASH2 --target-hash HASH1 --note "QA confirms same reproduction"
# Review the returned plan and its hash before owner approval.
py -m ember_harness --store STORE bug-reconcile-approve PLAN_HASH --root TRIAGE_ROOT --quote "Johnathan's recorded approval of this exact reconciliation"
py -m ember_harness --store STORE attempt-status BUG-0002
py -m ember_harness --store STORE attempt-report BUG-0001
py -m ember_harness --store STORE contract-lock
py examples/reconciliation_demo.py
```

The trusted host records approval attribution; it does not authenticate who typed a command. All demo QA, contract and owner approvals are explicitly labeled fixtures. The demo executes real pinned regression scripts against edited source files and retains their failures.

# Contract amendments and versioning

Implemented against the merged architecture's Part 6 (including sections 2.8
and 2.9), Part 12, and the contract addendum's sections 2–3. The held design
documents remain unchanged.

## Run the demonstration

```powershell
py examples/amendment_demo.py
```

The demo runs in a new `.harness/demos/amendments-*` directory each time. It
creates scope and worker v1, consumes v1's one-call budget, proposes a two-call
v2, demonstrates refusal without the separate widening acknowledgement, approves
v2, rechecks evidence without another tool call, rejects a v1-pinned action, and
rolls back through a new v3. Its Markdown report links the computed review and
raw audit log. Demo approvals apply only to the isolated demonstration requested
by the user; production approval methods must stay in a trusted human-facing host.

## Proposal and review

An agent supplies an untrusted proposal, never approved contract bytes:

```json
{
  "reason": "Review feedback requires another attempt",
  "round": 1,
  "source": {"kind": "review", "id": "REV-0001"},
  "changes": [
    {"op": "replace", "pointer": "/limits/max_calls", "value": 2}
  ]
}
```

`source.kind` accepts `bug`, `playtest`, `review`, `manual`, or `pipeline`.
JSON-pointer operations are `add`, `replace`, and `remove`; `~0`, `~1`, array
indices and append (`-`) are supported. `path` is accepted as an alias for
`pointer`. Identity, original intent, approval metadata, version, lineage, and
orchestration metadata are harness-managed and cannot be patched. Agent changes
are allowed but affect all actions. Roles stay fixed for an existing contract;
use a new contract ID for a different role. A renewal can replace the window
with a draft TTL; it is conservatively flagged as widening and must still fit
inside the approved parent when resolved at approval time.

```powershell
py -m ember_harness --store PATH amend CONTRACT_ID proposal.json --proposed-by worker
```

The harness copies the active approved head, computes vN+1, validates it, and
returns the draft, amendment record and field diff. The original `intent_text`
is preserved exactly. Hashed `extensions.lineage` names the predecessor's
version/hash and appends round, reason, source and optional `failing_step`.
Hand-written diff and widening fields in a proposal are ignored. Pending drafts
grant no authority. Only one pending successor exists; `--replace-pending`
explicitly recompiles that draft from the current head, invalidating old review
hashes and acknowledgements. No-op proposals are rejected.

The record lives at `contracts/ID/amendments/vN-to-vN+1.json`. The original
proposal is retained under a content-addressed name in `triage/amendments/`.
Audit entries bind the draft, record and proposal hashes. Editing any of them
prevents approval; recompile the proposal instead of editing derived records.

## Widening and approval

The same conservative `subset()` function checks child scope and amendment
widening. Higher limits, looser actions or evidence, removed forbids/approval
classes, and `each` → `approve_all` require acknowledgement. Unknown extension
changes are conservatively treated as widening and force a rerun, including
threshold changes. The review displays **WIDER THAN USUAL** and the computed
`widening_sha256` (SHA-256 of canonical `widening.items`).

Johnathan's separate acknowledgement is recorded before approval:

```powershell
py -m ember_harness --store PATH acknowledge-widening CONTRACT_ID 2 --widening-hash HASH --quote "Recorded acknowledgement"
py -m ember_harness --store PATH approve CONTRACT_ID 2 --reviewed-hash DRAFT_HASH --quote "Recorded approval"
```

These commands belong to Johnathan or the trusted host relaying his explicit
messages. The acknowledgement binds contract ID, version, widening hash and
draft hash. Wrong hashes, agent actors, and stale acknowledgements are rejected.
An inline acknowledgement on `approve` is no longer accepted. Approval inherits
the existing parent by default; a child still cannot exceed its parent, even
with a widening acknowledgement.

One durable approval entry approves vN+1, supersedes vN, records the acknowledgement
reference, and revokes or rebinds children. Calls reset per version; spending
remains hard-denied at $0, so amendments cannot reset a paid budget. New checks
use the approved head only; pinned old versions deny with `contract_superseded`.
Old one-time action approvals do not carry over. `history ID` returns audit-backed
statuses and `status_basis` sequence numbers. `STATE.json`, historical status
fields and `approvals/ID-vN.json` are derived caches; the audit is authoritative.
Post-commit cache failures are returned as `cache_warning`, never mistaken for
missing approval. Approval audit-write failures grant no new authority and keep
the draft retryable when the log remains intact. A process crash or partial log
write fails closed and requires inspection before recovery.

## Evidence across versions

```powershell
py -m ember_harness --store PATH carry-forward CONTRACT_ID
```

The harness identifies affected actions from the actual old/new terms. Changes
to one action or its evidence affect that action. Global permissions, inputs,
agent, art direction, narrowed limits and unknown extension changes affect all.
A pure numeric budget widening affects none. The latest complete results for
unaffected actions are reverified against current bytes and current requirements,
then recorded under the new version with `carried_from`. No new tool call is
consumed. Changed or missing files become incomplete; tampered stored evidence
is rejected. Input preflight is still required where the new version pins or
late-binds inputs. Carry-forward is an explicit host operation after approval.

Evidence arriving for an action allowed under an older version is recorded as
`late_under_superseded`, with its source version. Completion is judged against
the current version's requirements; newly required items can make it incomplete.
Supersession does not erase the old allowed decision. Removed actions cannot
claim completion under an action ID that no longer exists.

## Forward rollback

Use a proposal with `rollback_to` instead of `changes`:

```json
{
  "reason": "Restore known working terms",
  "round": 2,
  "source": {"kind": "manual", "id": "ROLLBACK-1"},
  "rollback_to": 1
}
```

At head v2 this creates draft v3 with v1's terms and new version, approval
metadata and lineage. Its lineage log records `reason: rollback` and
`rollback_to: 1`. Historical bytes must match their original audit-approved
hash. Widening is computed against the current head, so rollback to broader
terms needs the separate acknowledgement. Superseded and revoked versions are
terminal; nothing reactivates v1. Revoked IDs cannot be amended or reapproved.

These version files can be stored in a Git-tracked directory by selecting
`--store PATH`. Demo stores remain ignored local artifacts. The amendment compiler
does not create Git commits or PRs. [The local contract-lock and staged-fix slice](CONTRACT_LOCK.md)
now checks Git history/trailers and demonstrates a local fix commit. Full orchestration envelopes,
draft withdrawal, and general glob-subset proofs also remain deferred.

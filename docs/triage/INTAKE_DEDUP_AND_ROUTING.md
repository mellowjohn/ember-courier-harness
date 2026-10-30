# Intake, deduplication and routing

Implemented against merged architecture Part 4 sections 2.1–2.5 and the later
contract/triage fixes. Held source specs remain unchanged.

## Demo

```powershell
py examples/intake_demo.py
```

This local demo covers complete intake, missing repro details, completing a
partial record, duplicate proposals and QA confirmation, S0 review, owner routing,
and canonical frozen snapshots. Approvals and QA identities are demo fixtures.
No messages, public posts, paid calls or engine edits occur.

## Findings and gate

`schema/finding.schema.json` requires source (`vision_qa`, `playtest`, `log`) and
a nonblank summary. Optional fields include build/timestamp, area, symptom tag,
build family, steps, expected/actual, frequency, severity, structured impact,
demo-impact, log excerpt, subsystem, error code, stack frames, and local evidence
entries `{path, sha256}`. Unknown fields and malformed values fail validation;
finding JSON is capped at 128 KiB. Finding text is data and never executes tools.

Use an approved standing intake contract: read access to findings/evidence and
write access only to the intake `bugs/*.json` and evidence folder. These data
paths are separate from the harness authority store. `triage.inspect` gates
finding reads; `triage.ingest` gates the concrete read/write set. Evidence hashes
are recomputed, then copies are retained by hash under the intake evidence folder.
Different bytes at an existing evidence path are refused. The standing window
still expires; renewal requires normal contract approval/amendment.

## Completeness and severity

Triaged bugs need build ID, steps, expected, actual, frequency, area and at least
one hashed evidence file. A logs-only crash can substitute its excerpt for steps.
Missing fields produce `needs_repro`, QA ownership and an explicit missing list.
Updates preserve the bug ID and require its current `record_hash`.
Update input is a complete finding rather than a JSON patch; prior evidence and
finding references are accumulated, while supplied repro fields replace them.

Severity is proposed from reported severity and structured impact, taking the
more urgent value. The default is S2. Crash/hang/data-loss/demo-blocking impacts
propose S0, regardless of a lower self-reported rating. S0, changes away from
S0, and demo-impact severity/flag changes require QA confirmation. Pending
review stays `new` and cannot produce a code-fix snapshot. Ratings are labeled
reported/rule-based proposals or `qa_review`; a review note is an attestation,
not verified truth or permission to close a critical bug. Priority is S0,
demo-impact S1, other S1, demo-impact S2, other S2, S3.

## Routing

| Area tags | Owner | Policy |
|---|---|---|
| rendering, physics, crash, performance, engine/code | Engine | Engine pause; code-fix handoff blocked. |
| tools, level/world editing, asset import | Editor | Separate approved fix contract required. |
| repro, verification, regression tests | QA | Separate approved fix contract required. |
| dialogue, quest text, lore | Narrative | Separate approved fix contract required. |
| visual look, VFX, palette | Concept Artist | Separate approved fix contract required. |
| store pages, announcements, public posts | Herald | Non-code work. |
| user/community messages | Comms | Non-code work. |
| balance, crafting, loot, progression | Systems Designer | Separate approved fix contract required. |
| unknown/ambiguous areas | Hack Lead | Assignment queue; no automatic fix handoff. |

Routing records an owner; it never messages agents or creates chats. Severity
review cannot lift the engine pause or authorize publishing/spending.

## Deduplication

Logs fingerprint normalized top-three frames, or error code plus subsystem,
stripping addresses, timestamps and numbers. Visual/playtest findings use area,
symptom tag and explicit build family (exact build ID if no family was supplied).
Text similarity in the same area produces only a labeled hint.

Nothing merges automatically. A distinct approved QA contract (`verifier` role
with `extensions.triage.review_role: QA`) confirms candidates with both current
record hashes and a nonblank note. The oldest ID/title survives; evidence and
finding references are appended, duplicate count increases, and the other record
becomes `duplicate` with `duplicate_of`. Repro/severity requirements remain.

Aliases resolve to the canonical ID for snapshots and public attempt status.
New fix approval rejects a snapshot that still uses an alias. Late merges with
any allocated attempt history are refused pending owner reconciliation; the
adapter never silently drops counters. Use the [owner reconciliation flow](OWNER_RECONCILIATION.md)
for an explicit reviewed merge of terminal attempt histories. Candidate dismissal
remains future work. [Reopening closed bugs](REOPENING.md) is implemented as a separate QA transition followed by fresh intake. Unconfirmed candidates remain
visible proposals in fix-contract review data.

## Audit and fix handoff

Bug IDs are allocated from audit history, including existing attempt IDs. Each
mutation records the normalized record, hash and `status_basis`; ingest normalizes
and classifies in one entry. Bug JSON files are mutable derived caches. Reports
reconstruct the queue from the audit, so editing a cache cannot close or reroute
a bug. Stale review/update hashes fail. Cache-write failures are reported after
durable audit commit; audit failure never creates accepted intake state.

The trusted host's snapshot helper requires canonical, triaged, reviewed-where-
required, code-eligible data and intact evidence. It freezes a hashed file under
`STORE/triage/fix_contracts/CONTRACT_ID/bug_snapshot.json`. It never overwrites
changed bytes. Later bug edits leave existing snapshots/contracts unchanged.
A snapshot grants no source-edit authority: the fix still needs a scoped contract
and Johnathan's approval. Versioned snapshot-amendment helpers remain future work.

`contract-lock` checks intake decision links, record hashes/status bases,
retained evidence and snapshot integrity. Damaged evidence makes reports display
unverified state. The current QA interface records attribution through a trusted
host; it does not authenticate a human or perform independent judgment.

## Commands

```powershell
py -m ember_harness --store STORE bug-ingest finding.json --root TRIAGE_ROOT --contract INTAKE_CONTRACT
py -m ember_harness --store STORE bug-ingest updated.json --root TRIAGE_ROOT --contract INTAKE_CONTRACT --update BUG-0001 --expected-hash HASH
py -m ember_harness --store STORE bug-list --root TRIAGE_ROOT
py -m ember_harness --store STORE bug-show BUG-0001 --root TRIAGE_ROOT
py -m ember_harness --store STORE bug-confirm-duplicate BUG-0002 BUG-0001 --root TRIAGE_ROOT --contract QA_CONTRACT --bug-hash HASH2 --target-hash HASH1 --note "Recorded QA confirmation"
py -m ember_harness --store STORE bug-review-severity BUG-0001 --root TRIAGE_ROOT --contract QA_CONTRACT --expected-hash HASH --severity S0 --demo-impact true --note "Recorded QA review"
py -m ember_harness --store STORE bug-snapshot BUG-0001 ct-fix-0001-0001 --root TRIAGE_ROOT
py -m ember_harness --store STORE bug-report --root TRIAGE_ROOT
```

This slice adds local intake and handoff. It does not fetch remote attachments,
integrate issue trackers, automatically generate fix contracts, launch agents,
or supply an owner-assignment UI.

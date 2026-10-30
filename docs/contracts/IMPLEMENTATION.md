# Contract core: approvals, evidence and amendments

The first local implementation follows the merged architecture's Part 1,
Appendices 1A–1C and Part 12. Later decisions take precedence over the old
push/publish examples. The held specification files retain their original text.

## Run

Python 3.12 or later is required. From the repository directory:

```powershell
py -m pip install -e .
py -m unittest discover -s tests -v
py -m ember_harness --help
py -m ember_harness draft ct-scope-0001 scope-planner "Propose Ember Courier scope" --role scope
```

`draft` prints an empty template and grants no authority. Save its JSON to a file,
fill in the concrete actions, absolute path globs, evidence requirements and game
scope, then use:

```powershell
py -m ember_harness validate scope-draft.json
py -m ember_harness review scope-draft.json
py -m ember_harness save scope-draft.json
```

The human-facing host records approval using `approve ID VERSION
--reviewed-hash HASH --quote WORDS`, adding `--parent SCOPE_ID` for build
contracts. The hash is the exact draft hash returned by `review`; edits invalidate
it. This command must be invoked by Johnathan or a trusted host relaying his
explicit approval. Tests use simulated approval fixtures, which confer no real
authority. No real contract has been approved as part of building this code.

Approval resolves draft TTL windows, hashes the resolved contract, and returns
the approval sequence and audit head for external anchoring. Retain that head
outside the store if replacement detection is needed. `check action.json` returns
`allow`, `deny`, or `needs_approval`. `approve-action action.json --quote WORDS`
records a one-use approval for exactly that request; the next identical check
consumes it. `audit-verify`, `verify-inputs ID` and `revoke ID --reason WORDS`
are also available. `--store PATH` precedes the command and defaults to `.harness`.

## Implemented

- Draft 2020-12 JSON Schema in `ember_harness/schema/contract.schema.json`,
  plus semantic checks for tool classes, action IDs, evidence keys, windows,
  path globs and inputs. `validate()` runs both layers.
- Canonical UTF-8 JSON with sorted keys and compact separators. The four approval
  metadata fields are excluded from contract hashes; extensions, approval mode
  and art direction are included. Non-finite numbers are rejected. This is the
  Python canonicalization described in the docs, not RFC 8785 interoperability.
- A small explicit registry in `schema/tools.json`. Unknown tools deny. Path
  arguments are checked even when a caller omits them from `action.paths`.
- Ordered deny-by-default gate, intrinsic classes, exact argument constraints,
  normalized paths with symlink/junction resolution, $0 spend, input preflight,
  time windows, and per-version call limits reconstructed from audit decisions.
- Baseline network, deletion, publishing, submission, payment, deployment,
  remote manipulation, bare push and PR merge deny. `git.open_pr` models the
  documented coding-only approval request with fixed branch/base and force=false;
  it does not push or create a PR.
- Exact one-use action approvals; `approve_all` resolves only listed approval
  classes. Asset acceptance, scope selection, and S0/S1 closure still prompt.
- Hash-chained, flushed JSONL audit log. Approval state comes from the log;
  changing status fields cannot create authority. Audit errors and writer
  contention fail closed. An exclusive lock serializes local writers. After a
  crashed process, inspect state before manually removing `.writer.lock`.
- Build approval requires an active root scope, conservative subset proof, and
  inherited art direction. A scope is an authority ceiling: its agent can check
  only `scope.select`. Its allowed action list may describe coding capabilities
  for children, including PR requests; only coding children can use that entry.
- Successor approval supersedes the prior version in a single authoritative
  audit entry. Old pinned versions deny and old one-time approvals are void.
  Widening needs a distinct human acknowledgement entry bound to the computed
  widening hash and reviewed draft hash. Scope changes recheck children: fitting
  children remain active, while children that no longer fit become revoked in
  the same audit entry. Parent revocation cascades. Revocation is terminal.
- Evidence verification recomputes `file_hash`, `source_dest_hash` and file-list
  sizes; output snippets must match the approved pattern. File evidence is
  scoped and bound to an allowed action decision in the active version. Copy
  integrity and declared conversion hashes follow CT-16. Late-bound inputs
  remain pinned to the first successful preflight and cannot be rebound.
- Checklists, named reviewer notes and URLs are recorded as `self_reported`;
  URLs are never fetched. Submitted verdicts are ignored. Every required item
  must pass, and at least one machine check must pass, for `complete`.
- Canonical evidence payloads are stored by SHA-256 under `evidence/` and linked
  from audit entries. Completion includes `status_basis` pointing to its audit
  entry. `step-status` verifies the stored payload hash and rechecks current
  bytes, appending a fresh status record. Changed files become `incomplete`;
  corrupted payloads or audit failures raise an error and never claim completion.

## Evidence commands and demo

```powershell
py examples/contract_demo.py
py -m ember_harness --store PATH verify-evidence CONTRACT_ID ACTION_ID evidence-items.json --decision-seq 4
py -m ember_harness --store PATH step-status CONTRACT_ID ACTION_ID
```

The demo creates fresh isolated contracts, writes exact approved bytes, verifies
completion, changes the file to demonstrate failure, then restores and rechecks
it. Its report and audit log stay under `.harness/demos/`. Demo approval records
apply only to the isolated demonstration authorized by the user.

Evidence files passed to the command are arrays such as:

```json
[{"kind":"file_hash","params":{"path":"D:/demo/hello.txt","sha256":"<expected SHA-256>"}}]
```

Pin `path` and `sha256` in the contract's `required_evidence` to require specific
output bytes. Submitted values cannot override approved expectations. If the
contract leaves the hash open, verification proves that the submitted hash
matches the file, rather than asserting that its contents were specified in advance.
For `file_list`, supply `files: [{path, size}]` and use `expect_count` in the
approved requirement. Checklist submissions use `checks: {name: true}` and
`attested_by`; reviewer notes use `reviewer`, `role`, and `note`. These labels
record an attestation without authenticating the named person's identity.

## Deliberate first-version limits

This is a decision gate and trusted local approval API, not an OS isolation or
identity authentication system. Keep approval methods and store write access out
of agent toolsets. File paths can change between check and execution; a future
adapter must address that race. Regex constraints are trusted, anchored Python
regular expressions; glob matching is case-sensitive with `*`, `?`, and `**`.
Braces, character classes, backslashes and unnormalized glob prefixes are rejected.
Windows contracts use resolved `D:/folder/*.ext` paths; POSIX uses `/folder/*.ext`.

Subset proof currently accepts identical path globs and identical constraints,
numeric bound tightening, `one_of` subsets, and literal `equals` values satisfying
parent constraints. More complex subset
relations reject conservatively. This can require a wider scope proposal before
a safe child is accepted. The implementation does not allocate orchestration
envelopes or launch workers. Scope authoring is explicit; game features are not
inferred automatically from intent. The draft helper supplies safe empty role
templates rather than a full intent compiler. The deterministic
[intent-to-scope workflow](SCOPE_WORKFLOW.md) now supplies a small design proposal
with explicit assumptions and a fixed local capability ceiling; it does not
perform AI interpretation of intent.

Art scoring, asset acceptance workflows and general-purpose tool adapters
remain later slices. A gate `allow` never claims that an action ran or completed.
No runtime engine, model service, publishing or paid calls are included.
Output snippet verification checks the submitted text against the approved
pattern; trusted execution-output capture is still an adapter responsibility.
File verification establishes bytes at the time of inspection, not permanent
immutability. Call `step-status` to refresh completion before relying on it.

## Acceptance coverage

`tests/test_contracts.py` covers CT-1–7, CT-9–15 (hash/extension behavior), CT-17–18,
CT-20–21, CT-25 (limits/expiry), CT-28–30 as updated by v4, CT-46–47,
CT-50–55 (gate portions), and IT-18. CT-8/26's old bare-push expectation is
superseded by Part 12: bare push denies; coding PR requests prompt or auto-resolve.
Schema structure, canonical bytes, globs, audit failures and concurrent-writer
contention also have direct checks. This is partial architecture coverage.
`tests/test_evidence.py` adds CT-16, CT-22 and CT-23 coverage, required-item and
machine-check completion gates, approved-hash binding, decision binding, payload
tampering, stale file detection and fail-closed audit writes. Full orchestration
and art-score acceptance cases remain deferred.

## Amendments and versioning

See [the amendment workflow](AMENDMENTS.md) for the proposal format, separate
widening acknowledgement, rollback and CLI examples. `tests/test_amendments.py`
and the CT-34/51 tests cover computed lineage/diffs, supersession, stale approvals,
tampered proposals and records, parent scope checks, evidence carry-forward,
late evidence, terminal states, restart history, rollback, and approval audit
failure. The runnable scenario is `py examples/amendment_demo.py`.

## Local Git checks and staged fixes

[contract-lock and the staged workflow](CONTRACT_LOCK.md) documents the local
history/approval verifier, base-ref and trailer checks, and the staged bug-fix
demo. `tests/test_contract_lock.py` covers lock failures and Git guards;
`tests/test_staged_fix.py` runs the local workflow and exercises closure rejection.
The demo uses real test execution and a separate read-only automated checker;
it does not claim an independent human or AI review. The full triage service
and general tool transport remain later slices.

## Round checkpoints and reports

[Rounds and reports](../triage/ROUNDS_AND_REPORTS.md) adds audit-derived C0–C3,
clean baseline/fixed verification checkouts, one-open-round protection, terminal
abandonment, and generated provenance reports. Run `py examples/round_demo.py`.
`tests/test_rounds.py` covers checkpoint ordering, stale contracts, dirty
checkouts, incomplete closure, cache tampering, evidence/audit integrity and
report provenance. The intake and snapshot bridge is documented below.

## Attempt limits and escalation

[Attempt limits and escalation](../triage/ATTEMPTS_AND_ESCALATION.md) enforces the
three-attempt per-bug budget across contract IDs, amendments, restarts and rounds.
Only an owner decision can grant one extra attempt. `tests/test_attempts.py`
covers failure proof, allocation, terminal outcomes, identity binding, owner
decision hashes, retry consumption, reports and audit-write failures.
Run `py examples/attempt_demo.py` for the complete escalation scenario.

## Intake, deduplication and routing

[Intake, deduplication and routing](../triage/INTAKE_DEDUP_AND_ROUTING.md) adds
contract-gated findings, completeness and severity review, QA-confirmed duplicate
candidates, owner/policy routing and canonical frozen snapshots.
`tests/test_intake.py` covers those paths, stale reviews, evidence integrity,
canonical attempt budgets and audit failures. Run `py examples/intake_demo.py`.

# Optional Muse review adapter

This slice implements the architecture's transport-neutral adapter pattern (Part 1), untrusted model-output rule and contract-gated intake (Part 4). It adds a read-only reviewer transport, capture integrity checks and a review inbox. Automatic credit-consuming Meta review remains unavailable in this adapter; funded Muse conversations use the separate [chat transport and ledger](../MODELS_AND_CREDITS.md).

## Modes and budget

- `manual`: import a pinned JSON review response obtained separately. The harness makes no model request. The provider identity and judgment are `self_reported`; the file is evidence of a supplied claim, not proof that Muse generated it.
- `echo`: invoke the installed, hash-pinned Muse executable with its local echo provider. This verifies real CLI transport without AI calls or credit consumption. Findings come from an explicit fixture in the approved request and are labeled `fixture_echo`.
- `meta`: always denied with `muse_credit_limit_unavailable`, including under `approve_all` or an extension claiming credit permission. The inspected CLI exposes a model-step cap but no verified hard dollar limit, and `muse usage --json` reported `no_allowance` during integration. That is not evidence of a usable $150 balance or a zero-cost model request. The $150 free-credit policy is authorized. This review adapter has not been connected to the new credit ledger and therefore keeps its live-provider guard.

The existing $0 spend schema and baseline network restrictions remain unchanged. This adapter introduces no network permission or paid-call exception. Johnathan authorized up to $150 total in Muse free credits on October 30, 2026. This is a shared credit-only ceiling across sessions, with no out-of-pocket charges. Authorization is now granted. The separate conversation transport now uses bounded reservations; live review calls remain disabled until this adapter uses that ledger too. See [models and credits](../MODELS_AND_CREDITS.md). The current adapter supports reviewer tasks only; it cannot edit source, approve contracts, close bugs, grant retries or allocate a fix attempt.

## Approved request and execution

A reviewer needs an active approved `verifier` contract with no write paths, pinned inputs, `review.inspect` and `review.muse` permissions. The first gate authorizes inspection of the request; the second authorizes all source and imported-response reads before those bytes are read. Every file must be an approved pinned UTF-8 input. Changed bytes, unpinned files, paths outside scope, unsupported request keys and oversized inputs fail.

Request JSON:

```json
{
  "task": "Review reward arithmetic and report suspected bugs only.",
  "files": ["D:/workspace/src/reward.py"],
  "response_path": "D:/workspace/review-response.json"
}
```

Manual response JSON:

```json
[
  {
    "summary": "Reward may lose a coin",
    "area": "balance",
    "expected": "Return the delivered count",
    "actual": "Source subtracts one; reproduction has not been performed",
    "severity": "S2"
  }
]
```

Echo requests replace `response_path` with `fixture_findings`, using that same finding shape. Responses cannot include commands, output paths, approval fields or caller-selected evidence. Extra fields fail validation.

The trusted host selects and pins the executable; request data cannot select binaries, flags, endpoints or model providers. Echo runs directly without a shell, from a temporary directory, with a fixed empty preset, shell/write/web/reminder/input tools disabled, no personal-context loading requested, no session log and one model step. Only approved source snapshots are embedded in the prompt; the repository is not attached as a workspace. These are controls for the inspected echo path, not a claim that live Muse tools or plugins have been proven isolated. No live provider is enabled.

Limits: up to 16 files, 64 KiB combined review inputs, 20 findings, 1 MiB accepted capture and a 1–60 second timeout. Process output is redirected to temporary files and rejected if oversized before it is read into memory. The timeout also bounds process duration; there is no separate disk quota on those temporary files. There are no automatic retries. Each allowed inspection/run consumes a normal audited contract call. Failures, timeouts, stale inputs and authority changes produce failed captures and no accepted findings.

## Captures and bug intake

The host writes an immutable content-addressed capture at `STORE/muse_reviews/HASH/capture.json` and a matching `muse_review` audit event. It records the request bytes, exact source snapshots/hashes, backend, output, label and result. Derived `finding-NNN.json` files can be regenerated only if existing bytes match; they are not model-selected output paths. A capture alone grants no bug-write permission.

A separate approved intake contract can read those files and retained capture evidence. Findings enter as `source: code_review`, with review provenance and `independent_repro` missing. They always route to QA as `needs_repro`, even if a review supplies plausible steps or claims a frequency. Severity review cannot clear the reproduction requirement. QA must provide a fresh actual finding through the existing update flow before ordinary fix approval can proceed. Subsequent coding uses the existing per-bug attempt ledger.

Intake verifies that a provenance-bearing claim exactly matches an earlier successful capture; changing the claim, provider, label or evidence is refused. Reports show the origin and unverified label. These captures are not regression executions, independent verification or witnesses acceptable to the closure adapter.

Contract-lock checks capture hashes, allowed decision links, exact approved request/source/response hashes and labels. Historical checks use captured snapshots rather than requiring current source to remain frozen. Audit-write failure creates no accepted review event; unused capture files are ignored. Report output cannot overwrite review captures. Model output and imported files remain untrusted data throughout.

## Commands and demo

```powershell
py -m ember_harness --store STORE muse-review REQUEST.json --contract REVIEW_CONTRACT --provider manual
py -m ember_harness --store STORE muse-review REQUEST.json --contract REVIEW_CONTRACT --provider echo --binary PATH_TO_MUSE_EXE --binary-sha256 REVIEWED_BINARY_HASH
py -m ember_harness --store STORE muse-review-findings CAPTURE_HASH
py -m ember_harness --store STORE bug-ingest FINDING.json --root TRIAGE_ROOT --contract INTAKE_CONTRACT
py -m ember_harness --store STORE contract-lock
py examples/muse_review_demo.py
py examples/muse_review_demo.py --binary PATH_TO_MUSE_EXE
```

The demo uses fixture approvals and fixture review claims. It captures the suspected reward bug, ingests it under a separate contract, demonstrates QA routing and refusal of both a premature fix and live Meta credit consumption, and verifies the audit. Echo mode runs the installed Muse executable; it is explicitly not an AI review.

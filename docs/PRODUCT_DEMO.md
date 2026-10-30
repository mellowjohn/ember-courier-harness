# One complete offline product demo

```powershell
py examples/product_demo.py
```

The demo proposes one root scope and waits for owner approval, reviews three supplied original
PNG fixtures, records owner selection, ingests the selected asset and records
separate owner acceptance. It then intakes and freezes one S2 delivery-reward
bug, approves a fix contract, approves its budget-narrowing v2 amendment, and
runs the existing C0–C3 staged fix workflow. The version change retains one fix
attempt. All child contracts share the same scope and audit store.

The same regression checks both the accepted asset hash and the delivery reward.
It fails on the baseline reward logic, passes after the gated fix, and runs on
clean baseline and fixed checkouts. A separate read-only structural checker
reviews the fixed code. The local fix commit carries the approved v2 hash and
contract trailers; closure verifies the actual executions and named commits.

The intake finding is an explicit fixture. Owner decisions use the review flow
below; unattended regression tests must explicitly select `--fixture-approvals`.
Tests, file copies and local Git commits actually run. This proves the local harness flow;
it does not claim a playable game, live AI generation/review or engine import.
For real owner decisions, use the existing [scope](contracts/SCOPE_WORKFLOW.md)
and [asset](concepts/SELECTION_AND_INGEST.md) workflows.

Outputs stay under ignored `.harness/demos/staged-fix-*/`: `PRODUCT_DEMO.md`,
`product.json`, the sample project, audit/evidence and clean verification
checkouts. The existing staged runner supplies the bug-fix logic; the product
demo supplies shared scope and asset/intake setup. No production dependency or
separate orchestration framework is added.

Refresh a previous run without generating another sample project:

```powershell
py examples/product_demo.py --verify PATH_TO_PRODUCT_JSON
```

Refresh checks the manifest's audited binding, one shared root, current asset
acceptance and bytes, every captured script/source/asset input, clean named
checkouts, accepted asset presence in both Git builds, intake closure, the
amended fix version, single attempt, completed round, audit and contract-lock.
A changed asset, source, capture or run manifest fails and returns a nonzero
exit status. The Markdown report is a historical result; refresh before relying
on it after any changes.

Tests: `py -m unittest discover -s tests -p test_product_demo.py -v`.
The release gate runs this as the twelfth demo with explicit fixture approvals. Generated runs and
evidence are retained for review; they are not checked into the source repo.

## Owner review is the default

The product command prints `awaiting_owner`, an exact request hash, store path
and `REVIEW.md` path, then pauses. Read that packet before responding. The
human-facing host records the actual response with:

```powershell
py -m ember_harness --store STORE owner-decide REQUEST_HASH --choice approve --quote "ACTUAL_OWNER_RESPONSE"
```

Use `--choice decline` to stop. For a concept-choice packet use the exact
reviewed candidate slug instead of `approve`. The packet includes the PNGs,
pitches and hashes. Picking a candidate creates only that exact selection
approval; ingest still needs its approved contract, and the copied asset needs
separate owner acceptance. Changed packets/drafts and replayed responses reject.

There are seven checkpoints: scope; asset contract; concept choice; ingested
asset acceptance; intake/QA contracts; fix/verifier contracts; and the v2 fix
amendment. Contract batches list every concrete draft and approve each separately.
They never grant approval for future drafts. An interrupted receipt can be
retried using the same real response without duplicating core approval entries.
Decline stops the demo; it does not revoke grants already recorded before an
interrupted response. Revoke those explicitly if needed.

The process must remain running while waiting; request/decision evidence is
durable, but restarting the whole product process is not a checkpoint replay
engine. Approval windows still apply; an expired run needs a newly reviewed run.
No model inference starts until its contract and amendment are approved. The
model has no `owner-decide` tool. A broad instruction to run the demo is not an
approval of an unseen packet. Do not fabricate quotes or record an approval
merely to unblock a test. Approval methods belong to Johnathan or a trusted host
relaying his actual response. This is a local trust boundary, not identity
authentication, SSO or an independently signed human attestation.

Owner packets and receipts live under `STORE/owner-review/`. Product verification
requires every explicit contract/action approval in an owner-review run to have
a matching packet/response receipt. Contract-lock verifies packet hashes and
approval bindings. Markdown packets display state; the hash-checked request and
audit are authoritative.

For unattended tests only, run `py examples/product_demo.py --fixture-approvals`.
Reports and manifests label that mode `fixture`; it is not proof of real human
approval. Unit tests of the review protocol use synthetic host responses too.

## Clean installation check

Prepare dependency wheels for the same Python version and platform used for
the check (this download needs network access):

```powershell
py -3.12 -m pip download --only-binary=:all: --dest .harness/clean-install-wheelhouse "jsonschema>=4.26,<5" "Pillow>=12.1,<13" "setuptools>=68"
py -3.12 tools/clean_install_check.py --wheelhouse .harness/clean-install-wheelhouse
```

The check creates a fresh virtual environment without shared packages, builds
an isolated wheel using the local build dependency, installs it with its runtime
dependencies, runs `pip check`, and verifies installed module/schema locations
and the installed command. It then reuses the entire release suite, including
the product demo, from a validation copy containing no `ember_harness` source
directory. This prevents the repository source from shadowing the installed
package. Python import-path overrides are removed from child environments.

Once the wheels are available, the check uses no package index. Results, source
and wheel hashes, resolved dependency versions, logs and generated projects stay
under `.harness/clean-installs/`. It is an isolated wheel-install test of the
current working source snapshot, not a clean Git checkout or a live model test.
No additional production dependency is required. Consult that run's `REPORT.md`
and `report.json` for the tested Python, dependency versions and demo results.

## Real local coding agent at $0

With Ollama and a local GGUF coding model already installed:

```powershell
py examples/product_demo.py --local-agent-binary "C:/PATH/TO/ollama.exe" --local-agent-model qwen2.5-coder:7b
py tools/release_check.py --local-agent-binary "C:/PATH/TO/ollama.exe" --local-agent-model qwen2.5-coder:7b
```

The first command waits for real owner responses. The second runs the same
suite and twelve demos using explicit fixture approvals; its product demo uses
real local inference. Ordinary regression runs remain deterministic and need no
Ollama installation. Adapter unit tests use mocked inference and are not evidence
of a real model run. Live provenance is retained in the product manifest/report.

The trusted host pins the executable hash and model name in the scope and fix
contracts. `agent.propose` must be allowed before the adapter reads source or
starts inference. The adapter starts a hidden helper on a private loopback port
with `OLLAMA_NO_CLOUD=1`, requires the server's cloud-disabled confirmation and
installed GGUF metadata, and pins the model digest across generation. No model
download, cloud fallback, account credentials, proxy, external endpoint, shell
tool or automatic retry is provided. No global Ollama configuration is changed.
The helper exits and the model unloads after the request. Ollama documents its
[local-only configuration](https://docs.ollama.com/faq) and
[structured generation API](https://docs.ollama.com/api/generate).

The model receives current source and an actual captured regression failure,
then proposes one `fs.write` action. It receives no approval methods or direct
filesystem access. The host supplies the contract identity, paths and $0 budget;
the existing gate checks the proposed edit before any write. The demo's exact
approved content constraint still rejects incorrect logic. Only CRLF/LF line
endings and trailing newline formatting are normalized; both raw and normalized
proposals are retained and checked against the model response. No AST or semantic
rewrite substitutes a fixture solution for model output.

`STORE/agent-captures/` retains hashed prompt, source, response, local model
metadata, cloud-disabled startup confirmation and proposal evidence. Contract-lock
checks the inference decision and capture. Product verification additionally
binds the model's input failure and normalized proposal to the actual gated
write before the passing regression. Changed source, expired/revoked authority,
malformed proposals, failed inference and unavailable audit writes fail closed.

This is one bounded coding-agent action, not a general autonomous shell agent.
The intake finding remains a fixture and the independent verifier remains
deterministic. Owner responses are real in the default interactive mode and
simulated only with the explicit fixture flag. Qwen/Ollama does not establish Meta
model use or hackathon eligibility. Muse paid/credit-consuming providers remain
blocked. "$0" here means no model/API charges; ordinary local hardware operation
is outside that accounting. The trusted executable/local OS are not sandboxed
by this adapter, and a timed-out local request may take time to cancel.

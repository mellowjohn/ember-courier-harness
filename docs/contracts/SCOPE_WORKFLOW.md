# Intent to reviewed scope

`scope-propose` turns plain-language intent into a deterministic local draft.
It preserves the intent as the proposed game concept and supplies a small,
explicitly assumed core loop, feature list, exclusions, asset budget, done
criteria and original art direction. It does not interpret the intent with an
AI model. Check the assumptions and edit the draft before approval.

The default proposal allows child contracts to inspect and write files only
under `WORKSPACE/scope-output/**`. Writes require file-hash evidence. The scope
agent cannot execute those capabilities itself: the scope is an authority
ceiling. Each child still requires its own reviewed approval, a subset of the
parent's permissions and limits, and inherited art direction. Default limits
are $0, 50 calls per contract and a four-hour window resolved at approval.
Call budgets are per contract, not a shared worker allocation.

Game features, asset budgets and done criteria describe the design; the gate
enforces tool permissions, paths and limits. It does not automatically count
assets or prove gameplay completion. This slice implements the scope proposal
and approval workflow, not a game builder or asset production pipeline.

## Propose and review

From the repository directory, substituting the intended project folder:

```powershell
py -m ember_harness scope-propose ct-game-scope-0001 scope-planner "Ember Courier: carry embers past water to a brazier" --workspace "D:/Ember Harness/sample-game" > scope.json
py -m ember_harness scope-review scope.json
py -m ember_harness --store .harness/game save scope.json
```

The JSON review shows the design, assumptions, art direction, exact authority,
contract ID, version and `reviewed_hash`. Proposal and review do not create a
workspace or save contract state. `save` stores a draft and grants no authority.
Use UTF-8 JSON files; on older Windows PowerShell versions, use an editor or
`Set-Content -Encoding utf8` instead of redirection that emits UTF-16.

Optionally supply `--brief brief.json` containing any of `game_concept`,
`core_loop`, `features`, `out_of_scope`, `asset_budget`, and `done_criteria`.
These override design defaults. Unknown fields, blank text, duplicate list
entries and budgets above 16 total assets reject. A brief cannot supply tools,
paths, spending, approval mode or approval records. Intent text is data and
cannot grant those permissions. The generated draft remains editable; any
change requires reviewing the new hash.

## Approval belongs to Johnathan

After Johnathan has reviewed and explicitly approved the draft, the trusted
human-facing host records that decision with the existing command:

```powershell
py -m ember_harness --store .harness/game approve ct-game-scope-0001 1 --reviewed-hash HASH_FROM_REVIEW --quote "EXACT_APPROVAL_WORDS"
```

This command must be invoked by Johnathan or a trusted host relaying his actual
approval. Do not treat running proposal, review, save or a demonstration as
production approval. The local API records an attestation; it does not
authenticate human identity. Approval methods must stay outside agent toolsets.

The approved root fixes the time window. A child must use a window contained
within it; blindly reusing the draft's relative TTL later can exceed the parent
expiry and will reject. Copy the resolved parent window or explicitly narrow it.
Approve each reviewed child with `--parent ct-game-scope-0001`. The existing
approval API records the scope lineage. A child outside the ceiling rejects;
revoking the parent disables children. Amendments continue through the existing
versioning and separate widening acknowledgement workflow.

## End-to-end demonstration

```powershell
py examples/scope_demo.py
py -m unittest discover -s tests -p test_scope.py -v
py tools/release_check.py
```

The demo invokes the real CLI in separate processes and uses isolated fixture
approvals. It proves draft denial, parent-first approval, changed-draft rejection,
separate child approval, the root's ceiling-only behavior, actual local output
and hash evidence, outside-path denial, wider-child rejection, parent revocation,
audit verification and contract-lock. Reports are retained in
`.harness/demos/scope-*/SCOPE_DEMO.md`. No production contract is approved.
The release gate includes this as the tenth standalone offline demo.

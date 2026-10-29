> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Schema Decisions v0.2 (addendum to CONTRACT_SYSTEM.md)

Owner: Contract Smith (schema owner). Date: 2026-10-23. Documentation only; nothing built. `CONTRACT_SYSTEM.md` is held unchanged per Hack Lead. This addendum answers Pipeline Smith's schema questions (`/workspace/pipeline/PROPOSED_FIXES.md` sections 1, 2, 4, 7). Where the two documents differ, this addendum wins once Hack Lead merges.

Every decision below is **DECIDED by Contract Smith, Hack Lead/Johnathan may override.**

## What changed vs CONTRACT_SYSTEM.md

| # | Area | Before | Now |
|---|---|---|---|
| 1 | `action` | No contract id | Optional `contract_id`; required when the agent has several approved contracts |
| 2 | `extensions` | Optional, namespaced | Open object; `compile(..., extensions=None)` carries it verbatim |
| 3 | `source_dest_hash` | Hashes must be equal | New params `conversion`, `source_sha256`, `dest_sha256` |
| 4 | `requires_approval` | Exactly the six classes | Six mandatory plus additive extras; gate order confirmed unchanged |
| 5 | Args constraints | 5 kinds | New kind `no_overwrite_unless_same_hash` |
| 6 | `inputs[].sha256` | Checker unspecified | `verify_inputs()` pre-flight; `late_bind` inputs |
| 7 | Evidence | No format | Canonical payload; `evidence_refs` = sha256 of its canonical JSON |
| 8 | Ingest destination | `<slug>/refined/*.png` (CS example) | `<topic>/<slug>/<slug>_hero\|_impact\|_palette.png`; `refined/` reserved |
| 9 | `asset-step` defaults | Open (Q6) | `max_calls` 12, window approval time to +4h, approvals expire at `not_after` |
| 10 | StepResult | `incomplete` implied | `incomplete` is an explicit status |
| 11 | Tests | 1 to 12 | 13 to 25 added (section 10) |

Unchanged: contract id pattern `ct-<kind>-<n>`; hash rule; the six mandatory classes; deny by default.

## 1. Contract selection

`action` gains optional `contract_id` (string). Gate step 1 becomes:

> Collect the agent's `approved` contracts. If `action.contract_id` is set, use only that contract; if it is not approved, or its `agent` differs from `action.agent`, **deny** (`reason: contract_not_found`). If it is not set: zero approved contracts gives **deny**; exactly one is used; two or more gives **deny** (`reason: contract_id_required`).

One agent identity per step is not required. The audit entry records the chosen `contract_id` and `contract_version` (already in the entry shape).

## 2. Extensions

Schema: `extensions` is an object whose keys match `^[a-z][a-z0-9_]*$` (lowercase subsystem namespace). Each value is an object with `additionalProperties: true`. No other top-level key is allowed in the contract.

`compile(intent_text, agent, role, extensions=None) -> draft_contract, summary`: if `extensions` is given (e.g. read from `intents/<step>.intent.json`) it is copied verbatim into the draft, with no merge, rewrite or default-filling. The summary lists the namespaces present. The gate never reads `extensions`. The content hash covers it, so editing it resets approval.

## 3. `source_dest_hash` with conversion

Evidence kind `source_dest_hash` params: `source_path`, `dest_path`, and the following.

| Param | Type | Rule |
|---|---|---|
| `conversion` | null or string, e.g. `"jpeg_to_png"` | null means pure copy |
| `source_sha256` | hex | Must equal the actual hash of `source_path` |
| `dest_sha256` | hex | Must equal the actual hash of `dest_path` |

Check: recompute both hashes from the files. With `conversion` null, `source_sha256 == dest_sha256` is required. With a declared conversion they may differ; the check still verifies each against its file. Any mismatch fails the item and the step is `incomplete`. The legacy `sha256` param remains valid only when `conversion` is null (it means both hashes).

## 4. `requires_approval`, engine/project writes, gate order

- `requires_approval` must contain the six mandatory classes and may contain more. Extras are additive only; removing a mandatory class makes the schema invalid. Extra classes are free strings matching `^[a-z][a-z0-9_]*$`. An allowed action with `class` equal to a listed class returns `needs_approval`.
- Recommended extras: `engine_change`, `project_write`, `direction_selection`.
- Default for project or engine writes: the path is not in `allowed_paths.write`, so the gate returns **deny** (engine pause). A later approved version may add the path and the `project_write` or `engine_change` class, which then returns `needs_approval`.
- `direction_selection` is for the selection event: an action of that class returns `needs_approval`, and Johnathan's pick is recorded as a `reviewer_note` evidence item.
- **Gate order is unchanged and confirmed.** Step 7 (spend and `max_calls`) runs before step 8 (`requires_approval`). With `limits.spend_usd` 0, a call with `spend > 0` is **deny**. It is `needs_approval` only under a nonzero approved cap, when cumulative spend stays within the cap. Over the cap is **deny**.

## 5. New constraint kind `no_overwrite_unless_same_hash`

Used on a destination argument: `"dest": { "path_within": "...", "no_overwrite_unless_same_hash": true }`. The gate passes the constraint if the destination path does not exist, or if the sha256 of the existing file equals `args.expected_sha256`. For `fs.copy`, `expected_sha256` defaults to the source file's hash. For a converting tool it is required and equals the declared `dest_sha256`. If the file exists and the hashes differ, or `expected_sha256` is missing, the result is **deny**.

## 6. Inputs hash check

New harness call: `verify_inputs(contract_id) -> pass | fail(+items)`. Called once before the first action of a step. For each input with a non-null `sha256`, it recomputes the file hash. Result is an audit entry of kind `inputs_verify`.

New gate step 2b, after the hash check: if the contract has any input with `sha256` or `late_bind`, and no passing `inputs_verify` entry exists for this `(id, version)`, **deny** (`reason: inputs_unverified`). A failing verify means the step is not started and the failure is audit-logged. Contracts with no hashed inputs skip this.

Chained steps: an input may be `{ "name": "...", "path": "...", "sha256": null, "late_bind": true }`. `verify_inputs` records the actual hash in the audit log (`inputs_verify` entry, `late_bound` map) at step start. The `file_hash` evidence for that file is later checked against the recorded value. No new contract version or approval per step. The input still needs a read path in `allowed_paths.read`.

**[OPEN for Johnathan, Q14]** Is late binding acceptable, given that the approved contract does not pin those bytes? The alternative is a new approved version per chained step.

## 7. Evidence payload

The payload passed to `verify_evidence(contract_id, action_id, evidence)`:

```json
{ "contract_id": "ct-pipeline-ingest-0001", "contract_version": 1, "action_id": "ingest_convert",
  "items": [ { "kind": "source_dest_hash", "params": { "...": "..." }, "result": "pass" } ] }
```
`result` is the checker's output for that item (`pass`, or `fail` with a `detail` string). `evidence_refs` in the audit entry is a list holding one value: `sha256(canonical_json(payload))`, using the 3.1 canonical JSON rule. The payload file is stored by the harness; the log carries only the hash.

## 8. Ingest destination and corrected worked example

Convention (Concept Artist): `/workspace/concepts/<topic>/<slug>/<slug>_hero.png`, `_impact.png`, `_palette.png`. `<slug>` matches `^[a-z0-9]+(-[a-z0-9]+)*$` and equals the folder name. `<slug>/refined/` is reserved for refined frames and `engine_notes.md`, and ingest never writes there. Run files (generation log, evidence) live under `/workspace/runs/<run_id>/`, outside `/workspace/concepts/`.

Corrected example (replaces CONTRACT_SYSTEM.md 3.3; hashes and approval fields are placeholders):

```json
{
  "id": "ct-pipeline-ingest-0001", "version": 1, "agent": "pipeline-smith",
  "intent_text": "Bring the Molten Slag fireball concept images into the concepts folder and check they are intact.",
  "goal": "Convert the three Molten Slag images from the generation store to PNG in /workspace/concepts/fireball/molten-slag/ and record source and destination hashes.",
  "inputs": [
    { "name": "generation_log", "path": "/workspace/runs/run-0001/generation_log.json", "sha256": "<hex>" },
    { "name": "hero",    "path": "<generation-store>/<hex>.jpg", "sha256": "<hex>" },
    { "name": "impact",  "path": "<generation-store>/<hex>.jpg", "sha256": "<hex>" },
    { "name": "palette", "path": "<generation-store>/<hex>.jpg", "sha256": "<hex>" }
  ],
  "allowed_actions": [
    { "action_id": "ingest_convert", "tool": "image.convert_png", "class": "write",
      "args_constraints": {
        "src":  { "path_within": "<generation-store>/*.jpg" },
        "dest": { "path_within": "/workspace/concepts/fireball/molten-slag/molten-slag_*.png",
                  "no_overwrite_unless_same_hash": true },
        "expected_sha256": { "pattern": "^[0-9a-f]{64}$" } } },
    { "action_id": "hash_file", "tool": "fs.sha256", "class": "read",
      "args_constraints": { "path": { "path_within": "/workspace/concepts/fireball/molten-slag/molten-slag_*.png" } } }
  ],
  "forbidden_actions": [ { "tool": "git.push" }, { "tool": "network.*" }, { "tool": "publish.*" },
                         { "tool": "submit.*" }, { "tool": "payment.*" }, { "tool": "fs.delete" } ],
  "allowed_paths": {
    "read":  ["<generation-store>/*.jpg", "/workspace/runs/run-0001/generation_log.json",
              "/workspace/concepts/fireball/molten-slag/molten-slag_*.png"],
    "write": ["/workspace/concepts/fireball/molten-slag/molten-slag_*.png"] },
  "limits": { "spend_usd": 0, "max_calls": 12,
              "time_window": { "not_before": "<approved_at>", "not_after": "<approved_at + 4h>" } },
  "required_evidence": {
    "ingest_convert": [
      { "kind": "source_dest_hash", "params": { "conversion": "jpeg_to_png",
          "fields": ["source_path", "dest_path", "source_sha256", "dest_sha256"] } },
      { "kind": "file_list", "params": { "expect_count": 3 } },
      { "kind": "checklist", "params": { "items": ["images_viewed", "no_lore_text", "no_trademarked_material"] } } ] },
  "requires_approval": ["live", "publish", "spend", "push", "submit", "send_message",
                        "engine_change", "project_write", "direction_selection"],
  "extensions": { "pipeline": { "step": "B1", "run_id": "run-0001", "topic": "fireball", "direction": "molten-slag" } },
  "status": "approved", "approved_by": "johnathan",
  "approved_at": "<set at approval>", "content_hash": "<computed at approval>"
}
```
No `refined/` path appears. Hashed filenames are mapped to slots only through `generation_log`, never by eye.

## 9. `asset-step` template defaults

- `limits.max_calls`: 12. It counts every gate-checked action that returns `allow`, reads included (CS rule: counters increment on allow only). Three conversions plus three hashes plus margin fits within 12.
- `time_window`: the draft carries `{ "not_before": null, "not_after": null, "ttl_hours": 4 }`. `approve()` resolves `not_before` to `approved_at` and `not_after` to `approved_at + 4h`, then computes the hash.
- Approvals expire at `not_after`, which includes one-time per-action approvals. After that the gate denies and a new version is needed.
- `StepResult.status` is one of `complete`, `incomplete`, `failed`. A missing or failing evidence item gives `incomplete`.

## 10. New acceptance tests (continue after test 12)

13. **Selection, several contracts.** Given an agent with two approved contracts, when an action has no `contract_id`, then deny with `contract_id_required`.
14. **Selection, explicit.** Given the same agent, when an action names one approved contract, then that contract is used and audited. When the id is another agent's or is `draft`, then deny.
15. **Extensions.** Given an intent file with `extensions.pipeline`, when `compile` runs, then the draft holds it byte-for-byte. When the approved contract's `extensions` is edited on disk, then the gate denies with hash mismatch. When `extensions` is changed in a draft, the gate result for allowed actions is unaffected.
16. **Conversion hashes.** Given `conversion` null, when source and dest hashes differ, then the item fails. Given `jpeg_to_png`, when they differ and each matches its file, then pass. When `dest_sha256` does not match the real file, then fail and the step is `incomplete`.
17. **Extra classes.** Given `requires_approval` without a mandatory class, then schema validation fails. Given extra classes added, then it validates, and an allowed action of class `project_write` returns `needs_approval`.
18. **Project write default.** Given a project path not in `allowed_paths.write`, when an agent writes there, then deny.
19. **Spend order.** Given `spend_usd` 0, when `spend` is 0.05, then deny (not `needs_approval`). Given an approved cap of 1.00, when `spend` is 0.05, then `needs_approval`. When cumulative spend would exceed 1.00, then deny.
20. **No overwrite.** Given `no_overwrite_unless_same_hash`, when dest is absent, then allow. When dest exists with a hash equal to `expected_sha256`, then allow. When it differs or `expected_sha256` is missing, then deny.
21. **Inputs pre-flight.** Given an input whose file hash differs from `sha256`, when `verify_inputs` runs, then it returns fail and logs `inputs_verify`. When an action is then checked, then deny with `inputs_unverified`.
22. **Late bind.** Given `late_bind: true`, when `verify_inputs` runs, then the actual hash is in the audit entry. When the file later changes and `file_hash` evidence is checked, then fail.
23. **Evidence refs.** Given a verified payload, when the audit entry is written, then `evidence_refs[0]` equals sha256 of the payload's canonical JSON. When one byte of the stored payload changes, then recomputation no longer matches.
24. **Ingest destination.** Given the corrected example, when an action writes `molten-slag_hero.png` under `<slug>/`, then allow. When it writes under `<slug>/refined/` or outside `<topic>/<slug>/`, then deny.
25. **Defaults.** Given an `asset-step` contract, when a 13th allowed action is attempted, then deny. When `now > not_after`, then deny, and a one-time approval issued earlier is also void.

## 11. Open questions added

- **Q14 (Johnathan):** is `late_bind` acceptable (section 6)?
- **Q15 (Johnathan):** confirm the recommended extra classes, and that engine/project writes stay deny-by-default until the pause is lifted.
- **Q16 (RESOLVED by Pipeline Smith, 2026-10-23):** `image.convert_png` is the agreed tool name (class `write`, `src` and `dest` limited by `path_within`).

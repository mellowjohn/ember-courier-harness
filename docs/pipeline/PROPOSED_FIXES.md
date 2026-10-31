> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Proposed fixes to PIPELINE_SUBSYSTEM.md (hold; not merged)

Status: PROPOSAL. Documentation only. Written by Pipeline Smith on 2026-10-23, after Hack Lead asked for specs to be held as delivered.
Sources compared: `/workspace/contract-system-doc/CONTRACT_SYSTEM.md` (CS), `/workspace/concepts/CONCEPT_STEP_SPEC.md` (CA), `/workspace/pipeline/PIPELINE_SUBSYSTEM.md` (mine).
Version note: `PIPELINE_SUBSYSTEM.v1-as-delivered.md` is the exact pre-edit text. `PIPELINE_SUBSYSTEM.md` currently contains a partial first reconciliation pass (see section 8) and no Reconciliation note. I made no further edits after the hold.

## 1. Contract Smith field-name and shape mismatches (fix in 3.1 to 3.4)

| My v1 spec | CONTRACT_SYSTEM.md | Proposed fix |
|---|---|---|
| Top-level fields: `id`, `agent`, `intent_text`, `inputs`, `allowed_actions`, `allowed_paths`, `forbidden_actions`, `limits`, `required_evidence`, `requires_approval`, `status` | Also required: `version`, `goal`; set on approval: `approved_by` (`johnathan`), `approved_at`, `content_hash` | Add them to the 3.1 table and the 3.2 example |
| `inputs`: `{path or value, sha256?}` | `{name, path or value, sha256?}` | Add `name` |
| `allowed_actions`: `{tool, args: {dest_prefix}}`, tool `file_copy` | `{action_id, tool, class, args_constraints}`; constraint kinds `equals`, `one_of`, `pattern`, `max/min`, `path_within`; tools named `fs.copy`, `fs.sha256`, `image.generate`; `class` is `read`, `write`, `compute`, `local_commit` or an approval class | Rewrite with `action_id` and `path_within` globs |
| `forbidden_actions`: strings `"network"`, `"delete"`, `"overwrite_without_hash_match"` | Objects `{tool}` with baseline `git.push`, `network.*` (or `network.post`), `publish.*`, `submit.*`, `payment.*`, `fs.delete` | Use the baseline list; drop `overwrite_without_hash_match` (not a tool; see 4 below) |
| `allowed_paths`: directory prefixes | Globs; write does not imply read; symlinks resolved | Use globs, e.g. `.../molten-slag/molten-slag_*.png` |
| `limits.time_window: "1h"` | `{not_before, not_after}` ISO-8601 with zone | Use the object |
| `required_evidence: {"file_copy": ["file hash"]}` | Map `action_id` to `[{kind, params}]`; kinds `file_hash`, `file_list`, `source_dest_hash`, `url`, `output_snippet`, `reviewer_note`, `checklist` | Use kinds. Ingest: `source_dest_hash` (`source_path`, `dest_path`, `sha256`), `file_list` (`expect_count`), `checklist` (`images_viewed`, `no_lore_text`, `no_trademarked_material`) |
| `requires_approval: false` | List of classes; mandatory `live`, `publish`, `spend`, `push`, `submit`, `send_message` (removing one makes the schema invalid) | Use the full list in every contract |
| `status` values | Same (`draft`, `approved`, `revoked`) | OK |
| Gate: placeholder `gate.authorize(contract, action)` | `check(action) -> {decision, reason, contract_id, contract_version, audit_seq}`, `action = {agent, tool, args, paths{read[], write[]}, spend}`; `verify_evidence(contract_id, action_id, evidence) -> pass | fail(+items)`; `audit_verify() -> ok | first_bad_seq` | Wrapper uses the real names; steps must list `paths.read/write` in every action |
| Evidence "incomplete" not mentioned | A missing or failing item makes the step `incomplete` | Add `incomplete` to `StepResult.status` |
| Evidence file `{step_id, files[]}` | CS defines checks, not a file format | Keep as PROPOSAL, key it by `contract_id`, `contract_version`, `action_id`, `kind`; attach its sha256 to the audit log as `evidence_refs` |
| `contracts/templates` and `contracts/instances/<run_id>/` in my layout | Store is CS's: `contracts/<id>/v<version>.json`, `approvals/`, `audit/audit.jsonl`; compiler is `compile(intent_text, agent, role)`; MVP templates `asset-step` and `coding` | Replace my templates with `intents/<step>.intent.json` (role `asset-step`); do not keep a second contract store |
| Contract ids like `ingest-fireball-molten-slag-001` | `ct-<kind>-<n>` pattern | Use `ct-pipeline-ingest-0001` |

## 2. Gate-behaviour mismatches in my acceptance tests

- **G4 / B5-1 / sound step.** CS gate order checks spend and `max_calls` (step 7) before `requires_approval` (step 8). So with the default `spend_usd` 0, a spending call returns `deny`, not `needs_approval`. A paid call becomes `needs_approval` only under a nonzero approved cap. Fix G4, the sound step ("`requires_approval` true and `spend_usd` 0") and Q6 accordingly.
- **B5 import.** `requires_approval` classes are `live`, `publish`, `spend`, `push`, `submit`, `send_message`. There is no class for "write into the game project". Proposed: omit the project path from `allowed_paths` (gate returns `deny`, matching CS Q10 on engine paths); a later approved version adds it. B5-1 then expects `deny`, not `needs_approval`. If Johnathan prefers `needs_approval`, CS must add a class (Q10 below).
- **G1.** Add "no contract for the agent" to the draft or revoked case (CS tests 1 and 2).
- **G2.** Add read-side and `..` or symlink cases (CS test 5).
- **G3.** Add "argument outside `args_constraints`" (CS test 4).
- **G5.** CS says the input is refused if `sha256` differs but does not say whether the gate or the evidence checker does it (Q12).
- **G6.** Use `verify_evidence`; failure means `incomplete`.
- **New G7.** Every decision, including denies, has an audit entry, and `audit_verify()` is `ok` (CS test 10).
- **New G8.** Editing a hashed field, including `extensions.pipeline`, after approval makes the gate deny with a hash mismatch (CS tests 3 and 11).
- **Validate check 8.** Replace "audit log has an entry for each step run" with `audit_verify()` ok plus entries per `contract_id` and `contract_version`.
- **`max_calls`.** Counted on `allow`; copies and hash reads both count. Ingest example: 3 copies + 3 hashes + margin = 12 (CS uses 12). My v1 said "number of files".

## 3. `extensions.pipeline` (decided by Hack Lead, pending Johnathan's review)

Hack Lead decided the schema gets an optional `extensions` object, one namespace per subsystem. The gate ignores it; the content hash covers it. All pipeline-only data goes under `extensions.pipeline` and is enforced by step `check()` and validate, not the gate. Proposed keys [PROPOSAL]:

```json
"extensions": { "pipeline": {
  "step": "B1", "run_id": "run-0001", "topic": "fireball", "direction": "molten-slag",
  "upstream": [{"step": "A", "contract_id": "ct-...", "evidence_path": "runs/<run_id>/evidence/..."}],
  "outputs": [{"path_glob": "...", "naming": "<direction>_hero|impact|palette.png"}],
  "adapter_role": null,
  "thresholds": {},
  "generation_log": "runs/<run_id>/generation_log.json"
}}
```
Uses: how a step references an upstream output (answers my old Q3 gap), declared outputs for validate, alpha-coverage bounds for K2, size rule thresholds, adapter role. Consequence: editing it resets approval, so it is fixed at approval time.

## 4. Things the gate cannot express (proposed handling)

- "Overwrite only if the existing file has the same hash": `args_constraints` has no such kind. Proposed: ingest step enforces it (test I3) and records it as evidence; or CS adds a `dest_absent_or_hash_equal` constraint.
- Numeric bounds (alpha coverage, image sizes): `output_snippet` matches a pattern, not a range. Proposed: bounds in `extensions.pipeline.thresholds`, checked by the step's `check()`, measured value recorded in an `output_snippet`.
- Writing `runs/<run_id>/evidence/*.json` from a step whose `allowed_paths.write` is the concept folder: either the contract lists the run path in `allowed_paths.write` (Concept Artist's contract does) or the harness writes evidence outside the gate. Proposed: list it, and keep it out of `/workspace/concepts/` (CA does this too).
- Inputs whose sha256 is only known after an upstream step: `inputs[].sha256` is inside the hash, so each later contract can only be completed and approved after the previous step has produced its outputs. Proposed: draft all step contracts up front with the upstream inputs lacking `sha256`, then issue a new version with hashes per step (each needs Johnathan's approval), or approve an `inputs` entry without `sha256` and rely on the `file_hash` evidence plus validate check 2. Question for CS and Johnathan.
- "Which contract does this action belong to?": the gate finds "the agent's `approved` contract" and `action` has no contract id. One contract, one agent, but the pipeline has seven steps. Proposed: either each step runs under a distinct agent identity (`pipeline-ingest`, `pipeline-cut`, ...), or `action` gets an optional `contract_id`. CS to decide (Q13).

## 5. Ingest and the generation store (Concept Artist's correction)

Fact from Concept Artist [SRC, CA 2.5]: the generation store is readable from Shell at `/cursor/stores/<store-id>/grok-bot/agents/<agent-id>/attachments/<64-hex>.jpg` (I confirmed the folder lists hash-named `.jpg` files on this box). Files are 1280x720 JPEG with content-hash names unrelated to the prompt. The tool-reported `assets/` path stays empty from Shell. A Meta harness will have its own store, so the path must not be assumed.

Fixes to my spec:
1. Delete every "not shell-visible" statement (3.2 note, B1 step table, flow in 4.0, Q1). Replace with: "readable from Shell, hash-named, path is harness-specific."
2. B1 ingest `inputs` must include a **generation log** (`runs/<run_id>/generation_log.json`): one entry per generated image `{direction, role (hero|impact|palette|refined frame), prompt, source_path (hash-named file), source_sha256}`. Mapping from hashed file to direction and slot comes only from this log, never by eye (CA step order 2 and 3; CA Q4).
3. Ingest converts JPEG to PNG (CA 2.3), so `source_sha256` and the dest `sha256` differ. My v1 text and the CS `source_dest_hash` kind ("equal sha256 for both") assume an equal-hash copy. Proposed: for converted files record `source_sha256` and dest `sha256` as two fields, and use `file_hash` on the dest instead of `source_dest_hash`; CS to say whether `source_dest_hash` can allow a declared conversion (Q14). Pure copies still use `source_dest_hash`.
4. Contract: `inputs` entries `{name, path: "<store>/<hex>.jpg", sha256: "<hex>"}` plus `{name: "generation_log", path, sha256}`; `allowed_paths.read` includes the store glob and the log; `allowed_actions` add a conversion tool (proposed `image.convert_png`, class `write`) with `src` and `dest` `path_within`.
5. New ingest tests: **I6** every input in `generation_log.json` has exactly one destination and every destination has exactly one log entry (no unmapped or doubly mapped files); **I7** `source_sha256` equals the actual sha256 of the store file and equals the hex part of its filename.
6. Open question rewrite for Q1: "Generation store path in the Meta harness, and does it produce a generation log?" Answerer: Concept Artist, Hack Lead.
7. Step A contract: add a `generation_log` evidence item (CA evidence has "generation log"); kind is `file_hash` of the log.

## 6. Consistency with CONCEPT_STEP_SPEC.md

Consistent: step names (A `design-with-concepts`, B1 `ingest`, B2 `concept`), `runs/<run_id>/evidence/<step>.evidence.json`, run files outside `/workspace/concepts/`, `<direction>_hero|impact|palette.png` in the direction folder, `refined/engine_notes.md`, no heat distortion, no lore text, `image_gen` adapter with `manual` fallback, spend $0, no Meta model assumed.

Mismatches or gaps:
- **Direction naming.** CA uses `<direction-slug>` with regex `^[a-z0-9]+(-[a-z0-9]+)*$` and `<slug>` equal to the folder name. Mine: `<direction>`. Adopt CA's regex in I4 and the naming check.
- **Comparison sheet.** CA proposes `<topic>_comparison_sheet.png` (existing: `fireball_comparison_sheet.png`) plus `<topic>_comparison_sheet.manifest.json`. My Q9 and A2 say "name TBD"; point to CA Q6. A2 should also check the manifest (CA T10, T11).
- **Step A tests.** CA T1 to T14 are more specific than my A1 to A5; proposal: Step A's acceptance tests are CA's T1 to T14 by reference, and my A1 to A5 are kept as the summary.
- **Extra Step A actions.** CA's step builds palette PNGs, `notes.md` and the sheet (`file_write`, `file_copy`, `vision_review`). My Step A sketch lacks `file_copy` (ingest) and palette/sheet writes; add them or say Step A includes B1.
- **Step A and B1 overlap.** CA's Step A includes ingest (its step 3) and writes `<topic>/<slug>/...`, while mine treats B1 as a separate contract. Decide whether B1 is its own contract (mine) or an action inside Step A's contract (CA's 3.3 lists `file_copy`). Question for Hack Lead.
- **Allowed actions naming.** CA uses `file_read`, `image_gen`, `file_copy`, `file_write`, `vision_review`; CS tools are dotted (`fs.copy`, `image.generate`). CA's contract (3.4) has the same field mismatches listed in section 1 above (strings in `forbidden_actions`, `time_window: "4h"`, `requires_approval` with `post` and `engine_change` and `direction_selection`, which are not CS classes). CA said it could not find CS's schema when writing; CA should realign to CONTRACT_SYSTEM.md. Note CS mandatory classes are only the six listed; `engine_change` and `direction_selection` would need to be either extra classes (schema allows? CS silent; Q15) or handled as `reviewer_note` evidence and an omitted path.
- **Selection event.** Mine: B2 `reviewer_note` from Johnathan. CA: `selection {status, picked_direction, approved_by, approved_at}` in evidence. Align: the pick is recorded as a `reviewer_note` evidence item whose body is CA's `selection` object.
- **Image size rule (CA Q2).** CA T3: hero and impact >= 1024 on both sides (existing 1280x720 only passes if the rule is "long side >= 1024"); T4: palette width >= 600 and height >= 150 (existing 1000x240). Mine: "image checks: format, dimensions within budget" (4.7) and `size_budget` in `asset_spec.json`. Proposal: do not hard-code a size rule in the pipeline; put thresholds (`min_long_side`, `min_short_side`, palette minimums) in `extensions.pipeline.thresholds`, defaulting to CA's existing values (long side >= 1024, short side >= 720 for hero and impact; palette >= 600 x 150) until Johnathan answers CA Q2. Validate check 5 reads the thresholds.
- **Existing `notes.md` files** use an older format; CA proposes migrating to the template (CA Q6). B2 reads `notes.md`, so B2's tests should parse CA's template (T5, T7).
- **Palette.** CA: exactly 5 hex values, the last `#0B0807`; B2/`asset_spec.json` could carry those colors; optional.
- **Counts.** CA: 3 to 4 directions, `max_images` 12 for 3 directions. My Step A limit "max images per direction (set per run)" becomes `max_images` total per run, in `extensions.pipeline.thresholds` (not a schema field; gate enforces only `max_calls`).
- **Evidence kinds for CA items.** "References used": `file_hash` per reference plus the references listed in `inputs` with `sha256`. "viewed / no text / no trademark / no heat distortion": a `checklist` (add `no_heat_distortion`) plus a `reviewer_note`; CA's `review` object maps to a `checklist`.

## 7. Questions for Contract Smith

1. **Agent identity per step.** The gate finds "the agent's approved contract". Pipeline has several steps and one agent identity. One identity per step, or an optional `contract_id` in `action`? (Q13)
2. **Extensions in the compiler.** Does `compile(intent_text, agent, role)` accept and carry `extensions.pipeline` from an intent file, and does the JSON Schema leave `extensions` open (`additionalProperties`)?
3. **`source_dest_hash` with conversion.** Can it allow a declared JPEG-to-PNG conversion (two different hashes) or should we use `file_hash`? (Q14)
4. **Approval class for project import.** Is there or will there be a class for engine or project writes, or is "path not in `allowed_paths`" the intended way? Can `requires_approval` contain classes beyond the six (for example `engine_change`, `direction_selection`)? (Q10, Q15)
5. **"Destination absent or hash-equal"** constraint for overwrite protection, or is it step code? (Q11)
6. **Input hash timing.** Who checks `inputs[].sha256`, gate or evidence checker, and at which point? And how should chained steps whose inputs are produced upstream be approved (new version per step)? (Q12)
7. **Evidence file format.** Is there a canonical evidence payload that `verify_evidence(contract_id, action_id, evidence)` expects, and how are `evidence_refs` hashed into the audit log?
8. **Ingest destination.** CS's ingest example writes `molten_slag_*.png` into `.../molten-slag/refined/`; Concept Artist's convention puts `<slug>_hero|impact|palette.png` in `<slug>/` and reserves `refined/` for refined frames plus `engine_notes.md`. Which is intended? (Q10 in my spec)
9. **`time_window` and `max_calls` defaults** for `asset-step` (CS Q6) and whether `max_calls` also counts reads.

## 8. What I already changed in `PIPELINE_SUBSYSTEM.md` before the hold

The file now holds a partial pass of the section 1 and 2 fixes. Exact pre-edit text: `PIPELINE_SUBSYSTEM.v1-as-delivered.md`. Changed sections: header labels (added **[DECIDED]**), 1 Purpose (one line), 2.1 fail-closed bullet, 2.2 spend line, 2.3 layout (CS store, `intents/`), 2.4 step interface and gate calls and the `extensions` decision, 3.1 table, `extensions.pipeline` keys and gate order, 3.2 example and evidence record, 3.4 all step tables, 4.1 G1 to G8, I2, I3, I5, K2, K3, B5-1, B5-2, 4.7 checks 7 and 8, D-sound, 5.1 steps 0 and 1 and 6, Q3, Q6, new Q10 to Q12. Not done: the generation-store and generation-log changes (section 5), Concept Artist consistency (section 6), size thresholds, and the "Reconciliation with CONTRACT_SYSTEM.md" note at the end. Q3 and Q11 in the edited file point to a Reconciliation note that does not exist; if the edited file is merged, either use this file as that note or restore the v1-as-delivered file.

## 9. Open questions for Johnathan (new or changed)

- Size rule (CA Q2): both sides >= 1024, long side >= 1024, or higher for X-ready art?
- Does he confirm `extensions` (Hack Lead's decision)?
- Is Step B1 ingest its own contract, or part of Step A's?
- Is a chat "yes" through Ultralord sufficient as the recorded approval (CS Q8)? Affects how selection and one-time approvals are recorded.

## 10. Muse Image and SAM 3.1

Unchanged: both stay conditional on the event page and Official Rules (Hack Lead rechecks Oct 26). Neither is required, hard-coded or assumed anywhere in this file. Unsourced items remain labelled [PROPOSAL].

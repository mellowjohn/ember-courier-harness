> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Contract Fixes v0.3 (fix doc for CONTRACT_SYSTEM.md and SCHEMA_DECISIONS_v0.2.md)

Owner: Contract Smith (schema owner). Date: 2026-10-23. Documentation only; nothing built.
`CONTRACT_SYSTEM.md` and `SCHEMA_DECISIONS_v0.2.md` are **held and unchanged**. This file lists the edits they need, with replacement wording, so Hack Lead can apply them in the merge. Where this file and the held files differ, this file wins once merged.
Source: `/workspace/architecture-merge/ARCHITECTURE_DRAFT.md` (Part B mismatches, Part C open questions, Decisions D1 to D7) and the M-58 decision relayed by Hack Lead in the room.

Labels: **DECIDED by Contract Smith, Hack Lead/Johnathan may override** = my call as schema owner. **OPEN (Johnathan)** = needs his answer. "CS" = CONTRACT_SYSTEM.md, "1A" = SCHEMA_DECISIONS_v0.2.md. Line numbers are those of the held files today.

---

## 1. M-58: `git.push` becomes `needs_approval`

**Decision (Hack Lead, relayed; Johnathan can override):** `git.push` is not baseline-forbidden. It has class `push`, and the gate returns `needs_approval`. It is never `allow` without a recorded one-time approval from Johnathan. This matches his rule that nothing is pushed without his yes.

**Interaction (the reason for the edit).** `forbidden_actions` is checked at gate step 4 and returns `deny`. `requires_approval` is checked at step 8. A tool listed in both is always `deny` and never reaches step 8. So `git.push` must leave the forbidden baseline for `needs_approval` to be reachable. DECIDED by Contract Smith.

### 1.1 Rules added (DECIDED by Contract Smith, Hack Lead/Johnathan may override)

1. **Baseline forbidden list** is `network.*`, `publish.*`, `submit.*`, `payment.*`, `fs.delete`. These stay forbidden. `git.push` is removed. (Nothing else changes.)
2. **Intrinsic class.** The tool `git.push` always has class `push`. Schema validation rejects an `allowed_actions` item with `tool: "git.push"` and any other class (this stops a contract mislabelling a push as `compute`). `push` is already one of the six mandatory `requires_approval` members.
3. **A push is only reachable if the contract lists it.** Deny by default still applies at step 5. A contract with no allowed `git.push` action returns `deny` (`reason: no_matching_allowed_action`) for a push, which is stricter than `needs_approval`. Only roles that need a push request list it:
   - `coding` template: includes an allowed action `{ action_id: "git_push", tool: "git.push", class: "push", args_constraints: { remote: {equals: "<set by Johnathan>"}, branch: {pattern: "<glob>"}, commit: {pattern: "^[0-9a-f]{40}$"}, force: {equals: false} } }`.
   - `asset-step` and `triage` (intake) templates: no push action. The widening check flags adding one as "WIDER THAN USUAL".
4. **Other git tools unchanged.** `git.force`, `git.remote` and `deploy.*` stay in the coding template's `forbidden_actions` (Part 4 keeps them as `deny`).
5. **One-time approval record (new, makes "exact action" concrete).** When the gate returns `needs_approval`, Johnathan's yes (via Ultralord) is written as an audit entry of `kind: approval`, `scope: "action"`, `action_hash = sha256(canonical_json({agent, tool, args, paths, spend}))`, `approved_by: johnathan`, `approved_at`. On the next `check()` with an identical action, gate step 8 finds an unconsumed approval with the same `action_hash` and `(contract_id, version)` and returns `allow` (`reason: one_time_approval_consumed`), marking it consumed by that `audit_seq`. Consumed, expired (after `limits.time_window.not_after`), or hash-mismatched approvals never match, so a changed commit id or branch needs a new yes. Approval of a push is never inherited from a contract approval.
6. A contract may still add `git.push` to its own `forbidden_actions` as a hard deny (stricter). It is just not in the baseline.
7. The plain-language summary gets one line when a contract lists a push: "May request a push of <remote>/<branch>; each push needs your fresh yes."

### 1.2 Exact edits to CONTRACT_SYSTEM.md

| # | Where (CS line) | Current | Replace with |
|---|---|---|---|
| a | 3.1 `forbidden_actions`, line 197 | "Baseline entries for every contract: `git.push`, `network.post`, `publish.*`, `submit.*`, `payment.*`, `fs.delete` outside scratch." | "Baseline entries for every contract: `network.*`, `publish.*`, `submit.*`, `payment.*`, `fs.delete`. `git.push` is not baseline-forbidden: it has class `push` and returns `needs_approval` (section 2.4 step 8). A contract may add it here as a hard deny." |
| b | 3.1 `allowed_actions`, line 196 | "... `class` is `read`, `write`, `compute`, `local_commit`, or an approval class (below)." | Append: "The tool `git.push` must have class `push`; any other class makes the schema invalid." |
| c | 2.1 principle, line 55 | "These always return `needs_approval`, even inside an approved contract, and need a separate per-action approval recorded in the audit log. Spend defaults to $0. No `git push`, no posting, no submission." | "Actions in a `requires_approval` class (live, publish, spend, push, submit, send_message and any extras) are never `allow` without a separate one-time approval recorded in the audit log. Inside a contract that lists them they return `needs_approval`. `publish.*`, `submit.*`, `network.*` and `payment.*` are also baseline-forbidden, so they return `deny` unless a contract explicitly removes the forbidden entry and allows the action. Spend defaults to $0 (a spending call is then `deny`). `git.push` returns `needs_approval` only in a contract that lists it; otherwise `deny`." |
| d | 2.4 gate step 4 (line 108) | "Matches `forbidden_actions` gives **deny**." | Append: "Because this runs before step 8, a tool in both `forbidden_actions` and a `requires_approval` class is always `deny`." |
| e | 2.4 gate step 8 (line 112) | "Action class in `requires_approval` (live, publish, spend > 0, push) gives **needs_approval**. It becomes allowable only through a recorded one-time approval for that exact action." | "Action class in `requires_approval` (the six mandatory classes `live`, `publish`, `spend`, `push`, `submit`, `send_message`, plus any extras) gives **needs_approval**, unless an unconsumed one-time approval exists for the same `action_hash` and `(contract_id, version)` inside the time window, in which case **allow** (`reason: one_time_approval_consumed`) and the approval is consumed. Class `spend` is reached only when `spend > 0` and the contract has a nonzero approved cap; with `spend_usd` 0 step 7 already returned `deny`." |
| f | 2.9 test 8 (line 176) | "`git push`, post, publish, submit: always `needs_approval`." | "See tests 8, 26 to 30: a push in a contract that lists `git.push` is `needs_approval`, never `allow` without a one-time approval; a push in a contract that does not list it is `deny`. `publish.*`, `submit.*`, `network.*` are baseline `deny`; they are `needs_approval` only where a contract explicitly removes the forbidden entry and allows the action." (Test 8 text becomes: "`git.push` with an allowed push action: `needs_approval`; never `allow` without a recorded one-time approval.") |
| g | 2.9 test 7 (line 175) | "deny or `needs_approval`, never allow." | "**deny** with `spend_usd` 0; `needs_approval` only under a nonzero approved cap (see 1A test 19)." |
| h | 2.4 audit (2.6, line 139) | kinds undefined | Add the one-time approval entry (rule 5 above) to the list of entry kinds (full list in 3.5, M-23). |
| i | 3.5 coding template, line 282 | "`git.push` is forbidden and also in `requires_approval`." | "`git.push` is an allowed action of class `push` (remote, branch, commit pinned by constraints, `force` equals false). It is in `requires_approval`, so the gate returns `needs_approval`; Johnathan's one-time yes is required for each push. `git.force`, `git.remote` and `deploy.*` stay forbidden." |
| j | 3.3 example line 242 and 1A section 8 example line 110 | `forbidden_actions` lists `git.push` | Remove `{ "tool": "git.push" }`. The ingest contract has no push action, so a push is `deny` at step 5. (The 3.3 example is already replaced by 1A section 8.) |
| k | 2.1 / 3.4 table, line 276 | already lists `push` as per-action approval | No change. |
| l | 5 MVP cut, line 337 | "`needs_approval` for push/publish/spend/live/submit" | "`needs_approval` for push (in contracts that list it), and for publish/submit/spend/live/send_message where a contract explicitly allows them; baseline `deny` otherwise". Line 342 "tests 1 to 12" becomes "tests 1 to 30" (see M-43). |

### 1.3 Edits to Part 4 and Part 3 text (for their owners, wording only)

- Part 4 test 8: `git push` is `needs_approval` (coding contracts list it); `git remote add`, `git push --force`, `deploy.*`, `net.*` stay `deny`. Part 4 validator (build step 8): "forbidden `git.push`" becomes "`git.push` must have class `push`". `commit_guard` still refuses remote and force, and no longer refuses a plain push by itself; the gate decides.
- Part 3 (2.1, 4.2, G4): already says push needs approval; no change.

### 1.4 New acceptance tests (numbered after 1A test 25)

26. **Push needs approval.** Given a `coding` contract with an allowed `git.push` (class `push`) and `git.push` not in `forbidden_actions`, when the agent calls `check` for a push of an allowed remote and branch, then the decision is `needs_approval` and an audit entry exists. (It is never `allow` at this point.)
27. **Push without a listed action.** Given an `asset-step` contract with no `git.push` action, when a push is checked, then deny (`no_matching_allowed_action`). Given the same coding contract with `git.push` added to `forbidden_actions`, then deny at step 4 (forbidden wins over `requires_approval`).
28. **Baseline still forbidden.** Given a contract that allows `network.post`, `publish.x`, `submit.x`, `payment.pay` or `fs.delete` in `allowed_actions` without removing the baseline entries, when each is checked, then deny at step 4. Schema validation also warns that the contract lists an allowed action it forbids.
29. **Class pinning.** Given an `allowed_actions` item with `tool: "git.push"` and `class: "compute"`, then schema validation fails.
30. **One-time approval binding.** Given test 26's `needs_approval` and a recorded approval for that `action_hash`, when the identical action is checked, then `allow` (`one_time_approval_consumed`) and the approval is consumed. When it is checked a second time, then `needs_approval` again. When the commit id differs, then `needs_approval`. When `now > not_after`, then deny.

**OPEN (Johnathan), confirms OQ-C14:** confirm push is `needs_approval` (not hard `deny`), and who runs the push after approval (the agent, or Johnathan himself as Part 4 says). Default: Hack Lead's decision stands. The gate only returns the decision; it does not push. This closes M-58 and OQ-C14 once confirmed.

---

## 2. M-50: stale "section 3.9" reference

Found in CONTRACT_SYSTEM.md in two places. CS has no section 3.9 (section 3 ends at 3.6). The correct reference is **section 3.6** (Hackathon config placeholder).

- Line 59 (2.1, last bullet): "(see section 3.9)" becomes "(see section 3.6)".
- Line 84 (2.3, last paragraph): "no Meta model is assumed (3.9)" becomes "no Meta model is assumed (3.6)".

No other "3.9" appears in CS or 1A. DECIDED by Contract Smith. The draft's "twice" claim is correct.

---

## 3. Other Part B mismatches that touch the schema, gate, evidence, audit log or compiler

Format: ID, agree?, fix wording or "no change needed". All DECIDED by Contract Smith, Hack Lead/Johnathan may override, unless marked OPEN.

**M-01 Required top-level fields.** Agree. Fix: every example in Parts 2, 3, 4 carries `version`, `goal`, and the approval fields (`approved_by`, `approved_at`, `content_hash`, null while draft). Add to CS 3.2: "Rule 5. A record without `version` and `goal` is not a contract." Part 4's "bug record" is shaped like a contract: see M-24.

**M-02 `inputs` item shape.** Agree. Fix: every input has `name` (required) and `path` or `value`; Part 4 adds `name` (for example `impact_frame`, `run_log`).

**M-03 Allowed-action shape and constraint kinds.** Agree. Fix (mapping for owners): `{tool, args}` becomes `{action_id, tool, class, args_constraints}`. `dest_prefix`, `path_prefix` become `path_within` globs. `max_images`, `max_files`, `max_lines_changed` on a per-call argument become `max`; as step totals they are not gate fields (see M-10). `local_only: true` becomes `{equals: true}`. `allow: [...]` (cmd.run) becomes `one_of`. `message_must_include` becomes `pattern`. New text for CS 3.1: "`path_within` globs: `*` does not cross `/`, `**` does; a bare directory is not a glob and is invalid". The `*_prefix` forms are invalid in the schema.

**M-04 Tool names.** Agree. Fix: one registry `schema/tools.json` (a file in the proposed layout, 2.7) listing each tool name, intrinsic class (for example `git.push` is `push`) and argument names. Tool name regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_*]*$` (`*` only as a wildcard in `forbidden_actions` and constraints). An unknown tool matches nothing, so it is `deny`. Old names to map: `file_read` to `fs.read`, `file_copy` to `fs.copy`, `file_write` to `fs.write`, `image_gen` to `image.generate`, `vision_review` to `vision.review`, `net.*` and `net.upload` to `network.*` and `network.upload`, `cmd.run:rm -rf` and `fs.write:src/engine/` to constraints, and `fs.write_outside_allowed` is not a tool (path scope covers it; delete). `segmenter` and `audio_gen` become `image.segment` and `audio.generate`: names proposed, Pipeline Smith confirms. The `image.convert_png` name is settled (see M-26).

**M-05 `forbidden_actions` shape and baseline.** Agree. Fix: items are objects `{tool, args_constraints?}`, never strings. Baseline is as in 1.1 (`network.*`, `publish.*`, `submit.*`, `payment.*`, `fs.delete`; no `git.push`). Two stale words in CS 3.1 are fixed here: `network.post` becomes `network.*` (matches every example and the instruction), and "`fs.delete` outside scratch" becomes plain `fs.delete` (no schema field defines "scratch"; a contract that needs scratch deletion declares a separate allowed tool with a `path_within` constraint, and the widening check flags it). `overwrite_without_hash_match` is dropped in favour of the constraint (M-20). Part 4's `fs.write:...` strings become path scope.

**M-06 `requires_approval` shape and classes.** Agree. Fix: a list of class strings only; a boolean makes the schema invalid. The six mandatory classes must be present (Part 2's list missing `live`, `push`, `submit`, `send_message` is invalid). Extras `engine_change` and `direction_selection` are legal (1A section 4). `post` is not a class: use `publish` (public posting) or `send_message` (messages). Part 4: "requires_approval true for Engine bugs" becomes adding `engine_change` to the list and putting the engine path in `allowed_paths.write` only in a later approved version (default is deny, 1A section 4). Part 3 B5 and Step D: a list, not `true`.

**M-07 Ingest own contract.** Agree; decided D1. No schema change.

**M-08 `allowed_paths` format.** Agree. Fix: absolute globs everywhere (CS 3.1 already says globs). The compiler substitutes `<run_id>` and the run root from a harness config at compile time; the approved contract holds only absolute paths. A relative path or a bare directory is a schema error. Proposed CS 3.1 addition: "Paths are absolute globs; a path without a leading `/` is invalid." The repo root for Part 4 is part of the harness config (OQ-B3).

**M-09 `time_window` form.** Agree. Fix: the schema says `time_window` is one of two shapes. Draft shape `{not_before: null, not_after: null, ttl_hours: <int>}` is valid only when `status` is `draft`. Approved shape `{not_before, not_after}`, both ISO-8601 with zone, no `ttl_hours`. `approve()` resolves draft to approved and then hashes. `"4h"`, `"1h"`, `"PT1H"` are not valid; the compiler converts them to `ttl_hours` (1, 2, 4). Part 2 names a `time_window` with no value: give `ttl_hours`.

**M-10 `limits` keys.** Agree. Fix: the gate enforces only `spend_usd`, `max_calls`, `time_window`. Any other limit goes in one of two places: a per-call bound as a `max` or `min` constraint in `args_constraints` (for example `max_files` per `fs.write` call), or a measured step bound in `extensions.<ns>.thresholds` that the step's own check enforces (not the gate). `max_lines_changed` is a diff property: use `extensions.triage.thresholds.max_lines_changed` plus a `checklist` item `diff_within_limit`, with the measured value in an `output_snippet`. Keys `max_images`, `max_files`, `max_lines` are not allowed inside `limits` (schema: `limits` has `additionalProperties: false`). Defaults for other roles: **OPEN (Johnathan), OQ-C5**.

**M-11 `required_evidence` keying.** Agree. Fix: keys are `action_id` values of the same contract; schema validation rejects a key that is not an action id (this catches Part 4's tool-name keys and the `review` key). Part 4's `review` becomes an evidence item `reviewer_note` under the `git_commit` action (or under an explicit `review_gate` action of class `compute`). Part 3 `["file hash"]` becomes `[{kind: "file_hash", params: {...}}]`.

**M-12 Evidence kinds and checklist names.** Agree it is a mismatch. Fix: no new evidence kinds in v0.3. `commit_id` becomes an `output_snippet` with `pattern: "^[0-9a-f]{40}$"` under the commit action. Checklist item ids are free strings `^[a-z][a-z0-9_]*$` chosen by the template; there is no global registry. Each template lists its items (for example `asset-step`: `images_viewed`, `no_lore_text`, `no_trademarked_material`; `no_heat_distortion` is a Step A item per 3A). Part 2's "viewed / no text / no trademark / no heat distortion" are those same ids. **OPEN (Hack Lead, OQ-C13):** if Triage needs a numeric range check, add a kind `number_in_range` in a later version; I do not add it now.

**M-13 Which contract an action belongs to.** Agree, resolved by 1A section 1. Fix for Part 4: replace `gate(contract, action)` with `check(action)` carrying `contract_id`. No further change.

**M-14 `extensions` openness.** Agree, resolved (D4, 1A section 2). Part 2 and Part 3 move fields to `extensions.pipeline`; no schema change. Fix for Part 4: keys under `extensions.triage`.

**M-15 Part 4 mutable state inside hashed `extensions`.** Agree it is a real problem (the hash covers `extensions`). Fix, adopting the merger's proposal: add CS 3.2 rule 6: "`extensions` holds fixed facts only. State that changes during a run (`state`, `severity`, `duplicate_count`, `owner`) is stored outside any contract, in the subsystem's own record file." Bug records live in `triage/bugs/BUG-####.json` and carry no contract fields. The fix contract's `extensions.triage` holds fixed facts: `bug_id`, `author`, `reviewer`, `regression_test`, `gates`, `approval_points`. Intake is a contract (one per intake session, id `ct-triage-intake-0001`), not one per bug. **OPEN (Johnathan) only if he wants a different split (OQ-C7).**

**M-16 Who checks `inputs[].sha256`.** Agree; resolved by 1A section 6. Wording for Part 3 G5 and Part 2: "input sha256 mismatch" becomes "`verify_inputs` returns fail; gate step 2b denies (`inputs_unverified`); the step is not started and `StepResult.status` is `failed`". Late binding stays **OPEN (Johnathan), Q14 / OQ-C8**.

**M-17 Evidence record format and refs.** Agree; resolved by 1A section 7. Fix wording: Part 2 3.5 and Part 3 3.2 may keep their file names (`<step>.evidence.json`) but the file content is the 1A payload `{contract_id, contract_version, action_id, items[]}`, and `evidence_refs` is the single sha256 of its canonical JSON. Part 2 T12 tests that payload and that the hash matches. Part 3 `{step_id, files[]}` becomes `items[]` with `file_list` params.

**M-18 Spend rule.** Agree; D5. Fix: CS test 7 and step 8 reworded (1.2 g and e). Part 3 G4/Step D/Q6: "a spending call is deny at `spend_usd` 0". Part 4 test 10: a coding contract with `spend_usd` > 0 failing validation is acceptable as a **role-template rule** (`coding` template validation: `spend_usd` must be 0), not a schema rule. A nonzero approved cap stays possible for other roles. **OPEN (Johnathan), OQ-D9:** is any budget approved.

**M-19 `StepResult` statuses.** Agree it is a mismatch. Fix: `StepResult.status` is one of `complete`, `incomplete`, `failed`, `needs_approval`. `ok` is the old name for `complete`. `needs_approval` is returned when a gate call returned it, and `detail.class` names the class. Part 2's `awaiting_pick` is a run state of Part 2's own state machine, shown as `needs_approval` with `detail.class: direction_selection` in `StepResult`; it is not a separate `StepResult` status (differs from the merger's proposal, which adds `awaiting_pick`; Hack Lead decides). Contract `status` is unchanged. 1A section 9 line "StepResult.status is one of complete, incomplete, failed" is extended by `needs_approval`.

**M-20 Overwrite protection.** Agree; resolved by 1A section 5. Fix: Parts 2 and 3 drop the `overwrite_without_hash_match` string and put `no_overwrite_unless_same_hash` on each destination constraint. Part 3 I3 ("a different file at the same path is denied") is exactly 1A test 20.

**M-21 Writes to game project or engine.** Agree; resolved by 1A section 4. Fix: Part 3 B5-1 expects `deny` (project path not in `allowed_paths.write`); a later approved version may add the path plus class `project_write`, which then returns `needs_approval`. Part 4 uses `engine_change`. The `needs_approval` flow is demonstrated by the push test (26) instead. **OPEN (Johnathan), OQ-C9 and OQ-C12.**

**M-22 `asset-step` defaults.** Agree; resolved by 1A section 9. Part 3 B1's "max_calls = number of files" is replaced by 12. Part 2 limits take the same default.

**M-23 One gate and one audit log.** Agree it is a real mismatch. DECIDED by Contract Smith (answers OQ-C11; Triage Smith to confirm): one gate (`check(action)`), one audit log (`audit/audit.jsonl`), one canonical-JSON and hash rule. Part 4's own `gate`, `audit_append`, `audit_verify` are replaced by calls to Part 1's. Part 4's field names map to the Part 1 entry: `actor` to `agent`, `hash` to `entry_hash`, `args` inside `action`. Entry kinds (CS 2.6, listed explicitly): `gate`, `approval` (contract approval and one-time action approval), `revocation`, `evidence`, `inputs_verify`, `state_transition` (new, for Part 4 bug and fix state changes; `detail` object; does not change counters), `command` is not a kind (a command is a gated action, so it is a `gate` entry). The fix contract forbids writing `audit/` and `contracts/`; the path `triage/audit/` disappears.

**M-24 Contract store and layout.** Agree. Fix: one store `contracts/<id>/v<version>.json` for all subsystems. Part 3's `contracts/templates/` and `contracts/instances/<run_id>/` become `intents/<step>.intent.json` compiled into the one store (3A already says this); templates stay in `templates/<role>.json`. Contract id regex (replaces "ct-<kind>-<n>" in CS 3.1): `^ct-[a-z0-9]+(-[a-z0-9]+)*-[0-9]{4}$`. Fix contract ids: `FIX-0042-1` becomes `ct-fix-0042-0001` (last group is the attempt number); `FIX-0042-1` may remain as a display label in `extensions.triage.fix_ref`. `BUG-####` records are not contracts (see M-15). Roles: `asset-step`, `coding`, `triage` (the three templates already in CS 3.2).

**M-25 `source_dest_hash` with conversion.** Agree; resolved (D1, 1A section 3). No further schema change.

**M-26 Ingest tool name.** Agree. The merger lists it OPEN, but it is **resolved**: Pipeline Smith confirmed `image.convert_png` (class `write`, `src` and `dest` limited by `path_within`), see OQ-C10 and 1A Q16. `fs.copy` is a pure copy, `image.convert_png` a conversion. Parts 2 and 3 replace `file_copy`. Mark M-26 and the "OPEN" part of M-04 resolved.

**M-27 Palette ingested or rendered locally.** No schema change needed; both fit the schema. If OQ-D3 is answered "rendered locally", then 1A section 8's example changes `file_list.expect_count` from 3 to 2 and drops the palette input; the palette becomes a separate compute action in the Step A contract. Until OQ-D3 is answered the 1A example stays as written (it is illustrative). **OPEN (Concept Artist / Pipeline Smith, OQ-D3).**

**M-28, M-29, M-31, M-36 (slug, `<direction>`, ingest destination, hashed `.jpg` names).** Agree these hit CS 3.3 (my example). No new fix: 1A section 8 replaces CS 3.3 and already uses `^[a-z0-9]+(-[a-z0-9]+)*$`, `<topic>/<slug>/<slug>_*.png`, hashed `.jpg` sources. Merge edit: replace CS 3.3 and the 3.5 text ("copies ... into `/workspace/concepts/<topic>/`" stays; drop "`refined/`" references) with 1A section 8.

**M-33 Run directory root.** No schema impact, so no change from me. The gate checks whatever absolute globs the contract holds. DECIDED by Contract Smith: the root is a harness config value substituted at compile time (`<run_id>` and the root), so choosing `/workspace/runs/` or `/workspace/pipeline/runs/` later is a config change, with no schema or contract edit. 1A uses `/workspace/runs/`. **OPEN (Johnathan/Ultralord), OQ-B3.**

**M-34 Repo and tool roots.** No change needed: the shelved `/workspace/contract-system` folder is not part of the design (CS scope note), and the layout in CS 2.7 is a proposal, not a path decision. **OPEN (OQ-B3).**

**M-37 Generation log.** No new evidence kind needed. The log is an `inputs` item with `sha256` (1A section 8). Note a dependency for Hack Lead: if the ingest contract is approved before the log exists, the log input must use `late_bind: true` (Q14); if the log exists first, it is pinned. The one-to-one mapping and `source_sha256` checks (I6, I7) are step checks whose result is recorded as `checklist` item `generation_log_mapping_verified` plus the measured result as `output_snippet`. **OPEN (OQ-D2)** on whether a Meta harness produces one; unverified.

**M-38 Step A write paths.** Agree with 3A section 4: list the absolute run path in `allowed_paths.write` and give it a `no_overwrite_unless_same_hash` constraint where files are written. No schema change.

**M-41 Test ids collide.** Agree. DECIDED: prefix per part: `CS-1` to `CS-30` (this doc adds 26 to 30), `CA-T1..`, `PL-G1..`, `TR-1..`. A test cited across specs always carries its prefix.

**M-43 MVP test count.** Agree. CS 5 MVP step 7 "acceptance tests 1 to 12 in 2.9" becomes "`CS-1` to `CS-30` (2.9, 1A section 10, and section 1.4 of this file)".

**M-49 Where the gate stops.** Agree with the conclusion, with a correction to the reasoning. The gate can compare numbers: `max` and `min` constraints on call arguments. What it cannot do is compare a measured result: `output_snippet` matches a pattern, not a range. So: bounds in `extensions.<ns>.thresholds`, the measuring step records the value as an `output_snippet`, and a `checklist` item (for example `size_within_thresholds`) is attested by the step. The evidence checker records it and does not recompute (CS 2.5 rule on attestations).

**M-54, M-55 Questions answered by decisions.** No change needed. M-54 is answered by D4, D6, D7. For M-55: CS Q6 (answered for `asset-step`, open for other roles, OQ-C5), Q10 (open, OQ-C12), Q12 (answered by D7, OQ-C6), Q13 (answered by D4).

**M-59 (NEW, proposed): CS contradicts itself on publish and submit.** CS 2.1 and test 8 say post, publish and submit always return `needs_approval`, but the baseline forbids `publish.*`, `submit.*` and `network.*` (gate step 4, so they return `deny`). Same root cause as M-58. DECIDED by Contract Smith: baseline stays forbidden (so `deny`), and rewording is in 1.2 c and f. Hack Lead may want to add this to Part B.

**Not mine, no change from me (listed so nothing is lost):** M-32 and M-45 to M-48 (image size thresholds, pipeline step checks), M-30 (sheet name), M-35 (store visibility), M-39 and M-40 and M-42 (step actions, step names, Step A tests), M-44 (`notes.md`), M-52 and M-53 (Part 3 and 3A numbering), M-56 (Meta models, all unverified), M-57 (priority). None touches the schema, gate, evidence, audit log or compiler, apart from the notes already given above.

---

## 4. Index of ids addressed

M-01, M-02, M-03, M-04, M-05, M-06, M-07, M-08, M-09, M-10, M-11, M-12, M-13, M-14, M-15, M-16, M-17, M-18, M-19, M-20, M-21, M-22, M-23, M-24, M-25, M-26, M-27, M-28, M-29, M-31, M-33, M-34, M-36, M-37, M-38, M-41, M-43, M-49, M-50, M-54, M-55, M-58, and new M-59.

## 5. Items for Hack Lead

1. **M-58 reach:** `needs_approval` for a push exists only in contracts that list `git.push`. Contracts without it return `deny`. If you want `needs_approval` everywhere, say so; I would not, because it widens deny-by-default.
2. **M-19:** I do not add `awaiting_pick` as a `StepResult` status (differs from the merger's proposal).
3. **M-26 and the M-04 "OPEN" note:** stale, `image.convert_png` is resolved.
4. **M-59:** new mismatch to add to Part B.
5. **M-23/M-24:** Part 4 must adopt one gate, one log and the `ct-` id pattern; Triage Smith to confirm.
6. **Open for Johnathan:** push confirmation and who pushes (OQ-C14), late binding (OQ-C8), extra classes and engine deny-by-default (OQ-C9), default limits for other roles (OQ-C5), spend budget (OQ-D9), field-split for triage (OQ-C7), run root (OQ-B3).

---

## 6. Additions from Pipeline Smith's Part B review

Context read: `/workspace/pipeline/PIPELINE_FIXES_PARTB.md` and `/workspace/concepts/CONCEPT_FIXES_PARTB.md`. All items here are **DECIDED by Contract Smith, Hack Lead/Johnathan may override.**

**(a) Registered tool names (adds to M-04).** The tool registry (`schema/tools.json`) gets two more entries, both class `write`, each with `dest` limited by `path_within`:
- `image.render_palette`: renders the palette PNG locally from hex values.
- `image.render_sheet`: renders the comparison sheet `<topic>_comparison_sheet.png` (D3).

Rules for both: `dest` carries `no_overwrite_unless_same_hash`, and `expected_sha256` is required, as for `image.convert_png`. Evidence is a `file_hash` item. `image.convert_png` was agreed earlier (Q16) and is unchanged. Registering the names does not settle OQ-D3: whether the palette is rendered locally or ingested is still open.

**(b) Push scope wording (matches section 1).**
- `git.push` reaches `needs_approval` **only if** an `allowed_actions` item with `tool: "git.push"` and class `push` is listed, and `git.push` is not in `forbidden_actions`. If it is not listed, the result is `deny` (step 5, `no_matching_allowed_action`).
- Asset, pipeline and concept templates never list a push action. Only the `coding` template does.
- **Appendix 3A fix** (section 1, forbidden row) should read: "Use the v0.3 baseline list (CS baseline minus `git.push`)." It must not say "CS baseline", which imported `git.push` as forbidden.
- **M-58 row and OQ-C14** in the merged draft should say: "`git.push` is `needs_approval` in contracts that list it, `deny` otherwise (decided by Hack Lead; Johnathan can override)". They still show "PROPOSAL / default deny". Replace the proposal text; do not leave both.

**(c) The broad phrase is only partly true.** "Live, published, spent or pushed returns `needs_approval`" (Parts 2, 3, 4, and CS 2.1) holds **only for actions listed in `allowed_actions`** whose class is in `requires_approval`. Replacement wording for Parts 2, 3 and 4 gate-behaviour lines and tests (Pipeline Smith's G4 split is accepted):
> A listed action whose class is in `requires_approval` returns `needs_approval`. An unlisted action returns `deny`. `publish.*`, `submit.*`, `network.*`, `payment.*`, `deploy.*` and `fs.delete` are baseline-forbidden, so they return `deny`. Spend at `spend_usd` 0 returns `deny`; it is `needs_approval` only under a nonzero approved cap.

Tests: `PL-G4a` push with a listed action expects `needs_approval` (nothing runs); an unlisted push expects `deny`. `PL-G4b` spend at $0 expects `deny`. A `live` test is added only for a step that lists a `live` action (none do).

**(d) Refined-frame ingest.** A second instance of the ingest contract that writes only `<topic>/<slug>/refined/<slug>_*.png` **needs no schema change.** It is the same step B1 with a new `contract_id` (for example `ct-pipeline-ingest-0002`), `extensions.pipeline.phase: "refined"`, and `allowed_paths.write` and the `dest` `path_within` limited to that glob. It keeps `image.convert_png`, `source_sha256`/`dest_sha256`, `no_overwrite_unless_same_hash` and the generation-log input. The initial ingest contract (`ct-pipeline-ingest-0001`) still cannot write under `refined/`.
- Wording fix for 1A section 8: "ingest never writes there" becomes "the **initial** ingest contract never writes there; refined frames come from a second ingest contract limited to `refined/<slug>_*.png`. `refined/engine_notes.md` is written by the concept step, not by ingest."
- 1A test 24 splits into **24a** (initial ingest writing under `<slug>/refined/` or outside `<topic>/<slug>/`: deny) and **24b** (refine-ingest contract writing `refined/<slug>_*.png`: allow; writing `<slug>_hero.png` or any other path: deny).
- RESOLVED by Hack Lead and Concept Artist: refined frames keep the existing `<slug>_<frame>.png` pattern under `<slug>/refined/` (no `_refined_` prefix). The contract schema does not depend on the name.
- This answers the M-31 part where Pipeline Smith and Concept Artist found Part 2 step 9 conflicting with "ingest never writes to `refined/`".

---

## 7. Answers to Triage Smith (`/workspace/triage-spec/TRIAGE_PROPOSED_FIXES.md`)

All answers **DECIDED by Contract Smith, Hack Lead/Johnathan may override.** Numbers follow Triage Smith's questions.

1. **Push baseline.** Baseline `forbidden_actions` drops `git.push` (section 1). `git.push` is `needs_approval` in the `coding` template, `deny` where unlisted.
2. **`deploy.*`.** `deploy.*` is **baseline-forbidden (`deny`) in the MVP for all templates.** Deploy is out of the harness. Section 1.1 rule 1 is amended: the baseline is `network.*`, `publish.*`, `submit.*`, `payment.*`, `fs.delete`, `deploy.*`. Coding templates still also forbid `git.remote` and `git.force`.
3. **Contract id pattern.** `^ct-[a-z]+(-[a-z0-9]+)*-[0-9]+$`. Both `ct-fix-0042-1` and `ct-fix-0042-0001` are valid; 4-digit zero-padded numbers are the recommended convention, not required. This **replaces** the stricter pattern I gave under M-24 (`...-[0-9]{4}`). `BUG-####` stay data records, not contracts. `FIX-0042-1` may remain as a display label in `extensions.triage.fix_ref`.
4. **Glob dialect** (for CS 3.1 `allowed_paths` and `path_within`). Paths are POSIX-normalized; matching is case-sensitive; `*` and `?` do not cross `/`; `**` matches any depth; no brace expansion; symlinks are resolved before matching. Absolute globs remain the compiled form; repo-relative globs are accepted in intent files until OQ-B3 and are made absolute at compile time.
5. **Audit `kind`.** `kind` is an **open string**. Defined kinds: `decision` (every gate decision), `approval` (contract and one-time action approvals), `revocation`, `evidence`, `input_check` (the `verify_inputs` result), `extension_note`. Unknown kinds are allowed and are still hash-chained and counted by `audit_verify`. Triage may use `state_transition` and `command` as such unknown kinds; they never change gate counters. Renames against my earlier text: `gate` is now `decision`, and 1A's `inputs_verify` is now `input_check`. The gate's `reason: inputs_unverified` is unchanged. (This supersedes my M-23 kind list.)
6. **Source writes.** Writes to project or engine source use class `project_write`. Default is deny unless the path is in `allowed_paths.write`. While the engine pause stands, engine paths stay out of `allowed_paths.write` and are denied. `project_write` is a legal extra class (1A section 4). Clarification, for Hack Lead: whether it prompts on every write is set by listing it in `requires_approval`. The `coding` template does **not** list it (approving the fix contract with its exact paths is the approval, so each edit does not ask); `engine_change` is always listed. A contract may add `project_write` to `requires_approval` to make each write ask.
7. **Intake contract.** Intake may be **one standing contract per run window**, with `allowed_paths.write` limited to the bug folder (`triage/bugs/*.json` and evidence folder, absolute globs). It renews at `not_after`. A renewal is a new version with a new resolved window, and **each renewal needs Johnathan's approval**. CS 3.5's "intake is read-only" is wrong: it writes bug records. Replace with "intake reads evidence and writes only the bug folder".
8. **Fix window.** Two hours for a fix contract is fine. The template default stays 4 hours (`ttl_hours`). Hard cap is **24 hours** (`not_after - not_before` of an approved contract must not exceed 24h) unless Johnathan raises it. He does so by changing the harness setting `max_window_hours`, recorded as an `approval` audit entry. Schema validation fails above the cap.

**Triage Smith's pushbacks, acknowledged:**
- **M-16:** pinning a frozen `bug_snapshot.json` (with `sha256`) instead of `late_bind` on the mutable bug file is **acceptable and preferred**. It does not depend on Q14. Fix contracts use a pinned snapshot input. `late_bind` stays available but unused here.
- **M-12:** `output_snippet` (label `commit_id`, pattern `^[0-9a-f]{7,40}$`) for the commit id, plus a separate review contract (or a `reviewer_note` under a review action), is **acceptable**. No new evidence kinds. Note: this relaxes my earlier 40-hex pattern in section 3 (M-12) to 7 to 40 hex characters; the earlier line is superseded.

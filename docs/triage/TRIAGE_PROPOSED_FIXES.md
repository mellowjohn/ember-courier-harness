> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Triage Spec: Proposed Fixes (separate file; `TRIAGE_AND_CODE_SPEC.md` is untouched)

Owner: Triage Smith. Documentation only. "L" numbers refer to lines of our spec. Sources: `CONTRACT_SYSTEM.md` (CS), `SCHEMA_DECISIONS_v0.2.md` (1A, wins on conflict), `ARCHITECTURE_DRAFT.md` Part B. Decisions applied: D4/D6 (`extensions.triage`), D5 (spend), M-58 (push is `needs_approval`). Johnathan can override all of them.

## 1. Fields moved to `extensions.triage`

The content hash covers `extensions`, so any edit after approval resets approval. Only fixed fields go in the contract. Mutable state stays in the plain data file `triage/bugs/BUG-####.json` (M-15 proposal, accepted).

| Field (L) | New home |
|---|---|
| `bug_id`, `source`, `build_id`, `area`, `fingerprint` (L141-152) | `extensions.triage`, set at intake |
| `title`, `steps`, `expected`, `actual`, `frequency` | Bug file (content) |
| `severity`, `demo_impact`, `duplicate_*`, `owner`, `state`, `completeness` (L146-157) | Bug file (mutable) |
| `bug_id`, `reviewer_must_differ_from_author`, `regression_test`, `gates` (L198-203); `max_files`, `max_lines_changed` (L175) become `thresholds` | `extensions.triage` of the fix contract |
| `author` (L199) | Dropped: it is the contract's `agent` |
| `reviewer` (L200) | Review record and commit message; assigned after approval, so it cannot be hashed |
| `approval_points` (L204) | Dropped: `requires_approval` is the source of truth |

### Bug record (intake contract), corrected

```json
{ "id": "ct-triage-intake-0042", "version": 1, "agent": "triage-agent-1",
  "intent_text": "Triage finding: ember glow missing on Molten Slag fireball impact",
  "goal": "Record BUG-0042 from the attached evidence and rate it.",
  "inputs": [{"name": "frame", "path": "triage/evidence/BUG-0042/impact_frame.png", "sha256": "<hex>"},
             {"name": "log", "path": "triage/evidence/BUG-0042/run.log", "sha256": "<hex>"}],
  "allowed_actions": [
    {"action_id": "write_bug", "tool": "triage.write_bug", "class": "write", "args_constraints": {"path": {"path_within": "triage/bugs/BUG-0042.json"}}},
    {"action_id": "set_sev", "tool": "triage.set_severity", "class": "write", "args_constraints": {"severity": {"one_of": ["S1","S2","S3"]}}},
    {"action_id": "set_sev_s0", "tool": "triage.set_severity", "class": "write", "args_constraints": {"severity": {"equals": "S0"}}}],
  "forbidden_actions": [{"tool": "git.*"}, {"tool": "network.*"}, {"tool": "publish.*"}, {"tool": "submit.*"}, {"tool": "payment.*"}, {"tool": "fs.delete"}],
  "allowed_paths": {"read": ["triage/evidence/BUG-0042/*", "triage/bugs/*.json"], "write": ["triage/bugs/BUG-0042.json"]},
  "limits": {"spend_usd": 0, "max_calls": 50, "time_window": {"not_before": null, "not_after": null, "ttl_hours": 1}},
  "required_evidence": {"write_bug": [{"kind": "file_hash"}], "set_sev_s0": [{"kind": "reviewer_note"}]},
  "requires_approval": ["live","publish","spend","push","submit","send_message","engine_change","close_critical"],
  "extensions": {"triage": {"bug_id": "BUG-0042", "source": "vision_qa", "build_id": "dev-2026-10-27-a", "area": "vfx", "fingerprint": "vfx|fireball_impact|no_glow"}},
  "status": "draft", "approved_by": null, "approved_at": null, "content_hash": null }
```

### Fix contract, corrected

```json
{ "id": "ct-fix-0042-1", "version": 1, "agent": "coder-agent-1",
  "intent_text": "Restore ember glow on fireball impact (BUG-0042) without touching engine core",
  "goal": "Fix BUG-0042 in src/vfx/fireball with a regression test; local commit only.",
  "inputs": [{"name": "bug", "path": "triage/fix_contracts/ct-fix-0042-1/bug_snapshot.json", "sha256": "<hex>"}],
  "allowed_actions": [
    {"action_id": "read_src", "tool": "fs.read", "class": "read", "args_constraints": {"path": {"path_within": "src/vfx/**"}}},
    {"action_id": "write_src", "tool": "fs.write", "class": "write", "args_constraints": {"path": {"path_within": "src/vfx/fireball/**"}}},
    {"action_id": "write_test", "tool": "fs.write", "class": "write", "args_constraints": {"path": {"path_within": "tests/regression/BUG-0042/*"}}},
    {"action_id": "run_make", "tool": "cmd.run", "class": "compute", "args_constraints": {"cmd": {"one_of": ["make test","make lint","make format"]}}},
    {"action_id": "stage", "tool": "git.add", "class": "write", "args_constraints": {}},
    {"action_id": "commit", "tool": "git.commit", "class": "local_commit", "args_constraints": {"message": {"pattern": "^BUG-0042 ct-fix-0042-1: .+"}}},
    {"action_id": "push", "tool": "git.push", "class": "push", "args_constraints": {"force": {"equals": false}}}],
  "forbidden_actions": [{"tool": "git.remote"}, {"tool": "git.force"}, {"tool": "deploy.*"}, {"tool": "network.*"}, {"tool": "publish.*"},
    {"tool": "submit.*"}, {"tool": "payment.*"}, {"tool": "fs.delete"}, {"tool": "pkg.install"}],
  "allowed_paths": {"read": ["src/vfx/**", "tests/**", "triage/fix_contracts/ct-fix-0042-1/*"], "write": ["src/vfx/fireball/**", "tests/regression/BUG-0042/*"]},
  "limits": {"spend_usd": 0, "max_calls": 120, "time_window": {"not_before": null, "not_after": null, "ttl_hours": 2}},
  "required_evidence": {"write_src": [{"kind": "file_hash"}], "write_test": [{"kind": "file_hash"}],
    "run_make": [{"kind": "output_snippet", "params": {"label": "pre_fix_fail"}}, {"kind": "output_snippet", "params": {"label": "post_fix_pass"}}],
    "commit": [{"kind": "output_snippet", "params": {"label": "commit_id", "pattern": "^[0-9a-f]{7,40}$"}}]},
  "requires_approval": ["live","publish","spend","push","submit","send_message","engine_change","close_critical"],
  "extensions": {"triage": {"bug_id": "BUG-0042", "reviewer_must_differ_from_author": true,
    "regression_test": {"path": "tests/regression/BUG-0042/", "must_fail_before": true, "must_pass_after": true},
    "thresholds": {"max_files": 3, "max_lines_changed": 80},
    "gates": ["path_scope","lint","tests","diff_size","review","local_commit"]}},
  "status": "draft", "approved_by": null, "approved_at": null, "content_hash": null }
```
Engine-owned bugs (replacing `requires_approval: true`, L70, L195): engine paths stay out of `allowed_paths.write` (deny) until the pause lifts. A later approved version may add them with class `engine_change` (1A section 4). Review runs under a separate contract for the reviewer agent, with action `record_review` and `reviewer_note` evidence.

## 2. Push rule (M-58): `git.push` is `needs_approval`

Mechanics: `git.push` is not in `forbidden_actions` (step 4 would deny). It is an allowed action of class `push` (else step 5 denies), and `push` is in `requires_approval` (step 8). `force: false` makes a force push `deny`. `git.remote`, `git.force`, `deploy.*` and `network.*` stay forbidden, so they are `deny`. No triage contract allows a `live` class action, so deploy is `deny`. Corrected wording:

- **L14:** "Local commits only. `git.push` returns `needs_approval`; nothing is pushed without Johnathan's yes."
- **L94:** "never run `git.remote`, `git.force`, deploy, publish, network or package install. `git.push` returns `needs_approval` and runs only after Johnathan's one-time approval."
- **L96:** "Push, live, publish, submit and send_message return `needs_approval`. Spend at `spend_usd` 0 returns `deny`; it is `needs_approval` only under a nonzero approved cap. Network and deploy return `deny`."
- **L100:** "Commits stay local. A push is a gate action returning `needs_approval`; Johnathan approves it or pushes outside the harness."
- **L107, L221:** "Push: `needs_approval`, one-time approval. Deploy, publish, network: per schema class (deny or `needs_approval`). Never without approval." **L204:** delete.
- **L132, L185:** remove `git.push` from `forbidden_actions`.
- **L260 (flow):** `LC -. push action .-> PU[needs_approval: Johnathan yes]`.
- **L273 (MVP 6):** "a push attempt returns `needs_approval` and is logged; the demo has no remote, so nothing is pushed."
- **L325, L343:** `commit_guard` checks only message format and local-only; the gate decides push.
- **L340 (B8):** validator checks an allowed `push` action exists with `force` false, and `push` is in `requires_approval`.
- **L359 (test 8, split):** 8a `git push` returns `needs_approval`; with no approval nothing runs. 8b `git push --force`, `git remote add`, any `deploy.*` or `network.*` return `deny`.
- **L375 (App. D):** "executing a push without approval; deploying, publishing, any spend."

## 3. Field-name check

| Old (L) | New | Source |
|---|---|---|
| No `version`, `goal`, `approved_by`, `approved_at`, `content_hash` (L114, 119-206) | add all | CS Quick ref |
| `agent` `triage`, `coder` (L121, 168) | one identity per contract | CS 3.1 |
| `inputs` without `name` (L123, 171) | `{name, path, sha256}` | CS 3.1 |
| `{tool, args}`; `max_without_review`, `max_files`, `local_only`, `message_must_include` (L127-129, 173-179) | `{action_id, tool, class, args_constraints}`; `one_of`, `thresholds`, dropped, `pattern` | CS 3.1 |
| `allowed_paths` prefixes (L131, 181) | globs | CS 3.1 |
| `forbidden_actions` strings, `net.*`, `fs.write_outside_allowed`, `fs.write:...` (L132, 185-186) | `[{tool}]`; `network.*`; path scope covers paths | CS 3.1 |
| `time_window: "PT1H"` (L133, 188) | draft `ttl_hours`; approved ISO dates | 1A section 9 |
| `required_evidence` by tool (L134-137, 189-194) | by `action_id`, `[{kind, params}]` | CS 2.5 |
| `commit_id`, key `review` (L192-193); "merge note", "approver id", "verification output" (L214, 217, 222) | `output_snippet`; review contract; `reviewer_note`; approval record | CS 2.5 |
| `requires_approval: false/true` (L138, 195) | class list: six mandatory plus extras | 1A section 4 |
| Bug `state` (L74, 156) | stays; not a contract `status` (`draft/approved/revoked`) | CS 3.1 |
| `gate(contract, action)` (L322) | `check(action)` with optional `contract_id`, required with several approved contracts | 1A section 1 |
| Audit `actor`, `hash`, `args` (L102) | `agent`, `entry_hash`, inside `action`; add `kind`, `contract_version`, `reason`; `evidence_refs` is one sha256 of the canonical payload | CS 2.6, 1A section 7 |
| Evidence copy (L28) | `fs.copy`, `source_dest_hash` (`conversion` null, both sha256), `no_overwrite_unless_same_hash` on `triage/evidence/` only | 1A sections 3, 5 |
| No inputs pre-flight | `verify_inputs()` before the first action; failure gives `inputs_unverified` deny (add after L96) | 1A section 6 |
| Test 10 (L361): `spend_usd` > 0 invalid | valid only as an approved cap; `spend` 0.05 under cap 0 is `deny` | D5, 1A test 19 |
| Fix id `FIX-####-n` (L167, 305) | `ct-fix-0042-1`; bugs stay `BUG-####` (data) | CS 3.1 |
| Hack Lead may approve (L105) | `approved_by` must be `johnathan` until OQ-C3 | CS 3.1 |
| `diff_size` as a gate (L98) | a step check under `thresholds`, not a gate step | M-49 pattern |

New tests (prefix `TR-`): 21 two approved fix contracts, no `contract_id`: `deny`. 22 a pinned file changes: `verify_inputs` fails, action `deny`. 23 editing `extensions.triage` of an approved contract: `deny` (hash). 24 evidence overwrite with a different hash: `deny`. 25 engine path: `deny`. 26 bug-file state edits never change a contract hash.

## 4. Part B responses

| ID | Response |
|---|---|
| M-01, 02, 03, 05, 08, 09, 11, 13, 14 | **Accept**, fixed above. On M-08, repo-relative globs until OQ-B3. On M-03, `max_files` and `max_lines` are not per-call `max/min` args, so they move to `thresholds`. |
| M-04 | **Accept**; the registry needs `triage.*`, `fs.copy`, `cmd.run`, `git.*`. |
| M-06 | **Accept**: extras `engine_change`, `close_critical`. |
| M-10 | **Accept**. **Caveat**: 120 calls and 2 hours are untested (OQ-C5), and reads count. |
| M-12 | **Push back**: use `output_snippet` and a review contract rather than new kinds; new kinds are fine if Contract Smith prefers. |
| M-15 | **Accept**, with an amendment: `reviewer` and `author` also leave the hashed fields. |
| M-16 | **Accept**, with a change: pin a frozen `bug_snapshot.json` instead of `late_bind` on the mutable bug file, avoiding Q14. |
| M-17, 18, 19, 20, 21, 22 | **Accept** (D5 for M-18; deny-until-pause for M-21; `asset-step` defaults do not apply to coding for M-22). |
| M-23 | **Accept**: one gate and log; drop `triage/audit/`. **Condition**: `kind` stays open (`state_transition`, `command`). |
| M-24 | **Accept** ids and store; see Q3. |
| M-41 | **Accept** the `TR-` prefix. **Correct**: Part 4 has 20 tests, not 19. |
| M-54, 57 | **Accept**. Triage goes after the gate, in parallel with the pipeline slice. |
| M-58 | **Accept**. **Flag**: the draft's M-58 row, OQ-C14 and C.2 item 6 still say "deny" and are stale. |

## 5. Open questions

**Contract Smith / Hack Lead**
1. Baseline `forbidden_actions` lists `git.push`, and forbidden is checked first. Does the baseline drop it, with `git.push` of class `push` and `force: false` as an allowed action?
2. Is `deploy.*` baseline-forbidden, or a `live` class action denied by absence?
3. Does `ct-<kind>-<n>` allow `ct-fix-0042-1`?
4. Glob dialect (`**`), and repo-relative or absolute paths?
5. Is audit `kind` open, so state transitions and commands share the log?
6. Are repo source writes `write` or `project_write`?
7. Every contract needs Johnathan's approval, so per-bug intake contracts are unworkable. Should intake be one standing contract per build window? CS 3.5 also calls intake "read-only", but it writes `triage/bugs/`.
8. Is a 2-hour fix window workable, since approvals expire at `not_after`?

**Johnathan**
9. Who gives the one-time `close_critical` approval for S0/S1: you only, or Hack Lead too (OQ-C3)?
10. Is a nonzero spend cap ever allowed for triage (OQ-D9)? I assume $0.
11. Confirm the split: fixed fields in the contract, mutable in the bug file (OQ-C7).
12. Is push approval a one-time yes through Ultralord, with you pushing outside the harness as the default?

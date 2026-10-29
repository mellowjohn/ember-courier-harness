> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Pipeline Addendum: Iteration, Git, Orchestration, Transparency

Owner: Pipeline Smith. Date: 2026-10-23. Documentation only; nothing built, run or pushed. The held spec and all fix files are unchanged. Read with `CONTRACT_ADDENDUM_v0.4.md` (CA4), `CONTRACT_FIXES_v0.3.md` (CF), `TRIAGE_ADDENDUM_ITERATION.md` (TA) and `ARCHITECTURE_DRAFT_v2.md` (Draft v2).

**Labels.** **[S]** sourced (Johnathan's requirements via Ultralord, Hack Lead, CA4, CF, TA). **[A]** assumed by me, change freely. **[OPEN-J]** needs Johnathan. **[UNVERIFIED]** depends on the Oct 26 Official Rules check. LFS, OPA and Muse hooks are **options**, not decisions. No claim is made about any Meta model; adapters stay generic with a `manual` fallback.

## 1. Purpose and fixed rules

Johnathan's new requirements, for the asset pipeline only [S]: iteration-first (amendable contracts, cheap re-runs, feedback flows back), git (contracts as files, branch per round, reviewable diffs, LFS), workspace attach (read-only scan, dry-run scaffold, never overwrite), orchestrator/worker/verifier roles, transparency, quality over breadth.

Fixed [S]: gate order unchanged; spend $0 gives `deny`; `publish.*`, `submit.*`, `network.*`, `deploy.*`, `fs.delete` are baseline-forbidden (`deny`); `git.push` is `needs_approval` only where a contract lists it, otherwise `deny`; **pipeline contracts never list a push action**; status set `draft`, `approved`, `revoked`, `superseded`; engine paths stay blocked while the pause stands. Pipeline keys live in `extensions.pipeline` (including `thresholds`); the gate ignores them, the content hash covers them.

## 2. Cheap re-runs

### 2.1 Step cache key [A]

Each step result is stored under a key the harness computes, never an agent:

`step_key = sha256(canonical_json({ step, input_sha256s (sorted), params, adapter_id, contract_id, contract_version }))`

`params` is the step's slice of `extensions.pipeline`; `adapter_id` is the provider or `manual`. Rule: **same key and a `complete` result means skip.** Nothing is regenerated (generative steps are not reproducible). Forcing a re-run needs a new `run_id` and a reason in the manifest.

A version bump would change every key, so the harness first applies CA4 2.5 `affected_actions`: an unaffected action is `carried_forward` (the harness re-runs `verify_evidence` on the stored payload, recomputes hashes, runs no tool) and its key is re-stamped to the new version. Only affected actions get a fresh key and re-run.

### 2.2 Invalidation order

Dependency order: **ingest, concept, cut, bake, import, validate.** A changed input hash, param or adapter on step *k* invalidates *k* and everything after it.

| Change | Re-runs |
|---|---|
| Source image hash in generation log (new concept image) | ingest onward |
| `asset_spec.json` (name, size budget, source image) | cut onward |
| Cut param, adapter, or a threshold the cut step checks | cut onward |
| Bake params (Editor) or validate checks | that step onward |

`validate` is read-only and cheap: it re-runs whenever any upstream step changed. A failed check names the step it blames; that step and its successors are invalidated, not the whole run.

### 2.3 Run manifest and idempotent outputs

Default run root `/workspace/pipeline/runs/<run_id>/` (approved default, Johnathan has the final say; the held spec's `<run_root>` placeholder applies) **[OPEN-J]**. Layout [A]:

```
runs/<run_id>/
  steps/<step>.attempt-<n>.json   # one StepResult per attempt, written once by the step
  evidence/<step>.evidence.json
  generation_log.json
  manifest.json                   # derived by the harness at run close, never agent-written
```
`manifest.json` lists, per step: `step_key`, `attempt`, `status`, `status_basis` (audit seq), `outputs[{path, sha256, bytes}]`, `carried_from` (earlier `run_id` or null), `contract_id`, `contract_version`, `label`. It is plain git.

**Re-runs use a new `run_id`** (Draft v2, Part 6). Skipped steps point to the earlier run's outputs by path and sha256 (`carried_from`), with no copy, so nothing is duplicated. A later step's `allowed_paths.read` lists that earlier run folder. A retry inside the same run writes `attempt-<n+1>`. Writes use `no_overwrite_unless_same_hash`: the same bytes at the same path are a no-op (idempotent), different bytes at that path are `deny`.

### 2.4 Spend and counters

Spend stays $0. A skipped step makes zero calls. A re-run never raises spend: any spending call is `deny` at cap 0, and a higher cap is a widening only Johnathan approves. `max_calls` counters reset per contract version; **spend is cumulative across the whole lineage** of an id, so an amendment cannot reset a budget (CA4 D3). A re-run after the window expires needs a renewal version with its own window (default 4 hours, hard cap 24 hours, CF).

## 3. Failures become amendments

### 3.1 Which route

| Situation | Route |
|---|---|
| Transient: hash mismatch on copy, tool error, Editor timeout; same inputs, params and scope | **Re-run**, no contract change. Next attempt in the same version, consuming its `max_calls` |
| Johnathan rejects a direction | Re-run step A under the same contract if `max_images` allows |
| Needs a changed param, threshold, input pin, write path, window or action | **Amendment** `v<N+1>` |
| Cut fails K2 (alpha coverage) | New cut param (for example a different method) is an amendment. **Loosening the threshold to make it pass is a widening, flagged "WIDER THAN USUAL", never automatic** |
| Bake or import fails Editor-side | Re-run if transient; amendment if format or path changes; an engine path needs the pause lifted (`engine_change`) |
| Different asset or slug, different agent, or revived scope from a `revoked` or `superseded` version | **Fresh contract** with a new id and `extensions.lineage.derived_from` |
| Validation fails | Route by the blamed step using the rows above, then invalidate per 2.2 |

### 3.2 Amendment mechanics (CA4 2.4, 3.1) [S]

A failure or rejection is a finding with an id (`source.kind` `pipeline`, or `review` for a rejected direction). The orchestrator writes only a **proposal** file; the harness compiler makes the draft:

1. New draft `contracts/<id>/v<N+1>.json`. The approved `v<N>` is never edited (CI lock enforces it).
2. `intent_text` carries forward byte-for-byte. His comments go into `reason`.
3. An `amendment_log` entry `{to_version, round, reason, source_id, from_hash}` is added in `extensions.lineage`, so it is hashed. The compiler computes `changed_fields`, `diff`, `widening`.
4. Review diff: `v<N>` against `v<N+1>`, plus `contracts/<id>/amendments/v<N>-to-v<N+1>.json`.
5. Johnathan approves via Ultralord. One audit entry approves `v<N+1>` and sets `v<N>` to `superseded`. After that, `v<N>` actions get `deny` (`contract_superseded`). One-time approvals for `v<N>` are void.
6. The re-run planner (2.1, 2.2) then decides what runs.

### 3.3 Attempt cap

Cap **3 attempts per (step, slug)**, mirroring triage (Hack Lead D18). The count is derived from `failed` step results across the lineage, not stored in a contract, so an amendment does not reset it. After attempt 3 the step is `awaiting_decision`: **Johnathan decides through Ultralord**, as a recorded human pick (a `reviewer_note` plus an `approval`, in the style of `direction_selection`), before attempt 4.

## 4. Git, LFS and the workspace scan

### 4.1 Routing [A; LFS is an OPTION]

| Plain git | Git LFS |
|---|---|
| Contracts and amendment records (`contracts/**`, `approvals/`), run manifests, step results, evidence json, generation logs, `asset_spec.json`, `notes.md`, `engine_notes.md`, `assets/manifest.json` | Concept sheets and images (`png`, `jpg`), cut sprites (`png`), baked atlases (extension per Editor, Q2 in the held spec), audio (`wav`, `ogg`, `mp3`), models (`blend`, `glb`, `fbx`) |

Text and json under 1 MiB stay plain (size guard `extensions.git.thresholds.max_plain_file_bytes`, Draft v2); binaries go to LFS by extension. `assets/manifest.json` holds `path`, `sha256` of the real bytes and `size`, so verification works without LFS installed. A pointer-only checkout verifies as `basis: lfs_pointer` and is labeled `self_reported`.

`.gitattributes` is **design only**: the harness proposes the lines as a file in the scaffold plan and never edits an existing `.gitattributes`. Whether LFS and CI are set up for real or shown as design is **[OPEN-J]**.

### 4.2 Branches and commits

Local commits only. One branch per worker: `round/<N>/<contract_id>`, enforced by `equals` on `git.add`, `git.commit` and `git.branch` (CA4 D9). A commit anywhere else is `deny`. Trailers: `Round`, `Contract-Hash`, `Subsystem`. Amendments live on `contract/<id>/v<N+1>`, written by the harness only. Merges, PRs, pushes are Johnathan's. **No pipeline contract lists `git.push`**, so a push attempt is `deny` at gate step 5 (unlisted). A PR or network call is `deny` (baseline).

### 4.3 Read-only scan and dry-run plan

Attach reuses CA4 3.4: `ct-workspace-scan-0001`, then `ct-workspace-plan-0001`, then (stretch) `ct-workspace-apply-0001`. The pipeline adds only its **scope**: the scan reads the concept root (`/workspace/concepts/`), `/workspace/pipeline/`, the project's import directory (path unknown until Q2), and root-level `.gitattributes`. It reports per `<topic>/<slug>` which of hero, impact, palette, `notes.md`, `refined/` exist, plus existing runs, oversize files, existing LFS patterns and secret-like file names (never contents). The plan marks each entry `create`, `skip_exists`, `conflict` or `manual`. A differing existing file is `conflict` and is never written. `.github/**`, `.husky/**`, `.agents/**` are `manual` by default. Creating anything needs the apply contract's `scaffold_write` approval of the exact plan hash.

## 5. Roles under CA4 (sequential for the MVP)

One contract and one agent per role, `spend_usd` 0, role in `extensions.orchestration`. Ids follow `^ct-[a-z]+(-[a-z0-9]+)*-[0-9]+$`, four-digit padding recommended. Agent names are illustrative [A].

| | Orchestrator `ct-pipeline-orch-0001` | Worker 1 `ct-pipeline-prep-0001` | Worker 2 `ct-pipeline-editor-0001` | Verifier `ct-pipeline-verify-0001` |
|---|---|---|---|---|
| Agent | `pipeline-orch-1` | `pipeline-worker-1` | `editor-1` (Editor) | `pipeline-verifier-1` |
| Does | Plans the re-run, writes proposals and the round record | Ingest (both instances), concept lock, cut | Editor-side bake and import | Validate (B6), independent check |
| Writes | `pipeline/amendments/*.json`, round record | `runs/<run_id>/**`, its branch only | project path, **blocked** | `runs/<run_id>/validate/**` only |
| Never | any asset write, commit, push | concept folders (except ingest), `contracts/**`, push | `contracts/**`, push | any asset write, commit, push |
| `max_calls` | 12 | 12 | 12 | 12 |

Rules (CA4 2.6, D5) [S]: the verifier's agent differs from both workers' and from whoever proposed the amendment. One worker per branch, and at most **2 workers per round** for the MVP (Hack Lead). Child limits sit inside `budget_share`; parent cap plus child shares stay within `envelope` (assumed 60 calls [A]: 48 used, 12 spare for a widening amendment). Window default 4 hours, hard cap 24 hours. Revoking the parent revokes the children; narrowing re-checks them (`parent_narrowed`).

**Conflict to settle [OPEN-CS].** The held spec has one contract per step (seven), but the cap is two workers per round. I bundle steps into the two worker contracts as separate `action_id` groups, with evidence per action. CA4's carry-forward works per action, so re-runs still work per step. The alternative is a higher worker cap.

**Ownership.** Concept Artist owns concepts and runs step A under its own contract; Johnathan's pick is the checkpoint before ingest. Editor owns editor-side bake and import. I own the pipeline steps and the contracts between them. **Bake and import stay blocked on approval while the engine pause stands**: Worker 2 is drafted, not approved, and its actions return `needs_approval` (classes `engine_change`, `project_write`) once approved.

## 6. Transparency

- **Real statuses.** Every status in a step result or manifest carries `status_basis: <audit seq>`. The viewer shows it only if that entry exists and agrees; otherwise it shows "claimed, unverified". Bake and import show `needs_approval`, never "skipped" or "done".
- **Evidence labels** are the harness-derived set from CA4 2.8 and Draft v2 Part 10: `verified` (harness recomputed from bytes: `file_hash`, `source_dest_hash`, `file_list`, passing `output_snippet`), `self_reported` (`checklist` or `reviewer_note`, recorded not recomputed, plus a pointer-only LFS match), `unverified` (no evidence, or the payload hash no longer matches). Cut and alpha-coverage threshold compliance is attested by a checklist item, so it is `self_reported` unless the harness re-measures. A manual cut and the lore-text and trademark reviews are `self_reported`.
- **AI versus approved** is computed from `approval` audit entries (`actor_type: human`, `approved_by: johnathan`, `relayed_by`), joined to each `(contract_id, version)` and `approval_ref`. No agent writes it. Model id stays null **[UNVERIFIED]**.

## 7. Acceptance tests (`PL-R1` to `PL-R16`)

`PL-` is already used by letter groups (`PL-G`, `PL-A`, `PL-I`, `PL-K`, `PL-CL`, `PL-B4/B5`, `PL-AN`, `PL-SD`), so this addendum uses the group `PL-R`; no clash with `CT-`, `CS-T`, `TR-`, `IT-`, `GT-`, `WS-`, `OR-`, `TP-`.

- **PL-R1 Skip.** Given a `complete` run with unchanged input hashes, params and adapter, when the planner runs, then every step is skipped, zero calls are counted, and the new manifest points to earlier outputs with `carried_from`.
- **PL-R2 Key sensitivity.** Given a changed param, adapter id, or one input byte, then that step's key differs and it re-runs. Given a version bump whose diff touches only the cut action, then ingest and concept are `carried_forward` after `verify_evidence`, and cut re-runs.
- **PL-R3 Cascade.** A new source image hash invalidates ingest through validate; a changed cut param re-runs cut through validate only; a validate-only change re-runs validate only.
- **PL-R4 Idempotent outputs.** The same bytes written again to an output path are a no-op; different bytes there are `deny`; concept files keep their hashes.
- **PL-R5 Spend.** Given a re-run, then spend stays 0 and any spending call is `deny`. Given an amendment, then calls reset, and spend counted under v1 still counts under v2 (cumulative); an amendment raising `spend_usd` is flagged widening.
- **PL-R6 Amendment record.** Given a failed cut, when the proposal is compiled, then `v2.json` is `draft`, `v1.json` is byte-identical, `intent_text` is identical, `amendment_log` holds round, reason and source id and is part of the hash, and a hand-typed `widening` is overwritten.
- **PL-R7 Supersession.** Given `v2` approved, then one audit entry carries `supersedes: 1`; a `v1`-pinned action is `deny` (`contract_superseded`); a draft `v2` authorizes nothing.
- **PL-R8 Routing.** Fixtures (transient copy error, threshold change, new cut method, different slug, revived revoked scope) give: re-run, widening amendment, amendment, fresh contract, fresh contract with `derived_from`.
- **PL-R9 Attempt cap.** Given three failed attempts for one (step, slug), then a fourth is refused and the step is `awaiting_decision`; an amendment does not reset the count; only a recorded human pick by Johnathan reopens it.
- **PL-R10 LFS routing.** Given the file set, then `png`, `jpg`, `wav`, `ogg`, `mp3`, `blend` route to LFS and json, `notes.md`, manifests route to plain git; a plain file over 1 MiB fails the size guard; a pointer-only match shows `basis: lfs_pointer` and `self_reported`.
- **PL-R11 Scan and scaffold.** Given a workspace with a differing existing file, then the scan writes nothing, `.env` reads are `deny`, the plan marks `conflict` and omits it, `.github/**` is `manual`, and apply needs `scaffold_write` approval for the exact plan hash; existing files stay byte-identical; a rerun changes nothing.
- **PL-R12 No push.** Given any approved pipeline contract, then none lists `git.push`; a push attempt is `deny` (not `needs_approval`); publish, submit and PR creation are `deny`.
- **PL-R13 Branches.** Worker 1 commits on `round/1/ct-pipeline-prep-0001` are allowed; on `main` or another worker's branch `deny`; two workers sharing a branch fail validation.
- **PL-R14 Roles and budgets.** A verifier whose agent equals a worker's or the proposer's fails validation; orchestrator and verifier asset writes are `deny`; a third worker, a child above `budget_share`, or a window over 24 hours is refused.
- **PL-R15 Blocked on approval.** Under the engine pause, Worker 2 stays draft (no action allowed); once approved, bake and import return `needs_approval`; the project directory hash is unchanged; the manifest shows `needs_approval`.
- **PL-R16 Transparency.** A step claiming `complete` with no audit entry shows "claimed, unverified". A recomputed `file_hash` is `verified`; a checklist `self_reported`; one changed payload byte `unverified`. AI-versus-approved equals the approval join; an agent cannot write it.

## 8. MVP build order: Molten Slag slice

After the contract core (schema, audit, gate, evidence, compiler, approvals) and CA4 steps 1 to 9 exist:

1. Step result files, derived `manifest.json`, `step_key` (PL-R1, R2, R4).
2. Invalidation table and planner (PL-R3).
3. Run Molten Slag: ingest (2 images, palette rendered locally), concept lock, cut with `manual` or classic method, validate. Bake and import are recorded as blocked (PL-R15).
4. Force the cut to fail K2 once. Compile and approve the amendment (new cut param); re-run with ingest and concept carried forward (PL-R5 to R9).
5. Role validators, sequential, and the local worker-branch commit (PL-R12 to R14).
6. Labels and `status_basis` in the manifest report (PL-R16).
7. Scan and plan, read-only, for the pipeline folders (PL-R11, up to the plan).

**Must work by Nov 4:** 1 to 6, plus scan and plan from 7. **Stretch:** full planner carry-forward on version bumps, scaffold apply, the LFS routing check (PL-R10). **Not in the MVP:** parallel workers, real PRs or rulesets, real LFS or CI, OPA, Muse hooks, animation and sound re-runs, any spend.

## 9. Open questions for Johnathan

1. **Run root:** keep `/workspace/pipeline/runs/<run_id>/` or `/workspace/runs/<run_id>/`? (Default: the former.)
2. **LFS and CI:** design only plus manifest, or set up for real? (Default: design only.)
3. **Thresholds:** image size limits and alpha-coverage bounds in `extensions.pipeline.thresholds`; my defaults are long side at least 1024, short side at least 720, palette at least 600x150. Alpha bounds are still unset.
4. After a rejected direction, may step A re-run within `max_images`, or do you want to pick again first?
5. May the scaffold ever write under `.github/`, `.husky/`, `.agents/`? (Default: manual.)

For Contract Smith: the two-worker cap against seven step contracts (section 5), and registering `pipeline.write_step_result` (path_within `runs/<run_id>/steps/*.json`, `no_overwrite_unless_same_hash`) and `pipeline.propose_amendment` (path_within `pipeline/amendments/*.json`) as class `write`. For Hack Lead: confirm the `PL-R` group.

## 10. Changes this implies for the held spec (list only, no edits)

- 2.3 layout: add `steps/`, `manifest.json`, `amendments/`; state that runs are never reused by overwrite.
- 2.4 step interface: add `step_key`, `attempt`, `carried_from` and a planner entry point.
- 3.4 step sketches: add a per-step `params` slice and invalidation line; map steps to action groups under two worker contracts and Validate to the verifier.
- Common contract text: add the status `superseded`, the `equals` branch constraint, and "no push action listed".
- 4.1: add tests PL-R1 to PL-R16 by reference.
- 4.7 check 2 and 8: extend the hash chain check across `carried_from` runs.
- 5.1 build sequence: insert the manifest and planner before steps 3 to 6, and the amendment loop after step 5.
- 6: add the section 9 questions; link Q8 (repo location) to LFS and CI. Evidence shows `verified`, `self_reported`, `unverified`.

---

## Appendix: Contract Smith rulings on OPEN-CS (2026-10-23)

Defaults; Hack Lead and Johnathan can override.

- The `PL-R1` to `PL-R16` test prefix is accepted.
- Bundling the seven steps into a prep worker and an editor worker is accepted, with three conditions:
  1. Each worker gets one child contract, and its `allowed_actions` and `allowed_paths` must be a subset of the orchestrator's parent contract.
  2. Each step keeps its own evidence record with the step id in the evidence label. A failure amends the bundled worker contract, and the `amendment_log` entry must name the failing step. The 3-attempt cap counts per step across the lineage, not per bundle.
  3. Validate stays a separate verifier contract with read-only access to the workers' outputs.
- The worker cap stays at 2 for the MVP. Contract Smith does not recommend raising it, and the decision is Hack Lead's.
- `pipeline.write_step_result` and `pipeline.propose_amendment` are registered as class `write`. The first writes only via `path_within` the run directory's `steps/**`, with every call audit-logged. The second produces drafts only and never approves. A widening still needs Johnathan's separate acknowledgement.
- The gate order, the $0 spend limit and the no-push rule are unchanged.

## Appendix: Johnathan's decisions (via Ultralord, 2026-10-23 7:00 PM ET) and pipeline effects

- **Approval mode** (approve each action, or approve all): pipeline contracts inherit this setting. Spend at $0, publish, submit and `deploy.*` still return `deny`, and bake and import stay blocked while the engine pause stands.
- **Rollback on git versioning:** a pipeline rollback is a new amendment whose content equals an earlier version.
- **Contracts are harness-stored system files.**
- **Scaffolding:** the harness may create its own `.github`, `.husky` and `.agents` files, still as a dry-run diff that never overwrites existing files. This supersedes my open question on scaffolding.
- **Commits and PRs:** these stay in the coding template only. Pipeline contracts list no push action and no `git.open_pr`.
- **OPA:** no-go. Every OPA reference in this addendum is void.
- **Amendments path:** `/workspace/pipeline/amendments/*.json` at the pipeline root, shared across runs. Not under `runs/<run_id>/`, because a re-run gets a new `run_id`. Confirmed by Ultralord, 2026-10-23.

## Appendix: Johnathan's batch closed (via Hack Lead, 2026-10-23 7:03 PM ET) and pipeline effects

- **Scope contract first.** From Johnathan's intent, the harness scopes a small sample game, and he approves that scope as the first contract. Every pipeline contract (orchestrator, prep worker, editor worker, verifier) must be a subset of that scope contract, and the validator checks this at approval with `scope_subset`. The engine pause stays, so bake and import remain blocked.
- **Image quality is judged against `art_direction`.** The contract carries an `art_direction` block (style, palette, mood, references, do, dont), which Contract Smith's schema note defines. The verifier (validate) scores each asset against that block and records a score, the evidence and a confidence for each asset in `steps/validate.attempt-<n>.json`. Its label is `self_reported` until Johnathan approves. The verifier recommends; Johnathan approves each asset.
- **Size and alpha are basic technical gates only.** The verifier checks that the image decodes and that the alpha channel is present where the step needs it. Size uses the Hack Lead / Contract Smith ruling below (precondition then declared dimensions). The numeric thresholds are dropped: `extensions.pipeline.thresholds` and the open question about image thresholds are void, and so are the earlier size defaults from my fix files.
- **Re-runs.** A failed art-direction score is a judgment failure. It becomes an amendment that names the step in `failing_step` (for example, a sharper `do` or `dont`, or a new reference image), not a re-run with no contract change. The cap stays at 3 attempts per step.
- **New tests.** These continue the PL-R series:
  - **PL-R17:** a pipeline contract that is wider than the approved scope contract is rejected at approval.
  - **PL-R18:** validate writes one score with evidence and a confidence per asset, and the asset stays unapproved until Johnathan's approval entry exists.
  - **PL-R19:** an image that is missing alpha or does not decode fails the technical gate before any art-direction scoring.
- **Alignment with Contract Smith's v0.4 Appendix A:** the verifier's per-asset score is the `art_score` evidence record. It scores each criterion, gives a confidence and includes the hash of the `art_direction` it was scored against, and only the verifier writes it. The viewer label is "AI-scored, not approved", so asset acceptance stays with Johnathan even under approve-all. Pipeline contracts carry the `scope_id` and inherit `art_direction` from the scope contract.
- **Size gate (Hack Lead's pick, 2026-10-23):** the technical size gate is "dimensions match the declared target in the asset spec". This replaces "size not zero". It is pass or fail against the declared value, not a quality threshold.
- **Size gate precondition (Contract Smith, 2026-10-23):** the file must open and its size must not be zero, and this check always runs first. The dimension match then runs if the contract declares target dimensions for that asset. If no target is declared, only the precondition applies.

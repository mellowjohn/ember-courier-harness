> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Tool registry note: pipeline tools (Contract Smith, 2026-10-23)
Documentation only. Held specs untouched. Registers two tools requested by Hack Lead / Pipeline Smith.

| tool | class | args_constraints | notes |
|---|---|---|---|
| `pipeline.write_step_result` | write | `dest`: `path_within` `<run_dir>/steps/**`; `step_id`: `one_of` the step ids in the worker's child contract | One call per step result. Audit-logged as a decision. Output carries path + sha256 (evidence kind `source_dest_hash` or `file_hash`). |
| `pipeline.propose_amendment` | write | `dest`: `path_within` `<pipeline_root>/amendments/*.json` (shared across runs; default `/workspace/pipeline/amendments/`) | Drafts only (same contract as `triage.propose_amendment`). Never approves, never sets `status: approved`. Draft v(N+1) must name the failing `step_id` in its `amendment_log` entry. A widening needs Johnathan's separate explicit acknowledgement. |

Rules unchanged: gate order (9 steps, first match wins), spend $0, no push action listed, deny-by-default.
Bundling: prep worker (ingest, concept lock, cut) and editor worker (bake, import) each hold one child contract that is a subset of the orchestrator parent. Validate is a separate read-only verifier contract. Attempt cap 3 is counted per step_id across the lineage.
Tests: covered by Pipeline Smith's PL-R1 to PL-R16; no new CT- tests needed.

RESOLVED 2026-10-23: `propose_amendment` dest is `<pipeline_root>/amendments/*.json` (shared across runs; default `/workspace/pipeline/amendments/`) (matches Pipeline Smith addendum; the narrower path wins). Verifier writes `<run_dir>/validate/**` and its own step result `steps/validate.attempt-<n>.json`.
UPDATE 2026-10-23 7:00 PM ET: amendments live at the pipeline root, not inside a run dir, because a re-run gets a new run_id and would orphan them (Pipeline Smith). Confirmed by Hack Lead, 7:01 PM ET. Envelope: 72 calls (prep 36, editor 24, verifier 12).

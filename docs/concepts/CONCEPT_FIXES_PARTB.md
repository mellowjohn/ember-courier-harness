> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Concept Artist review of Part B (M-28 to M-39, M-40 to M-44, M-51 to M-53)

Documentation only. Written 2026-10-23, America/New_York. No existing spec was edited.
Compared against: `/workspace/concepts/CONCEPT_STEP_SPEC.md` ("my spec", sections cited as §), `PIPELINE_SUBSYSTEM.md`, `PROPOSED_FIXES.md` (3A), `CONTRACT_SYSTEM.md`, `SCHEMA_DECISIONS_v0.2.md` (1A).
Room decisions applied: D1 ingest is its own contract with `source_sha256` + `dest_sha256`; D2 slug rule is the pipeline convention; D3 sheet is `<topic>_comparison_sheet.png`; D4 size thresholds live in `extensions.pipeline.thresholds`.

## Agree (accurate about my spec)

M-28, M-29, M-30, M-32, M-33, M-35, M-36, M-41, M-42, M-43, M-44, M-52, M-53

Minor notes on agreed entries (no change to status needed):
- M-29: the open "working-tree name `fireball/molten-slag` must be confirmed" is confirmed. `/workspace/concepts/fireball/molten-slag/` exists (my spec §2.3 worked example). In my spec `<direction-slug>` (folder) and `<slug>` (file prefix) are the same string.
- M-30: the existing `fireball_comparison_sheet.png` already matches D3, so no rename. My Q6 (sheet name half) is now answered. The `.manifest.json` name stays a PROPOSAL (§2.3).
- M-41/M-42: my T3, T4 and T13 change under D4 (they read thresholds instead of fixed numbers), and T12 changes under D1 (`sha256` becomes `dest_sha256`, ingest evidence moves to the ingest contract).
- M-43, M-52, M-53 concern Parts 1 and 3 and 3A. Checked: 3A's references to "CA Q2 / Q4 / Q6", "CA 2.3 / 2.5" and "T3 / T4" match my numbering.

## Disputed

### M-31 Ingest destination and `refined/`
- Draft says: Parts 2, 3 and 1A agree that `refined/` is reserved and "ingest never writes there".
- My spec says: refined frames are generated and then ingested into `<slug>/refined/` "the same way as step 3" (§2.4 step 9; §4 data flow, `[refine]` arrow). So Part 2 does write into `refined/` through ingest. Existing files: `molten-slag/refined/molten-slag_flight_closeup.png` and two more. Refined frame names are `<slug>_<frame>.png` (§2.3).
- Consequence: 1A section 8 and test 24 deny any write under `<slug>/refined/`. Under that rule the refine step cannot ingest its frames.
- Proposed wording: "Part 1 3.3 wrote the initial hero, impact and palette ingest into `<slug>/refined/`; this is wrong. The initial ingest contract writes only `<topic>/<slug>/<slug>_{hero,impact,palette}.png`. Refined frames are ingested by a second ingest contract for the picked direction (same tool and hash evidence) whose write path is `<topic>/<slug>/refined/<slug>_*.png`. `refined/engine_notes.md` is written by the concept step, not by ingest. Test 24 is split: initial ingest under `refined/` is denied; the refine-ingest contract is allowed there only."
- Source of the pending fix: Part 2 must say the refine ingest is a separate contract (D1 applied to §2.4 step 9).

### M-34 Repo and tool roots
- Draft says: lists Parts 1, 3, 4 only.
- My spec says: Part 2 also hardcodes `/workspace/concepts/` (§2.3, §3.4), `/workspace/pipeline/runs/<run_id>/` (§2.3, §3.3, T9, T12), `config/adapters.json` (§2.2), the trailer still `/workspace/wrathful-conquest-trailer/scratch/pass27/stills/f990.png` and `/workspace/sc22/vc02-concept.png` as references (§2.1, §3.4), and the generation store path (§2.5).
- Proposed wording: add "Part 2: `/workspace/concepts/` (outputs), `/workspace/pipeline/runs/` and `config/adapters.json` (harness files), `/workspace/sc22/` and the trailer scratch stills (reference inputs), generation store (harness-specific). A Meta-built harness may use other roots, so each is a parameter, not a fixed value."

### M-37 Generation log
- Draft says: Part 2 "requires mapping only via a generation log but leaves its format as a question (Q4)".
- My spec says: §2.4 step 2 does give per-image fields: direction, role, prompt, source file path. It gives no file name, location or hash. Q4 asks only whether the harness must require a log, not what is in it. §2.4 step 3 says the source-to-destination mapping comes from the log, and §2.5 repeats it.
- Proposed wording: "Part 2 (§2.4 steps 2 to 3, §2.5) defines per-image log fields `{direction, role, prompt, source file path}` but not the file name, location or `source_sha256`; Q4 asks whether the log is mandatory. 1A and 3A supply the rest: `runs/<run_id>/generation_log.json` with `source_sha256`, as an input of the ingest contract. Part 2 accepts this format. Part 2 has no test equivalent to 3A I6 (one-to-one mapping) or I7 (`source_sha256` equals file hash and file name); add them to Part 2 §2.6 or leave them in the ingest contract's tests."
- Also: Q4 is now answered in substance by 1A section 8 ("never by eye"). The 1A path `/workspace/runs/...` still conflicts with Part 2's `/workspace/pipeline/runs/...` (M-33, OPEN).

### M-38 Step A write paths
- Draft says: Part 2 writes to the topic folder and the run dir. Proposed fix is to adopt 3A section 4.
- My spec says: correct (§3.3 `allowed_paths`, §3.4 example, T9). Missing: after D1, Step A is no longer one linear contract, because ingest sits in the middle of §2.4. Order: generate (step 2), then ingest (step 3, now its own contract), then QA, palette, sheet, checks and hand-off (steps 4 to 8). Generation also writes outside both allowed write paths (the generation store), which the harness writes, not the contract.
- Proposed wording: "Adopt 3A section 4 (run path listed in `allowed_paths.write`). With D1, Part 2's Step A runs as two contract phases around the ingest contract: A1 generate (reads references; writes `generation_log.json` and evidence under `runs/<run_id>/`; image files land in the generation store by the adapter) then ingest (own contract) then A2 finish (reads `/workspace/concepts/<topic>/`; writes `notes.md`, palette PNGs, sheet, manifest and evidence). Which of A1 and A2 is one contract with two actions or two contracts is OPEN (Part 3 should name them)."

### M-39 Step A actions
- Draft says: Part 2 Step A includes ingest, palette render, sheet build, `vision_review`; Part 3 lacks them. Pending: Part 3 adds palette and sheet writes. With D1 ingest moves out.
- My spec says: §3.3 lists `file_read`, `image_gen` (or `manual`), `file_copy`, `file_write` (notes, palette, sheet, evidence), `vision_review`. Correct as far as it goes. Missing: after D1 my `file_copy`, `dest_prefix`, the `required_evidence.file_copy` key and the "overwrite_without_hash_match" forbidden string (§3.3, §3.4) all leave Step A. Also, palette and sheet are produced by local compute, but §3.3 calls them `file_write`; they need a registered tool name (M-04 OPEN).
- Proposed wording: "Part 2 Step A actions after D1: `file_read`, `image_gen` via adapter or `manual`, `file_write` (notes, palette PNG, sheet, manifest, evidence), `vision_review`. `file_copy`, `dest_prefix` and `required_evidence.file_copy` are removed and move to the ingest contract (`image.convert_png` per 1A Q16, now agreed). Palette and sheet renders need a compute-class tool name from the shared registry (M-04). `overwrite_without_hash_match` becomes the constraint `no_overwrite_unless_same_hash` on the ingest destination."

### M-40 Step names and numbering
- Draft says: step names are consistent; no fix beyond label care.
- My spec says: names match (A `design-with-concepts`, B1 `ingest`, B2 `concept` lock; header line 4). Two real differences: (a) §2.4 lists "ingest (B1)" as sub-step 3 inside Step A, which D1 contradicts; (b) the pick is recorded in Part 2 evidence as `selection {status, picked_direction, approved_by, approved_at}` (§3.5, §3.6) but in Part 3 as B2's `reviewer_note` (3A section 6). Part 2's refine and engine-notes sub-steps (9, 10) have no Part 3 step name; B2 reads their outputs.
- Proposed wording: "Step names are consistent. Part 2's ten sub-steps are labels inside Step A and must not be read as pipeline steps; sub-step 3 (ingest) is pipeline step B1, a separate contract (D1), and sub-step 9's refine-ingest is a second B1 run. The pick is recorded once: as a `reviewer_note` whose body is Part 2's `selection` object (3A section 6). Sub-steps 9 and 10 (refine, engine notes) belong to Step A and finish before B2 starts."

### M-51 Part 2 "could not find the contract schema"
- Draft says: Part 2 §3.2 and Q5 say the schema was not found; it now exists. Part 2 cites "[PIPELINE draft]". Spec fix: realign to Part 1 + 1A.
- My spec says: correct. §3.2 header ("DRAFT; do not extend") and Q5 say the schema file was not found. "[PIPELINE draft]" tags appear in §3.1 and §3.2. The realign list is wider than the draft says: `version`, `goal`, approval fields; `inputs[].name`; `action_id` + `args_constraints` with `path_within`; forbidden actions as `{tool}` objects; the six mandatory `requires_approval` classes plus `engine_change`/`direction_selection` as legal extras (1A section 4); `time_window` form; evidence keyed by `action_id` with Part 1 kinds (`source_dest_hash`, `file_list`, `checklist`, `reviewer_note`, `output_snippet`); `extensions.pipeline.thresholds` (D4); `contract_id` on actions; evidence payload per 1A section 7.
- Proposed wording: "Part 2 §3.2 and Q5: the schema now exists at `/workspace/contract-system-doc/CONTRACT_SYSTEM.md` (with `SCHEMA_DECISIONS_v0.2.md`). Realign §3.2 to §3.5 to it in full: M-01, M-02, M-03, M-05, M-06, M-08, M-09, M-11, M-12, M-14, M-17. Q5 is closed. Drop the `[PIPELINE draft]` tags."

## Outside my range, noticed while reading
- M-25 attributes "copy's sha256 equals the recorded sha256" to Part 2 step 3 as well as Part 3 I1. Part 2 §2.4 step 3 and §3.5 already record `source_sha256` and a separate dest `sha256` and say nothing about equal hashes. Only the key name `sha256` (to become `dest_sha256`) changes.
- M-26 is marked OPEN, but 1A Q16 says it was resolved by Pipeline Smith on 2026-10-23: `image.convert_png` is the agreed tool name.

## Addendum (2026-10-23, after Hack Lead decisions H1-H5)
- H1: refined frames keep the existing pattern `<slug>_<frame>.png` under `<slug>/refined/` (no `_refined_` prefix, no rename). Second ingest instance writes only `<slug>/refined/<slug>_*.png`.
- H2: run directory is `/workspace/pipeline/runs/<run_id>/` (Johnathan has the final say, M-33). The concept spec's `runs/<run_id>/` should read that absolute path.
- H5: test ids T1..T14 become `CS-T1`..`CS-T14`; T3, T4 and T13 read size limits from `extensions.pipeline.thresholds`.
- Compute tools: palette and sheet renders use `image.render_palette` and `image.render_sheet` (class write, path_within).
- H4: notes.md migration for the four fireball directions is a stage-0 note in the build order. Notes only, after the merge settles the template and thresholds.
- I7 check: 4 sampled store files had file name == sha256 of bytes; not exhaustive.

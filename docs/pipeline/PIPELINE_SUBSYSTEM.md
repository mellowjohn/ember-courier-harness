> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Production-Pipeline Subsystem: Build-Ready Spec

Project: Wrathful Conquest contract-driven game-development harness
Event: Meta Global AI Developer Hackathon, Oct 26 to Nov 4, 2026 (submission due Nov 4, 9:00 PM ET)
Owner: Pipeline Smith. Status: DRAFT spec for Johnathan's review. Documentation only; nothing here is built.

**Labels.** **[SRC]** = given by Johnathan, Hack Lead, Contract Smith or Concept Artist. **[PROPOSAL]** = my suggestion, not fact; change freely. Contract fields are Contract Smith's DRAFT, and Contract Smith owns them. Where a field is missing I say so instead of inventing one.

**Hard rules [SRC].** No copyrighted or trademarked material anywhere. Nothing live, published, spent or pushed without Johnathan's yes (via Ultralord). Engine work needs his yes while the engine pause stands. Do not invent facts about Meta models beyond the event page.

---

## 1. Purpose

Turn an approved design intent into game-ready assets by a chain of small steps. Each step runs under its own contract, produces evidence, and is checked by the deny-by-default gate. Subsystems [SRC]:

1. **Design-with-concepts**: Concept Artist makes visual concepts and Johnathan picks one.
2. **Asset pipeline**: ingest, concept, cut, bake, import, validate.
3. **Animation pipeline**: lower priority.
4. **Sound pipeline**: lower priority.

Priority [SRC, tentative until Hack Lead's plan]: contract gate and compiler first (Contract Smith); then one vertical slice, concept to asset to validated import for a single asset; animation and sound only if time remains.

Ownership [SRC]:

| Area | Owner |
|---|---|
| Contract schema, compiler, gate, audit log | Contract Smith |
| Concepts in `/workspace/concepts/<topic>/` | Concept Artist |
| Editor-side import and bake | Editor (needs Johnathan's yes via Ultralord) |
| Engine changes | Engine (paused; needs Johnathan's yes) |
| Pipeline steps and the contracts between them | Pipeline Smith |

---

## 2. Design

### 2.1 Principles
- **Contract first.** No step runs without an `approved` contract for it [SRC].
- **Each step reads only the previous step's declared outputs.** Every handoff is a file plus a sha256 [PROPOSAL on mechanism; sha256 on inputs is in the draft].
- **Evidence is mechanical where possible.** Hashes, file lists and sizes, and checks done by a script. Human or vision reviewer notes cover only what code cannot check (for example "no lore text").
- **Model calls sit behind an adapter** so a model can be swapped or absent [SRC].
- **Fail closed.** Anything unlisted in `allowed_actions` or `allowed_paths` is denied. Anything live, published, spent or pushed returns "needs approval" [SRC].

### 2.2 Model adapters [SRC constraints, PROPOSAL interface]
- Muse Image and SAM 3.1 are used only if the event page allows them. This is **unverified**; Hack Lead rechecks the official rules on Oct 26. Never hardcode either as required.
- A step that needs a model names an adapter role (`image_gen`, `segmenter`, `audio_gen`). A config file maps each role to a provider or to `manual`.
- Roles: `image_gen` (candidates: Muse Image if allowed, or whatever Concept Artist already uses), `segmenter` (candidate: SAM 3.1 if allowed; the fallback is manual or classic image-processing cut), `audio_gen` (ElevenLabs).
- ElevenLabs is the audio provider [SRC]. Any call that spends money requires Johnathan's yes first. Default spend is $0.

### 2.3 Proposed directory layout [PROPOSAL]
Only `/workspace/concepts/<topic>/` is fixed by Concept Artist [SRC]. Everything else is proposed.

```
/workspace/pipeline/
  PIPELINE_SUBSYSTEM.md          this spec
  steps/                         one module per step
    ingest.py  cut.py  bake.py  import_.py  validate.py
    animate.py  sound.py                    (animate/sound: stretch)
  adapters/                      model adapters behind a common interface
    image_gen.py  segmenter.py  audio_gen.py
  contracts/                     step contracts as JSON (schema owned by Contract Smith)
    templates/<step>.contract.json
    instances/<run_id>/<step>.contract.json
  runs/<run_id>/                 per-run working output (never inside /workspace/concepts)
    ingest/  cut/  bake/  import/  validate/
    evidence/<step>.evidence.json
  config/adapters.json           role -> provider | "manual"
  tests/                         acceptance tests (Section 4.x)
/workspace/concepts/<topic>/     owned by Concept Artist (fixed layout, see 3.3)
```

### 2.4 Step interface [PROPOSAL]
Every step module exposes the same entry point so a gate can wrap it:

| Item | Description |
|---|---|
| `run(contract, ctx) -> StepResult` | Executes the step. First asks the gate to authorize each action; never touches a path outside `allowed_paths`. |
| `StepResult` | `{ step_id, status: ok|failed|needs_approval, outputs: [{path, sha256}], evidence_path }` |
| `check(contract, result) -> list[Failure]` | Re-verifies the acceptance tests for this step from files alone. Used by validate and by tests. |
| `ctx` | Gate handle, adapter registry, run directory, clock. No network handle unless the contract allows it. |

The gate call shape and the compile call shape belong to Contract Smith. Pipeline code must call them through a thin wrapper (`gate.authorize(contract, action) -> allow | deny | needs_approval`, a **placeholder name**, [PROPOSAL]) so the real call can be dropped in.

---

## 3. Contracts

### 3.1 Contract shape (Contract Smith's DRAFT; do not extend here)
A step contract has these fields [SRC]:

| Field | Meaning |
|---|---|
| `id` | Unique step contract id |
| `agent` | Which agent may execute it |
| `intent_text` | Plain-language intent the user approved |
| `inputs` | List of `{path or value, optional sha256}` |
| `allowed_actions` | List of `{tool, argument constraints}` |
| `allowed_paths` | Read paths and write paths |
| `forbidden_actions` | Explicit denies |
| `limits` | Spend (default $0), max calls, time window |
| `required_evidence` | Per action: file hash, URL, output snippet or reviewer note |
| `requires_approval` | Anything live, published, spent or pushed |
| `status` | `draft`, `approved` or `revoked` |

Gate behavior [SRC]: deny by default; live, published, spent or pushed actions always return "needs approval".

**Gaps to resolve with Contract Smith (not invented here):** exact JSON key names and nesting, how argument constraints are written, how a contract references an upstream step's output, and the evidence file format. The examples below use the draft's field names with illustrative values.

### 3.2 Illustrative contract and evidence (ingest) [PROPOSAL values]
```json
{
  "id": "ingest-fireball-molten-slag-001",
  "agent": "pipeline-smith",
  "intent_text": "Copy the approved Molten Slag concept images into /workspace/concepts/fireball/ and record hashes.",
  "inputs": [
    {"path": "<generation-store>/molten_slag_hero.png"},
    {"path": "<generation-store>/molten_slag_impact.png"},
    {"path": "<generation-store>/molten_slag_palette.png"}
  ],
  "allowed_actions": [{"tool": "file_copy", "args": {"dest_prefix": "/workspace/concepts/fireball/"}}],
  "allowed_paths": {"read": ["<generation-store>/"], "write": ["/workspace/concepts/fireball/"]},
  "forbidden_actions": ["network", "delete", "overwrite_without_hash_match"],
  "limits": {"spend_usd": 0, "max_calls": 10, "time_window": "1h"},
  "required_evidence": {"file_copy": ["file hash"]},
  "requires_approval": false,
  "status": "approved"
}
```
Evidence record the step writes [PROPOSAL format]:
```json
{
  "step_id": "ingest-fireball-molten-slag-001",
  "files": [
    {"source_path": "<generation-store>/molten_slag_hero.png",
     "dest_path": "/workspace/concepts/fireball/molten-slag/molten-slag_hero.png",
     "sha256": "<64 hex chars>", "bytes": 123456}
  ]
}
```
`<generation-store>` is the real store folder path that Concept Artist knows; it is not visible from the shell today [SRC]. Open question Q1.

### 3.3 Concept Artist's conventions (fixed) [SRC]
```
/workspace/concepts/<topic>/
  <direction>/
    <direction>_hero.png
    <direction>_impact.png
    <direction>_palette.png
    notes.md                         shape, color, motion beats, readability
    refined/
      (refined frames)
      engine_notes.md                for Engine/Studio
  comparison sheet                   at the topic root (file name TBD with Concept Artist)
```
- Evidence from Concept Artist: file list with sizes; which references were used (trailer stills, VC-02); confirmation that images were viewed and contain no lore text and no copyrighted or trademarked material.
- Constraints: must match the approved VC-02 look and trailer look; must be buildable in the v1 pipeline, **no heat distortion**; no lore text.
- Worked example and test case: `fireball/molten-slag` (`/workspace/concepts/fireball/molten-slag/refined/` with `engine_notes.md`).
- Note: the worked example folder name in the working tree is `fireball/molten-slag`. This spec treats `fireball` as `<topic>` and `molten-slag` as `<direction>`; confirm against the real tree before the build.

### 3.4 Per-step contract sketches
Common to all steps [SRC]: `status` must be `approved`; `limits.spend_usd` is 0 unless stated; live, published, spent or pushed actions set `requires_approval` true. Paths below are proposals except `/workspace/concepts/`.

#### Step A: design-with-concepts (owner: Concept Artist; Pipeline Smith defines the contract)
| Field | Content |
|---|---|
| inputs | Brief (topic, direction names), references (trailer stills, VC-02) with sha256, pipeline limits (v1 buildable, no heat distortion) |
| allowed_actions | `image_gen` via adapter; `file_write` into the topic folder; vision review of generated images |
| allowed_paths | read: references; write: `/workspace/concepts/<topic>/` only |
| forbidden_actions | publish or post; writing outside the topic folder; spend without approval |
| limits | spend $0 unless Johnathan approves an image-generation budget; max images per direction (set per run) |
| required_evidence | file list and sizes; references used; reviewer note: images viewed, no lore text, no copyrighted or trademarked material |
| outputs | Section 3.3 layout; Johnathan picks the direction (approval event recorded) |

#### Step B1: ingest
| Field | Content |
|---|---|
| inputs | Images in the generation store (not shell-visible; Concept Artist lists them) |
| allowed_actions | `file_copy` only |
| allowed_paths | read: store folder; write: `/workspace/concepts/<topic>/<direction>/` |
| forbidden_actions | network; delete; overwrite an existing file with a different hash |
| limits | spend $0; max calls = number of files |
| required_evidence | per file: `source_path`, `dest_path`, `sha256` [SRC] |
| outputs | The images at `dest_path`; `evidence/ingest.evidence.json`. Later steps read only from `/workspace/concepts/` |

#### Step B2: concept (selection and spec lock) [PROPOSAL scope]
| Field | Content |
|---|---|
| inputs | Chosen direction's hero, impact, palette, `notes.md`, `refined/engine_notes.md` with sha256 |
| allowed_actions | read files; write an `asset_spec.json` |
| allowed_paths | read: concept folder; write: `runs/<run_id>/` |
| required_evidence | hash of each input; reviewer note recording Johnathan's pick |
| outputs | `asset_spec.json` listing asset name, size budget and the source image to cut |

#### Step B3: cut
| Field | Content |
|---|---|
| inputs | Source image from the spec, with sha256 |
| allowed_actions | `segmenter` via adapter (SAM 3.1 only if the event page allows; otherwise manual or classic cut); image file write |
| allowed_paths | read: concept folder; write: `runs/<run_id>/cut/` |
| forbidden_actions | overwriting concept files; spend |
| required_evidence | output hashes; adapter name used; output snippet (dimensions, alpha coverage) |
| outputs | Cut image(s) with alpha, named per asset spec |

#### Step B4: bake
| Field | Content |
|---|---|
| inputs | Cut outputs with sha256 |
| allowed_actions | **Editor-side bake; interface not yet defined** (Q2). Needs Editor and Johnathan's yes via Ultralord |
| allowed_paths | write: `runs/<run_id>/bake/` |
| required_evidence | output hashes; bake log snippet |
| outputs | Engine-ready baked asset (format per Editor) |

#### Step B5: import
| Field | Content |
|---|---|
| inputs | Baked asset with sha256 |
| allowed_actions | **Editor-side import into the project; touches engine content, so blocked while the engine pause stands** unless Johnathan approves |
| requires_approval | true for any write into the real game project [PROPOSAL; the engine pause is SRC] |
| required_evidence | import log snippet; resulting asset path and hash |
| outputs | Asset registered in the project (or a dry-run report if not approved) |

#### Step B6: validate
| Field | Content |
|---|---|
| inputs | All upstream evidence files and outputs |
| allowed_actions | read only; run checks; write a report |
| allowed_paths | read: concept folder, runs; write: `runs/<run_id>/validate/` |
| required_evidence | pass/fail per check; list of failures |
| outputs | `validate/report.json` with overall `pass|fail` |

Checks list: Section 4.7 (Q5 asks Editor to confirm).

#### Step C: animation (stretch) [PROPOSAL scope]
Inputs: validated asset plus motion beats from `notes.md`. Output: frame sequence or animation spec under `runs/<run_id>/animate/`. Evidence: frame count, hashes, motion beats checked against notes. Allowed actions: file write, optional image adapter. Engine-side hookup needs approval.

#### Step D: sound (stretch) [PROPOSAL scope]
Inputs: sound brief tied to an asset. Allowed actions: `audio_gen` via ElevenLabs adapter. **Any call that spends money has `requires_approval` true and `spend_usd` 0 until Johnathan says yes** [SRC]. Outputs: audio files under `runs/<run_id>/sound/`. Evidence: file hashes, durations, license note confirming the audio carries no copyrighted or trademarked material.

---

## 4. Data flow and per-step acceptance tests

### 4.0 Flow
```
brief + refs -> [A design-with-concepts] -> /workspace/concepts/<topic>/<direction>/*  (Johnathan picks)
   generation store (not shell-visible) -> [B1 ingest] -> /workspace/concepts/... + ingest evidence
   -> [B2 concept lock] -> asset_spec.json
   -> [B3 cut] -> cut images
   -> [B4 bake] (Editor) -> baked asset
   -> [B5 import] (Editor, approval) -> project asset
   -> [B6 validate] -> report.json
   -> (stretch) [C animate] -> [D sound]
Every arrow = outputs listed by path + sha256 in the evidence file; next step's `inputs` must match those hashes.
```
Each step is gated before and after: the gate authorizes actions, then the evidence check confirms every `required_evidence` item exists. A missing item means the step fails.

### 4.1 General tests (every step) [PROPOSAL]
- G1: the step refuses to start unless contract `status` is `approved`. Pass: attempt on a `draft` or `revoked` contract returns deny.
- G2: write outside `allowed_paths` is denied. Pass: attempt to write one directory up is denied and logged.
- G3: an action not in `allowed_actions` is denied (deny-by-default).
- G4: any action marked live, published, spent or pushed returns "needs approval" and does not execute.
- G5: input sha256 mismatch aborts the step.
- G6: every `required_evidence` item is present in the evidence file; otherwise fail.

### 4.2 Step A tests
- A1: each direction folder has `_hero.png`, `_impact.png`, `_palette.png` and `notes.md`. Pass: all four exist and are non-empty.
- A2: comparison sheet exists at the topic root.
- A3: evidence lists files with sizes, references (trailer stills, VC-02) and the reviewer confirmation. Pass: all three present.
- A4: no image outside `/workspace/concepts/<topic>/` was created by this step.
- A5 (manual review): no lore text, no copyrighted or trademarked material, no heat distortion in the design. Pass: reviewer note attached.

### 4.3 Step B1 ingest tests
- I1: every input has a copy at `dest_path` and the copy's sha256 equals the recorded sha256. Pass/fail per file.
- I2: evidence has `source_path`, `dest_path`, `sha256` for every file.
- I3: re-running with identical inputs is idempotent (no change, no error). Re-running with a different file at the same `dest_path` is denied.
- I4: names match `<direction>_hero.png`, `_impact.png`, `_palette.png`.
- I5: nothing was written outside `/workspace/concepts/<topic>/<direction>/`.

### 4.4 Step B2 concept lock tests
- C1: `asset_spec.json` references only files whose hashes match ingest evidence.
- C2: spec has the required keys (names are proposals: `asset_name`, `source_image`, `size_budget`, `direction`).
- C3: a selection note records Johnathan's pick.

### 4.5 Step B3 cut tests
- K1: each cut file exists, is a PNG with an alpha channel, and is non-empty.
- K2: alpha coverage is between a lower and upper bound set in the contract (values TBD, Q5). Pass if within bounds.
- K3: evidence names the adapter used. If the segmenter is `manual`, a reviewer note exists.
- K4: source concept files are unchanged (hash equal to input).

### 4.6 Steps B4 and B5 tests (depend on Q2)
- B4-1: baked asset exists and its hash is recorded.
- B4-2: bake log contains no errors.
- B5-1: with no approval on file, the step returns "needs approval" and the project is unchanged (project directory hash before equals after).
- B5-2: with approval, the asset appears at the expected project path and the hash matches the baked asset.

### 4.7 Step B6 validate checks (proposed list; Q5)
1. Every upstream evidence file exists and parses.
2. Hash chain: each step's input hashes equal the previous step's output hashes.
3. All required files exist and are non-empty.
4. File naming follows the conventions in Section 3.3.
5. Image checks: format, dimensions within budget, alpha present for cut assets.
6. Constraint checks: no heat-distortion flag in `engine_notes.md`; a reviewer note on lore text and trademarks exists.
7. No spend recorded unless an approval record exists; no pushed or published actions.
8. Audit log (Contract Smith's hash chain) has an entry for each step run.
Pass: all checks pass. Any failure fails the report and names the failing check.

### 4.8 Stretch tests
- C-anim: frame count matches the spec; hashes recorded.
- D-sound: files exist; if any provider call happened, an approval record with spend amount exists; otherwise zero provider calls.

---

## 5. MVP cut

**One asset, end to end: concept to asset to validated import for a single asset** [SRC]. Test case: the Molten Slag fireball (`fireball/molten-slag`) [SRC].

### 5.1 Build sequence (ordered) [PROPOSAL]
0. **Prerequisite: Contract Smith's gate and schema.** Do not start until the final schema and gate call exist (Q2 in the open list covers the schema). Use stubs behind the wrapper in 2.4 only to test the pipeline code in the meantime.
1. **Contract templates**: write `templates/<step>.contract.json` for A, B1 to B6 using Section 3.4. Pass: each validates against Contract Smith's schema.
2. **Step wrapper**: implement `run`/`check` skeleton and gate wrapper. Pass: G1 to G6.
3. **Ingest (B1)**: Pass: I1 to I5 on the Molten Slag images.
4. **Concept lock (B2)**: Pass: C1 to C3.
5. **Cut (B3)** with `manual` or classic cut first, adapter later. Pass: K1 to K4.
6. **Validate (B6)** built before bake and import so earlier steps can be checked early. Pass: all 4.7 checks on steps 3 to 5.
7. **Bake (B4)**, with Editor, after Johnathan's yes. Pass: B4-1, B4-2.
8. **Import (B5)** as a dry run first; the real import only with approval. Pass: B5-1; B5-2 if approved.
9. **Model adapters**: wire `segmenter` and `image_gen` only after the event page rules are confirmed.
10. **Stretch, only if time remains**: animation (C), then sound (D, with approval for any spend).

Dependencies: steps 3 to 6 need no engine work and no spend. Steps 7 to 8 need Editor and Johnathan's yes. The vertical slice is "done" when the validate report passes for the single asset, or when it passes through step 6 with 7 and 8 recorded as blocked on approval (the fallback if the engine pause stands).

### 5.2 Out of scope for the MVP
Animation, sound, multiple assets, any engine change, any Muse or SAM dependency, any spend.

---

## 6. Open questions

| # | Question | Who answers |
|---|---|---|
| Q1 | What is the generation store path, and can Concept Artist copy to `/workspace/concepts/` (it does today by hand) or must ingest read the store directly? | Concept Artist |
| Q2 | Bake and import interface with Editor: input and output formats, how they are invoked, where the imported asset lives, and whether a dry run is possible while the engine pause stands. | Editor, Johnathan |
| Q3 | Final contract schema fields: key names, argument-constraint syntax, how a step references an upstream output, evidence file format, gate and compile call shape. | Contract Smith |
| Q4 | Event page rules: are Muse Image and SAM 3.1 allowed or required? Any restrictions on other models or on ElevenLabs? Recheck Oct 26. | Hack Lead |
| Q5 | Validation checks list (Section 4.7) and numeric thresholds (alpha coverage, size budgets). | Editor, Concept Artist, Johnathan |
| Q6 | Audio spend: any ElevenLabs budget? Default stays $0 and each call needs Johnathan's yes. | Johnathan via Ultralord |
| Q7 | Which language or runtime will the Meta coding agents use? Contract Smith started in dependency-free Python, and the layout above assumes that, as a proposal. | Hack Lead, Contract Smith |
| Q8 | Where does the repo live and where do runs write? Currently `/workspace/pipeline/` is local only; no repo location yet. | Ultralord |
| Q9 | Comparison-sheet file name and the exact `fireball/molten-slag` folder naming. | Concept Artist |

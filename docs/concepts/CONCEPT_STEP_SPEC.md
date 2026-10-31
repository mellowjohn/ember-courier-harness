> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

**Wrathful Conquest harness: `design-with-concepts` step spec (Step A, plus its ingest hand-off B1)**
Status: DRAFT for Johnathan's review. Documentation only; nothing here is built. Written for a Meta coding agent to implement later.
Labels: **[SRC]** = observed in the real workflow (`/workspace/concepts/fireball/`, `/workspace/sc22/`, `wc-brand-consistency`, `/workspace/pipeline/PIPELINE_SUBSYSTEM.md`). **[PROPOSAL]** = my suggestion, change freely. **[OPEN]** = unsettled, see section 6.
Step names and folder conventions follow `PIPELINE_SUBSYSTEM.md`: Step A `design-with-concepts`, B1 `ingest`, B2 `concept` (lock), `runs/<run_id>/`, `evidence/<step>.evidence.json`.

## 1. Purpose

Turn a short brief (a topic such as "fireball") into 3 to 4 distinct, on-brand visual concept directions that Johnathan can compare and pick from. Each direction ships with a hero image, an impact image, a labeled palette, and short notes. A topic-level comparison sheet puts them side by side. After the pick, an optional `refined/` folder holds refined frames and `engine_notes.md` for Engine.

Scope: concept art and notes only. It ends at "directions ready, Johnathan picks" (plus optional refine). It does not cut, bake, import, animate or make sound.

Roles and non-goals:
- **Concept Artist** (or a Meta agent in that role) runs the step. **Johnathan picks**; the step never selects a winner.
- **Never publish or post** anything. Concepts may later be reused for X posts, but only Johnathan can approve that, outside this step.
- **No lore or story text** in images or notes. No text of any kind inside generated images.
- **No copyrighted or trademarked material** (names, characters, logos, styles of named IP) in images, prompts or notes.
- **No heat distortion** in v1. Concepts must be buildable with the v1 pipeline: animated noise-scrolled emissive core, bloom, `fire_bolt` particles (core, embers, trail, impact, flash), impact burst, point light on stone, in a dark cathedral interior with torches.
- **No engine changes** and no spend (default $0). Both need Johnathan's yes first.
- Do not assume Muse Image or any other Meta model is available; the event page and Official Rules get rechecked Oct 26 [OPEN].

## 2. Design

### 2.1 Brand and look rules [SRC]
- Match the live trailer: molten orange-red on Nefarium black (`#0B0807`). Luceran is a low-poly stone armored figure with twin red eyes. Prefer literal trailer frames as references over new invention; if output drifts, discard and regenerate with stronger "strict match, do not restyle" wording.
- Match approved **VC-02** (`/workspace/sc22/vc02-concept.png`): faceted forms, controlled glow, readable silhouettes, warm emissive glow against dark stone.
- Silhouettes must read at gameplay distance. Palette uses 4 warm colors plus the background.

### 2.2 Model adapter [SRC constraint, PROPOSAL interface]
Image generation sits behind the `image_gen` adapter role from `config/adapters.json` (provider name or `manual`). The step never names a specific model. If no provider is allowed, the step still runs with `manual` (a human supplies images and the step does ingest, QA, palette, sheet).

### 2.3 Output contract (exact layout) [SRC, with fixed template added]
```
/workspace/concepts/<topic>/
  <topic>_comparison_sheet.png          topic root; name is a PROPOSAL (existing: fireball_comparison_sheet.png)
  <topic>_comparison_sheet.manifest.json   PROPOSAL: sheet builder's record of slots (see T10)
  <direction-slug>/
    <slug>_hero.png                     projectile (or subject) in flight
    <slug>_impact.png                   impact frame
    <slug>_palette.png                  labeled swatches, 5 colors
    notes.md                            fixed template, 2.3.1
    refined/                            optional, only for the picked direction
      <slug>_<frame>.png                e.g. flight_closeup, trail_ember_breakdown, impact_sequence
      engine_notes.md                   template in 2.3.2
```
Rules:
- `<direction-slug>`: lowercase, hyphens only, matches `^[a-z0-9]+(-[a-z0-9]+)*$`. `<slug>` in file names equals the folder name exactly.
- Images are PNG (RGB). Generated JPEG is converted to PNG at ingest.
- Per-run working files and evidence live in `/workspace/pipeline/runs/<run_id>/`, never inside `/workspace/concepts/` [SRC from PIPELINE].
- Worked example: `/workspace/concepts/fireball/` with `molten-slag/`, `wrath-comet/`, `shardfire/`, `nefarium-ember/`; `molten-slag/refined/` has `engine_notes.md` and 3 frames.

#### 2.3.1 `notes.md` template (exact; replace `<...>`)
```markdown
# <Direction Name>

**Pitch:** <one line, max 140 characters, no line breaks>

## Palette
- <#RRGGBB> <label>
- <#RRGGBB> <label>
- <#RRGGBB> <label>
- <#RRGGBB> <label>
- #0B0807 Nefarium

## Shape language
<1 to 2 sentences: silhouette, how it reads at gameplay distance>

## Core vs. outer flame
<1 to 2 sentences: emissive core vs. outer layer, colors>

## Motion / ember behavior
<1 to 2 sentences: embers, trail, gravity, impact behavior>

## Readability against dark stone
<1 to 2 sentences: contrast, bloom, point light on stone>

Pipeline: noise-scrolled emissive core + bloom + fire_bolt particles (core/embers/trail/impact/flash) + impact burst + point light. No heat distortion.
```
Notes: exactly 5 palette lines, last one `#0B0807`. Hex is uppercase `#RRGGBB`. The existing `fireball/*/notes.md` files use an older bullet format (`- Shape:`, `- Core vs. outer:`, `- Vs. stone:`, no palette list) and must be migrated to this template [SRC gap].

#### 2.3.2 `refined/engine_notes.md` section template
Header paragraph (required): "v1 pipeline only ... **No heat distortion.** ... Emissive values are linear HDR multipliers on the sRGB hex colour." Then these `##` sections in this order (mark a section `N/A: <reason>` if the topic has no such element):
1. `## 1. Emissive core graph`: two noise octaves (scale, UV scroll speed, weight), temperature ramp table (`n | hex | HDR multiplier`), dark crust mask (scale, speed, smoothstep thresholds), Fresnel rim.
2. `## 2. Outer flame`: shell shape and scale, scroll speed, alpha erosion, colors and intensity, stretch.
3. `## 3. Bloom`: threshold, knee, intensity, radius; readability check.
4. `## 4. Particles (fire_bolt)`: table with one row each for `core`, `embers`, `trail`, `impact`, `flash`; columns Count/rate, Lifetime, Size, Colour over life (hex x HDR), Notes (gravity for drips).
5. `## 5. Impact burst timing`: ms-based timeline from t=0 (flash, burst, particles, decal).
6. `## 6. Point light`: color hex, radius m, intensity, flicker formula, impact spike and fade.
7. `## 7. Fade-out`: end-of-life behavior without a hit, with durations.
8. `## 8. Readability against dark stone`: value contrast, silhouette, warm light on stone, what to avoid.
Values are starting points to tune in engine [SRC].

### 2.4 Step order (numbered, follow in sequence) [PROPOSAL consolidating the real workflow]
1. **brief**: load the brief and reference list; compute sha256 of every reference; confirm references exist (trailer stills, VC-02).
2. **generate**: for each direction (3 to 4), create hero, then impact, via the `image_gen` adapter, passing the references and "strict match, do not restyle, no text, no heat haze". Keep a generation log line per image: direction, role, prompt, source file path. Respect `max_images` in the contract.
3. **ingest (B1)**: copy each image from the generation store into `/workspace/concepts/<topic>/<slug>/<slug>_<role>.png` (convert JPEG to PNG). Record `source_path`, `source_sha256`, `dest_path`, dest `sha256`, `bytes`. Source to destination mapping comes only from the generation log, never guessed by eye (see Q4).
4. **view and QA**: open every image. Regenerate any that are off-brand, unreadable, contain text, or drift from VC-02/trailer. Record a reviewer note per image: viewed, no text, no trademark, no heat distortion.
5. **palette build**: choose 5 hex values per direction (4 warm plus `#0B0807`), write `notes.md` (template 2.3.1), then render `<slug>_palette.png` with 5 labeled swatches whose colors are exactly those hex values.
6. **sheet build**: compose `<topic>_comparison_sheet.png`: one row per direction with title and pitch, columns hero, impact, palette, each labeled. Text must fit the canvas (the existing fireball sheet clips the Shardfire pitch; wrap or truncate). Write the sheet manifest.
7. **run checks**: execute acceptance tests T1 to T12 (2.6); write the evidence record. Fix and re-run on any failure.
8. **hand-off to picker**: set the run to `awaiting_pick`, send Johnathan the sheet path, per-direction paths and one-line pitches via the harness, with no posting. Stop. Johnathan's pick is an approval event recorded in evidence.
9. **refine (optional, picked direction only)**: generate the refined frames from the picked direction's hero, impact and VC-02 as references (match strictly); ingest them into `<slug>/refined/` the same way as step 3; QA as step 4.
10. **engine notes**: write `refined/engine_notes.md` (template 2.3.2); run T13.

### 2.5 Generation-store handling [SRC, important]
`GenerateImage` ignores any requested file path; images land in a store. Shell can see them at `/cursor/stores/<store-id>/grok-bot/agents/<agent-id>/attachments/<64-hex>.jpg` (not at the `assets/` path the tool reports, which stays empty from Shell). File names are content hashes, unrelated to the prompt name, and files are 1280x720 JPEG. A Meta harness will have its own store; the ingest step must take a mapping, not assume this path [OPEN Q4].

### 2.6 Acceptance tests (mechanical; each returns pass/fail with the failing path)
| ID | Check |
|---|---|
| T1 | Topic folder has 3 to 4 direction folders; each slug matches the regex in 2.3. |
| T2 | Each direction has `<slug>_hero.png`, `<slug>_impact.png`, `<slug>_palette.png`, `notes.md`; all non-empty; names exact. |
| T3 | Hero and impact files open as PNG with width and height both >= 1024 px (existing: 1280x720 passes only if the rule is "long side >= 1024"; see Q2 for the exact rule). |
| T4 | Palette PNG opens as PNG, width >= 600 and height >= 150 (existing: 1000x240). |
| T5 | `notes.md` contains, in order, these exact headers: `# `, `**Pitch:**`, `## Palette`, `## Shape language`, `## Core vs. outer flame`, `## Motion / ember behavior`, `## Readability against dark stone`, and the final `Pipeline:` line. |
| T6 | Pitch is one line, <= 140 characters. |
| T7 | Palette section lists exactly 5 hex values matching `^#[0-9A-F]{6}$`, all distinct, and the last equals `#0B0807`. |
| T8 | Palette PNG sampled at the center of each of the 5 swatches equals the 5 hex values in `notes.md` (tolerance 2 per channel). |
| T9 | No file in the run was written outside `/workspace/concepts/<topic>/` and `runs/<run_id>/`; no network or publish action in the audit log. |
| T10 | Comparison sheet exists at the topic root, opens as PNG, and its manifest shows `slots_filled == slots_total == 3 x directions`, with no `[image pending]` and no clipped text (every text width <= its cell). |
| T11 | Each direction's hero, impact and palette in the sheet come from the current files (manifest sha256 equals file sha256). |
| T12 | Evidence record exists at `runs/<run_id>/evidence/design-with-concepts.evidence.json`, parses, and has every key in section 3.5. File sizes and sha256 in it match disk. |
| T13 | If `refined/` exists: it has `engine_notes.md` with all 8 `##` section headers (or `N/A: ...`), the phrase "No heat distortion", and at least 1 PNG >= 1024 px. |
| T14 | `engine_notes.md`, `notes.md` and the evidence do not contain flags for heat distortion/haze/refraction as a feature (string check: only "No heat distortion" or "no heat haze" allowed). |
Human or vision review covers only what code cannot check: images contain no lore text, no trademarked material, match brand and VC-02. That is a required reviewer note (3.5), not a test code can pass alone.

## 3. Contracts (inputs, allowed actions and paths, limits, required evidence, approval points)

### 3.1 Inputs (the brief)
```json
{
  "topic": "fireball",
  "directions": 3,
  "direction_names": ["optional names, otherwise agent proposes"],
  "references": [
    {"path": "/workspace/wrathful-conquest-trailer/scratch/pass27/stills/f990.png", "role": "trailer-look"},
    {"path": "/workspace/sc22/vc02-concept.png", "role": "approved-vc02"}
  ],
  "pipeline_limits": ["v1 buildable", "noise-scrolled emissive core", "bloom", "fire_bolt particles", "impact burst", "point light on stone", "no heat distortion"],
  "setting": "dark cathedral interior with torches",
  "background_hex": "#0B0807"
}
```
Each reference carries a sha256 in the contract `inputs` [PIPELINE draft].

### 3.2 Contract fields (Contract Smith's DRAFT; do not extend) [SRC via PIPELINE]
`id`, `agent`, `intent_text`, `inputs`, `allowed_actions`, `allowed_paths`, `forbidden_actions`, `limits`, `required_evidence`, `requires_approval`, `status` (`draft`, `approved`, `revoked`). Deny by default; anything live, published, spent or pushed returns "needs approval". I could not find Contract Smith's schema file on disk (the draft is only visible in `PIPELINE_SUBSYSTEM.md`), so key names and nesting below are illustrative [OPEN Q5].

### 3.3 Step A contract: field contents
| Field | Content |
|---|---|
| allowed_actions | `file_read` (references), `image_gen` via adapter (or `manual`), `file_copy` (ingest), `file_write` (notes, palette, sheet, evidence), `vision_review` |
| allowed_paths | read: references, generation store; write: `/workspace/concepts/<topic>/` and `/workspace/pipeline/runs/<run_id>/` |
| forbidden_actions | `publish`, `post`, `network` (except the allowed adapter call), `delete`, `overwrite_without_hash_match`, `engine_change`, any write outside allowed paths |
| limits | `spend_usd: 0`; `max_images` (total per run; the example uses 12 for 3 directions: 2 base images each plus retries); `max_calls`; `time_window` |
| requires_approval | true for: any spend, any publish/post, any engine change, and the selection event (Johnathan's pick is recorded, not decided by the agent) |
| status | must be `approved` before the step starts |

### 3.4 Example contract (fireball-style) [illustrative values]
```json
{
  "id": "design-with-concepts-fireball-001",
  "agent": "concept-artist",
  "intent_text": "Make 3 distinct fireball concept directions (hero, impact, palette, notes) plus a comparison sheet under /workspace/concepts/fireball/. Match the trailer look and VC-02. Buildable in v1, no heat distortion, no lore text, nothing copyrighted or trademarked. Do not publish. Johnathan picks.",
  "inputs": [
    {"path": "/workspace/wrathful-conquest-trailer/scratch/pass27/stills/f990.png", "sha256": "<64 hex>"},
    {"path": "/workspace/sc22/vc02-concept.png", "sha256": "<64 hex>"},
    {"value": {"topic": "fireball", "directions": 3, "background_hex": "#0B0807"}}
  ],
  "allowed_actions": [
    {"tool": "file_read", "args": {}},
    {"tool": "image_gen", "args": {"adapter_role": "image_gen", "max_images": 12}},
    {"tool": "file_copy", "args": {"dest_prefix": "/workspace/concepts/fireball/"}},
    {"tool": "file_write", "args": {"path_prefix": ["/workspace/concepts/fireball/", "/workspace/pipeline/runs/<run_id>/"]}},
    {"tool": "vision_review", "args": {}}
  ],
  "allowed_paths": {
    "read": ["/workspace/wrathful-conquest-trailer/scratch/pass27/stills/", "/workspace/sc22/", "<generation-store>/"],
    "write": ["/workspace/concepts/fireball/", "/workspace/pipeline/runs/<run_id>/"]
  },
  "forbidden_actions": ["publish", "post", "delete", "overwrite_without_hash_match", "engine_change", "write_outside_allowed_paths"],
  "limits": {"spend_usd": 0, "max_calls": 40, "time_window": "4h"},
  "required_evidence": {
    "file_copy": ["source_path", "source_sha256", "dest_path", "sha256", "bytes"],
    "file_write": ["file list with sizes and sha256"],
    "image_gen": ["references used", "adapter/provider name", "generation log"],
    "vision_review": ["reviewer note: every image viewed; no lore text; no copyrighted or trademarked material; no heat distortion"]
  },
  "requires_approval": ["spend", "publish", "post", "engine_change", "direction_selection"],
  "status": "approved"
}
```

### 3.5 Required evidence record [PROPOSAL format; Contract Smith owns the final format]
File: `/workspace/pipeline/runs/<run_id>/evidence/design-with-concepts.evidence.json`
```json
{
  "step_id": "design-with-concepts-fireball-001",
  "references": [{"path": "...", "sha256": "<64 hex>", "role": "trailer-look"}],
  "adapter": {"role": "image_gen", "provider": "<name or manual>"},
  "files": [
    {"direction": "molten-slag", "role": "hero",
     "source_path": "<generation-store>/<64hex>.jpg", "source_sha256": "<64 hex>",
     "dest_path": "/workspace/concepts/fireball/molten-slag/molten-slag_hero.png",
     "sha256": "<64 hex>", "bytes": 1249673, "width": 1280, "height": 720}
  ],
  "sheet": {"path": "/workspace/concepts/fireball/fireball_comparison_sheet.png", "sha256": "<64 hex>", "bytes": 0},
  "review": {"viewed_all": true, "no_lore_text": true, "no_trademark": true, "no_heat_distortion": true,
             "reviewer": "<agent or human>", "notes": "<free text>"},
  "tests": {"T1": "pass"},
  "selection": {"status": "awaiting_pick", "picked_direction": null, "approved_by": null, "approved_at": null}
}
```
Required: file list with sizes and sha256, references used, the viewed/no-text/no-trademark confirmation, test results, and (after the pick) the selection record.

### 3.6 Approval points
1. Contract `status: approved` before start (Johnathan via Ultralord).
2. Any spend (default $0) or use of a paid or restricted model.
3. Johnathan's pick of a direction (recorded in `selection`).
4. Anything posted, published, or pushed (always denied by this step).
5. Any engine change from `engine_notes.md` (Engine is separate and needs Johnathan's yes).

## 4. Data flow

```
brief + references (sha256)
  -> [generate]  image_gen adapter (or manual) -> generation store (JPEG, hash-named) + generation log
  -> [ingest B1] copy + convert -> /workspace/concepts/<topic>/<slug>/<slug>_{hero,impact}.png + ingest evidence (source/dest/sha256)
  -> [view + QA] reviewer notes; regenerate and re-ingest as needed
  -> [palette]   notes.md (5 hex) -> <slug>_palette.png
  -> [sheet]     <topic>_comparison_sheet.png + manifest
  -> [checks]    T1..T12 -> evidence.json
  -> [hand-off]  status awaiting_pick -> Johnathan picks
  -> [refine]    refined frames -> <slug>/refined/ (picked direction only)
  -> [engine notes] refined/engine_notes.md -> T13, T14
  -> downstream: B2 `concept` lock reads the picked direction's hero, impact, palette, notes.md and engine_notes.md by path and sha256
```
Every arrow is a file plus sha256; the next step's `inputs` must match the hashes in this step's evidence. Later steps read only from `/workspace/concepts/`, never the generation store [SRC from PIPELINE]. Palette hex flows one way: `notes.md` is the source of truth; the palette PNG and the sheet are derived from it.

## 5. MVP cut

**Smallest part that must work by Nov 4 (submission due 9:00 PM ET):** one topic, 3 directions, run end to end through step 8 (hand-off to the picker) with the checks passing, plus the refine and engine notes for one picked direction using the existing Molten Slag set as the golden example.
Must work:
- Folder layout and file naming (2.3), `notes.md` template, 5-hex palette, `<slug>_palette.png`.
- Ingest with sha256 recording and a source-to-destination mapping from the generation log.
- Comparison sheet with manifest and no empty or clipped slots.
- Acceptance tests T1 to T12 as a script that exits non-zero on failure, plus the evidence record.
- `manual` adapter mode, so the step works even if no image model is allowed.
- The step contract (3.4) and its example, validated with Contract Smith's gate.
Dropped for the MVP:
- Automated vision QA (the reviewer note stays manual), automatic trademark or text detection, multi-topic batches, automatic refine, X-post crops, animated previews, any provider-specific adapter beyond one, and the stretch checks T13 and T14 if time runs short (engine notes are then reviewed by hand).
- Any spend, any Muse or other Meta model dependency until the rules are confirmed.

## 6. Open questions (for Johnathan)

| # | Question |
|---|---|
| Q1 | Which image model should the step use? Are Muse Image or other Meta models allowed or required? Not verified; the event page and Official Rules get rechecked Oct 26. Until then the spec uses an `image_gen` adapter role with a `manual` fallback, and nothing is hardcoded. |
| Q2 | Image size rule: the existing hero and impact files are 1280x720 and the palette is 1000x240. Should the rule be "both sides >= 1024" (existing files would fail), "long side >= 1024" (as written in T3), or something higher for X-ready art? |
| Q3 | Should the MVP require refined frames and `engine_notes.md` for the picked direction, or only the 3 directions plus the sheet? |
| Q4 | Generation store: the generation tool hash-names files and ignores the requested path. Should the harness require a generation log (prompt, role, source path) so ingest never has to match files by eye? I did that by hand last time. The pipeline spec says the store is "not shell-visible", but I found it readable from Shell; please confirm that is expected. |
| Q5 | Contract Smith's final schema: key names, argument-constraint syntax, evidence file format and gate call shape. I could not find the schema file on disk, so the example uses only the draft field names. |
| Q6 | Comparison sheet file name and the migration of the four existing `notes.md` files to the new template (`fireball_comparison_sheet.png` vs `<topic>_comparison_sheet.png`). |
| Q7 | Is "art striking enough for possible X posts later" a requirement for this step (for example an extra crop or aspect ratio), or only a quality bar? Posting itself stays out of scope. |
| Q8 | Number of directions: the real run made 4; MVP says 3 to 4. Is 3 enough? |

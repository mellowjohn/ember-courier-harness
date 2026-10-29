# AGENTS.md — concepts

Scope: **design-with-concepts** (Step A) and ingest hand-off (B1). Parent: [`../../AGENTS.md`](../../AGENTS.md).

## Primary docs

| File | Role |
|------|------|
| `CONCEPT_STEP_SPEC.md` | Held Step A spec |
| `CONCEPT_ADDENDUM_ART_DIRECTION.md` | Art direction fields tied to scope contract |
| `CONCEPT_FIXES_PARTB.md` | Cross-spec fixes |

Merged: `../architecture/ARCHITECTURE_DRAFT_v4.md` Part 2 + Appendix 2A. Pipeline folder layout and step names: `../pipeline/PIPELINE_SUBSYSTEM.md`.

## Art direction inheritance

- **`art_direction`** lives on the approved **scope contract** (see `../contracts/CONTRACT_ADDENDUM_v0.4.md`).
- Every **build / asset-step contract** is a **subset** of that scope; agents judge visual output against `art_direction`, not ad-hoc prompts alone (architecture D42).
- Johnathan **picks** the winning direction; the step must not auto-select a winner.

## Hard rules (concept-specific)

- **No publish or post** from this step.
- **No text inside generated images**; no lore dumps in notes.
- **No copyrighted or trademarked** material in prompts, images, or notes.
- **No heat distortion** in v1 visuals (buildable with the v1 particle/emissive pipeline).
- **Johnathan accepts each asset** even when parent contract uses `approve_all`.
- Default **$0 spend**; no engine changes without his yes.

## Model / adapter

- Use the **`image_gen` adapter** abstraction; do not assume a specific Meta model is available — **[UNVERIFIED]** until event rules recheck.

## Verification

Acceptance tests: prefix **`CS-T`** (CS-T1–CS-T14 in architecture). Evidence per step under the run/evidence layout described in the concept spec (paths in docs may use historical `/workspace/...` prefixes).

## Agents in this folder

- Docs and proposals only in this repo; no concept art binaries or private reference packs.
- For contract boundaries, see [`../contracts/AGENTS.md`](../contracts/AGENTS.md).

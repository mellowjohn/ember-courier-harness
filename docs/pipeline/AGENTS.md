# AGENTS.md — pipeline

Scope: production pipeline (ingest → concept lock → cut → bake → import → validate; stretch animation/sound). Parent: [`../../AGENTS.md`](../../AGENTS.md).

## Primary docs

| File | Role |
|------|------|
| `PIPELINE_SUBSYSTEM.md` | Held pipeline spec (Step A hand-off through B6) |
| `PIPELINE_ADDENDUM_ITERATION.md` | Caching, failure-as-amendment, worker bundling (PL-R tests) |
| `PROPOSED_FIXES.md` | Proposal — not auto-applied to held Part 3 |
| `PIPELINE_FIXES_PARTB.md` | Part B–style fixes |

Merged narrative: `../architecture/ARCHITECTURE_DRAFT_v4.md` Part 3, section 5A, Appendix 3A/3B. Contract tool names: `TOOL_REGISTRY_NOTE_pipeline.md` in `../contracts/`.

## Hard rules (pipeline-specific)

- **No `git.push` or `git.open_pr` on pipeline contracts.** Local commits on worker branches only; push/merge/PR are Johnathan's (see architecture Part 7 and pipeline "Common contract text").
- **Engine pause:** Import/engine work needs Johnathan's yes while the pause stands.
- **Spend $0** unless a future approved contract sets a nonzero cap (default deny).
- **Image quality:** Judged against **`art_direction`** from the approved scope contract (D42); size/alpha are technical gates only — do not rely on voided numeric art thresholds alone.

## Roles (design)

- **Orchestrator** parent contract; **two workers** (prep + editor) with child contracts ⊆ parent under `scope_subset`; **verifier** separate for validate (read-only to worker outputs). See architecture D28 and pipeline addendum.

## Verification

Pipeline acceptance tests use prefix **`PL-`** (including **`PL-R1–PL-R16`** for iteration). Concept hand-off tests live under **`CS-T`** in `../concepts/`.

## Agents in this folder

- Implement or document against step ids (B1–B6, etc.) and evidence labels (`verified`, `self_reported`, `unverified`) per architecture Part 10.
- Do not add engine code, binary assets, or `runs/` trees to this public repo.
- Propose contract **drafts** only; never write approved `contracts/**` (see [`../contracts/AGENTS.md`](../contracts/AGENTS.md)).

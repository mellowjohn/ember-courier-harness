# AGENTS.md — architecture

Scope: merged harness architecture. Parent rules: repo root [`AGENTS.md`](../../AGENTS.md).

## Primary document

Read **`ARCHITECTURE_DRAFT_v4.md`** in this directory first before implementing any subsystem.

That file merges contract, concept, pipeline, and triage specs plus Parts 6–11 (iteration, git, workspace, orchestration, transparency, quality). Later amend docs in `docs/*/` override their source parts where stated; **where the merge conflicts, this draft wins** (see each folder's README).

## How to use the draft

- **"Decisions made" (D1–D45):** Treat **[v4]** items tagged as Johnathan's decisions as **decided**, not defaults (D32–D45 include approval mode, contracts as system files, art_direction scoring, D44 S0/S1 closes, and more).
- **Part B (`M-xx`):** Cross-spec consistency — use when two subsystem docs disagree.
- **Part C (`OQ-xx`):** Deduplicated **open questions** — do not invent answers; flag for Johnathan.
- **Part D:** **[UNVERIFIED]** register — Meta models, agents, hackathon dates/rules until official recheck.

## Labels in sources

- **[OPEN]** / **[PROPOSAL]** — not settled or suggestion only.
- **[UNVERIFIED]** — depends on Meta or event rules; do not remove the marker without evidence from the official event page.
- **[SRC]** / **[DECIDED]** — vary by part; see "How to read this document" in the draft.

## Agents in this folder

- **Do:** Summarize, implement, or test against cited sections and decision ids (`D44`, `D35`, etc.).
- **Do not:** Copy multi-page schema or gate algorithms into chat; link `ARCHITECTURE_DRAFT_v4.md` and the relevant Part.
- **Do not:** Add runtime code, `.cursor/rules`, or harness implementations to this public docs repo unless Johnathan explicitly expands scope.

## Related nested guides

- Contracts → [`../contracts/AGENTS.md`](../contracts/AGENTS.md)
- Pipeline → [`../pipeline/AGENTS.md`](../pipeline/AGENTS.md)
- Concepts → [`../concepts/AGENTS.md`](../concepts/AGENTS.md)
- Triage → [`../triage/AGENTS.md`](../triage/AGENTS.md)

# pipeline skill

**Contract-first, gate-first, deny-by-default.** Every pipeline step runs under its own contract; call the gate before side effects and attach required evidence.

**Specs:** `docs/pipeline/` — held spec `PIPELINE_SUBSYSTEM.md`; iteration addendum and fixes alongside. Architecture Part 3: `docs/architecture/ARCHITECTURE_DRAFT_v4.md`.

Pipeline contracts must not list `git.push` or `git.open_pr`. Inherit `art_direction` from the approved scope contract.

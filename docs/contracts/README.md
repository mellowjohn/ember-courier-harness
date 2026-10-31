# Contracts docs — reading order

Documentation only until Johnathan builds with Meta's agents. Nothing here is runtime code.

1. `CONTRACT_SYSTEM.md` — held base spec (schema, gate, evidence, audit). Read first.
2. `SCHEMA_DECISIONS_v0.2.md` — schema decisions on top of the held spec.
3. `CONTRACT_FIXES_v0.3.md` — fixes.
4. `CONTRACT_ADDENDUM_v0.4.md` — addendum; Appendix A covers the scope contract, `art_direction`, `art_score`, CT-46..49.
5. Notes:
   - `APPROVAL_MODE_AND_PR_NOTE.md` — `approval_mode` (`each` / `approve_all`) and `git.open_pr`.
   - `TOOL_REGISTRY_NOTE_pipeline.md` — registry entries for the pipeline tools.

Later documents amend earlier ones; where they conflict, the later one wins, and `docs/architecture/ARCHITECTURE_DRAFT_v4.md` is the merged source of truth. Contract tests use the `CT-` prefix.

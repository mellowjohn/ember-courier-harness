# ember-courier-harness

Public documentation for a **contract-driven game development harness**, demonstrated on the sample game **Ember Courier**. Prepared for Johnathan Rossi's Meta Global AI Developer Hackathon entry (Track 1, indie, solo).

This repository is **documentation only**: architecture, contracts, pipeline, concept, and triage specifications. It does not include private engine code, game assets, or runtime tooling.

## Start here

- **Agents & hard rules:** [`AGENTS.md`](AGENTS.md)
- **Architecture (merged source of truth):** [`docs/architecture/ARCHITECTURE_DRAFT_v4.md`](docs/architecture/ARCHITECTURE_DRAFT_v4.md)
- **Contracts (reading order):** [`docs/contracts/README.md`](docs/contracts/README.md)

## Documentation tree

| Path | Contents |
|------|----------|
| `docs/architecture/` | Architecture draft v4 |
| `docs/contracts/` | Contract system, schema decisions, fixes, addenda, approval/PR notes |
| `docs/pipeline/` | Pipeline subsystem and iteration addenda |
| `docs/concepts/` | Concept step spec and art direction |
| `docs/triage/` | Triage and code step specs |

## Conventions

- Doc headers that mention `/workspace/...` are historical authoring paths, not paths in this repo.
- Technical content is unchanged from the sanitized docs pack; `[UNVERIFIED]` markers are kept where present (e.g. Meta model or rules claims until checked against official event materials).
- Contract tests use prefixes: `CT-` contracts · `CS-T` concept · `PL-` pipeline · `TR-` triage.

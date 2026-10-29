# ember-courier-harness

Public documentation for a **contract-driven game development harness**, demonstrated on the sample game **Ember Courier**. Prepared for Johnathan Rossi's Meta Global AI Developer Hackathon entry (Track 1, indie, solo).

This repository is **documentation only**: architecture, contracts, pipeline, concept, and triage specifications. It does not include private engine code, game assets, or runtime tooling.

## Start here

- **Agents & hard rules:** [`AGENTS.md`](AGENTS.md)
- **Architecture (merged source of truth):** [`docs/architecture/ARCHITECTURE_DRAFT_v4.md`](docs/architecture/ARCHITECTURE_DRAFT_v4.md)
- **Contracts (reading order):** [`docs/contracts/README.md`](docs/contracts/README.md)

## Documentation tree

| Path | Contents | Agent guide |
|------|----------|-------------|
| `docs/architecture/` | Architecture draft v4 | [`docs/architecture/AGENTS.md`](docs/architecture/AGENTS.md) |
| `docs/contracts/` | Contract system, schema decisions, fixes, addenda, approval/PR notes | [`docs/contracts/AGENTS.md`](docs/contracts/AGENTS.md) |
| `docs/pipeline/` | Pipeline subsystem and iteration addenda | [`docs/pipeline/AGENTS.md`](docs/pipeline/AGENTS.md) |
| `docs/concepts/` | Concept step spec and art direction | [`docs/concepts/AGENTS.md`](docs/concepts/AGENTS.md) |
| `docs/triage/` | Triage and code step specs | [`docs/triage/AGENTS.md`](docs/triage/AGENTS.md) |

Cursor merges root [`AGENTS.md`](AGENTS.md) with the nearest nested `AGENTS.md`; the closest file wins on conflict.

## Conventions

- Doc headers that mention `/workspace/...` are historical authoring paths, not paths in this repo.
- Technical content is unchanged from the sanitized docs pack; `[UNVERIFIED]` markers are kept where present (e.g. Meta model or rules claims until checked against official event materials).
- Contract tests use prefixes: `CT-` contracts · `CS-T` concept · `PL-` pipeline · `TR-` triage.

# AGENTS.md

NSG MES — agent-native repository. Read only what your task requires.

## Always read first (every session)

1. [ARCHITECTURE.md](ARCHITECTURE.md) — layer rules, non-negotiable.
2. [docs/golden-principles.md](docs/golden-principles.md) — mechanical rules that evolve.
3. [docs/workflows/DEFINITION_OF_DONE.md](docs/workflows/DEFINITION_OF_DONE.md).
4. [docs/generated/STATE.md](docs/generated/STATE.md) — what exists today (auto-generated).

## Read by task type

| Ticket type   | Also read                                               |
|---------------|---------------------------------------------------------|
| Feature       | `docs/product-specs/{module}/`                          |
| Bug           | `docs/architecture/` + `docs/generated/STATE.md`        |
| Integration   | `docs/architecture/integrations/{system}.md`            |
| Compliance    | `docs/domain/compliance/`                               |
| Refactor      | `docs/decisions/` + `docs/golden-principles.md`         |
| Harness-Fix   | `docs/golden-principles.md` + `tools/`                  |

## Do NOT read unless strictly necessary

- `docs/exec-plans/completed/` — historical.
- `docs/decisions/` older than 90 days — unless you propose to revise.
- `docs/references/` — only if implementing with that specific library.

## When you encounter strategic ambiguity

DO NOT GUESS. Invoke the Consultant agent. See [docs/workflows/escalation.md](docs/workflows/escalation.md).

## Conventions

- Tests live next to the code in a `tests/` subdirectory.
- Domain language uses ISA-95 terms in English; Spanish equivalents in [docs/domain/glossary.md](docs/domain/glossary.md).
- All commits follow Conventional Commits.
- Branch naming: `feat/NSG-123-short-description` from ticket ID.
- Code, identifiers, commits, PRs in English. Domain/vision docs and `Question` tickets for the human operator in Spanish.

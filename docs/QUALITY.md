---
title: Quality — code quality standards
status: skeleton
last_updated: 2026-05-04
---

# QUALITY

Standards that go beyond `golden-principles.md`. Tactical, not strategic.

## Linting and formatting

- **`ruff check`** + **`ruff format`** — config in `pyproject.toml`. No `# noqa` without an issue link.
- **`mypy --strict`** for `packages/` and `tools/`. `apps/*` follows the same rule once it has Django stubs.
- Frontend: **ESLint** (config TBD by first frontend Worker) + **Prettier**.

## Testing

- **Pyramid:** unit (domain + application) > integration (infrastructure with real DB and Redis) > E2E (Playwright happy paths).
- **Coverage minimum per module: 80%** for `domain/`, 60% for `application/`, 40% for `infrastructure/`. The Reviewer agent enforces "no decrease" per PR.
- **Property-based tests** (Hypothesis) for value objects with arithmetic or invariants.

## Code review checklist (mechanical)

The Reviewer agent walks every PR through this list:

1. Does each AC have a test that mentions it (`# AC-N: ...`)?
2. Is the diff scoped only to files this ticket should touch?
3. Does the architecture linter pass?
4. Are there `print()` statements left behind? Bare `except:`? `TODO` without ticket link?
5. Are migrations included if models changed?
6. Are docstrings present for public surface (`__init__`, public methods)?
7. Is type coverage at least as strict as the surrounding code?

## What we don't enforce mechanically (yet)

- Cyclomatic complexity (left to Reviewer's judgement for now).
- Per-function length (no magic number).
- Prose docstring style (rough convention is Google-style, but no auto-check).

The Gardener may propose making any of these mechanical when patterns appear in `Failed` tickets.

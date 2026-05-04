# CLAUDE.md

Instructions specific to Claude Code running inside this repo. For general routing, see [AGENTS.md](AGENTS.md).

## Verification — run before proposing closure

Always run the relevant verifier before announcing a ticket as ready:

```bash
./tools/verification/verify_ticket.sh <ticket-id>
```

This wraps the full local pipeline: `ruff check`, `mypy --strict`, the architecture linter, `pytest` for the affected module, and any module-specific checks. If it fails, fix the code — never silence the failure.

For PR-level checks (used by the Reviewer agent):

```bash
./tools/verification/verify_pr.sh <pr-number>
```

## Expected MCP servers

The orchestrator launches Claude Code with these MCPs available. If any is missing, raise a `Question` ticket — do not work around it.

| MCP        | Purpose                                                    |
|------------|------------------------------------------------------------|
| `linear`   | Read/update tickets, post comments, attach files.          |
| `github`   | Create PRs, post review comments, manage labels.           |
| `context7` | Pull current library/framework docs (Django, DRF, asyncua, Playwright, React, Vite). Prefer over web search. |
| `semgrep`  | Security and pattern scans on diffs.                       |

## Hooks active in this repo

Defined in `.claude/settings.json`. Both run automatically — do not edit your code to make them happy without understanding why they fired.

| Hook           | Trigger              | What it checks                                                           |
|----------------|----------------------|--------------------------------------------------------------------------|
| `PostToolUse`  | After Write/Edit     | `ruff check` on the file; architecture linter if it lives in `apps/` or `packages/`. |
| `Stop`         | Before agent closes  | Full `ruff check`, `mypy --strict`, architecture linter, `pytest`.       |

A hook exit code 2 means "feedback for the agent" — read the message and fix the underlying issue.

## Hard rules for the architecture linter

- The linter at `tools/linters/architecture.py` enforces the layer rules in [ARCHITECTURE.md](ARCHITECTURE.md).
- **Bypassing it with `# noqa`, `# type: ignore`, conditional imports inside functions, or `importlib` tricks is forbidden.** If the linter fails, the design is wrong, not the linter.
- If you genuinely believe the rule is incorrect for a specific case, open a `Harness-Fix` ticket proposing a change to the linter or the rule. Do not silence it locally.

## Working agreements

- Touch only the files your ticket scopes. The Reviewer agent rejects diffs that wander.
- Every Acceptance Criterion (AC) in the ticket must have at least one test that mentions it explicitly (e.g., a comment `# AC-1: order can be created with valid product`).
- If the ticket affects UI, attach a Playwright screenshot of the happy path to the Linear ticket via the `linear` MCP.
- Do not create files outside the tree documented in this repo without justifying it in the commit message.
- Migrations: when you touch Django models, generate the migration and commit it in the same PR.

## When to escalate via Consultant

See [docs/workflows/escalation.md](docs/workflows/escalation.md). Short version: irreversible schema decisions, integration changes with external systems, compliance trade-offs, ambiguous specs that docs do not resolve, or conflicts between two `docs/golden-principles.md` rules.

#!/usr/bin/env bash
#
# verify_ticket.sh — run the full local verification pipeline for a ticket
# *before* proposing it as ready/closed. This is the command CLAUDE.md tells
# every agent to run ("./tools/verification/verify_ticket.sh <ticket-id>").
#
# It deliberately mirrors the Stop hook (.claude/hooks/stop.sh) so that what an
# agent runs by hand is exactly what the hook enforces on session close and
# what CI runs on the PR — no drift between the three. Steps (all must pass):
#   1. ruff check .
#   2. mypy --strict          (uses [tool.mypy] config in pyproject.toml)
#   3. tools/linters/architecture.py
#   4. pytest -q
#
# The <ticket-id> argument is required and is echoed for traceability. Module
# scoping of pytest (CLAUDE.md mentions "pytest for the affected module") is a
# deliberate non-goal here: running the full suite is a safe superset that can
# never under-test, and resolving ticket-id -> module requires Linear access
# this offline script must not depend on. A future enhancement may add an
# optional `--module <path>` once that mapping is available locally.
#
# Exit codes:
#   0 — every check is green
#   1 — at least one check failed; stderr names which (fix the underlying
#       cause; bypassing with `# noqa` / `type: ignore` is forbidden — CLAUDE.md)
#   2 — usage error (missing <ticket-id>)
#
# Override hooks (used only by the contract test, default to real behaviour):
#   PY         — Python interpreter to invoke each step with.
#   REPO_ROOT  — repo root to run from.

set -uo pipefail

TICKET_ID="${1:-}"
if [ -z "$TICKET_ID" ]; then
    echo "Usage: tools/verification/verify_ticket.sh <ticket-id>" >&2
    exit 2
fi

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$HOOK_DIR/.." && pwd)}"

# When a Worker runs this inside a per-ticket worktree, REPO_ROOT is the
# worktree path, which doesn't carry its own .venv. Resolve the main checkout
# via git so we find the actual interpreter regardless of cwd (mirrors stop.sh).
GIT_COMMON_DIR="$(cd "$REPO_ROOT" && git rev-parse --git-common-dir 2>/dev/null || echo '')"
if [ -n "$GIT_COMMON_DIR" ]; then
    case "$GIT_COMMON_DIR" in
        /*|?:*) ;;
        *) GIT_COMMON_DIR="$REPO_ROOT/$GIT_COMMON_DIR" ;;
    esac
    MAIN_REPO="$(dirname "$GIT_COMMON_DIR")"
else
    MAIN_REPO="$REPO_ROOT"
fi

cd "$REPO_ROOT"

# --- locate a Python interpreter (prefer the main repo's venv) ---
PY="${PY:-}"
if [ -z "$PY" ]; then
    if [ -x "$MAIN_REPO/.venv/Scripts/python.exe" ]; then
        PY="$MAIN_REPO/.venv/Scripts/python.exe"
    elif [ -x "$MAIN_REPO/.venv/bin/python" ]; then
        PY="$MAIN_REPO/.venv/bin/python"
    elif [ -x ".venv/Scripts/python.exe" ]; then
        PY="$REPO_ROOT/.venv/Scripts/python.exe"
    elif [ -x ".venv/bin/python" ]; then
        PY="$REPO_ROOT/.venv/bin/python"
    else
        PY="$(command -v python3 || command -v python || echo "")"
    fi
fi

if [ -z "$PY" ]; then
    echo "[verify_ticket $TICKET_ID] no Python interpreter found." >&2
    echo "[verify_ticket $TICKET_ID] Run \`uv sync --extra dev\` from the repo root." >&2
    exit 1
fi

echo "[verify_ticket $TICKET_ID] running local verification pipeline..." >&2

failures=0

run_step() {
    local label="$1"; shift
    echo "[verify_ticket $TICKET_ID] $label..." >&2
    if "$@" 1>&2; then
        echo "[verify_ticket $TICKET_ID] $label OK" >&2
    else
        echo "[verify_ticket $TICKET_ID] $label FAILED" >&2
        failures=$((failures + 1))
    fi
}

run_step "ruff check"          "$PY" -m ruff check .
run_step "mypy --strict"       "$PY" -m mypy --strict
run_step "architecture linter" "$PY" tools/linters/architecture.py
run_step "pytest"              "$PY" -m pytest -q

if [ "$failures" -gt 0 ]; then
    echo "" >&2
    echo "[verify_ticket $TICKET_ID] $failures check(s) failed." >&2
    echo "[verify_ticket $TICKET_ID] Fix the underlying issues. Bypassing checks" >&2
    echo "[verify_ticket $TICKET_ID] (\`# noqa\`, \`type: ignore\`, conditional imports," >&2
    echo "[verify_ticket $TICKET_ID] importlib tricks) is forbidden — see CLAUDE.md." >&2
    exit 1
fi

echo "[verify_ticket $TICKET_ID] all checks green." >&2
exit 0

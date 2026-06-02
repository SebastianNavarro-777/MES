#!/usr/bin/env bash
# Ticket-level local verification pipeline for the NSG MES harness.
#
#   ./tools/verification/verify_ticket.sh <ticket-id>
#
# Runs the full local gate so a Worker never proposes a ticket as done with the
# repo red. Mirrors the Stop hook (.claude/hooks/stop.sh) for Python and adds
# the frontend gate (AC-7 of NSG-19):
#   1. ruff check .
#   2. mypy --strict
#   3. tools/linters/architecture.py
#   4. pytest -q
#   5. frontend type-check (strict) + lint   (only if frontend/ exists)
#
# Exit codes:
#   0 — every check green
#   1 — at least one check failed (stderr says which)
set -uo pipefail

TICKET_ID="${1:-<unspecified>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# A Worker runs inside a per-ticket worktree that has no .venv of its own.
# Resolve the main checkout via git to find the interpreter (same trick as
# .claude/hooks/stop.sh).
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

if [ -z "$PY" ]; then
    echo "[verify_ticket $TICKET_ID] no Python interpreter found." >&2
    echo "[verify_ticket $TICKET_ID] Run \`uv sync --extra dev\` from the repo root." >&2
    exit 1
fi

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

# Frontend gate (AC-7). Delegated so the rules live in one place.
if [ -f "$REPO_ROOT/frontend/package.json" ]; then
    run_step "frontend (tsc strict + eslint)" bash "$SCRIPT_DIR/verify_frontend.sh"
fi

if [ "$failures" -gt 0 ]; then
    echo "" >&2
    echo "[verify_ticket $TICKET_ID] $failures check(s) failed. Fix the cause —" >&2
    echo "[verify_ticket $TICKET_ID] bypassing checks is forbidden (see CLAUDE.md)." >&2
    exit 1
fi

echo "[verify_ticket $TICKET_ID] all checks green." >&2
exit 0

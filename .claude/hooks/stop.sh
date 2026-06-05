#!/usr/bin/env bash
# Claude Code Stop hook for the NSG MES harness.
#
# Triggered by .claude/settings.json before the agent finishes its turn.
# Runs the full local pipeline so an agent cannot end a session with the
# repo in a red state. Steps:
#   0. regenerate docs/generated/STATE.md and module-map.md (write steps)
#   1. ruff check .
#   2. mypy --strict   (uses [tool.mypy] config in pyproject.toml)
#   3. tools/linters/architecture.py
#   4. pytest -q
#
# Step 0 keeps STATE.md honest: it is rewritten only when the substantive
# content changed (the timestamp alone never triggers a rewrite), so closing
# a session that touched the tree regenerates the snapshot with no manual
# action — making the DoD box "STATE.md regenerated via hook" mechanically
# true. The generators degrade gracefully (e.g. Linear offline) and only
# return non-zero on a real generator error.
#
# Exit codes:
#   0 — every check is green
#   2 — at least one check failed; stderr describes which (the agent reads
#       this and is expected to fix the underlying cause, NOT to bypass)

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"

# When a Worker spawns claude inside a per-ticket worktree, $REPO_ROOT is
# the worktree path, which doesn't carry its own .venv. Resolve the main
# checkout via git so we find the actual interpreter regardless of cwd.
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
    echo "[stop hook] no Python interpreter found." >&2
    echo "[stop hook] Run \`uv sync --extra dev\` from the repo root." >&2
    exit 2
fi

# Drain stdin without blocking: we don't use the JSON Claude Code passes,
# but if we don't read it some shells emit SIGPIPE on close.
if [ ! -t 0 ]; then
    cat > /dev/null 2>&1 || true
fi

failures=0

run_step() {
    local label="$1"; shift
    echo "[stop hook] $label..." >&2
    if "$@" 1>&2; then
        echo "[stop hook] $label OK" >&2
    else
        echo "[stop hook] $label FAILED" >&2
        failures=$((failures + 1))
    fi
}

# Step 0: regenerate the auto-generated snapshots (write steps, run first so
# the freshly generated docs are present for the rest of the pipeline).
run_step "regenerate STATE.md"     "$PY" -m tools.verification.update_state
run_step "regenerate module-map"   "$PY" -m tools.verification.dump_module_map

run_step "ruff check"          "$PY" -m ruff check .
run_step "mypy --strict"       "$PY" -m mypy --strict
run_step "architecture linter" "$PY" tools/linters/architecture.py
run_step "pytest"              "$PY" -m pytest -q

if [ "$failures" -gt 0 ]; then
    echo "" >&2
    echo "[stop hook] $failures check(s) failed." >&2
    echo "[stop hook] Fix the underlying issues. Bypassing checks (\`# noqa\`," >&2
    echo "[stop hook] \`type: ignore\`, conditional imports, importlib tricks)" >&2
    echo "[stop hook] is forbidden — see CLAUDE.md and ARCHITECTURE.md." >&2
    exit 2
fi

echo "[stop hook] all checks green." >&2
exit 0

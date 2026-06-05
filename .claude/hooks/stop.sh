#!/usr/bin/env bash
# Claude Code Stop hook for the NSG MES harness.
#
# Triggered by .claude/settings.json before the agent finishes its turn.
# Runs the full local pipeline so an agent cannot end a session with the
# repo in a red state. Steps:
#   1. ruff check .
#   2. mypy --strict   (uses [tool.mypy] config in pyproject.toml)
#   3. tools/linters/architecture.py
#   4. pytest -q
#   5. regenerate docs/generated/STATE.md       (write step, NSG-50)
#   6. regenerate docs/generated/module-map.md  (write step, NSG-50)
#
# Steps 5-6 are *write* steps, not verifications: they rewrite the generated
# docs from the working tree so the DoD box "STATE.md se actualizó
# automáticamente vía hook" is mechanically true. They degrade gracefully
# (e.g. Linear unreachable → the Open Questions section is marked unavailable)
# and only count as a failure if the generator itself errors out.
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

run_step "ruff check"          "$PY" -m ruff check .
run_step "mypy --strict"       "$PY" -m mypy --strict
run_step "architecture linter" "$PY" tools/linters/architecture.py
run_step "pytest"              "$PY" -m pytest -q

# Write steps: regenerate the auto-generated docs from the working tree.
# A short --linear-timeout keeps the Stop hook responsive; if Linear is
# unreachable the generator still exits 0 (the section is marked unavailable),
# so these never tip the pipeline red on a network outage.
run_step "regenerate STATE.md"    "$PY" -m tools.verification.update_state --root "$REPO_ROOT" --linear-timeout 4
run_step "regenerate module-map"  "$PY" -m tools.verification.dump_module_map --root "$REPO_ROOT"

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

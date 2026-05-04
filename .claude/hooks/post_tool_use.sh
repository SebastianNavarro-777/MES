#!/usr/bin/env bash
# Claude Code PostToolUse hook for the NSG MES harness.
#
# Triggered by .claude/settings.json after every Write or Edit tool call.
# Reads structured JSON from stdin (the canonical Claude Code hook protocol),
# extracts the modified file path, and runs:
#   - `ruff check` on the file (always, for any .py file)
#   - the architecture linter on the file (only if it lives in apps/ or
#     packages/, since tools/ is exempt from layer rules per ARCHITECTURE.md)
#
# Exit codes:
#   0 — no problem (or file isn't a .py file, or modified file isn't lintable)
#   2 — feedback to the agent (the model sees stderr and is asked to fix)

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# --- locate a Python interpreter (prefer the project venv) ---
if [ -x ".venv/Scripts/python.exe" ]; then
    PY="$REPO_ROOT/.venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
    PY="$REPO_ROOT/.venv/bin/python"
else
    PY="$(command -v python3 || command -v python || echo "")"
fi

if [ -z "$PY" ]; then
    echo "[hook] post_tool_use: no Python interpreter found." >&2
    echo "[hook] Run \`uv sync --extra dev\` from the repo root." >&2
    exit 2
fi

# --- parse the stdin JSON ---
parsed="$("$PY" -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print(data.get("tool_name", ""))
print(data.get("tool_input", {}).get("file_path", ""))
' 2>/dev/null)" || exit 0

tool_name="$(printf "%s" "$parsed" | sed -n '1p')"
file_path="$(printf "%s" "$parsed" | sed -n '2p')"

# Defensive: matcher in settings.json already filters, but tolerate misuse.
case "$tool_name" in
    Write|Edit|MultiEdit) ;;
    *) exit 0 ;;
esac

# Only act on Python source files.
case "$file_path" in
    *.py) ;;
    *) exit 0 ;;
esac

# Make the path relative to the repo root, normalised to forward slashes
# so the bash `case` patterns below match on Windows too.
rel_path="$("$PY" -c '
import os, sys
abs_path = os.path.abspath(sys.argv[1])
root = os.path.abspath(sys.argv[2])
try:
    rel = os.path.relpath(abs_path, root)
except Exception:
    rel = abs_path
print(rel.replace(os.sep, "/"))
' "$file_path" "$REPO_ROOT")"

# --- run ruff on the single file ---
if ! "$PY" -m ruff check "$rel_path" 1>&2; then
    echo "[hook] ruff check failed on $rel_path. Fix the warnings before continuing." >&2
    exit 2
fi

# --- run architecture linter when the file lives in the layered tree ---
case "$rel_path" in
    apps/*|packages/*)
        if ! "$PY" tools/linters/architecture.py "$rel_path" 1>&2; then
            echo "[hook] architecture linter rejected $rel_path." >&2
            echo "[hook] Bypassing the linter is forbidden — see CLAUDE.md and ARCHITECTURE.md." >&2
            exit 2
        fi
        ;;
esac

exit 0

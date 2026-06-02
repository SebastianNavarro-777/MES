#!/usr/bin/env bash
# Frontend verification — AC-7 of NSG-19.
#
# The DoD's `ruff` + `mypy --strict` gates apply to Python. For `frontend/` the
# equivalent quality gate is `tsc --noEmit` in strict mode + ESLint. This script
# runs both and fails (non-zero) on any TypeScript type error or lint error, so
# the ticket-level verifier (verify_ticket.sh) and CI can block on it.
#
# Exit codes:
#   0 — type-check and lint both green (or no frontend present)
#   1 — at least one check failed
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"

if [ ! -f "$FRONTEND_DIR/package.json" ]; then
    echo "[verify_frontend] no frontend/package.json — nothing to check." >&2
    exit 0
fi

# Resolve a pnpm invocation: prefer pnpm on PATH, fall back to Corepack (which
# honours the pinned packageManager in package.json) so CI doesn't need a global
# pnpm install.
if command -v pnpm >/dev/null 2>&1; then
    PNPM=(pnpm)
elif command -v corepack >/dev/null 2>&1; then
    PNPM=(corepack pnpm)
else
    echo "[verify_frontend] neither pnpm nor corepack found on PATH." >&2
    echo "[verify_frontend] Install Node >= 20 and enable Corepack." >&2
    exit 1
fi

cd "$FRONTEND_DIR"

if [ ! -d node_modules ]; then
    echo "[verify_frontend] installing dependencies (frozen lockfile)..." >&2
    if ! "${PNPM[@]}" install --frozen-lockfile 1>&2; then
        echo "[verify_frontend] pnpm install FAILED" >&2
        exit 1
    fi
fi

failures=0

run_step() {
    local label="$1"; shift
    echo "[verify_frontend] $label..." >&2
    if "$@" 1>&2; then
        echo "[verify_frontend] $label OK" >&2
    else
        echo "[verify_frontend] $label FAILED" >&2
        failures=$((failures + 1))
    fi
}

run_step "tsc --noEmit (strict)" "${PNPM[@]}" run typecheck
run_step "eslint"                "${PNPM[@]}" run lint

if [ "$failures" -gt 0 ]; then
    echo "[verify_frontend] $failures frontend check(s) failed." >&2
    exit 1
fi

echo "[verify_frontend] frontend checks green." >&2
exit 0

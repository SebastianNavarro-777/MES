#!/usr/bin/env bash
#
# deploy_staging.sh — build and deploy a given merge SHA to the shared staging
# stand, then verify it is serving. Consumed by QA Smoke (see
# tools/orchestrator/prompts/qa_smoke.md).
#
# LOAD-BEARING OUTPUT CONTRACT (do not change without updating qa_smoke.md):
#   * On success: prints exactly  "staging ready at <url>"  on stdout, exit 0.
#   * On failure: prints a human-readable error on stderr, exits non-zero, and
#     tears the stand down so nothing is left half-started (AC-4).
#   * Idempotent: re-running with the same (or any) SHA resets the stand —
#     fresh DB volume, fixed ports, no leftover containers (AC-7).
#   * A successful deploy completes well under 10 minutes; QA Smoke aborts at
#     10 min and treats it as an infra failure (AC-5).
#
# Usage:
#   tools/verification/deploy_staging.sh <merge-sha>
#
# Build strategy (documented decision): build-from-source. The script extracts
# a snapshot of <merge-sha> with `git archive` into a temp dir and builds the
# images from that snapshot, so the stand runs exactly that commit regardless
# of the working tree. Override hooks (DOCKER/GIT/CURL/REPO_ROOT/SKIP_ARCHIVE)
# exist purely so the behaviour can be unit-tested without a real engine.

set -Eeuo pipefail

# --- Overridable hooks (default to the real binaries / behaviour) ----------
DOCKER="${DOCKER:-docker}"
GIT="${GIT:-git}"
CURL="${CURL:-curl}"

# --- Fixed staging configuration (documented; shared + serialized host) ----
PROJECT_NAME="nsg_mes_staging"
COMPOSE_FILE_NAME="docker-compose.staging.yml"
ENV_FILE_NAME=".env.staging"
ENV_EXAMPLE_NAME=".env.staging.example"
STAGING_HOST="${STAGING_HOST:-localhost}"
STAGING_WEB_PORT="${STAGING_WEB_PORT:-8080}"
STAGING_URL="http://${STAGING_HOST}:${STAGING_WEB_PORT}"
HEALTH_PATH="/healthz"
# Stay safely under QA Smoke's 10-minute abort (AC-5).
DEPLOY_TIMEOUT_SECONDS="${DEPLOY_TIMEOUT_SECONDS:-540}"

# Populated once the build dir exists, so the ERR trap can clean up.
BUILD_DIR=""
COMPOSE_READY=0

log()  { printf '[deploy_staging] %s\n' "$*" >&2; }
err()  { printf '[deploy_staging] ERROR: %s\n' "$*" >&2; }

usage() {
    cat >&2 <<'USAGE'
Usage: deploy_staging.sh <merge-sha>

Builds the given commit and deploys the staging stand (Postgres, Redis,
Django app, React bundle). On success prints "staging ready at <url>".
USAGE
}

# compose <args...> — run docker compose against the staging project/files.
compose() {
    "${DOCKER}" compose \
        -p "${PROJECT_NAME}" \
        -f "${COMPOSE_FILE}" \
        --env-file "${ENV_FILE}" \
        "$@"
}

# teardown — remove the stand's containers, networks and volumes. Best-effort:
# never fails the script (used both for idempotent reset and error cleanup).
teardown() {
    if [ "${COMPOSE_READY}" -eq 1 ]; then
        log "tearing down any existing '${PROJECT_NAME}' stand (containers + volumes) ..."
        compose down --volumes --remove-orphans 1>&2 || true
    fi
}

on_error() {
    local code=$?
    err "deploy failed (exit ${code}). Cleaning up so the next run starts clean."
    teardown
    if [ -n "${BUILD_DIR}" ] && [ -d "${BUILD_DIR}" ]; then
        rm -rf "${BUILD_DIR}" || true
    fi
    exit "${code}"
}
trap on_error ERR

# --- 1. Validate arguments -------------------------------------------------
if [ "$#" -ne 1 ]; then
    err "expected exactly one argument (<merge-sha>), got $#."
    usage
    exit 2
fi
MERGE_SHA="$1"

# --- 2. Resolve repo root --------------------------------------------------
if [ -n "${REPO_ROOT:-}" ]; then
    REPO_ROOT="$(cd "${REPO_ROOT}" && pwd)"
else
    REPO_ROOT="$("${GIT}" rev-parse --show-toplevel)"
fi
log "repo root: ${REPO_ROOT}"

# --- 3. Verify the SHA exists ----------------------------------------------
if ! "${GIT}" -C "${REPO_ROOT}" cat-file -e "${MERGE_SHA}^{commit}" 2>/dev/null; then
    err "merge SHA '${MERGE_SHA}' is not a commit in this repository."
    exit 3
fi

# --- 4. Materialise a snapshot of the SHA (build-from-source) --------------
if [ "${SKIP_ARCHIVE:-0}" = "1" ]; then
    # Test/fast path: build straight from the repo root, no snapshot.
    BUILD_DIR=""
    SOURCE_DIR="${REPO_ROOT}"
    log "SKIP_ARCHIVE=1 → building from working tree at ${SOURCE_DIR}"
else
    BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/nsg-staging-XXXXXX")"
    SOURCE_DIR="${BUILD_DIR}"
    log "extracting snapshot of ${MERGE_SHA} into ${BUILD_DIR} ..."
    "${GIT}" -C "${REPO_ROOT}" archive --format=tar "${MERGE_SHA}" | tar -x -C "${BUILD_DIR}"
fi

COMPOSE_FILE="${SOURCE_DIR}/${COMPOSE_FILE_NAME}"
ENV_FILE="${SOURCE_DIR}/${ENV_FILE_NAME}"
if [ ! -f "${COMPOSE_FILE}" ]; then
    err "compose file not found at ${COMPOSE_FILE}."
    exit 4
fi

# --- 5. Ensure an env file exists (never commit real secrets) --------------
if [ ! -f "${ENV_FILE}" ]; then
    if [ -f "${SOURCE_DIR}/${ENV_EXAMPLE_NAME}" ]; then
        log "no ${ENV_FILE_NAME}; seeding from ${ENV_EXAMPLE_NAME} (staging defaults)."
        cp "${SOURCE_DIR}/${ENV_EXAMPLE_NAME}" "${ENV_FILE}"
    else
        err "neither ${ENV_FILE_NAME} nor ${ENV_EXAMPLE_NAME} present in ${SOURCE_DIR}."
        exit 4
    fi
fi
COMPOSE_READY=1

# --- 6. Idempotent reset: tear down any previous stand ---------------------
teardown

# --- 7. Build + start, waiting for every service to be healthy (AC-1) ------
# Redirect build/up stdout to stderr so the only thing on stdout is the
# final "staging ready at <url>" contract line.
log "building images for ${MERGE_SHA} ..."
compose build 1>&2

log "starting stand (waiting up to ${DEPLOY_TIMEOUT_SECONDS}s for healthy) ..."
compose up -d --wait --wait-timeout "${DEPLOY_TIMEOUT_SECONDS}" 1>&2

# --- 8. Verify the served app answers (AC-3) -------------------------------
log "verifying ${STAGING_URL}${HEALTH_PATH} ..."
if ! "${CURL}" --fail --silent --show-error --max-time 15 "${STAGING_URL}${HEALTH_PATH}" >/dev/null; then
    err "health check against ${STAGING_URL}${HEALTH_PATH} failed."
    exit 5
fi

# --- 9. Success: emit the load-bearing line + a logs hint (AC-6) -----------
# Clean up the snapshot dir (the stand keeps running); ignore failures.
if [ -n "${BUILD_DIR}" ] && [ -d "${BUILD_DIR}" ]; then
    rm -rf "${BUILD_DIR}" || true
fi
trap - ERR

log "logs available via: ${DOCKER} compose -p ${PROJECT_NAME} -f ${COMPOSE_FILE_NAME} logs"
printf 'staging ready at %s\n' "${STAGING_URL}"
exit 0

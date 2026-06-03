---
adr: 0002
title: Staging deploy contract & merging foundational high-risk infra during ramp-up
status: Accepted
date: 2026-06-03
deciders: Sebas (NSG founder)
tags: [infrastructure, ramp-up, qa-smoke, deployment]
---

# 0002 — Staging deploy contract & merging foundational high-risk infra during ramp-up

## Status

Accepted — 2026-06-03.

## Context and problem statement

NSG-22 ("Setup `tools/verification/deploy_staging.sh` + docker-compose staging") delivers the foundational `staging` stand that QA Smoke runs after every merge for the rest of Phase 1 (Epic NSG-14, "Núcleo de órdenes"). The Definition of Done for every Phase-1 Story ends with "QA Smoke pasó en staging", so this stand is load-bearing: every later Story depends on it.

PR #4 introduces three foundational things at once:

1. The **deploy contract** that QA Smoke consumes on every subsequent Story: `deploy_staging.sh <merge-sha>` prints exactly `staging ready at <url>` to stdout and returns exit code 0 on success; non-zero with a readable message on failure; a successful deploy completes in under 10 minutes (QA Smoke treats >10 min as an infra failure).
2. The first minimal deployable Django + React skeleton (the repo was in seed state — 0 bounded contexts, no `docker-compose`, no Dockerfile).
3. `docker-compose.staging.yml` with Postgres, Redis, the Django app and the served React bundle.

The Reviewer agent confirmed **all mechanical verification passes**: the ticket was in `In Review` with all 7 ACs carrying a `# AC-N:` test, CI green 9/9 (ruff, mypy, architecture linter, pytest, secret-scan, CodeQL), module coverage not decreasing from the 0 baseline, and scope authorized by the ticket itself. The Worker reported a real end-to-end deploy (1m29s cold, idempotent re-run).

The only thing holding the merge was the **ramp-up policy**: while fewer than ~30 PRs have merged (repo is in seed state, PRs #4–#8), any `high-risk` merge requires a human eye even when the Reviewer would approve. That policy — not a detected defect — is what triggered the escalation (Question NSG-48).

## Decision drivers

- **Phase-1 throughput.** Every Phase-1 Story ends in "QA Smoke passed in staging." Without this stand merged, the entire phase is blocked.
- **Contract stability.** QA Smoke `grep`s the literal `staging ready at <url>` line and enforces the 10-minute ceiling. The contract must be fixed and not drift without a coordinated update to `tools/orchestrator/prompts/qa_smoke.md`.
- **Ramp-up risk posture.** Foundational infra is exactly the class of `high-risk` change ramp-up is meant to gate; but full mechanical verification plus a reported real deploy is strong evidence.
- **Reversibility.** A deploy script and compose file are revisable; the *contract strings and exit-code semantics* are the hard-to-reverse part, because downstream consumers couple to them.

## Considered options

### A) Merge now (squash + delete branch) ← **chosen**

Pros:
- Unblocks QA Smoke and the whole of Phase 1 immediately.
- Fixes the deploy contract so downstream Stories can rely on it.
- Trusts the complete mechanical verification plus the Worker's reported real end-to-end deploy, which is the appropriate evidence bar for foundational infra.

Cons:
- Accepts a `high-risk` merge during ramp-up on Reviewer approval plus a single reported deploy, rather than a second independent environment validation.

### B) Merge with conditions

Pros:
- Reduces future drift risk (e.g. require `verify_pr.sh` / `verify_ticket.sh` to exist first, or freeze the contract chain explicitly in `qa_smoke.md` before merging).

Cons:
- Delays the unblock of Phase 1 for conditions that can be tracked as follow-up tickets rather than merge blockers.

### C) Do not merge yet

Pros:
- Maximum caution: wait for the minimal Phase-1 backend, or validate the stand on an environment other than the reference laptop.

Cons:
- Blocks all of Phase 1 with no defect identified to justify the hold.

## Decision outcome

**Option A — merge PR #4 now (squash + delete branch).** Mechanical verification passes in full, scope is authorized by the ticket, and the Worker reports a successful real end-to-end deploy (1m29s cold, idempotent re-run). The only brake was the ramp-up `high-risk` policy, not a detected defect; Sebas exercised the human gate and approved.

This decision also establishes two things going forward:

- The **staging deploy contract is now fixed and load-bearing**: the literal stdout line `staging ready at <url>`, exit code 0 on success / non-zero on failure, and the 10-minute success ceiling. It MUST NOT change without a coordinated update to `tools/orchestrator/prompts/qa_smoke.md` in the same PR.
- During ramp-up, a **foundational `high-risk` infrastructure PR may be merged on the human gate when all three hold**: (1) mechanical verification passes in full, (2) scope is authorized by the ticket, and (3) a real end-to-end deploy is reported. This is the evidence bar Sebas accepted here.

### Positive consequences

- QA Smoke and all of Phase 1 are unblocked.
- The deploy contract downstream Stories couple to is now stable and documented.
- A clear, repeatable evidence bar exists for human-gating foundational infra during ramp-up.

### Negative consequences

- The contract strings/semantics are now hard to reverse; changing them requires a coordinated update across `deploy_staging.sh` and `qa_smoke.md`.
- The stand was validated on the reference laptop only; a second environment has not yet exercised it.

## Pros and cons summary

Option A wins because there was no defect to justify holding all of Phase 1 — only the ramp-up policy, which Sebas resolved by exercising the human gate. The contract-stability and second-environment-validation concerns from B/C are real but are better handled as follow-up discipline (the frozen contract recorded here, plus future verification tooling) than as merge blockers.

## Links

- Source decision: Question ticket NSG-48 — <https://linear.app/nsg-engineering/issue/NSG-48>.
- Blocking Story: NSG-22 — <https://linear.app/nsg-engineering/issue/NSG-22>; PR #4 — <https://github.com/SebastianNavarro-777/MES/pull/4>.
- Phase-1 Epic: NSG-14 — <https://linear.app/nsg-engineering/issue/NSG-14>.
- QA Smoke contract consumer: `tools/orchestrator/prompts/qa_smoke.md`.
- Ramp-up gate: `tools/orchestrator/prompts/reviewer.md` (step 8).

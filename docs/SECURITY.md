---
title: Security — controls and threat model
status: living
last_updated: 2026-06-01
---

# SECURITY

Security baseline for any MES deployment. Sections marked _living_ are
actively enforced; sections marked _skeleton_ are doctrine that will be
codified as the relevant phase lands.

## Authentication

- Django sessions (cookie-based) for the web UI.
- DRF token auth for service-to-service and mobile.
- TOTP-based 2FA for `supervisor` and `admin` roles in production.

## Authorization

- Django groups + permissions; one group per role (`operator`, `supervisor`, `admin`, `quality_inspector`, `maintenance_tech`).
- Object-level permissions where needed (e.g., a quality inspector can only close NCRs they opened).

## Audit log

Mandatory for every model marked `compliance_relevant = True` (per `golden-principles.md` GP-009). Includes actor, timestamp, before-state, after-state, reason.

## Secrets management

- `SECRET_KEY`, DB credentials, OPC-UA passwords: environment variables in development; vault (HashiCorp Vault, AWS Secrets Manager, or per-customer equivalent) in production.
- **Pre-commit / pre-PR scanning (live):**
  - `.claude/hooks/post_tool_use.sh` — runs on every Worker `Write`/`Edit`. Greps for `ghp_…`, `github_pat_…`, `lin_api_…`, `AKIA…`, Slack `xox[baprs]-…`, and PEM `BEGIN … PRIVATE KEY` blocks. Allowlists `.env.example`, `docs/`, and the hooks dir. Exits 2 → agent fixes before the commit even happens.
  - `.github/workflows/security.yml` — `gitleaks` runs on every push to `main` and on every PR; full-history scan. Belt-and-suspenders with the local hook.
- Rotated quarterly minimum. If a leak is detected (hook or CI), **rotate first, fix the code second**.

## Transport

- TLS 1.2+ everywhere external-facing.
- Internal services may use plain TCP if on a customer's segregated VLAN; documented per deployment.

## Input validation

- DRF serializers validate at the boundary.
- Domain constructors re-validate (defence in depth).
- File uploads: size cap, MIME sniff (not just extension), antivirus scan if present in the customer's stack.

## OWASP Top 10 baseline

The Reviewer agent (with help from the `semgrep` MCP) checks for: SQLi (`raw()`, `extra()`), XSS (autoescape off), insecure deserialisation (`pickle` from external), SSRF (URL fetches without allowlist), open redirects.

## Supply chain (live)

The repo enforces four mechanical controls against malicious or vulnerable dependencies:

| Control | Where | What it does |
|---|---|---|
| Hash-pinned lockfile | `uv.lock` committed + `uv sync --frozen` in CI | Prevents tampering. If `uv.lock` and the installed deps don't match, CI fails. |
| CVE scanner | `security-audit` job in `.github/workflows/ci.yml` (`pip-audit`) | Fails the build if any installed package has a known CVE in the PyPI Advisory DB. |
| Dependency updates | `.github/dependabot.yml` (pip + github-actions, weekly) | Auto-opens PRs to bump out-of-date deps and Actions versions. Reviewer processes them like any harness PR. |
| License gate | `license-check` job in CI (`pip-licenses`) | Rejects `AGPL`, `GPL`, `LGPL` deps — they would contaminate the commercial distribution. |

When the frontend lands (NSG-6 in the seed), the same controls are extended to `pnpm`/`npm` via the corresponding Dependabot ecosystem and an npm-audit step.

## Static analysis (live)

- **CodeQL** (`.github/workflows/codeql.yml`) — `security-extended` query pack runs on every PR and weekly on `main`. Catches taint flows, crypto misuse, command injection.
- **`semgrep` MCP** — per the Worker prompt, runs on the diff before opening the PR. Catches SQLi via `raw()`/`extra()`, autoescape-off XSS, `pickle` on external input, SSRF on URL fetches, open redirects.
- **`ruff`** — surface-level (no `print()` left behind, no bare `except`, no `pickle` import without a paired `# noqa: <ticket>`).

## Threat model (high level)

| Asset | Threat | Mitigation |
|---|---|---|
| Audit log | Tampering by privileged user | DB-level `REVOKE UPDATE/DELETE` on the role used by the app; access via stored procedure for `admin` only. |
| Production credentials | Leak via repo | PostToolUse hook (local) + `gitleaks` CI (push + PR). |
| OPC-UA channel | MITM on plant network | TLS-equivalent in OPC-UA (Basic256Sha256). |
| Supply chain | Malicious / vulnerable dependency | `uv` hash-pinned lock + `pip-audit` in CI + Dependabot weekly + `pip-licenses` AGPL/GPL gate. |
| Application code | SAST-detectable bug class | CodeQL `security-extended` weekly + on PR; semgrep MCP pre-PR by the Worker. |

## SBOM (skeleton)

CycloneDX SBOM generation will be added when the first compliance audit is on the calendar (likely Phase 4 — quality/NCR module). Until then `uv.lock` + the CI artefacts of `pip-audit` and `pip-licenses` give a reproducible bill of materials.

## Incident response

Runbook lives in this file once the first deployment exists and a SecOps point of contact is assigned. Until then, the rotation playbook for a leaked credential is:

1. Revoke the credential at the source (Linear, GitHub, AWS) — minutes, not hours.
2. Issue a replacement and update `.env` on every machine that uses it.
3. Open a `Harness-Fix` ticket describing how the leak got past the hook + gitleaks so the Gardener can tighten the rules.

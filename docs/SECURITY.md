---
title: Security — controls and threat model
status: skeleton
last_updated: 2026-05-04
---

# SECURITY

Security baseline for any MES deployment. Skeleton — populated as features land.

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
- `git-secrets` (or equivalent) hook in `.claude/hooks/post_tool_use.sh` blocks accidental commits of high-entropy strings — TODO Phase 4.
- Rotated quarterly minimum.

## Transport

- TLS 1.2+ everywhere external-facing.
- Internal services may use plain TCP if on a customer's segregated VLAN; documented per deployment.

## Input validation

- DRF serializers validate at the boundary.
- Domain constructors re-validate (defence in depth).
- File uploads: size cap, MIME sniff (not just extension), antivirus scan if present in the customer's stack.

## OWASP Top 10 baseline

The Reviewer agent (with help from the `semgrep` MCP) checks for: SQLi (`raw()`, `extra()`), XSS (autoescape off), insecure deserialisation (`pickle` from external), SSRF (URL fetches without allowlist), open redirects.

## Threat model (high level)

| Asset | Threat | Mitigation |
|---|---|---|
| Audit log | Tampering by privileged user | DB-level `REVOKE UPDATE/DELETE` on the role used by the app; access via stored procedure for `admin` only. |
| Production credentials | Leak via repo | Pre-commit hook + secret scanner. |
| OPC-UA channel | MITM on plant network | TLS-equivalent in OPC-UA (Basic256Sha256). |
| Supply chain | Malicious dependency | `uv` with hash-pinned lock; `pnpm` with frozen-lockfile in CI. |

## Incident response

Runbook lives in this file once the first deployment exists and a SecOps point of contact is assigned.

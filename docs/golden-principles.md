---
title: Golden principles
description: Mechanical, machine-checkable rules that every agent must respect. Evolves over time via Gardener PRs.
audience: every agent (read on every session).
last_updated: 2026-05-04
---

# Golden principles

These are **mechanical** rules — small, specific, machine-checkable when possible. The Gardener agent adds new principles when failures recur; the human (Sebas) reviews Gardener's PRs.

Every principle has the same shape: **rule**, **rationale**, **enforcement**.

---

### GP-001: Domain layer is framework-agnostic

The `domain/` layer (`packages/domain/`, `packages/shared/`, `apps/*/domain/`) MUST NOT import Django, DRF, httpx, asyncua, Celery, Redis, Pydantic, SQLAlchemy, or any third-party package. Pure Python + stdlib only.

**Rationale:** lets the same domain logic be reused in CLI tools, async workers, Playwright tests, and unit tests without framework setup. Forces business rules to be expressible without ORM idioms.

**Enforcement:** `tools/linters/architecture.py` (Phase 3 of bootstrap).

---

### GP-002: Money as integer cents

Never store or compute monetary values as `float`. Use `int` for cents, or `decimal.Decimal` when fractional units are needed (e.g., currencies with > 2 decimals). Convert to a display string only at the interface layer.

**Rationale:** `float` arithmetic introduces silent precision errors that compound across thousands of records.

**Enforcement:** Reviewer agent (mypy-checkable when types are precise).

---

### GP-003: Datetimes are timezone-aware UTC

Every `datetime` stored, transmitted, or logged is timezone-aware (`tzinfo=UTC`). Naive datetimes are rejected at boundaries (deserialisation, ORM `.save()`).

**Rationale:** plants with multi-shift operations across timezones, plus daylight saving transitions, make naive datetimes silently wrong.

**Enforcement:** Django `USE_TZ=True`; runtime assertion in domain constructors; mypy with `--strict-equality` flags comparisons of aware vs. naive.

---

### GP-004: No shared mutable state across requests

Module-level mutable state (`global` lists/dicts that accept writes after import) is forbidden. Use Django settings, dependency injection, or per-request caches.

**Rationale:** Celery workers, Django dev server, and Gunicorn each have different lifecycles. Shared mutable state behaves differently in each, causing heisenbugs.

**Enforcement:** Reviewer agent flags writes to module-level mutables. Future linter check.

---

### GP-005: Traceability events are immutable

Records in `apps/traceability/` and any audit log are append-only. There is no UPDATE or DELETE on these tables — only INSERT.

**Rationale:** regulatory compliance (21 CFR Part 11, IATF 16949) requires demonstrable immutability. A "fix" is a new event that supersedes, not a mutation.

**Enforcement:** Django model uses a custom manager that raises on `.update()` and `.delete()`; database-level grants prevent the app role from running UPDATE/DELETE on those tables in production.

---

### GP-006: OEE always at the equipment level

OEE is computed per equipment, per period (shift / day). Plant-level or line-level OEE is **always** an aggregation of equipment-level results — never computed directly from plant-wide totals.

**Rationale:** plant-wide OEE without per-equipment breakdown hides the bottleneck and is operationally useless.

**Enforcement:** `oee.compute_oee()` signature requires `equipment_id`; aggregation views are explicit.

---

### GP-007: All PLC reads/writes are async

Every interaction with `asyncua` (or any PLC library) happens inside an `async def` and uses `await`. No `asyncio.run()` inside synchronous code paths.

**Rationale:** PLC connections are slow, occasionally hang, and need supervised reconnection. Sync calls block Django request threads or Celery workers and cascade into outages.

**Enforcement:** Reviewer agent flags sync OPC-UA calls; `tools/linters/architecture.py` rejects `asyncio.run` outside `__main__` blocks.

---

### GP-008: Idempotency keys on every integration endpoint

Any endpoint that ingests data from an external system (ERP, SCADA, IoT, webhook) requires a client-supplied `idempotency_key`. The handler stores it and returns the cached response on repeat.

**Rationale:** networks are unreliable; clients retry. Without idempotency, a retried ERP confirmation creates a duplicate consumption record.

**Enforcement:** Reviewer agent rejects new public ingestion endpoints without an `idempotency_key` field. Schema check in `apps/*/interface/` tests.

---

### GP-009: Audit log mandatory for compliance entities

Any model declared `compliance_relevant = True` (mixin) MUST have an audit log entry created on every CREATE/UPDATE/SOFT-DELETE. Includes actor, timestamp, before-state, after-state, reason.

**Rationale:** 21 CFR Part 11 and IATF 16949 require a complete trail. Implementing this case-by-case forgets edge cases — make it mechanical.

**Enforcement:** Mixin emits a Django `pre_save`/`pre_delete` signal that writes the audit row in the same transaction. Test fixtures verify a model with the mixin cannot be saved without an audit entry.

---

### GP-010: No string literals for enumerated states

Ticket states, order states, NCR states, etc. are `enum.StrEnum` or `models.TextChoices`. Comparing to bare string literals (`if order.status == "released"`) is rejected.

**Rationale:** typos compile fine and break silently. Enums make the set of valid states discoverable by IDE and refactor-safe.

**Enforcement:** Reviewer agent flags string-literal comparisons in conditionals. Future ruff custom rule.

---

### GP-011: Tests required for every new domain entity

A PR that adds a new class in `apps/*/domain/` or `packages/domain/` MUST also add a test file at `apps/*/domain/tests/test_<entity>.py` covering construction, invariants, and at least one state transition.

**Rationale:** domain logic without tests rots. Domain is the highest-leverage layer; bugs here propagate everywhere.

**Enforcement:** Reviewer agent checks that the diff adds matching test files. Future hook in `.claude/hooks/post_tool_use.sh`.

---

### GP-012: Exception class per bounded context

Each context defines `apps/<context>/domain/exceptions.py` with at minimum a base exception (`<Context>DomainError`) and specific subclasses. Use these, never raise built-ins (`ValueError`, `RuntimeError`) from domain code.

**Rationale:** specific exceptions let the application layer translate them into precise HTTP status codes and event types. Bare `ValueError` is unactionable.

**Enforcement:** Reviewer agent flags `raise ValueError` / `raise RuntimeError` in `domain/` and `application/` layers.

---

### GP-013: High-risk harness PRs merge only with CI-proven safety on a rebased branch

A PR labeled `high-risk` that modifies a harness pipeline file — the Stop / PostToolUse hooks (`.claude/hooks/*`) or any `tools/verification/*` script those hooks invoke — MUST NOT be merged during ramp-up until: (1) **CI** (not just a local run) demonstrates the hook degrades gracefully — no hang and no failure — when an external dependency (network, Linear, git remote) is unavailable; (2) **CI** demonstrates idempotency — consecutive runs on an unchanged tree produce no spurious diff churn (e.g. timestamp-only rewrites); and (3) the branch is **rebased on `main`** (not `BEHIND`) immediately before the merge.

**Rationale:** harness hooks run on every agent session close, so their blast radius is every future session. A hook that hangs, fails, or dirties the diff would degrade every Worker run. A local green is insufficient evidence for that blast radius — CI must prove both the no-dependency degradation path and the no-churn idempotency before the change lands.

**Example:** NSG-50's PR #23 regenerates `STATE.md` / `module-map.md` via the Stop hook. All mechanical checks passed locally and CI was 9/9, but because the PR is `high-risk` and touches `.claude/hooks/stop.sh`, the merge was gated until CI evidence proved AC-7 (no-network degradation) and no timestamp churn on consecutive runs, and the `BEHIND` branch was rebased on `main`.

**Source:** [NSG-53](https://linear.app/nsg-engineering/issue/NSG-53).

**Enforcement:** Reviewer agent — during ramp-up, blocks the merge of a `high-risk` PR touching harness hook files until the CI logs show the degradation + idempotency evidence and the branch is not `BEHIND` `main`.

---

## How this file evolves

- The Gardener agent proposes new principles via PR after observing patterns in `Failed` tickets and closed `Harness-Fix`s.
- Sebas reviews and merges (or rejects) Gardener PRs. No agent merges to this file unilaterally.
- Numbering is permanent: never renumber, never reuse numbers. Removed principles get marked `### GP-NNN: [retired YYYY-MM-DD]` with a brief reason.

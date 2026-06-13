---
adr: 0002
title: High-risk PRs during ramp-up require explicit human approval before merge
status: Accepted
date: 2026-06-13
deciders: Sebas (NSG founder)
tags: [process, ramp-up, review, merge-policy]
---

# 0002 — High-risk PRs during ramp-up require explicit human approval before merge

## Status

Accepted — 2026-06-13.

## Context and problem statement

The system is in **ramp-up** (3 of the first 30 PRs merged). During ramp-up,
the Reviewer agent's mechanical approval is not sufficient on its own for any PR
labelled `high-risk`: the ramp-up safeguard asks for a human eye before the
merge, even when every automated check is green.

The concrete trigger was [NSG-16](https://linear.app/nsg-engineering/issue/NSG-16)
(scaffold the `orders` bounded context with base domain models), whose
[PR #16](https://github.com/SebastianNavarro-777/MES/pull/16) was labelled
`high-risk`. The Reviewer ran the full mechanical checklist and everything
passed — all 7 ACs had annotated tests, CI was 100% green (ruff, `mypy --strict`,
`pytest` 238 passed, architecture linter, CodeQL, gitleaks, pip-audit, license
check), the diff was scoped to `apps/orders/**` plus two `pyproject.toml` lines,
and the change is **pure domain** (stdlib only: a frozen `ManufacturingOrder`
dataclass, the `OrderStatus` `StrEnum`, a linear state-machine helper, and the
`OrdersDomainError` hierarchy). No persisted schema, no integrations, no auth,
no events, no REST endpoints. The technical blast radius is low and reversion is
cheap.

Despite the low technical risk, the `high-risk` label plus ramp-up meant the
Reviewer escalated rather than auto-merging. This was the **third** PR in the
same pattern: [NSG-48](https://linear.app/nsg-engineering/issue/NSG-48) (staging
stand, resolved per-PR) and [NSG-51](https://linear.app/nsg-engineering/issue/NSG-51)
(license gate, escalated) preceded it. None of them had been codified into a
reusable rule, so each new equivalent PR keeps escalating.

The question raised to Sebas ([NSG-52](https://linear.app/nsg-engineering/issue/NSG-52)):
should PR #16 be merged now, or held until explicit human approval, given the
ramp-up state? — and, implicitly, should pure-domain scaffolds be exempted from
the gate going forward?

## Decision drivers

- **Ramp-up safety.** Early in a project, a wrong merge can set bad precedents
  that propagate; a human gate on `high-risk` PRs catches what mechanical checks
  cannot.
- **Throughput.** NSG-16 is the foundation of the Phase 1 vertical slice; holding
  it blocks [NSG-39](https://linear.app/nsg-engineering/issue/NSG-39) and the rest
  of the orders core.
- **Consistency with precedent.** NSG-48 and NSG-51 were both handled as per-PR
  human decisions, not as a blanket auto-exemption.
- **Auditability.** "A human reviewed this" is not a machine-checkable property,
  so the gate cannot simply become a linter rule.

## Considered options

### A) Approve and merge now (squash-merge + delete branch) ← **chosen (via human review)**

Pros:
- Unblocks NSG-39 and the rest of the orders core.
- The change is pure domain with no schema/integration/auth — low reversion risk.

Cons:
- If merged purely on mechanical approval, it would skip the ramp-up human gate
  for a `high-risk` ticket.

### B) Hold the PR unmerged until explicit human approval

Pros:
- Respects the ramp-up safeguard and the NSG-48 / NSG-51 pattern.

Cons:
- Delays unblocking NSG-39 and dependent Stories until a human responds.

## Decision outcome

**Option A, satisfied by Option B's safeguard.** Sebas reviewed PR #16 himself
and instructed: *"Ya lo revisé, mérgalo"* ("I already reviewed it, merge it").
The PR is **approved for merge** (squash-merge + delete branch).

Crucially, the gate was **exercised, not waived**: Sebas provided the human eye
that the ramp-up safeguard requires, then approved. He did **not** create a
standing exemption for pure-domain scaffolds. Therefore:

- **The ramp-up human gate for `high-risk` PRs stands.** During ramp-up, a
  `high-risk` PR is merged only after explicit human approval, even when all
  mechanical checks pass. The Reviewer continues to escalate such PRs as
  `Question` tickets rather than auto-merging.
- **No auto-exemption for pure-domain scaffolds.** "Pure domain, stdlib only" is
  not by itself grounds to skip the gate; the human decides per-PR, consistent
  with NSG-48 and NSG-51.
- This policy is scoped to **ramp-up**. It can be revisited (and likely relaxed)
  once the project exits ramp-up.

### Positive consequences

- A human continues to catch risks that mechanical checks miss while the project
  is young.
- The precedent set by NSG-48 / NSG-51 / NSG-52 is now recorded, so future
  reviewers and resolvers have an explicit reference instead of re-deriving it.
- NSG-16 / PR #16 are unblocked and can be merged.

### Negative consequences

- Each `high-risk` PR during ramp-up still incurs a human round-trip, even for
  low-blast-radius changes like pure-domain scaffolds. This is accepted cost for
  the duration of ramp-up.
- The gate is not machine-enforceable, so it relies on the Reviewer's discipline
  to escalate rather than auto-merge.

## Links

- Source question: [NSG-52](https://linear.app/nsg-engineering/issue/NSG-52).
- Blocking Story: [NSG-16](https://linear.app/nsg-engineering/issue/NSG-16) /
  [PR #16](https://github.com/SebastianNavarro-777/MES/pull/16).
- Cascade: [NSG-39](https://linear.app/nsg-engineering/issue/NSG-39).
- Precedent: [NSG-48](https://linear.app/nsg-engineering/issue/NSG-48),
  [NSG-51](https://linear.app/nsg-engineering/issue/NSG-51).
- Escalation rules: [docs/workflows/escalation.md](../workflows/escalation.md).

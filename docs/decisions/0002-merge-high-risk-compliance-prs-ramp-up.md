---
adr: 0002
title: High-risk + compliance PRs merge only after explicit human approval during ramp-up
status: Accepted
date: 2026-06-13
deciders: Sebas (NSG founder)
tags: [harness, ramp-up, compliance, workflow]
---

# 0002 — High-risk + compliance PRs merge only after explicit human approval during ramp-up

## Status

Accepted — 2026-06-13.

## Context and problem statement

The harness is in **ramp-up** (only 3 of the first 30 PRs merged). During ramp-up the
agents are not yet trusted to merge unsupervised, and a safeguard requires a human to
look at any PR labelled **`high-risk`** and touching **compliance** surfaces before it
lands.

The trigger was PR [SebastianNavarro-777/MES#15](https://github.com/SebastianNavarro-777/MES/pull/15)
for [NSG-46](https://linear.app/nsg-engineering/issue/NSG-46), which scopes the CI
license gate to **runtime** dependencies only — leaving the copyleft `--fail-on` list
(AGPL/GPL/LGPL, all `-only`/`-or-later` variants) fully intact, and keeping the dev-only
tool `yamllint` declared in the `dev` dependency group. The Reviewer ran the full
mechanical checklist (checks 1–7 passed: CI green including the License check job, all 6
ACs have an annotated test, the architecture linter is clean, the diff is scoped to
`module:harness`, no domain-glossary clashes). Because the PR is `high-risk` **+**
compliance, the Reviewer escalated rather than auto-merging — exactly as the precedent
[NSG-48](https://linear.app/nsg-engineering/issue/NSG-48) (PR for [NSG-22](https://linear.app/nsg-engineering/issue/NSG-22),
staging stand) had been handled: a per-PR human decision, not a codified rule.

The question raised in [NSG-51](https://linear.app/nsg-engineering/issue/NSG-51): merge
PR #15 now, or hold it until explicit human approval, given ramp-up?

## Decision drivers

- **Irreversibility of compliance mistakes.** Weakening copyleft protection on
  distributed software — even unintentionally — is hard to reverse once merged and
  propagated. It warrants human eyes during ramp-up.
- **Cost of holding.** Keeping PR #15 unmerged keeps CI red on every other PR and blocks
  [NSG-40](https://linear.app/nsg-engineering/issue/NSG-40), which waits on CI returning
  to green.
- **Consistency with precedent.** NSG-48 established that high-risk PRs during ramp-up
  get a human decision before merge. The pattern should stay consistent.
- **The change does not weaken the gate.** It only narrows the *audited set* to runtime
  deps; the prohibited-licence list is untouched, and a runtime copyleft dependency still
  fails the job (AC-4/AC-5).

## Considered options

### A) Approve and merge PR #15 now (squash-merge) ← **chosen**

Pros:
- Unblocks [NSG-40](https://linear.app/nsg-engineering/issue/NSG-40) and returns CI to
  green for every other PR.
- The change was pre-authorised by the Architect (option A of NSG-46) and does not weaken
  the distributed-software copyleft protection — only the audited set is narrowed.
- Human review still happened: the safeguard ran (escalate → human looks → approve), it
  was not bypassed.

Cons:
- Lands a compliance-labelled change; relies on the human having actually reviewed it
  (Sebas confirmed he did).

### B) Hold PR #15 until explicit human approval

Pros:
- Maximally conservative; mirrors NSG-48 literally.

Cons:
- Redundant once the human has already reviewed and approved — holding longer adds no
  safety, only delay.
- Keeps CI red and [NSG-40](https://linear.app/nsg-engineering/issue/NSG-40) blocked.

## Decision outcome

**Option A.** Sebas reviewed PR #15 himself and approved the merge ("merge it now, I've
already looked and I'm fine with it being merged"). PR #15 / [NSG-46](https://linear.app/nsg-engineering/issue/NSG-46)
proceeds to squash-merge from `In Review`.

This confirms the ramp-up criterion for **high-risk + compliance** PRs: agents do **not**
auto-merge them; the Reviewer escalates a `Question`, a human reviews, and the merge
proceeds **only** on explicit human approval. Approval is per-PR — this ADR does not
pre-authorise future high-risk + compliance merges; each still requires its own human
decision while ramp-up is in effect.

### Positive consequences

- [NSG-40](https://linear.app/nsg-engineering/issue/NSG-40) is unblocked and CI returns
  to green across open PRs.
- The escalate → human-review → approve pattern is now documented, consistent with
  NSG-48, so future Reviewers and Resolvers have a reference instead of re-deriving it.
- The copyleft gate stays intact; only the audited dependency set was narrowed.

### Negative consequences

- The safeguard remains manual (human-in-the-loop) — it costs Sebas a review per
  high-risk + compliance PR during ramp-up. Accepted as the price of safety until the
  harness earns more autonomy.
- This is per-PR; it does not generalise into a mechanical rule the linters can enforce,
  so the criterion lives in docs and Reviewer behaviour, not in code.

## Links

- Source Question: [NSG-51](https://linear.app/nsg-engineering/issue/NSG-51).
- Blocking ticket: [NSG-46](https://linear.app/nsg-engineering/issue/NSG-46) — scope license gate to runtime deps.
- PR: [SebastianNavarro-777/MES#15](https://github.com/SebastianNavarro-777/MES/pull/15).
- Precedent: [NSG-48](https://linear.app/nsg-engineering/issue/NSG-48) (PR for [NSG-22](https://linear.app/nsg-engineering/issue/NSG-22), staging stand).
- Downstream unblocked: [NSG-40](https://linear.app/nsg-engineering/issue/NSG-40).
- Escalation rules: [docs/workflows/escalation.md](../workflows/escalation.md).

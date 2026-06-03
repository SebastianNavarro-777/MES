---
adr: 0002
title: Architect phase-gating cadence — wait when the active phase is fully decomposed
status: Accepted
date: 2026-06-03
deciders: Sebas (NSG founder)
tags: [orchestration, architect, roadmap, cadence]
---

# 0002 — Architect phase-gating cadence: wait when the active phase is fully decomposed

## Status

Accepted — 2026-06-03.

Resolves Question [NSG-47](https://linear.app/nsg-engineering/issue/NSG-47/fase-1-totalmente-descompuesta-y-en-curso-el-architect-espera-o-se).

## Context and problem statement

The orchestrator's trigger dispatcher fires the **Architect agent** to generate backlog
whenever the count of issues in the `Backlog` state falls below
`ARCHITECT_BACKLOG_THRESHOLD` (default 5).

On 2026-06-03 this produced an **empty start**: Phase 1 of the `ROADMAP.md` was already
fully decomposed into 3 Epics (NSG-14 orders/REST/frontend, NSG-23 auth/roles, NSG-32 WIP)
and ~25 Stories, all in flight (`Ready for Agent` / `Blocked` / `In Review`) and none in
`Done`. Because healthy Stories had already advanced out of `Backlog`, only the 3 Epics
remained in that state — a count of 3 < 5 — so the Architect was triggered with no
legitimate work to create.

Two failure paths were available to the Architect in that moment:

1. Create a redundant Phase 1 Epic → duplicates existing scope and pollutes the backlog.
2. Pre-arm a Phase 2 (Traceability) Epic → violates the roadmap rule that no Stories exist
   outside the active phase until Phase 1 is `Done` and human-approved.

We need a durable doctrine for what the Architect does when the active phase is already
decomposed and in flight, plus a fix so the trigger stops misfiring on a low `Backlog`-state
count alone.

## Decision drivers

- **Roadmap discipline.** No Stories outside the active phase until the active phase is
  `Done` and explicitly approved by the human. Pre-arming future phases is irreversible noise.
- **Backlog hygiene.** A redundant Epic confuses the Worker and inflates apparent scope.
- **Signal quality.** `Backlog`-state count is a poor proxy for "work remaining"; a healthy,
  fully-decomposed phase in execution reads as "backlog exhausted" and triggers empty starts.
- **No human saturation.** The Architect must not generate spurious work that a human then
  has to triage away.

## Considered options

### A) Wait — create no Epic ← **chosen**

The Architect treats a low `Backlog` count as a spurious signal when the active phase is
fully decomposed and in flight. It creates nothing and retries on the next window.

Pros:
- Respects the roadmap and keeps the backlog clean.
- Zero risk of duplicate scope or premature phase opening.

Cons:
- On its own, the Architect keeps being triggered into a no-op until the trigger is fixed
  (addressed by option C).

### B) Open Phase 2 (Traceability) now

Begin decomposing Phase 2 immediately.

Pros:
- Pre-arms downstream work.

Cons:
- Violates the "no Stories outside the active phase" roadmap rule.
- Requires explicit human approval of a phase change that has not been given.
- Phase 1 is not yet `Done`.

### C) Adjust the trigger (Harness-Fix) ← **also chosen, delegated**

Make the threshold count in-flight unfinished Stories (all states except `Done`/`Failed`),
not just the `Backlog` state, so a fully-decomposed phase no longer reads as empty.

Pros:
- Removes the root cause of empty starts.
- Keeps the existing positive case (genuinely low backlog still fires the Architect).

Cons:
- Code change in `tools/orchestrator/`; tracked and verified as its own ticket.

## Decision outcome

**Options A and C, together.**

1. **A — Wait, create no Epic.** When the active phase is fully decomposed and its Stories
   are in flight (none in `Done`), the Architect creates no new Epic. It does not pre-arm a
   future phase. A future phase is decomposed only after the active phase is `Done` and the
   human has explicitly approved the phase transition. A low `Backlog`-state count, by itself,
   is not authorization to generate work.

2. **C — Fix the trigger.** The Architect trigger must measure in-flight unfinished Stories
   (every `TicketState` except `Done` and `Failed`), not just the `Backlog` state, and must
   not count Epics as missing backlog. This mechanical work is delegated to the Harness-Fix
   ticket [NSG-49](https://linear.app/nsg-engineering/issue/NSG-49/architect-trigger-misfires-when-phase-is-fully-decomposed-count-in)
   (already `Ready for Agent`); this ADR records the accepted intent, not the implementation.

Option B is rejected: pre-arming Phase 2 is forbidden until Phase 1 is `Done` and approved.

### Positive consequences

- The Architect no longer duplicates scope or opens phases early.
- The backlog stays a faithful picture of the active phase.
- Empty starts disappear once NSG-49 lands; until then the Architect safely no-ops.
- Phase transitions remain a deliberate, human-gated event.

### Negative consequences

- Until NSG-49 merges, the Architect may still be triggered into a no-op (harmless: it waits).
- The threshold's semantics broaden from "Backlog state" to "in-flight unfinished work,"
  which must be kept documented in `config.py` so the field name does not mislead.

## Links

- Source Question: [NSG-47](https://linear.app/nsg-engineering/issue/NSG-47/fase-1-totalmente-descompuesta-y-en-curso-el-architect-espera-o-se).
- Trigger fix (option C): [NSG-49](https://linear.app/nsg-engineering/issue/NSG-49/architect-trigger-misfires-when-phase-is-fully-decomposed-count-in).
- Roadmap phase rules: [ROADMAP.md](../../ROADMAP.md).
- Escalation workflow: [docs/workflows/escalation.md](../workflows/escalation.md).
- Trigger code: `tools/orchestrator/orchestrator/run_all.py`, `trigger_dispatcher.py`.

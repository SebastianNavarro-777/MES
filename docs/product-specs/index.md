---
title: Product specs — index
description: One folder per bounded context. Workers consult these when implementing tickets.
last_updated: 2026-05-04
---

# Product specs — index

Each module folder mirrors a bounded context under `apps/`. Specs evolve as the Architect agent fleshes out each phase of the [roadmap](../../ROADMAP.md).

| Module | Folder | Roadmap phase | Status |
|---|---|---|---|
| Orders | [orders/](orders/README.md) | Phase 1 | skeleton |
| WIP | [wip/](wip/README.md) | Phase 1 | skeleton |
| Traceability | [traceability/](traceability/README.md) | Phase 2 | skeleton |
| OEE | [oee/](oee/README.md) | Phase 3 | skeleton |
| Downtime | [downtime/](downtime/README.md) | Phase 3 | skeleton |
| Quality | [quality/](quality/README.md) | Phase 4 | skeleton |
| Scheduling | [scheduling/](scheduling/README.md) | Phase 5 | skeleton |
| Maintenance | [maintenance/](maintenance/README.md) | Phase 5 | skeleton |

## How to read a spec

Each module README has the same shape:
1. **Overview** — what this context owns.
2. **Domain entities** — names, invariants, lifecycle states.
3. **Use cases** — application-layer functions and the events they emit.
4. **API contract** — DRF endpoints exposed by the interface layer.
5. **Events emitted / consumed** — wire-format on the Redis Streams event bus.
6. **Open questions** — explicit ambiguities. The Spec Writer agent fills these or escalates.

If a section is missing or marked `TODO`, the agent must either fill it (Spec Writer) or escalate via `Question` (any other agent).

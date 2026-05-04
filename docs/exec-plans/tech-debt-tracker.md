---
title: Tech debt tracker
description: Lista viva de deuda técnica conocida. El Auditor agent agrega entradas; el Architect agent las prioriza.
last_updated: 2026-05-04
---

# Tech debt tracker

Each row is a known compromise that we accepted (consciously or not) in exchange for shipping. The Auditor agent adds entries when it spots drift between docs and code, dead branches, or principles violated under pressure. The Architect agent decides when each item gets a Story.

Severity:
- **High** — blocks compliance, security, or a roadmap deliverable.
- **Med** — slows future development or risks a regression class.
- **Low** — cosmetic / nice-to-have.

| ID | Description | Module | Severity | Discovered by | Discovered at | Status |
|---|---|---|---|---|---|---|

_(empty — populated as MES is built)_

## Lifecycle

1. **Detected** — a row is added with `Status = open`.
2. **Triaged** — Architect assigns severity and a target Roadmap phase, sets `Status = triaged`.
3. **Scheduled** — converted to a Story, sets `Status = scheduled` with a link to the ticket.
4. **Resolved** — Story closes; sets `Status = resolved`.
5. **Accepted** — explicitly decided to live with it; sets `Status = accepted` with rationale and review date.

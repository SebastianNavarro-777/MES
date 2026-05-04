---
title: Generated docs
last_updated: 2026-05-04
---

# ⚠ Auto-generated. Do not edit by hand.

Files in this folder are produced by scripts in `tools/verification/` and rebuilt automatically by the `Stop` hook (`.claude/hooks/stop.sh`) every time an agent finishes a session.

**The agents READ these files to understand current state. They do NOT edit them.**

If you find a file is wrong, missing data, or out of date:

1. Do **not** edit it manually — your edit will be wiped on the next regeneration.
2. Open a `Harness-Fix` ticket proposing improvements to the script that generates it (likely in `tools/verification/update_state.py` or a sibling).

## Files in this folder

| File | What it summarises | Generator |
|---|---|---|
| [STATE.md](STATE.md) | Top-level snapshot: counts of models, endpoints, modules, recent merges. | `tools/verification/update_state.py` |
| [db-schema.md](db-schema.md) | All Django models and their fields, dumped from `migrations/`. | `tools/verification/dump_db_schema.py` |
| [api-routes.md](api-routes.md) | DRF / Django URL routes and the views they map to. | `tools/verification/dump_api_routes.py` |
| [module-map.md](module-map.md) | Per bounded context: layers present, line counts, public surface. | `tools/verification/dump_module_map.py` |
| [coverage-by-module.md](coverage-by-module.md) | Test coverage per `apps/*` / `packages/*` from the latest `pytest --cov` run. | `tools/verification/dump_coverage.py` |

The generator scripts themselves are scaffolded as Harness-Fix tickets in early phases of MES development; until then, these files are seed placeholders.

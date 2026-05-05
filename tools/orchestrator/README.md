# Orchestrator

Reactive orchestrator that ties **Linear** (tickets) ↔ **Claude Code** (execution) ↔ **GitHub** (delivery) for the NSG MES project. Runs as a single Python process on Sebas's laptop. No cron, no GitHub Actions cron, no separate API key — just one daemon supervising several smaller ones.

## What lives here

```
tools/orchestrator/
├── orchestrator/             ← the Python package (this is what `python -m` runs)
│   ├── __main__.py           CLI entry: run-all, architect/auditor/gardener --run-now, trigger-dispatcher --inspect
│   ├── config.py             Pydantic Settings — reads .env at the repo root
│   ├── db.py                 SQLite schema + helpers at .orchestrator-state/queue.db
│   ├── state_machine.py      Linear states + valid transitions (pure logic, well-tested)
│   ├── linear_client.py      Async wrapper over Linear's GraphQL API
│   ├── github_client.py      Wrapper over `gh` CLI / GitHub API
│   ├── workspace.py          Per-ticket git worktrees under $WORKTREES_DIR
│   ├── claude_runner.py      Spawns Claude Code headless against a workspace + system prompt
│   ├── recolector.py         Daemon — polls Linear and enqueues actionable tickets
│   ├── worker.py             Daemon pool — runs the Worker agent on dequeued tickets
│   ├── reviewer.py           Daemon — runs the Reviewer agent on PRs in `In Review`
│   ├── qa_smoke_runner.py    Daemon — runs QA Smoke on tickets in `Ready for QA`
│   ├── consultant_resolver.py Daemon — closes Question tickets and writes ADRs
│   ├── trigger_dispatcher.py Daemon — fires Architect/Auditor/Gardener on counter thresholds
│   ├── architect.py          One-shot — invoked by trigger_dispatcher (or --run-now)
│   ├── auditor.py            One-shot — same
│   ├── gardener.py           One-shot — same
│   └── run_all.py            asyncio.gather of all daemons + a startup reconciliation pass
├── prompts/                  System prompts for the 8 agents (see Phase 5)
├── tests/                    pytest suite (state machine, linear client, trigger dispatcher)
├── launchd/                  macOS service template
├── systemd/                  Linux service template
└── seed/                     Initial Linear tickets to bootstrap the system
```

## Running it

From the repo root:

```bash
# Help (lists all subcommands)
cd tools/orchestrator && python -m orchestrator --help

# Run all daemons (the normal mode — leave the terminal open)
cd tools/orchestrator && python -m orchestrator run-all

# Inspect trigger counters without firing anything
cd tools/orchestrator && python -m orchestrator trigger-dispatcher --inspect

# Manually fire a one-shot agent (ignores cooldown)
cd tools/orchestrator && python -m orchestrator architect --run-now
cd tools/orchestrator && python -m orchestrator auditor   --run-now
cd tools/orchestrator && python -m orchestrator gardener  --run-now
```

Equivalently from the repo root without cd:

```bash
python -m tools.orchestrator.orchestrator --help
```

## Configuration

Environment variables are loaded from `.env` at the repo root (see `.env.example`). The orchestrator reads thresholds (`AUDITOR_PR_THRESHOLD`, `GARDENER_LEARNING_THRESHOLD`, etc.) so you can tune cadence without code changes.

State is stored in `.orchestrator-state/queue.db` (SQLite) at the repo root, plus per-ticket worktrees under `$WORKTREES_DIR`.

## Tests

```bash
python -m uv run pytest tools/orchestrator/tests/
```

The suite covers:
- `test_state_machine.py` — every valid transition + a sample of invalid ones.
- `test_linear_client.py` — GraphQL wrapper using `respx` (no real Linear contact).
- `test_trigger_dispatcher.py` — Architect / Auditor / Gardener trigger conditions, cooldowns, `--run-now`.

## Deployment

For now: `python -m orchestrator run-all` in a terminal on Sebas's laptop.

Background-service options when you want it: see `launchd/com.nsg.mes-orchestrator.plist.template` (macOS) and `systemd/mes-orchestrator.service.template` (Linux).

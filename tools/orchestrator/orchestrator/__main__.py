"""CLI entry point for the orchestrator.

Subcommands:
    run-all                          Bring up every daemon (normal mode).
    architect    --run-now           Force the Architect once.
    auditor      --run-now           Force the Auditor once.
    gardener     --run-now           Force the Gardener once.
    trigger-dispatcher --inspect     Print the current trigger counters.

Run from the orchestrator package root::

    cd tools/orchestrator
    python -m orchestrator --help

or, equivalently, from the repo root::

    python -m tools.orchestrator.orchestrator --help
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import architect as architect_mod
from . import auditor as auditor_mod
from . import gardener as gardener_mod
from .claude_runner import ClaudeRunner
from .config import Settings
from .db import Database
from .linear_client import LinearClient
from .run_all import run_all
from .state_machine import TicketState
from .trigger_dispatcher import (
    AgentName,
    ArchitectDecision,
    AuditorDecision,
    GardenerDecision,
    TriggerDispatcher,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="NSG MES orchestrator -- reactive harness driver.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run-all", help="Bring up every daemon (normal mode).")

    arch = sub.add_parser("architect", help="Architect one-shot runner.")
    arch.add_argument(
        "--run-now",
        action="store_true",
        help="Force a run regardless of cooldown (threshold still applies).",
    )

    aud = sub.add_parser("auditor", help="Auditor one-shot runner.")
    aud.add_argument(
        "--run-now",
        action="store_true",
        help="Force a run regardless of cooldown (threshold still applies).",
    )

    gar = sub.add_parser("gardener", help="Gardener one-shot runner.")
    gar.add_argument(
        "--run-now",
        action="store_true",
        help="Force a run regardless of cooldown (threshold still applies).",
    )

    td = sub.add_parser(
        "trigger-dispatcher", help="Inspect the trigger dispatcher."
    )
    td.add_argument(
        "--inspect",
        action="store_true",
        help="Print the current counter snapshot. (Currently the only mode.)",
    )

    return parser


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def _make_settings() -> Settings:
    return Settings()


async def _backlog_count(linear: LinearClient | None) -> int:
    if linear is None:
        return 0
    try:
        return await linear.count_issues_by_state(TicketState.BACKLOG.value)
    except Exception:
        return 0


async def cmd_architect(force: bool) -> int:
    settings = _make_settings()
    db = Database(settings.db_path)
    linear = (
        LinearClient(settings.LINEAR_API_KEY, settings.LINEAR_TEAM_ID)
        if settings.is_configured()
        else None
    )
    claude = ClaudeRunner(claude_binary=settings.CLAUDE_CONFIG_PATH or None)
    try:
        backlog = await _backlog_count(linear)

        def _backlog_provider() -> int:
            return backlog

        disp = TriggerDispatcher(
            settings=settings,
            db=db,
            backlog_count_provider=_backlog_provider,
        )
        decision = disp.evaluate_architect(force=force)
        print(f"architect decision: fire={decision.fire} ({decision.reason})")
        if not isinstance(decision, ArchitectDecision):
            return 0
        return await architect_mod.run_architect(
            decision, settings=settings, db=db, claude=claude
        )
    finally:
        if linear is not None:
            await linear.aclose()
        db.close()


async def cmd_auditor(force: bool) -> int:
    settings = _make_settings()
    db = Database(settings.db_path)
    claude = ClaudeRunner(claude_binary=settings.CLAUDE_CONFIG_PATH or None)
    try:
        disp = TriggerDispatcher(
            settings=settings,
            db=db,
            backlog_count_provider=lambda: 0,
        )
        decision = disp.evaluate_auditor(force=force)
        print(f"auditor decision: fire={decision.fire} ({decision.reason})")
        if not isinstance(decision, AuditorDecision):
            return 0
        return await auditor_mod.run_auditor(
            decision, settings=settings, db=db, claude=claude
        )
    finally:
        db.close()


async def cmd_gardener(force: bool) -> int:
    settings = _make_settings()
    db = Database(settings.db_path)
    claude = ClaudeRunner(claude_binary=settings.CLAUDE_CONFIG_PATH or None)
    try:
        disp = TriggerDispatcher(
            settings=settings,
            db=db,
            backlog_count_provider=lambda: 0,
        )
        decision = disp.evaluate_gardener(force=force)
        print(f"gardener decision: fire={decision.fire} ({decision.reason})")
        if not isinstance(decision, GardenerDecision):
            return 0
        return await gardener_mod.run_gardener(
            decision, settings=settings, db=db, claude=claude
        )
    finally:
        db.close()


async def cmd_trigger_dispatcher_inspect() -> int:
    settings = _make_settings()
    db = Database(settings.db_path)
    linear = (
        LinearClient(settings.LINEAR_API_KEY, settings.LINEAR_TEAM_ID)
        if settings.is_configured()
        else None
    )
    try:
        backlog = await _backlog_count(linear)

        def _backlog_provider() -> int:
            return backlog

        disp = TriggerDispatcher(
            settings=settings,
            db=db,
            backlog_count_provider=_backlog_provider,
        )
        snap = disp.inspect()
        print("Trigger dispatcher -- counter snapshot")
        print("  -----------------------------------------------------")
        print(f"  Architect: backlog={snap.backlog_count} "
              f"threshold={snap.architect_threshold} "
              f"cooldown={'yes' if snap.architect_in_cooldown else 'no'}")
        print(f"  Auditor:   pending={snap.pending_audit_pr_count} "
              f"threshold={snap.auditor_threshold} "
              f"cooldown={'yes' if snap.auditor_in_cooldown else 'no'}")
        print(f"  Gardener:  learning={snap.unconsumed_learning_events}/"
              f"{snap.learning_threshold}, "
              f"pr_safety={snap.pr_safety_pending}/"
              f"{snap.pr_safety_threshold}, "
              f"cooldown={'yes' if snap.gardener_in_cooldown else 'no'}")
        if snap.notes:
            print()
            for note in snap.notes:
                print(f"  note: {note}")
        return 0
    finally:
        if linear is not None:
            await linear.aclose()
        db.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-all":
        return asyncio.run(run_all())
    if args.command == "architect":
        return asyncio.run(cmd_architect(force=bool(args.run_now)))
    if args.command == "auditor":
        return asyncio.run(cmd_auditor(force=bool(args.run_now)))
    if args.command == "gardener":
        return asyncio.run(cmd_gardener(force=bool(args.run_now)))
    if args.command == "trigger-dispatcher":
        # Currently --inspect is the only mode; if absent we still print snapshot.
        _ = args.inspect
        return asyncio.run(cmd_trigger_dispatcher_inspect())

    parser.print_help()
    return 1


# Re-export for tools that prefer accessing AgentName via __main__.
_ = AgentName

if __name__ == "__main__":
    sys.exit(main())

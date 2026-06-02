"""``run-all`` — orchestrator main process.

Performs a startup reconciliation pass, then ``asyncio.gather``s every
daemon together. Cancels them all cleanly on SIGINT/SIGTERM.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

from . import architect as architect_mod
from . import auditor as auditor_mod
from . import gardener as gardener_mod
from .claude_runner import ClaudeRunner
from .config import Settings, repo_root
from .consultant_resolver import ConsultantResolver
from .db import Database
from .failed_recovery import FailedRecoveryDaemon
from .github_client import GitHubClient
from .linear_client import LinearClient
from .qa_smoke_runner import QASmokeDaemon
from .recolector import Recolector
from .reviewer import ReviewerDaemon
from .spec_writer_runner import SpecWriterDaemon
from .state_machine import TicketState
from .trigger_dispatcher import (
    AgentName,
    ArchitectDecision,
    AuditorDecision,
    GardenerDecision,
    TriggerDispatcher,
)
from .worker import WorkerPool
from .workspace import WorkspaceManager

__all__ = ["run_all", "startup_check"]


console = Console(stderr=True)


def _setup_logging(settings: Settings) -> None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RichHandler(rich_tracebacks=True, console=console, show_path=False),
        logging.FileHandler(
            settings.logs_dir / "orchestrator.jsonl", encoding="utf-8"
        ),
    ]
    logging.basicConfig(level=logging.INFO, handlers=handlers, format="%(message)s")


async def startup_check(
    *, settings: Settings, db: Database, linear: LinearClient | None
) -> None:
    """Print a colourful summary of what's pending, and reconcile orphans."""
    console.rule("[bold]NSG MES orchestrator — startup")

    if not settings.is_configured():
        console.print(
            "[yellow]Warning:[/] live credentials missing — running in dry mode."
        )
        console.print(
            "Set LINEAR_API_KEY, LINEAR_TEAM_ID, GITHUB_TOKEN, GITHUB_REPO."
        )

    pending_audit = len(db.list_pr_events(audited=False))
    pending_learning = len(db.list_learning_events(consumed_by_gardener=False))
    console.print(
        f"SQLite: {pending_audit} PR(s) pending audit, "
        f"{pending_learning} learning event(s) unconsumed."
    )

    if linear is not None:
        try:
            for state in [
                TicketState.SPEC_DRAFT,
                TicketState.READY_FOR_AGENT,
                TicketState.IN_PROGRESS,
                TicketState.IN_REVIEW,
                TicketState.READY_FOR_QA,
                TicketState.FAILED,
            ]:
                count = await linear.count_issues_by_state(state.value)
                console.print(f"  Linear  {state.value:20s}  {count}")
            # All three stuck states self-heal: spec_writer_runner re-drives
            # orphaned Spec Drafts, and failed_recovery re-queues Failed
            # tickets immediately and stale In Progress orphans once they
            # pass IN_PROGRESS_GRACE_SECONDS — all bounded by MAX_AUTO_RETRIES
            # before a `needs-human` label stops the loop.
        except Exception:
            console.print("[red]Linear unreachable[/] — recolector will retry.")

    workspaces = WorkspaceManager(
        repo_root=repo_root(),
        worktrees_dir=settings.worktrees_path,
    )
    try:
        orphans = await workspaces.list_orphans()
    except Exception:
        orphans = []
    if orphans:
        console.print(
            f"[yellow]Reconciliation:[/] "
            f"{len(orphans)} orphan worktree(s) on disk."
        )
        for o in orphans:
            console.print(f"  {o}")

    dispatcher = TriggerDispatcher(
        settings=settings,
        db=db,
        backlog_count_provider=lambda: 0,
    )
    snap = dispatcher.inspect()
    console.print()
    console.print(
        f"  Architect: backlog={snap.backlog_count} "
        f"threshold={snap.architect_threshold} "
        f"cooldown={'yes' if snap.architect_in_cooldown else 'no'}"
    )
    console.print(
        f"  Auditor:   pending={snap.pending_audit_pr_count} "
        f"threshold={snap.auditor_threshold} "
        f"cooldown={'yes' if snap.auditor_in_cooldown else 'no'}"
    )
    console.print(
        f"  Gardener:  learning={snap.unconsumed_learning_events}/"
        f"{snap.learning_threshold}, "
        f"pr_safety={snap.pr_safety_pending}/{snap.pr_safety_threshold}, "
        f"cooldown={'yes' if snap.gardener_in_cooldown else 'no'}"
    )
    console.rule()


async def run_all(*, env_overrides: dict[str, Any] | None = None) -> int:
    """Bring up every daemon and wait for SIGINT/SIGTERM.

    Returns the exit code (0 normal stop, non-zero on unhandled error).
    """
    settings = Settings(**env_overrides) if env_overrides else Settings()
    _setup_logging(settings)
    log = logging.getLogger(__name__)

    db = Database(settings.db_path)
    linear: LinearClient | None = None
    if settings.is_configured():
        linear = LinearClient(settings.LINEAR_API_KEY, settings.LINEAR_TEAM_ID)
    claude = ClaudeRunner(claude_binary=settings.CLAUDE_CONFIG_PATH or None)
    workspaces = WorkspaceManager(
        repo_root=repo_root(), worktrees_dir=settings.worktrees_path
    )

    await startup_check(settings=settings, db=db, linear=linear)

    if linear is None:
        log.warning("orchestrator running without Linear; daemons will idle.")
        return 0

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _handle_signal() -> None:
        log.info("signal received; shutting down")
        stop_event.set()

    for sig in _supported_signals():
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, _handle_signal)

    recolector = Recolector(linear=linear, db=db)
    github = GitHubClient(token=settings.GITHUB_TOKEN or None)
    worker_pool = WorkerPool(
        settings=settings,
        db=db,
        linear=linear,
        claude=claude,
        workspaces=workspaces,
        github=github,
    )
    reviewer = ReviewerDaemon(
        settings=settings, db=db, linear=linear, claude=claude
    )
    qa = QASmokeDaemon(settings=settings, db=db, linear=linear, claude=claude)
    consultant = ConsultantResolver(
        settings=settings, db=db, linear=linear, claude=claude
    )
    spec_writer = SpecWriterDaemon(
        settings=settings, db=db, linear=linear, claude=claude
    )
    failed_recovery = FailedRecoveryDaemon(
        settings=settings, db=db, linear=linear
    )

    try:
        await asyncio.gather(
            recolector.run_forever(stop_event=stop_event),
            worker_pool.run_forever(stop_event=stop_event),
            reviewer.run_forever(stop_event=stop_event),
            qa.run_forever(stop_event=stop_event),
            consultant.run_forever(stop_event=stop_event),
            spec_writer.run_forever(stop_event=stop_event),
            failed_recovery.run_forever(stop_event=stop_event),
            _trigger_loop(
                settings=settings,
                db=db,
                linear=linear,
                claude=claude,
                stop_event=stop_event,
            ),
        )
    finally:
        await linear.aclose()
        await github.aclose()
        db.close()
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _supported_signals() -> list[signal.Signals]:
    out: list[signal.Signals] = [signal.SIGINT]
    if hasattr(signal, "SIGTERM"):
        out.append(signal.SIGTERM)
    return out


async def _trigger_loop(
    *,
    settings: Settings,
    db: Database,
    linear: LinearClient,
    claude: ClaudeRunner,
    stop_event: asyncio.Event,
) -> None:
    """Run the dispatcher → one-shot agents loop until stop is set."""
    log = logging.getLogger(__name__)

    while not stop_event.is_set():
        try:
            backlog = 0
            with contextlib.suppress(Exception):
                backlog = await linear.count_issues_by_state(
                    TicketState.BACKLOG.value
                )

            captured_backlog = backlog

            def _provider(b: int = captured_backlog) -> int:
                return b

            disp = TriggerDispatcher(
                settings=settings,
                db=db,
                backlog_count_provider=_provider,
            )
            for decision in disp.evaluate():
                if not decision.fire:
                    continue
                if decision.agent == AgentName.ARCHITECT and isinstance(
                    decision, ArchitectDecision
                ):
                    await architect_mod.run_architect(
                        decision, settings=settings, db=db, claude=claude
                    )
                elif decision.agent == AgentName.AUDITOR and isinstance(
                    decision, AuditorDecision
                ):
                    await auditor_mod.run_auditor(
                        decision, settings=settings, db=db, claude=claude
                    )
                elif decision.agent == AgentName.GARDENER and isinstance(
                    decision, GardenerDecision
                ):
                    await gardener_mod.run_gardener(
                        decision, settings=settings, db=db, claude=claude
                    )
        except Exception:
            log.exception("trigger loop tick failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except TimeoutError:
            continue

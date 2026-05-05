"""Worker pool daemon.

Dequeues tickets in ``Ready for Agent`` state and runs the Worker agent
prompt against a per-ticket worktree. Concurrency is bounded by
``MAX_CONCURRENT_WORKERS``.

This module owns the *daemon shape* (the loop, the bounded pool, the
state transitions). The actual implementation work happens inside
Claude Code, driven by the ``worker.md`` prompt.
"""

from __future__ import annotations

import asyncio
import logging

from .claude_runner import ClaudeRunner
from .config import Settings
from .db import Database
from .linear_client import LinearClient
from .state_machine import TicketState
from .workspace import WorkspaceManager

__all__ = ["WorkerPool"]

log = logging.getLogger(__name__)


class WorkerPool:
    """Bounded pool of Worker agents."""

    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        linear: LinearClient,
        claude: ClaudeRunner,
        workspaces: WorkspaceManager,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self._settings = settings
        self._db = db
        self._linear = linear
        self._claude = claude
        self._workspaces = workspaces
        self._interval = poll_interval_seconds
        self._sem = asyncio.Semaphore(settings.MAX_CONCURRENT_WORKERS)

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("worker pool tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def tick(self) -> None:
        items = self._db.list_work_items(state=TicketState.READY_FOR_AGENT.value)
        if not items:
            return
        tasks: list[asyncio.Task[None]] = []
        for item in items:
            tasks.append(asyncio.create_task(self._run_one(item.ticket_id)))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_one(self, ticket_id: str) -> None:
        async with self._sem:
            try:
                workspace = await self._workspaces.create(ticket_id)
            except Exception:
                log.exception("workspace creation failed for %s", ticket_id)
                return
            try:
                user_prompt = (
                    f"Implement ticket {ticket_id}. "
                    f"Read it via the linear MCP and follow tools/orchestrator/"
                    f"prompts/worker.md."
                )
                result = await self._claude.run(
                    agent_name="worker",
                    user_prompt=user_prompt,
                    workspace=workspace.path,
                )
                if result.exit_code != 0:
                    log.warning(
                        "worker for %s exited %s: %s",
                        ticket_id,
                        result.exit_code,
                        result.stderr[-500:],
                    )
                    self._db.record_learning_event("ticket_failed", ticket_id)
            finally:
                await self._workspaces.cleanup(workspace)
                self._db.remove_work_item(ticket_id)

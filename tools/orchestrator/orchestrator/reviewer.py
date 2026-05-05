"""Reviewer daemon.

Detects tickets in ``In Review`` with a linked PR, runs the Reviewer
agent prompt, and consumes the result by transitioning the ticket to
``Ready for QA`` (on merge) or ``Failed`` (on reject).

The actual decision logic is in ``prompts/reviewer.md``; this module is
the daemon shell.
"""

from __future__ import annotations

import asyncio
import logging

from .claude_runner import ClaudeRunner
from .config import Settings
from .db import Database
from .linear_client import LinearClient
from .state_machine import TicketState

__all__ = ["ReviewerDaemon"]

log = logging.getLogger(__name__)


class ReviewerDaemon:
    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        linear: LinearClient,
        claude: ClaudeRunner,
        poll_interval_seconds: float = 60.0,
    ) -> None:
        self._settings = settings
        self._db = db
        self._linear = linear
        self._claude = claude
        self._interval = poll_interval_seconds

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("reviewer tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def tick(self) -> None:
        items = self._db.list_work_items(state=TicketState.IN_REVIEW.value)
        for item in items:
            try:
                await self._review_one(item.ticket_id)
            except Exception:
                log.exception("reviewer failed on %s", item.ticket_id)

    async def _review_one(self, ticket_id: str) -> None:
        user_prompt = (
            f"Review the open PR for ticket {ticket_id}. "
            f"Follow tools/orchestrator/prompts/reviewer.md exactly."
        )
        result = await self._claude.run(
            agent_name="reviewer",
            user_prompt=user_prompt,
            workspace=self._settings.worktrees_path,
        )
        # Reviewer agent owns the Linear transitions; we just consume the queue.
        if result.exit_code == 0:
            self._db.remove_work_item(ticket_id)

"""QA Smoke daemon.

Picks tickets in ``Ready for QA`` and runs the QA Smoke agent prompt.
Serialised by a single asyncio.Lock — staging is shared, only one
QA run at a time.
"""

from __future__ import annotations

import asyncio
import logging

from .claude_runner import ClaudeRunner
from .config import Settings
from .db import Database
from .linear_client import LinearClient
from .state_machine import TicketState

__all__ = ["QASmokeDaemon"]

log = logging.getLogger(__name__)


class QASmokeDaemon:
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
        self._lock = asyncio.Lock()

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("qa smoke tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def tick(self) -> None:
        items = self._db.list_work_items(state=TicketState.READY_FOR_QA.value)
        if not items:
            return
        async with self._lock:
            for item in items:
                try:
                    await self._run_one(item.ticket_id)
                except Exception:
                    log.exception("qa smoke failed on %s", item.ticket_id)

    async def _run_one(self, ticket_id: str) -> None:
        user_prompt = (
            f"Deploy the merged PR for ticket {ticket_id} to staging "
            f"and run the smoke suite. Follow tools/orchestrator/"
            f"prompts/qa_smoke.md exactly."
        )
        result = await self._claude.run(
            agent_name="qa_smoke",
            user_prompt=user_prompt,
            workspace=self._settings.worktrees_path,
        )
        if result.exit_code == 0:
            self._db.remove_work_item(ticket_id)

"""Consultant Resolver daemon.

Watches for ``Question`` tickets that Sebas has resolved, parses the
decision, writes the appropriate ADR or golden-principle update via a
PR (driven by Claude Code), and unblocks the original ticket back to
``Ready for Agent``.

This is the only daemon that ever creates a PR without going through a
Worker — it's a tightly-scoped harness operation.
"""

from __future__ import annotations

import asyncio
import logging

from .claude_runner import ClaudeRunner
from .config import Settings
from .db import Database
from .linear_client import LinearClient

__all__ = ["ConsultantResolver"]

log = logging.getLogger(__name__)

QUESTION_LABEL = "needs-human-decision"


class ConsultantResolver:
    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        linear: LinearClient,
        claude: ClaudeRunner,
        poll_interval_seconds: float = 120.0,
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
                log.exception("consultant resolver tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def tick(self) -> None:
        # Done tickets with the question label = newly-resolved Questions.
        # We rely on the original question ticket carrying that label.
        # NB: Linear's GraphQL filter by label name is also possible; we
        # just check the label list on each Done issue for simplicity.
        from .state_machine import TicketState

        done_issues = await self._linear.list_issues_by_state(
            TicketState.DONE.value
        )
        for issue in done_issues:
            if QUESTION_LABEL not in issue.labels:
                continue
            await self._consume_one(issue.identifier)

    async def _consume_one(self, ticket_id: str) -> None:
        user_prompt = (
            f"Question ticket {ticket_id} was just resolved by the human. "
            f"Read its body, parse the marked decision, write the resulting "
            f"docs/decisions ADR or docs/golden-principles update via PR, "
            f"and transition the blocking ticket back to Ready for Agent. "
            f"You are the Consultant Resolver."
        )
        # NOTE: this resolves to prompts/consultant_resolver.md (not
        # consultant.md). The two prompts are deliberately separate because
        # they have opposite write-permissions: the Consultant is read-only
        # and creates Questions, the Consultant Resolver writes docs and
        # opens PRs after Sebas answers.
        await self._claude.run(
            agent_name="consultant_resolver",
            user_prompt=user_prompt,
            workspace=self._settings.worktrees_path,
        )

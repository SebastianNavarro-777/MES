"""Recolector daemon — polls Linear and enqueues actionable tickets.

Cadence: every 60 seconds. For each actionable state (see
``state_machine.actionable_states()``), the recolector lists Linear
tickets in that state and pushes them to the SQLite work queue. Other
daemons (Worker pool, Reviewer, QA Smoke) consume from the queue.

This daemon also detects ``Harness-Fix`` tickets that closed (Done) and
records them as learning events for the Gardener.
"""

from __future__ import annotations

import asyncio
import logging

from .db import Database
from .linear_client import LinearClient
from .state_machine import TicketState, actionable_states

__all__ = ["Recolector"]

log = logging.getLogger(__name__)


class Recolector:
    """Daemon that mirrors Linear state into the local SQLite queue."""

    def __init__(
        self,
        *,
        linear: LinearClient,
        db: Database,
        poll_interval_seconds: float = 60.0,
    ) -> None:
        self._linear = linear
        self._db = db
        self._interval = poll_interval_seconds

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("recolector tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def tick(self) -> None:
        """One pass: enqueue actionable tickets, record learning events."""
        for state in actionable_states():
            issues = await self._linear.list_issues_by_state(state.value)
            for issue in issues:
                self._db.enqueue(
                    issue.identifier,
                    state.value,
                    metadata={
                        "title": issue.title,
                        "labels": list(issue.labels),
                        "parent_id": issue.parent_id,
                    },
                )

        # Detect closed Harness-Fix tickets → learning events for Gardener.
        done = await self._linear.list_issues_by_state(TicketState.DONE.value)
        for issue in done:
            if "harness-fix" in issue.labels:
                self._db.record_learning_event("harness_fix_closed", issue.identifier)

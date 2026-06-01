"""Recolector daemon — polls Linear and enqueues actionable tickets.

Cadence: every 60 seconds. For each actionable state (see
``state_machine.actionable_states()``), the recolector lists Linear
tickets in that state and pushes them to the SQLite work queue. Other
daemons (Worker pool, Reviewer, QA Smoke) consume from the queue.

This daemon also emits learning events for the Gardener:

* ``harness_fix_closed`` — a Harness-Fix ticket reached Done.
* ``default_decision_applied`` — a ticket carries ``applied-default-decision``,
  meaning the Consultant hit its quota and applied a default-of-record
  for Sebas to audit later. The Gardener mines patterns across these
  to surface gaps in product specs or roadmap clarity.

Both events use ``record_learning_event_once`` so a single ticket
generates exactly one unconsumed event per Gardener cycle, regardless of
how many times the recolector polls.
"""

from __future__ import annotations

import asyncio
import logging

from .db import Database
from .linear_client import LinearClient
from .state_machine import TicketState, actionable_states

__all__ = ["Recolector"]

log = logging.getLogger(__name__)

# Linear label that the Consultant applies when count >= 3 and it had to
# fall back to a lowest-risk default. Mirrors the constant baked into
# ``prompts/consultant.md`` and the canonical set in
# ``seed/sync_labels.py``.
DEFAULT_DECISION_LABEL = "applied-default-decision"
HARNESS_FIX_LABEL = "harness-fix"


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
                # applied-default-decision can appear on tickets in any
                # state (Architect labels Epics in Backlog, Worker may
                # see it on a Story moving through the queue, etc.) so
                # we scan during the per-state walk rather than only on
                # Done.
                if DEFAULT_DECISION_LABEL in issue.labels:
                    self._db.record_learning_event_once(
                        "default_decision_applied", issue.identifier
                    )

        # Done is not in actionable_states() — scan it separately for
        # closed Harness-Fix tickets and for any default-decision
        # tickets that already shipped.
        done = await self._linear.list_issues_by_state(TicketState.DONE.value)
        for issue in done:
            if HARNESS_FIX_LABEL in issue.labels:
                self._db.record_learning_event_once(
                    "harness_fix_closed", issue.identifier
                )
            if DEFAULT_DECISION_LABEL in issue.labels:
                self._db.record_learning_event_once(
                    "default_decision_applied", issue.identifier
                )

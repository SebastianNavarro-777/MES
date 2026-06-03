"""Recovery daemon — re-drives tickets that no other daemon will touch.

Two dead ends are closed here:

* **Failed** tickets. ``Failed`` is not an actionable state, so the
  recolector never re-enqueues it; without this daemon a Worker that
  gave up strands its ticket forever. Each ``Failed`` ticket is re-queued
  to ``Ready for Agent`` so the recolector + Worker pool re-attempt it.

* **Stale In Progress** tickets. If a Worker crashes (or the whole
  orchestrator is killed) after the agent set the ticket to ``In
  Progress`` but before it reached ``In Review`` / ``Failed`` / ``Blocked``,
  the ticket strands there — ``In Progress`` is not actionable either.
  We re-queue it to ``Ready for Agent`` once it has sat there longer than
  ``Settings.IN_PROGRESS_GRACE_SECONDS`` (a window wider than the longest
  possible Worker run, so a *live* agent is never yanked).

Both paths are bounded by ``Settings.MAX_AUTO_RETRIES`` (shared "worker"
budget): past the budget the ticket is labelled ``needs-human`` and left
alone, so a genuinely broken ticket never loops forever burning Claude
usage.

Cadence: every 90 s — slower than the Worker pool (30 s) so a re-queued
ticket gets a full implementation attempt before we reconsider it, and
slower than the recolector (60 s) so the re-queue has propagated.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from .config import Settings
from .db import Database
from .linear_client import Issue, LinearClient
from .recovery import escalate_to_human, needs_human
from .state_machine import TicketState

__all__ = ["FailedRecoveryDaemon"]

log = logging.getLogger(__name__)

# Retry-budget key in the ``ticket_attempts`` table. Failed re-queues and
# In Progress orphan re-claims share it (both end in a fresh Worker run),
# kept separate from the Spec Writer's "spec" budget.
_WORKER_STAGE = "worker"


class FailedRecoveryDaemon:
    """Re-queues Failed + stale In Progress tickets on a bounded budget."""

    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        linear: LinearClient,
        poll_interval_seconds: float = 90.0,
    ) -> None:
        self._settings = settings
        self._db = db
        self._linear = linear
        self._interval = poll_interval_seconds
        # Cached state-name → UUID map, filled on the first re-queue.
        self._state_ids: dict[str, str] | None = None

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("recovery tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def tick(self) -> None:
        await self._recover_failed()
        await self._reap_in_progress()

    # -- Failed → Ready for Agent -------------------------------------------

    async def _recover_failed(self) -> None:
        issues = await self._linear.list_issues_by_state(TicketState.FAILED.value)
        for issue in issues:
            try:
                await self._recover_failed_one(issue)
            except Exception:
                log.exception("failed-recovery on %s errored", issue.identifier)

    async def _recover_failed_one(self, issue: Issue) -> None:
        if needs_human(issue):
            return
        if (
            self._db.get_attempts(issue.identifier, _WORKER_STAGE)
            >= self._settings.MAX_AUTO_RETRIES
        ):
            await escalate_to_human(
                self._linear,
                issue,
                reason="Worker kept failing across auto-retries",
            )
            return
        if not await self._requeue(issue):
            return
        attempt = self._db.bump_attempt(issue.identifier, _WORKER_STAGE)
        await self._linear.add_comment(
            issue.id,
            f"Auto-retry {attempt}/{self._settings.MAX_AUTO_RETRIES}: "
            f"re-queued to Ready for Agent after a Worker failure.",
        )
        log.info(
            "recovered Failed %s (attempt %s/%s)",
            issue.identifier,
            attempt,
            self._settings.MAX_AUTO_RETRIES,
        )

    # -- stale In Progress → Ready for Agent --------------------------------

    async def _reap_in_progress(self) -> None:
        issues = await self._linear.list_issues_by_state(
            TicketState.IN_PROGRESS.value
        )
        # Restart the staleness clock for tickets that have since left the
        # state, so a future re-entry isn't judged against an old timestamp.
        self._db.prune_in_progress_seen([i.identifier for i in issues])
        for issue in issues:
            try:
                await self._reap_in_progress_one(issue)
            except Exception:
                log.exception("in-progress reap on %s errored", issue.identifier)

    async def _reap_in_progress_one(self, issue: Issue) -> None:
        if needs_human(issue):
            self._db.clear_in_progress_seen(issue.identifier)
            return
        first_seen = self._db.mark_in_progress_seen(issue.identifier)
        elapsed = (datetime.now(UTC) - first_seen).total_seconds()
        if elapsed < self._settings.IN_PROGRESS_GRACE_SECONDS:
            # Still within the window where a live Worker could own it.
            return
        if (
            self._db.get_attempts(issue.identifier, _WORKER_STAGE)
            >= self._settings.MAX_AUTO_RETRIES
        ):
            await escalate_to_human(
                self._linear,
                issue,
                reason="orphaned in In Progress and out of auto-retries",
            )
            self._db.clear_in_progress_seen(issue.identifier)
            return
        if not await self._requeue(issue):
            return
        attempt = self._db.bump_attempt(issue.identifier, _WORKER_STAGE)
        self._db.clear_in_progress_seen(issue.identifier)
        minutes = int(self._settings.IN_PROGRESS_GRACE_SECONDS // 60)
        await self._linear.add_comment(
            issue.id,
            f"Orphan recovery (attempt {attempt}/{self._settings.MAX_AUTO_RETRIES}): "
            f"stuck in In Progress for over {minutes} min with no active "
            f"Worker — re-queued to Ready for Agent.",
        )
        log.info(
            "reaped orphaned In Progress %s (attempt %s/%s)",
            issue.identifier,
            attempt,
            self._settings.MAX_AUTO_RETRIES,
        )

    # -- shared helpers ------------------------------------------------------

    async def _requeue(self, issue: Issue) -> bool:
        """Move ``issue`` to Ready for Agent. Returns False on error."""
        states = await self._get_state_ids()
        target = states.get(TicketState.READY_FOR_AGENT.value)
        if target is None:
            log.error(
                "no '%s' workflow state in this team; cannot recover %s",
                TicketState.READY_FOR_AGENT.value,
                issue.identifier,
            )
            return False
        try:
            await self._linear.update_issue_state(issue.id, target)
        except Exception:
            log.exception(
                "re-queue %s → Ready for Agent failed", issue.identifier
            )
            return False
        return True

    async def _get_state_ids(self) -> dict[str, str]:
        if self._state_ids is None:
            self._state_ids = await self._linear.list_team_states()
        return self._state_ids

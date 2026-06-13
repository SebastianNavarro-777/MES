"""Blocked-dependency recovery daemon.

A ticket reaches ``Blocked`` for one of two reasons:

* **Blocked by a Question** — an agent invoked the Consultant, which opened a
  ``needs-human-decision`` ticket. The Consultant Resolver releases the Story
  once Sebas answers (the Question reaches ``Done``).
* **Blocked by another ticket** — a Story depends on a sibling Story that must
  land first (e.g., NSG-41 needs the order-detail screen NSG-21). Nothing
  released these automatically, so they sat in ``Blocked`` indefinitely.

This daemon closes the second dead end. Because Linear models *both* kinds as
``blockedBy`` relations, it handles them uniformly: it releases a ``Blocked``
ticket back to ``Ready for Agent`` once **every** ticket in its ``blockedBy``
set is ``Done``. Requiring *all* blockers to be done (not just one) is what
stops a multi-blocker Story like NSG-41 from being let through while a sibling
dependency is still open — the premature release that previously churned it
straight back to ``Blocked``.

Cadence: every 120 s. Relations change slowly and this only ever moves a
ticket *out* of ``Blocked``, so there is no fast feedback loop to chase.
"""

from __future__ import annotations

import asyncio
import logging

from .config import Settings
from .db import Database
from .linear_client import Issue, LinearClient
from .recovery import is_question, needs_human
from .state_machine import TicketState

__all__ = ["BlockedRecoveryDaemon"]

log = logging.getLogger(__name__)


class BlockedRecoveryDaemon:
    """Releases Blocked tickets whose blockers have all reached Done."""

    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        linear: LinearClient,
        poll_interval_seconds: float = 120.0,
    ) -> None:
        self._settings = settings
        self._db = db
        self._linear = linear
        self._interval = poll_interval_seconds
        # Cached state-name → UUID map, filled on the first release.
        self._state_ids: dict[str, str] | None = None

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("blocked recovery tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def tick(self) -> None:
        issues = await self._linear.list_issues_by_state(TicketState.BLOCKED.value)
        for issue in issues:
            try:
                await self._maybe_release(issue)
            except Exception:
                log.exception("blocked recovery on %s errored", issue.identifier)

    async def _maybe_release(self, issue: Issue) -> None:
        # A human asked us to stop touching this ticket.
        if needs_human(issue):
            return
        # A Question parked in Blocked is the human's to answer and the
        # Consultant Resolver's to release — never push one into the work
        # pipeline.
        if is_question(issue):
            return
        blockers = await self._linear.list_blocker_states(issue.identifier)
        if not blockers:
            # No dependency relation to reason about: it may be blocked on a
            # Question with no relation (the Resolver owns that) or parked by
            # a human. Either way, not ours to release.
            return
        unresolved = sorted(
            ident
            for ident, state in blockers.items()
            if state != TicketState.DONE.value
        )
        if unresolved:
            return  # still blocked by at least one open ticket
        if not await self._release(issue):
            return
        cleared = ", ".join(sorted(blockers))
        await self._linear.add_comment(
            issue.id,
            f"Desbloqueado automáticamente: sus bloqueadores ({cleared}) ya "
            f"están en Done. Vuelvo el ticket a Ready for Agent.",
        )
        log.info(
            "released blocked %s (blockers done: %s)", issue.identifier, cleared
        )

    async def _release(self, issue: Issue) -> bool:
        """Move ``issue`` to Ready for Agent. Returns False on error."""
        states = await self._get_state_ids()
        target = states.get(TicketState.READY_FOR_AGENT.value)
        if target is None:
            log.error(
                "no '%s' workflow state in this team; cannot release %s",
                TicketState.READY_FOR_AGENT.value,
                issue.identifier,
            )
            return False
        try:
            await self._linear.update_issue_state(issue.id, target)
        except Exception:
            log.exception("release %s → Ready for Agent failed", issue.identifier)
            return False
        return True

    async def _get_state_ids(self) -> dict[str, str]:
        if self._state_ids is None:
            self._state_ids = await self._linear.list_team_states()
        return self._state_ids

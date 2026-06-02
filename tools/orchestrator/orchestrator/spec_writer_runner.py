"""Spec Writer daemon.

Closes the Backlog → Spec Draft → Ready for Agent path that the seed
prompts assumed existed. Without this daemon, tickets created in
``Backlog`` (by the seed script or the Architect) never reach the
Worker pool — the recolector only enqueues *actionable* states (Spec
Draft, Ready for Agent, In Review, Ready for QA), and the Worker only
dequeues Ready for Agent.

Cadence: every 120 s — slower than the recolector (60 s) because Spec
Writer work is heavier per ticket than queue mirroring, and we want the
daemons to interleave cleanly.

Concurrency: serial. One ticket per tick. A long Backlog drains at
roughly the same rate the Worker pool absorbs, so back-pressure flows
naturally without explicit coordination.

Filter:
* ``type:story``, ``type:bug``, ``type:harness-fix`` — enriched.
* ``type:epic`` — skipped (Epics are containers; the Architect manages
  them, the Spec Writer does not).
* ``type:question`` — skipped (Consultant owns Question tickets).
"""

from __future__ import annotations

import asyncio
import logging

from .claude_runner import ClaudeRunner
from .config import Settings, repo_root
from .db import Database
from .linear_client import Issue, LinearClient
from .state_machine import TicketState

__all__ = ["SpecWriterDaemon"]

log = logging.getLogger(__name__)

# Type labels indicating a ticket needs Spec Writer treatment. Mirrors
# ``tools/orchestrator/seed/sync_labels.py``.
ENRICHABLE_TYPES: tuple[str, ...] = ("type:story", "type:bug", "type:harness-fix")


class SpecWriterDaemon:
    """One-ticket-per-tick promotion from Backlog → Spec Draft.

    The agent (driven by ``prompts/spec_writer.md``) is responsible for
    the final Spec Draft → Ready for Agent transition after enrichment
    completes. This daemon only does the first transition + the spawn.
    """

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
        # Cached per-team state-name → UUID map. Filled on the first
        # transition attempt; survives until the process restarts.
        self._state_ids: dict[str, str] | None = None
        # Tickets currently being processed by an in-flight Claude session.
        # Prevents a second tick from picking the same ticket before the
        # agent has had time to transition it out of Backlog.
        self._in_flight: set[str] = set()

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("spec writer tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def tick(self) -> None:
        ticket = await self._pick_one()
        if ticket is None:
            return
        self._in_flight.add(ticket.identifier)
        try:
            if not await self._transition_to_spec_draft(ticket):
                # Transition failed → leave the ticket in Backlog so a
                # later tick (or a manual move) can retry. Don't spawn
                # the agent on a half-failed state change.
                return
            await self._spawn_agent(ticket)
        finally:
            self._in_flight.discard(ticket.identifier)

    async def _pick_one(self) -> Issue | None:
        """Pick the first Backlog ticket of an enrichable type."""
        issues = await self._linear.list_issues_by_state(
            TicketState.BACKLOG.value
        )
        for issue in issues:
            if issue.identifier in self._in_flight:
                continue
            if any(t in issue.labels for t in ENRICHABLE_TYPES):
                return issue
        return None

    async def _transition_to_spec_draft(self, ticket: Issue) -> bool:
        """Move ``ticket`` Backlog → Spec Draft. Returns False on error."""
        try:
            states = await self._get_state_ids()
            state_id = states.get(TicketState.SPEC_DRAFT.value)
            if state_id is None:
                log.error(
                    "no '%s' workflow state in this team; create it in "
                    "Linear (see SETUP step 1.1).",
                    TicketState.SPEC_DRAFT.value,
                )
                return False
            await self._linear.update_issue_state(ticket.id, state_id)
        except Exception:
            log.exception(
                "transition %s Backlog → Spec Draft failed",
                ticket.identifier,
            )
            return False
        return True

    async def _spawn_agent(self, ticket: Issue) -> None:
        """Run Spec Writer headless against the repo root.

        The agent only edits Linear (no git/code work), so it runs in
        the main checkout's ``cwd`` rather than in a worktree. That
        gives it filesystem access to ``docs/product-specs/`` and the
        rest of the documentation tree.
        """
        user_prompt = (
            f"Enrich Story {ticket.identifier}. The ticket has just "
            f"been transitioned to Spec Draft. Read it via the linear "
            f"MCP and follow tools/orchestrator/prompts/spec_writer.md."
        )
        result = await self._claude.run(
            agent_name="spec_writer",
            user_prompt=user_prompt,
            workspace=repo_root(),
        )
        if result.exit_code != 0:
            log.warning(
                "spec writer for %s exited %s: %s",
                ticket.identifier,
                result.exit_code,
                result.stderr[-500:],
            )
            self._db.record_learning_event(
                "spec_writer_failed", ticket.identifier
            )

    async def _get_state_ids(self) -> dict[str, str]:
        if self._state_ids is None:
            self._state_ids = await self._linear.list_team_states()
        return self._state_ids

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
from .workspace import WorkspaceManager

__all__ = ["ConsultantResolver"]

log = logging.getLogger(__name__)

QUESTION_LABEL = "needs-human-decision"

# ``ticket_attempts`` stage used to mark a resolved Question as already
# processed, so the daemon doesn't re-run the agent on it every tick.
_RESOLVER_STAGE = "resolver"


class ConsultantResolver:
    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        linear: LinearClient,
        claude: ClaudeRunner,
        workspaces: WorkspaceManager,
        poll_interval_seconds: float = 120.0,
    ) -> None:
        self._settings = settings
        self._db = db
        self._linear = linear
        self._claude = claude
        self._workspaces = workspaces
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
            # A resolved Question stays Done + needs-human-decision forever,
            # so without this guard the daemon would re-run the resolver
            # agent on it every tick (duplicate ADRs, wasted Claude usage).
            if self._db.get_attempts(issue.identifier, _RESOLVER_STAGE) > 0:
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
        #
        # Runs in a dedicated worktree (not the main checkout): the agent
        # does `git checkout -b harness/...` + commit + push, and doing
        # that in the main checkout would leave it stranded on a harness
        # branch (and risk sweeping unrelated changes into the ADR commit).
        workspace = await self._workspaces.create(f"resolver-{ticket_id}")
        try:
            result = await self._claude.run(
                agent_name="consultant_resolver",
                user_prompt=user_prompt,
                workspace=workspace.path,
            )
        finally:
            await self._workspaces.cleanup(workspace)
        # Mark processed only on success, so a transient failure retries on
        # the next tick but a clean resolution is never re-processed.
        if result.exit_code == 0:
            self._db.bump_attempt(ticket_id, _RESOLVER_STAGE)
        else:
            log.warning(
                "consultant resolver for %s exited %s: %s",
                ticket_id,
                result.exit_code,
                result.stderr[-500:],
            )

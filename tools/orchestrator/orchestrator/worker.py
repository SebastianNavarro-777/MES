"""Worker pool daemon.

Dequeues tickets in ``Ready for Agent`` state and runs the Worker agent
prompt against a per-ticket worktree. Concurrency is bounded by
``MAX_CONCURRENT_WORKERS``.

This module owns the *daemon shape* (the loop, the bounded pool, the
state transitions). The actual implementation work happens inside
Claude Code, driven by the ``worker.md`` prompt.

A ticket that reaches ``Ready for Agent`` while it *already has an open
PR* is not a fresh story — it is a re-queue of a PR the Reviewer rejected
(failed CI, missing AC test, etc.). The pool detects that and runs the
``worker_fix`` prompt against the PR's existing branch, so the failure is
fixed in place and the same PR is updated (CI re-runs) instead of a
duplicate PR being opened.
"""

from __future__ import annotations

import asyncio
import logging

from .claude_runner import ClaudeRunner
from .config import Settings
from .db import Database
from .github_client import GitHubClient
from .linear_client import LinearClient
from .state_machine import TicketState
from .workspace import Workspace, WorkspaceManager

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
        github: GitHubClient,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self._settings = settings
        self._db = db
        self._linear = linear
        self._claude = claude
        self._workspaces = workspaces
        self._github = github
        self._interval = poll_interval_seconds
        self._sem = asyncio.Semaphore(settings.MAX_CONCURRENT_WORKERS)
        # Tickets with an in-flight Worker run. The recolector keeps a
        # ticket in the queue as Ready for Agent until the agent moves it
        # on in Linear (which can take minutes), so without this guard a
        # later tick re-spawns the same ticket and collides on
        # ``workspace.create`` ("worktree already exists").
        self._in_flight: set[str] = set()

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
            if item.ticket_id in self._in_flight:
                continue
            # Claim the ticket at task-creation time (not after acquiring
            # the semaphore) so a tick that fires while earlier tasks are
            # still queued on the semaphore doesn't spawn duplicates.
            self._in_flight.add(item.ticket_id)
            tasks.append(asyncio.create_task(self._run_one(item.ticket_id)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_one(self, ticket_id: str) -> None:
        try:
            async with self._sem:
                plan = await self._plan_run(ticket_id)
                if plan is None:
                    # Couldn't prepare the run (transient gh / git error).
                    # Leave the ticket queued so a later tick retries it.
                    return
                workspace, agent_name, user_prompt = plan
                try:
                    result = await self._claude.run(
                        agent_name=agent_name,
                        user_prompt=user_prompt,
                        workspace=workspace.path,
                    )
                    if result.exit_code != 0:
                        log.warning(
                            "%s for %s exited %s: %s",
                            agent_name,
                            ticket_id,
                            result.exit_code,
                            result.stderr[-500:],
                        )
                        self._db.record_learning_event("ticket_failed", ticket_id)
                finally:
                    await self._workspaces.cleanup(workspace)
                    self._db.remove_work_item(ticket_id)
        finally:
            self._in_flight.discard(ticket_id)

    async def _plan_run(
        self, ticket_id: str
    ) -> tuple[Workspace, str, str] | None:
        """Decide fix-vs-fresh and set up the worktree + prompt.

        Returns ``(workspace, agent_name, user_prompt)`` or ``None`` when
        the run can't be prepared (a transient gh/git failure) — the caller
        then leaves the ticket queued for a later retry rather than risk a
        duplicate PR.
        """
        try:
            existing_pr = await self._github.find_open_pr_for_ticket(
                repo=self._settings.GITHUB_REPO, ticket_id=ticket_id
            )
        except Exception as exc:
            # If we can't tell whether a PR exists, do NOT start a fresh
            # implementation — that could open a second PR. Skip + retry.
            # Logged concisely (no traceback): the usual cause is a
            # transient gh hiccup, and a later tick retries. A *persistent*
            # failure means gh is missing/misconfigured — fix the env.
            log.warning(
                "open-PR lookup for %s failed (%s); skipping this run, will retry",
                ticket_id,
                exc,
            )
            return None

        if existing_pr is not None:
            # Re-queued after a rejected/failed PR → fix it in place.
            try:
                workspace = await self._workspaces.create_from_branch(
                    ticket_id, branch=existing_pr.head_ref
                )
            except Exception:
                log.exception(
                    "worktree-from-branch failed for %s (branch %s)",
                    ticket_id,
                    existing_pr.head_ref,
                )
                return None
            user_prompt = (
                f"Ticket {ticket_id} already has open PR #{existing_pr.number} "
                f"on branch {existing_pr.head_ref}, which failed review/CI. "
                f"You are in a worktree already checked out on that branch. "
                f"Read the PR's failing checks and the Reviewer's reject "
                f"comments, fix them, and push to the SAME branch — do NOT "
                f"open a new PR. Follow tools/orchestrator/prompts/worker_fix.md."
            )
            return workspace, "worker_fix", user_prompt

        # Fresh story: implement from main.
        try:
            workspace = await self._workspaces.create(ticket_id)
        except Exception:
            log.exception("workspace creation failed for %s", ticket_id)
            return None
        user_prompt = (
            f"Implement ticket {ticket_id}. "
            f"Read it via the linear MCP and follow tools/orchestrator/"
            f"prompts/worker.md."
        )
        return workspace, "worker", user_prompt

"""Tests for the Worker pool daemon.

Focus: the in-flight guard. The recolector keeps a ticket queued as
Ready for Agent until the agent moves it on in Linear, so overlapping
ticks must not spawn a second Worker on a ticket already being worked —
that used to collide on ``workspace.create`` ("worktree already exists").
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from tools.orchestrator.orchestrator.claude_runner import ClaudeRunner, ClaudeRunResult
from tools.orchestrator.orchestrator.config import Settings
from tools.orchestrator.orchestrator.db import Database
from tools.orchestrator.orchestrator.github_client import (
    GitHubClient,
    PullRequestSummary,
)
from tools.orchestrator.orchestrator.linear_client import LinearClient
from tools.orchestrator.orchestrator.state_machine import TicketState
from tools.orchestrator.orchestrator.worker import WorkerPool
from tools.orchestrator.orchestrator.workspace import Workspace, WorkspaceManager

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _Spawn:
    agent_name: str
    workspace: Path
    user_prompt: str


@dataclass
class FakeClaudeRunner:
    spawns: list[_Spawn] = field(default_factory=list)
    next_exit_code: int = 0
    next_stderr: str = ""
    next_duration: float = 0.0
    gate: asyncio.Event | None = None

    async def run(
        self,
        *,
        agent_name: str,
        user_prompt: str,
        workspace: Path,
        timeout: float = 60 * 30,
        extra_args: list[str] | None = None,
    ) -> ClaudeRunResult:
        self.spawns.append(_Spawn(agent_name, workspace, user_prompt))
        if self.gate is not None:
            await self.gate.wait()
        return ClaudeRunResult(
            exit_code=self.next_exit_code,
            stdout="",
            stderr=self.next_stderr,
            duration_seconds=self.next_duration,
        )


@dataclass
class FakeWorkspaceManager:
    created: list[str] = field(default_factory=list)
    created_from_branch: list[tuple[str, str]] = field(default_factory=list)
    cleaned: list[str] = field(default_factory=list)

    async def create(
        self, ticket_id: str, *, base_branch: str = "main"
    ) -> Workspace:
        self.created.append(ticket_id)
        return Workspace(
            ticket_id=ticket_id,
            path=Path(f"/tmp/{ticket_id}"),
            branch=f"feat/{ticket_id}-wip",
        )

    async def create_from_branch(
        self, ticket_id: str, *, branch: str
    ) -> Workspace:
        self.created_from_branch.append((ticket_id, branch))
        return Workspace(
            ticket_id=ticket_id, path=Path(f"/tmp/{ticket_id}"), branch=branch
        )

    async def cleanup(self, workspace: Workspace) -> None:
        self.cleaned.append(workspace.ticket_id)


@dataclass
class FakeGitHubClient:
    """Returns canned open/merged PR lookup results per ticket."""

    open_pr: PullRequestSummary | None = None
    merged_pr: PullRequestSummary | None = None
    raise_on_lookup: bool = False

    async def find_open_pr_for_ticket(
        self, *, repo: str, ticket_id: str
    ) -> PullRequestSummary | None:
        if self.raise_on_lookup:
            raise RuntimeError("simulated gh failure")
        return self.open_pr

    async def find_merged_pr_for_ticket(
        self, *, repo: str, ticket_id: str
    ) -> PullRequestSummary | None:
        if self.raise_on_lookup:
            raise RuntimeError("simulated gh failure")
        return self.merged_pr


def _pr(number: int, head_ref: str, *, state: str = "OPEN") -> PullRequestSummary:
    return PullRequestSummary(
        number=number,
        title="t",
        state=state,
        url=f"https://example/pr/{number}",
        head_ref=head_ref,
        base_ref="main",
        is_draft=False,
        labels=(),
    )


@dataclass
class _Issue:
    id: str
    identifier: str


@dataclass
class FakeLinear:
    """Minimal Linear stand-in for the already-merged advance path."""

    state_ids: dict[str, str] = field(default_factory=dict)
    transitions: list[tuple[str, str]] = field(default_factory=list)
    comments: list[tuple[str, str]] = field(default_factory=list)

    async def get_issue(self, identifier: str) -> _Issue:
        return _Issue(id=f"uuid-{identifier}", identifier=identifier)

    async def list_team_states(self) -> dict[str, str]:
        return dict(self.state_ids)

    async def update_issue_state(self, issue_id: str, new_state_id: str) -> None:
        self.transitions.append((issue_id, new_state_id))

    async def add_comment(self, issue_id: str, body: str) -> None:
        self.comments.append((issue_id, body))


class _NoLinear:
    """The Worker run path never touches Linear; this stands in for it."""


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(tmp_path / "queue.db")
    yield d
    d.close()


def _make_pool(
    settings: Settings,
    db: Database,
    claude: FakeClaudeRunner,
    workspaces: FakeWorkspaceManager,
    github: FakeGitHubClient | None = None,
    linear: FakeLinear | None = None,
) -> WorkerPool:
    return WorkerPool(
        settings=settings,
        db=db,
        linear=cast(LinearClient, linear or _NoLinear()),
        claude=cast(ClaudeRunner, claude),
        workspaces=cast(WorkspaceManager, workspaces),
        github=cast(GitHubClient, github or FakeGitHubClient()),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runs_a_queued_ticket_and_clears_it(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    db.enqueue("NSG-10", TicketState.READY_FOR_AGENT.value)
    claude = FakeClaudeRunner()
    workspaces = FakeWorkspaceManager()
    pool = _make_pool(settings, db, claude, workspaces)

    await pool.tick()

    assert len(claude.spawns) == 1
    assert workspaces.created == ["NSG-10"]
    assert workspaces.cleaned == ["NSG-10"]
    assert db.list_work_items(state=TicketState.READY_FOR_AGENT.value) == []
    assert pool._in_flight == set()


@pytest.mark.asyncio
async def test_overlapping_tick_does_not_double_spawn(
    tmp_path: Path, db: Database
) -> None:
    """A second tick while the first run is still in flight must not spawn
    a second Worker on the same ticket."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    db.enqueue("NSG-10", TicketState.READY_FOR_AGENT.value)
    gate = asyncio.Event()
    claude = FakeClaudeRunner(gate=gate)
    workspaces = FakeWorkspaceManager()
    pool = _make_pool(settings, db, claude, workspaces)

    # First tick: starts the run, which blocks on the gate.
    first = asyncio.create_task(pool.tick())
    # Let the run progress until it's actually blocked on the gate.
    for _ in range(1000):
        if claude.spawns:
            break
        await asyncio.sleep(0)
    assert pool._in_flight == {"NSG-10"}
    assert len(claude.spawns) == 1

    # Second tick while the first is still in flight: no new spawn.
    await pool.tick()
    assert len(claude.spawns) == 1
    assert workspaces.created == ["NSG-10"]

    # Release the gate and let the first run finish.
    gate.set()
    await first
    assert pool._in_flight == set()


@pytest.mark.asyncio
async def test_failed_run_records_learning_event(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    db.enqueue("NSG-10", TicketState.READY_FOR_AGENT.value)
    claude = FakeClaudeRunner(next_exit_code=1)
    workspaces = FakeWorkspaceManager()
    pool = _make_pool(settings, db, claude, workspaces)

    await pool.tick()

    events = db.list_learning_events()
    assert len(events) == 1
    assert events[0].event_type == "ticket_failed"
    assert events[0].ticket_id == "NSG-10"
    assert pool._in_flight == set()


@pytest.mark.asyncio
async def test_timed_out_run_posts_diagnostic_comment_on_ticket(
    tmp_path: Path, db: Database
) -> None:
    """A worker that exits non-zero (here: a timeout → exit 124) must leave a
    diagnostic breadcrumb on the Linear ticket, not just in the JSONL log, so
    Auditor/Gardener can triage the stall at a glance."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    db.enqueue("NSG-15", TicketState.READY_FOR_AGENT.value)
    claude = FakeClaudeRunner(
        next_exit_code=124,
        next_stderr="claude run timed out after 1800s",
        next_duration=1800.0,
    )
    workspaces = FakeWorkspaceManager()
    linear = FakeLinear()
    pool = _make_pool(settings, db, claude, workspaces, linear=linear)

    await pool.tick()

    # Learning event still recorded (unchanged behaviour).
    events = db.list_learning_events()
    assert [e.event_type for e in events] == ["ticket_failed"]
    # And a diagnostic comment landed on the ticket.
    assert len(linear.comments) == 1
    issue_id, body = linear.comments[0]
    assert issue_id == "uuid-NSG-15"
    assert "worker" in body  # names the agent that failed
    assert "tiempo límite" in body  # timeout (exit 124) phrased as a timeout
    assert pool._in_flight == set()


@pytest.mark.asyncio
async def test_failure_comment_failure_does_not_crash_pool(
    tmp_path: Path, db: Database
) -> None:
    """If Linear is unreachable when posting the diagnostic, the pool must
    still record the learning event and clear the ticket cleanly."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    db.enqueue("NSG-10", TicketState.READY_FOR_AGENT.value)
    claude = FakeClaudeRunner(next_exit_code=1)
    workspaces = FakeWorkspaceManager()
    # _NoLinear has no get_issue/add_comment → _comment_failure swallows it.
    pool = _make_pool(settings, db, claude, workspaces)

    await pool.tick()

    events = db.list_learning_events()
    assert [e.event_type for e in events] == ["ticket_failed"]
    assert db.list_work_items(state=TicketState.READY_FOR_AGENT.value) == []
    assert pool._in_flight == set()


# ---------------------------------------------------------------------------
# Fix mode: a re-queued ticket that already has an open PR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_ticket_with_no_pr_uses_worker_prompt(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    db.enqueue("NSG-10", TicketState.READY_FOR_AGENT.value)
    claude = FakeClaudeRunner()
    workspaces = FakeWorkspaceManager()
    github = FakeGitHubClient(open_pr=None)
    pool = _make_pool(settings, db, claude, workspaces, github)

    await pool.tick()

    assert claude.spawns[0].agent_name == "worker"
    assert workspaces.created == ["NSG-10"]
    assert workspaces.created_from_branch == []


@pytest.mark.asyncio
async def test_requeued_ticket_with_open_pr_runs_fix_mode(
    tmp_path: Path, db: Database
) -> None:
    """A ticket back in Ready for Agent that already has an open PR is a
    rejected PR being re-queued — fix it on the same branch, don't start
    over."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    db.enqueue("NSG-10", TicketState.READY_FOR_AGENT.value)
    claude = FakeClaudeRunner()
    workspaces = FakeWorkspaceManager()
    github = FakeGitHubClient(open_pr=_pr(7, "feat/NSG-10-add-orders"))
    pool = _make_pool(settings, db, claude, workspaces, github)

    await pool.tick()

    assert claude.spawns[0].agent_name == "worker_fix"
    assert workspaces.created_from_branch == [("NSG-10", "feat/NSG-10-add-orders")]
    assert workspaces.created == []  # no fresh branch from main
    assert "#7" in claude.spawns[0].user_prompt  # prompt carries the PR number
    assert "worker_fix.md" in claude.spawns[0].user_prompt
    assert db.list_work_items(state=TicketState.READY_FOR_AGENT.value) == []


@pytest.mark.asyncio
async def test_gh_lookup_failure_skips_run_and_keeps_ticket_queued(
    tmp_path: Path, db: Database
) -> None:
    """If we can't tell whether a PR exists, don't risk a duplicate PR:
    skip the run and leave the ticket queued for a later retry."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    db.enqueue("NSG-10", TicketState.READY_FOR_AGENT.value)
    claude = FakeClaudeRunner()
    workspaces = FakeWorkspaceManager()
    github = FakeGitHubClient(raise_on_lookup=True)
    pool = _make_pool(settings, db, claude, workspaces, github)

    await pool.tick()

    assert claude.spawns == []
    assert workspaces.created == []
    assert workspaces.created_from_branch == []
    # Ticket stays queued so a later tick retries it.
    assert len(db.list_work_items(state=TicketState.READY_FOR_AGENT.value)) == 1
    assert pool._in_flight == set()


@pytest.mark.asyncio
async def test_already_merged_pr_advances_to_ready_for_qa_without_rerun(
    tmp_path: Path, db: Database
) -> None:
    """A ticket re-queued with NO open PR but an *already-merged* PR (the
    Reviewer merged then crashed before Ready for QA) must NOT be
    re-implemented — finish the move to Ready for QA instead."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    db.enqueue("NSG-10", TicketState.READY_FOR_AGENT.value)
    claude = FakeClaudeRunner()
    workspaces = FakeWorkspaceManager()
    github = FakeGitHubClient(
        open_pr=None,
        merged_pr=_pr(7, "feat/NSG-10-add-orders", state="MERGED"),
    )
    linear = FakeLinear(state_ids={"Ready for QA": "state-qa"})
    pool = _make_pool(settings, db, claude, workspaces, github, linear)

    await pool.tick()

    # No implementation run at all.
    assert claude.spawns == []
    assert workspaces.created == []
    assert workspaces.created_from_branch == []
    # Ticket advanced to Ready for QA and dropped from the queue.
    assert linear.transitions == [("uuid-NSG-10", "state-qa")]
    assert len(linear.comments) == 1
    assert "#7" in linear.comments[0][1]
    assert db.list_work_items(state=TicketState.READY_FOR_AGENT.value) == []
    assert pool._in_flight == set()

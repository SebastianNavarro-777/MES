"""Tests for the Consultant Resolver daemon.

Contract that matters for consistency:

* A resolved Question (Done + ``needs-human-decision``) is processed
  exactly once — it stays in that state forever, so without a "processed"
  marker the daemon would re-run the agent every tick (duplicate ADRs).
* A failed resolver run is NOT marked processed, so it retries.
* Each run happens in an isolated worktree (never the main checkout).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from tools.orchestrator.orchestrator.claude_runner import ClaudeRunner, ClaudeRunResult
from tools.orchestrator.orchestrator.config import Settings
from tools.orchestrator.orchestrator.consultant_resolver import ConsultantResolver
from tools.orchestrator.orchestrator.db import Database
from tools.orchestrator.orchestrator.linear_client import Issue, LinearClient
from tools.orchestrator.orchestrator.workspace import Workspace, WorkspaceManager


@dataclass
class FakeLinearClient:
    done: list[Issue] = field(default_factory=list)

    async def list_issues_by_state(self, state: str) -> list[Issue]:
        return list(self.done) if state == "Done" else []


@dataclass
class FakeClaudeRunner:
    runs: int = 0
    next_exit_code: int = 0

    async def run(
        self,
        *,
        agent_name: str,
        user_prompt: str,
        workspace: Path,
        timeout: float = 60 * 30,
        extra_args: list[str] | None = None,
    ) -> ClaudeRunResult:
        self.runs += 1
        return ClaudeRunResult(
            exit_code=self.next_exit_code,
            stdout="",
            stderr="",
            duration_seconds=0.0,
        )


@dataclass
class FakeWorkspaceManager:
    created: list[str] = field(default_factory=list)
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

    async def cleanup(self, workspace: Workspace) -> None:
        self.cleaned.append(workspace.ticket_id)


def _question(identifier: str) -> Issue:
    return Issue(
        id=f"uuid-{identifier}",
        identifier=identifier,
        title="Q",
        description="",
        state="Done",
        labels=("type:question", "needs-human-decision"),
        parent_id=None,
    )


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(tmp_path / "queue.db")
    yield d
    d.close()


def _make(
    db: Database,
    linear: FakeLinearClient,
    claude: FakeClaudeRunner,
    workspaces: FakeWorkspaceManager,
    tmp_path: Path,
) -> ConsultantResolver:
    return ConsultantResolver(
        settings=Settings(WORKTREES_DIR=str(tmp_path / "wt")),
        db=db,
        linear=cast(LinearClient, linear),
        claude=cast(ClaudeRunner, claude),
        workspaces=cast(WorkspaceManager, workspaces),
    )


@pytest.mark.asyncio
async def test_resolved_question_processed_once_in_isolated_worktree(
    db: Database, tmp_path: Path
) -> None:
    linear = FakeLinearClient(done=[_question("NSG-42")])
    claude = FakeClaudeRunner(next_exit_code=0)
    workspaces = FakeWorkspaceManager()
    daemon = _make(db, linear, claude, workspaces, tmp_path)

    await daemon.tick()
    await daemon.tick()  # second tick: Question still Done+needs-human

    assert claude.runs == 1  # NOT re-processed
    assert workspaces.created == ["resolver-NSG-42"]  # isolated worktree
    assert workspaces.cleaned == ["resolver-NSG-42"]


@pytest.mark.asyncio
async def test_failed_resolution_is_retried(db: Database, tmp_path: Path) -> None:
    linear = FakeLinearClient(done=[_question("NSG-42")])
    claude = FakeClaudeRunner(next_exit_code=1)  # agent fails
    workspaces = FakeWorkspaceManager()
    daemon = _make(db, linear, claude, workspaces, tmp_path)

    await daemon.tick()
    await daemon.tick()

    assert claude.runs == 2  # not marked processed → retried


@pytest.mark.asyncio
async def test_non_question_done_ticket_ignored(
    db: Database, tmp_path: Path
) -> None:
    plain = Issue(
        id="uuid-NSG-1",
        identifier="NSG-1",
        title="story",
        description="",
        state="Done",
        labels=("type:story",),
        parent_id=None,
    )
    linear = FakeLinearClient(done=[plain])
    claude = FakeClaudeRunner()
    workspaces = FakeWorkspaceManager()
    daemon = _make(db, linear, claude, workspaces, tmp_path)

    await daemon.tick()

    assert claude.runs == 0

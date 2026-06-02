"""Per-ticket git worktrees.

Each Worker run executes inside a dedicated worktree under
``$WORKTREES_DIR/<ticket-id>/``. This isolates implementations so two
Workers never collide on the same files, and makes orphaned cleanup
trivial (just delete the worktree directory).

We shell out to ``git worktree`` rather than using a Python git library
because the repo is the user's, not ours, and we want behaviour to match
what the user sees with their own git.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Workspace",
    "WorkspaceError",
    "WorkspaceManager",
]


@dataclass(frozen=True)
class Workspace:
    ticket_id: str
    path: Path
    branch: str


class WorkspaceError(RuntimeError):
    """Raised when git worktree operations fail."""


class WorkspaceManager:
    """Manages worktrees for one orchestrator process."""

    def __init__(self, *, repo_root: Path, worktrees_dir: Path) -> None:
        self.repo_root = repo_root
        self.worktrees_dir = worktrees_dir
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    async def create(
        self, ticket_id: str, *, base_branch: str = "main"
    ) -> Workspace:
        """Create a new worktree for the ticket on a fresh feature branch.

        The branch name is derived from the ticket id; the agent prompts
        say the Worker re-creates it explicitly anyway, so this is the
        starting point.
        """
        wt_path = self.worktrees_dir / ticket_id
        if wt_path.exists():
            raise WorkspaceError(
                f"worktree already exists at {wt_path}; run cleanup first"
            )
        branch = f"feat/{ticket_id}-wip"
        await self._git(
            "worktree",
            "add",
            "-b",
            branch,
            str(wt_path),
            base_branch,
            cwd=self.repo_root,
        )
        return Workspace(ticket_id=ticket_id, path=wt_path, branch=branch)

    async def create_from_branch(
        self, ticket_id: str, *, branch: str
    ) -> Workspace:
        """Create a worktree checked out on an existing PR branch.

        Used for *fix* runs: a ticket whose PR failed review/CI is
        re-worked on the same branch rather than starting from ``main``,
        so the existing PR is updated in place (CI re-runs) instead of a
        duplicate PR being opened.

        We fetch the branch from ``origin`` first because the orchestrator's
        main checkout may not have the Worker's pushed branch locally, then
        reset a local branch of the same name to the remote tip so the
        worktree reflects exactly what is on the PR.
        """
        wt_path = self.worktrees_dir / ticket_id
        if wt_path.exists():
            raise WorkspaceError(
                f"worktree already exists at {wt_path}; run cleanup first"
            )
        await self._git("fetch", "origin", branch, cwd=self.repo_root)
        await self._git(
            "worktree",
            "add",
            "-B",
            branch,
            str(wt_path),
            f"origin/{branch}",
            cwd=self.repo_root,
        )
        return Workspace(ticket_id=ticket_id, path=wt_path, branch=branch)

    async def cleanup(self, workspace: Workspace) -> None:
        """Remove the worktree and delete its directory."""
        with contextlib.suppress(WorkspaceError):
            await self._git(
                "worktree",
                "remove",
                str(workspace.path),
                "--force",
                cwd=self.repo_root,
            )
        if workspace.path.exists():
            shutil.rmtree(workspace.path, ignore_errors=True)

    async def list_orphans(self) -> list[Path]:
        """Worktree directories that exist on disk but git no longer tracks.

        Useful for the orchestrator's startup reconciliation.
        """
        existing = (
            {p for p in self.worktrees_dir.iterdir() if p.is_dir()}
            if self.worktrees_dir.exists()
            else set()
        )
        out = await self._git(
            "worktree", "list", "--porcelain", cwd=self.repo_root
        )
        tracked: set[Path] = set()
        for line in out.splitlines():
            if line.startswith("worktree "):
                tracked.add(Path(line[len("worktree ") :]).resolve())
        orphans: list[Path] = []
        for p in existing:
            if p.resolve() not in tracked:
                orphans.append(p)
        return orphans

    # -- helper --------------------------------------------------------------

    async def _git(self, *args: str, cwd: Path) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_b, stderr_b = await proc.communicate()
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise WorkspaceError(
                f"`git {' '.join(args)}` failed: {stderr.strip()[:300]}"
            )
        return stdout

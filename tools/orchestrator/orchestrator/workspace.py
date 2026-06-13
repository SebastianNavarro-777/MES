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
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .proc_utils import resolve_executable

log = logging.getLogger(__name__)

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

    def __init__(
        self,
        *,
        repo_root: Path,
        worktrees_dir: Path,
        git_binary: str = "git",
    ) -> None:
        self.repo_root = repo_root
        self.worktrees_dir = worktrees_dir
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        # Resolve to an absolute path so asyncio can spawn it on Windows
        # (create_subprocess_exec ignores PATHEXT → bare "git" can miss
        # the git shim and raise FileNotFoundError).
        self._git_bin = resolve_executable(git_binary)

    async def create(
        self, ticket_id: str, *, base_branch: str = "main"
    ) -> Workspace:
        """Create a new worktree for the ticket on a fresh feature branch.

        The branch name is derived from the ticket id; the agent prompts
        say the Worker re-creates it explicitly anyway, so this is the
        starting point.

        Idempotent: any stale worktree left at this path by a previous
        unclean shutdown is force-cleared first, and the branch is
        (re)created with ``-B`` rather than ``-b`` — so a leftover dir or
        branch never stalls the ticket, it just gets recreated.
        """
        wt_path = self.worktrees_dir / ticket_id
        await self._force_clear(wt_path)
        branch = f"feat/{ticket_id}-wip"
        await self._git(
            "worktree",
            "add",
            "-B",
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

        Idempotent: a stale worktree at this path is force-cleared first.
        """
        wt_path = self.worktrees_dir / ticket_id
        await self._force_clear(wt_path)
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
        await self._force_clear(workspace.path)

    async def _force_clear(self, wt_path: Path) -> None:
        """Best-effort removal of any worktree (tracked or orphaned) at a path.

        De-registers it from git, deletes the directory, and prunes stale
        metadata. Suppresses errors so a partially-removed or untracked
        leftover never blocks the caller — this is what makes ``create``
        idempotent and ``purge_all`` safe.

        If the directory survives the first delete it is almost always
        because a process the agent spawned is still holding it open — a
        Vite dev server + esbuild started for UI evidence are the usual
        culprits, and on Windows they orphan when the agent exits. We kill
        whatever lives under the path, then retry the delete. Without this,
        the leftover dir makes the next ``git worktree add`` fail with
        "<path> already exists" and the ticket stalls.
        """
        with contextlib.suppress(WorkspaceError):
            await self._git(
                "worktree", "remove", str(wt_path), "--force", cwd=self.repo_root
            )
        if wt_path.exists():
            shutil.rmtree(wt_path, ignore_errors=True)
        if wt_path.exists():
            await self._kill_processes_under(wt_path)
            for _ in range(3):
                shutil.rmtree(wt_path, ignore_errors=True)
                if not wt_path.exists():
                    break
                await asyncio.sleep(0.3)
            if wt_path.exists():
                log.warning(
                    "could not fully remove worktree dir %s (still locked?)",
                    wt_path,
                )
        with contextlib.suppress(WorkspaceError):
            await self._git("worktree", "prune", cwd=self.repo_root)

    async def _kill_processes_under(self, wt_path: Path) -> None:
        """Kill any process whose command line / image lives under ``wt_path``.

        Frees a worktree dir held open by an orphaned dev server. Best-effort
        and never raises: if the lookup tool is missing or matches nothing,
        the subsequent rmtree retry simply may not succeed.
        """
        target = str(wt_path)

        def _run() -> None:
            try:
                if sys.platform == "win32":
                    ps = (
                        "Get-CimInstance Win32_Process | Where-Object { "
                        "$_.CommandLine -like $p -or $_.ExecutablePath -like $p "
                        "} | ForEach-Object { Stop-Process -Id $_.ProcessId "
                        "-Force -ErrorAction SilentlyContinue }"
                    )
                    subprocess.run(
                        [
                            "powershell",
                            "-NoProfile",
                            "-NonInteractive",
                            "-Command",
                            f"$p='*{target}*'; {ps}",
                        ],
                        capture_output=True,
                        timeout=20,
                    )
                else:
                    subprocess.run(
                        ["pkill", "-9", "-f", target],
                        capture_output=True,
                        timeout=20,
                    )
            except Exception:
                pass

        await asyncio.to_thread(_run)

    async def purge_all(self) -> int:
        """Remove every worktree dir under ``worktrees_dir``. Returns the count.

        Called at startup: no Worker runs yet, so any worktree on disk is
        residue from a previous (possibly Ctrl-C'd) run. Purging here means
        a stale worktree can never put a ticket into limbo on the next run.
        """
        if not self.worktrees_dir.exists():
            return 0
        removed = 0
        for p in list(self.worktrees_dir.iterdir()):
            if p.is_dir():
                await self._force_clear(p)
                removed += 1
        return removed

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
            self._git_bin,
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

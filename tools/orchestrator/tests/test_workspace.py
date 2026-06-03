"""Tests for WorkspaceManager binary resolution.

The git-shelling worktree operations need a real repo, so they're left to
integration runs; here we lock in that ``git`` is resolved to an absolute
path (asyncio ignores PATHEXT on Windows → a bare "git" can raise
FileNotFoundError).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tools.orchestrator.orchestrator.workspace import WorkspaceManager


def test_workspace_manager_resolves_git_binary(tmp_path: Path) -> None:
    wm = WorkspaceManager(
        repo_root=tmp_path,
        worktrees_dir=tmp_path / "wt",
        git_binary="python",
    )
    assert shutil.which(wm._git_bin) == wm._git_bin or wm._git_bin == "python"


def _init_repo(path: Path) -> None:
    """Create a minimal git repo with one commit on a `main` branch."""
    path.mkdir(parents=True, exist_ok=True)

    def g(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    g("init", "-b", "main")
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "Test")
    g("config", "commit.gpgsign", "false")
    (path / "README.md").write_text("hi", encoding="utf-8")
    g("add", "-A")
    g("commit", "-m", "init")


@pytest.mark.asyncio
async def test_create_is_idempotent_over_stale_worktree(tmp_path: Path) -> None:
    """Creating a worktree when a stale one is already at the path must not
    raise — the leftover is force-cleared and recreated. This is what keeps
    a ticket from going into limbo after an unclean shutdown."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    wm = WorkspaceManager(repo_root=repo, worktrees_dir=repo / "worktrees")

    ws1 = await wm.create("NSG-1")
    assert ws1.path.exists()

    # Second create over the existing worktree: idempotent, no raise.
    ws2 = await wm.create("NSG-1")
    assert ws2.path.exists()
    assert ws2.branch == "feat/NSG-1-wip"


@pytest.mark.asyncio
async def test_purge_all_removes_stale_worktrees(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    wm = WorkspaceManager(repo_root=repo, worktrees_dir=repo / "worktrees")

    a = await wm.create("NSG-1")
    b = await wm.create("NSG-2")
    assert a.path.exists() and b.path.exists()

    removed = await wm.purge_all()

    assert removed == 2
    assert not a.path.exists()
    assert not b.path.exists()


@pytest.mark.asyncio
async def test_purge_all_on_empty_is_zero(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    wm = WorkspaceManager(repo_root=repo, worktrees_dir=repo / "worktrees")
    assert await wm.purge_all() == 0

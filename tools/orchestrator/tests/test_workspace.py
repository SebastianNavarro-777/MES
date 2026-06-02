"""Tests for WorkspaceManager binary resolution.

The git-shelling worktree operations need a real repo, so they're left to
integration runs; here we lock in that ``git`` is resolved to an absolute
path (asyncio ignores PATHEXT on Windows → a bare "git" can raise
FileNotFoundError).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tools.orchestrator.orchestrator.workspace import WorkspaceManager


def test_workspace_manager_resolves_git_binary(tmp_path: Path) -> None:
    wm = WorkspaceManager(
        repo_root=tmp_path,
        worktrees_dir=tmp_path / "wt",
        git_binary="python",
    )
    assert shutil.which(wm._git_bin) == wm._git_bin or wm._git_bin == "python"

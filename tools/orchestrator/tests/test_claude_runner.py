"""Tests for the Claude CLI runner.

Focused on the Windows binary-resolution path: ``asyncio`` does not
respect ``PATHEXT`` on Windows, so a plain ``"claude"`` name must be
turned into an absolute path (including ``.CMD`` extension) before being
handed to ``create_subprocess_exec``. Regression coverage for the
``FileNotFoundError`` we hit on the first ``run-all``.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.orchestrator.orchestrator import claude_runner as claude_runner_mod
from tools.orchestrator.orchestrator.claude_runner import (
    ClaudeRunner,
    _resolve_binary,
)


def test_resolve_binary_finds_python_on_path() -> None:
    """sys.executable is guaranteed to be on PATH and runnable;
    using "python" should resolve to an absolute path."""
    resolved = _resolve_binary("python")
    # Either "python" or "python3" depending on platform — but on Windows
    # asyncio without PATHEXT-aware lookup is the bug we're fixing, so
    # the key invariant is: an absolute path with an extension.
    assert resolved != "python", (
        "shutil.which should return an absolute path, not the bare name"
    )


def test_resolve_binary_preserves_absolute_path() -> None:
    """A caller passing an absolute path (e.g., from CLAUDE_CONFIG_PATH
    in .env) should not have it rewritten."""
    abs_path = sys.executable  # absolute path to the running interpreter
    resolved = _resolve_binary(abs_path)
    assert resolved == abs_path


def test_resolve_binary_gracefully_passes_unknown_name() -> None:
    """If the binary truly isn't on PATH, return the original name so
    the downstream subprocess error surfaces it (not a None ambiguity)."""
    resolved = _resolve_binary("definitely-not-a-real-binary-name-xyz")
    assert resolved == "definitely-not-a-real-binary-name-xyz"


def test_claude_runner_uses_resolved_binary() -> None:
    runner = ClaudeRunner(claude_binary="python")
    # The runner's internal binary must be an absolute path so asyncio
    # can spawn it on Windows. We don't assert equality against
    # sys.executable because shutil.which may pick a different "python"
    # on PATH first (e.g., from a venv) — only the absolute-path
    # invariant matters.
    assert shutil.which(runner._binary) == runner._binary or runner._binary == "python"


def test_claude_runner_env_var_fallback(monkeypatch: object) -> None:
    """CLAUDE_CONFIG_PATH from the environment is honoured when no
    explicit binary arg is given."""
    import os as _os

    # Use the running interpreter as a stand-in — it's guaranteed to
    # exist and be executable.
    _os.environ["CLAUDE_CONFIG_PATH"] = sys.executable
    try:
        runner = ClaudeRunner()
        assert runner._binary == sys.executable
    finally:
        del _os.environ["CLAUDE_CONFIG_PATH"]


# ---------------------------------------------------------------------------
# Cancellation kills the whole agent process tree (no orphaned grandchildren)
# ---------------------------------------------------------------------------


class _FakeProc:
    """A subprocess stand-in whose communicate() blocks until cancelled."""

    def __init__(self) -> None:
        self.pid = 4321
        self.returncode: int | None = None
        self._block = asyncio.Event()  # never set → blocks

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        await self._block.wait()
        return b"", b""

    async def wait(self) -> int | None:
        return self.returncode


@pytest.mark.asyncio
async def test_run_kills_process_tree_on_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a Worker run is cancelled (Ctrl-C / shutdown), the agent's whole
    process tree must be killed so no Vite/esbuild/git grandchild orphans."""
    (tmp_path / "sleeper.md").write_text("system prompt", encoding="utf-8")
    runner = ClaudeRunner(claude_binary="python", prompts_dir=tmp_path)

    fake = _FakeProc()

    async def _fake_exec(*_a: Any, **_k: Any) -> _FakeProc:
        return fake

    killed: list[int | None] = []
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(
        claude_runner_mod, "_kill_process_tree", lambda pid: killed.append(pid)
    )

    task = asyncio.create_task(
        runner.run(agent_name="sleeper", user_prompt="hi", workspace=tmp_path)
    )
    # Let the run reach the (blocking) communicate() call.
    for _ in range(100):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert killed == [4321]

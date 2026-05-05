"""Spawn Claude Code headless with a system prompt.

The orchestrator never invokes the Claude API directly. Instead, it
shells out to the user's ``claude`` CLI (which carries the user's
Pro/Max subscription via the system keychain). This module handles the
subprocess plumbing and surfaces a small typed result.

Each agent — Worker, Reviewer, QA Smoke, etc. — is just a different
system prompt fed to the same ``claude`` binary inside a per-ticket
workspace.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ClaudeRunResult",
    "ClaudeRunner",
    "ClaudeRunnerError",
]

# The orchestrator's prompts dir is at tools/orchestrator/prompts/, relative
# to this file's package root. Resolve once at import time.
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass(frozen=True)
class ClaudeRunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


class ClaudeRunnerError(RuntimeError):
    """Raised when ``claude`` cannot be launched (binary missing, etc.)."""


class ClaudeRunner:
    """Async runner that launches Claude Code headless against a workspace."""

    def __init__(
        self,
        *,
        claude_binary: str | None = None,
        prompts_dir: Path = PROMPTS_DIR,
    ) -> None:
        self._binary = claude_binary or os.environ.get("CLAUDE_CONFIG_PATH") or "claude"
        self._prompts_dir = prompts_dir

    def prompt_path(self, agent_name: str) -> Path:
        """Resolve the on-disk system-prompt file for the given agent."""
        path = self._prompts_dir / f"{agent_name}.md"
        if not path.is_file():
            raise ClaudeRunnerError(f"prompt file not found: {path}")
        return path

    async def run(
        self,
        *,
        agent_name: str,
        user_prompt: str,
        workspace: Path,
        timeout: float = 60 * 30,
        extra_args: list[str] | None = None,
    ) -> ClaudeRunResult:
        """Launch ``claude`` with the agent's system prompt + a user prompt.

        Returns once the process exits or the timeout fires.
        """
        system_prompt_path = self.prompt_path(agent_name)
        args: list[str] = [
            self._binary,
            "--print",  # non-interactive
            "--system-prompt-file",
            str(system_prompt_path),
        ]
        if extra_args:
            args.extend(extra_args)
        # User prompt goes via stdin so we don't have to escape long strings.
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace,
        )
        loop = asyncio.get_running_loop()
        start = loop.time()
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=user_prompt.encode("utf-8")),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ClaudeRunResult(
                exit_code=124,  # standard timeout exit code
                stdout="",
                stderr=f"claude run timed out after {timeout}s",
                duration_seconds=timeout,
            )
        return ClaudeRunResult(
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            duration_seconds=loop.time() - start,
        )

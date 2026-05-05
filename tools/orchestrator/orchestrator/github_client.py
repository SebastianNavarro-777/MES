"""Wrapper over the ``gh`` CLI.

We shell out to ``gh`` instead of using the GitHub REST API directly so
the orchestrator inherits the user's existing ``gh auth login``. This
also matches what the agent prompts assume when they say
"open a PR via ``gh pr create``".

All methods are async. They use :func:`asyncio.create_subprocess_exec`
so daemons remain non-blocking.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from dataclasses import dataclass
from typing import Any

__all__ = [
    "GitHubClient",
    "GitHubClientError",
    "PullRequestSummary",
]


@dataclass(frozen=True)
class PullRequestSummary:
    number: int
    title: str
    state: str  # "OPEN" | "MERGED" | "CLOSED"
    url: str
    head_ref: str
    base_ref: str
    is_draft: bool
    labels: tuple[str, ...]


class GitHubClientError(RuntimeError):
    """Raised when ``gh`` returns non-zero or unexpected output."""


class GitHubClient:
    """Async wrapper over the ``gh`` CLI.

    ``gh_binary`` defaults to ``gh`` on $PATH; tests override it to point
    at a fake script for hermetic runs.
    """

    def __init__(self, *, gh_binary: str = "gh") -> None:
        self._gh = gh_binary

    # -- low-level subprocess helper ----------------------------------------

    async def _run(self, *args: str, cwd: str | None = None) -> str:
        proc = await asyncio.create_subprocess_exec(
            self._gh,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout_b, stderr_b = await proc.communicate()
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise GitHubClientError(
                f"`gh {' '.join(shlex.quote(a) for a in args)}` failed "
                f"(rc={proc.returncode}): {stderr.strip()[:500]}"
            )
        return stdout

    # -- pull requests ------------------------------------------------------

    async def create_pr(
        self,
        *,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
        cwd: str | None = None,
        draft: bool = False,
    ) -> str:
        """Create a PR; returns the PR URL printed by ``gh``."""
        args: list[str] = [
            "pr",
            "create",
            "--repo",
            repo,
            "--head",
            head,
            "--base",
            base,
            "--title",
            title,
            "--body",
            body,
        ]
        if draft:
            args.append("--draft")
        out = await self._run(*args, cwd=cwd)
        return out.strip()

    async def view_pr(
        self, *, repo: str, number: int, cwd: str | None = None
    ) -> PullRequestSummary:
        """Read PR metadata as a typed object via ``gh pr view --json``."""
        out = await self._run(
            "pr",
            "view",
            str(number),
            "--repo",
            repo,
            "--json",
            "number,title,state,url,headRefName,baseRefName,isDraft,labels",
            cwd=cwd,
        )
        data: object = json.loads(out)
        if not isinstance(data, dict):
            raise GitHubClientError(f"unexpected JSON from gh pr view: {data!r}")
        labels_list = data.get("labels", [])
        labels: tuple[str, ...] = ()
        if isinstance(labels_list, list):
            labels = tuple(
                str(label.get("name", ""))
                for label in labels_list
                if isinstance(label, dict)
            )
        return PullRequestSummary(
            number=int(data.get("number", number)),
            title=str(data.get("title", "")),
            state=str(data.get("state", "")),
            url=str(data.get("url", "")),
            head_ref=str(data.get("headRefName", "")),
            base_ref=str(data.get("baseRefName", "")),
            is_draft=bool(data.get("isDraft", False)),
            labels=labels,
        )

    async def merge_pr(
        self,
        *,
        repo: str,
        number: int,
        squash: bool = True,
        delete_branch: bool = True,
        cwd: str | None = None,
    ) -> None:
        args: list[str] = ["pr", "merge", str(number), "--repo", repo]
        if squash:
            args.append("--squash")
        if delete_branch:
            args.append("--delete-branch")
        await self._run(*args, cwd=cwd)

    async def comment_on_pr(
        self, *, repo: str, number: int, body: str, cwd: str | None = None
    ) -> None:
        await self._run(
            "pr",
            "comment",
            str(number),
            "--repo",
            repo,
            "--body",
            body,
            cwd=cwd,
        )

    async def revert_pr(
        self, *, repo: str, number: int, title: str, cwd: str | None = None
    ) -> None:
        """Use ``gh pr revert`` to auto-create + merge a revert PR."""
        await self._run(
            "pr",
            "revert",
            str(number),
            "--repo",
            repo,
            "--title",
            title,
            cwd=cwd,
        )

    async def list_recent_merged_prs(
        self, *, repo: str, limit: int = 30, cwd: str | None = None
    ) -> list[dict[str, Any]]:
        out = await self._run(
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--limit",
            str(limit),
            "--json",
            "number,title,headRefName,mergedAt,url",
            cwd=cwd,
        )
        data: object = json.loads(out)
        if not isinstance(data, list):
            raise GitHubClientError("gh pr list did not return a list")
        return [d for d in data if isinstance(d, dict)]

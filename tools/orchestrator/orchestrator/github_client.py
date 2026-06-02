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

import httpx

from .proc_utils import resolve_executable

__all__ = [
    "GitHubClient",
    "GitHubClientError",
    "PullRequestSummary",
    "branch_matches_ticket",
]


def branch_matches_ticket(head_ref: str, ticket_id: str) -> bool:
    """Whether a PR head branch belongs to a ticket.

    Worker branches are ``<type>/<TICKET-ID>-<slug>`` (``feat``/``fix``/
    ``refactor``/``harness``) or occasionally bare ``<TICKET-ID>-<slug>``.
    We match the ticket segment with a boundary so ``NSG-1`` does not
    match ``NSG-10``'s branch.
    """
    segment = head_ref.split("/")[-1]
    return segment == ticket_id or segment.startswith(f"{ticket_id}-")


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
    """GitHub access for the orchestrator.

    Most mutating operations shell out to the ``gh`` CLI (so they inherit
    the user's ``gh auth login``). Read-only PR lookups go over the REST
    API with ``token`` instead, because the daemon host may not have the
    ``gh`` binary installed at all — the Claude agents create PRs through
    the GitHub MCP, not the CLI — yet ``GITHUB_TOKEN`` is always present
    in live mode.

    ``gh_binary`` defaults to ``gh`` on $PATH; tests override it to point
    at a fake script for hermetic runs.
    """

    def __init__(
        self,
        *,
        gh_binary: str = "gh",
        token: str | None = None,
        api_base: str = "https://api.github.com",
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        # Resolve to an absolute path so asyncio can spawn it on Windows
        # (create_subprocess_exec ignores PATHEXT, so a bare "gh" misses
        # the gh.cmd/gh.exe shim → FileNotFoundError).
        self._gh = resolve_executable(gh_binary)
        self._token = token
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

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

    async def check_auth(self, *, repo: str) -> str:
        """One-shot REST credential check for startup diagnostics.

        Returns ``"ok"`` when the token can read ``repo``, or a short
        human-readable diagnostic otherwise. Never raises — startup must
        not crash just because GitHub is misconfigured.
        """
        if not self._token:
            return "no GITHUB_TOKEN set"
        if not repo:
            return "no GITHUB_REPO set"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            response = await self._http().get(
                f"{self._api_base}/repos/{repo}",
                headers=headers,
                timeout=self._timeout,
            )
        except Exception as exc:  # network, DNS, etc.
            return f"unreachable ({exc})"
        if response.status_code == 200:
            return "ok"
        if response.status_code == 401:
            return "token INVALID (401 Bad credentials) — regenerate it"
        if response.status_code == 404:
            return f"repo {repo} not found or token lacks access (404)"
        return f"HTTP {response.status_code}"

    async def find_open_pr_for_ticket(
        self, *, repo: str, ticket_id: str
    ) -> PullRequestSummary | None:
        """Return the open PR whose branch belongs to ``ticket_id``, if any.

        Used by the Worker pool to tell a *fix* (a ticket re-queued after
        its PR failed review/CI, which already has an open PR) from a
        *fresh* implementation (a ticket with no PR yet). Uses the REST
        API (not the ``gh`` CLI) so it works on hosts without ``gh``.
        """
        if not self._token:
            raise GitHubClientError(
                "GITHUB_TOKEN required to query open pull requests"
            )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        response = await self._http().get(
            f"{self._api_base}/repos/{repo}/pulls",
            params={"state": "open", "per_page": 100},
            headers=headers,
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            raise GitHubClientError(
                f"GitHub HTTP {response.status_code}: {response.text[:200]}"
            )
        data: object = response.json()
        if not isinstance(data, list):
            raise GitHubClientError("GitHub pulls endpoint did not return a list")
        for entry in data:
            if not isinstance(entry, dict):
                continue
            head = entry.get("head")
            head_ref = str(head.get("ref", "")) if isinstance(head, dict) else ""
            if not branch_matches_ticket(head_ref, ticket_id):
                continue
            base = entry.get("base")
            base_ref = str(base.get("ref", "")) if isinstance(base, dict) else ""
            labels_list = entry.get("labels", [])
            labels: tuple[str, ...] = ()
            if isinstance(labels_list, list):
                labels = tuple(
                    str(label.get("name", ""))
                    for label in labels_list
                    if isinstance(label, dict)
                )
            return PullRequestSummary(
                number=int(entry.get("number", 0)),
                title=str(entry.get("title", "")),
                state=str(entry.get("state", "")).upper(),
                url=str(entry.get("html_url", "")),
                head_ref=head_ref,
                base_ref=base_ref,
                is_draft=bool(entry.get("draft", False)),
                labels=labels,
            )
        return None

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

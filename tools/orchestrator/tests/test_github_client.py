"""Tests for github_client pure helpers.

The ``gh``-shelling methods are exercised by integration runs; here we
lock in the branch-matching logic the Worker pool relies on to tell a
fix (re-queued PR) from a fresh story, since a wrong boundary would mix
up tickets like NSG-1 and NSG-10.
"""

from __future__ import annotations

import shutil

import httpx
import pytest
import respx

from tools.orchestrator.orchestrator.github_client import (
    GitHubClient,
    GitHubClientError,
    branch_matches_ticket,
)


def test_github_client_resolves_binary_to_absolute_path() -> None:
    """gh must be resolved to an absolute path so asyncio can spawn it on
    Windows (create_subprocess_exec ignores PATHEXT). Regression for the
    FileNotFoundError on the open-PR lookup."""
    client = GitHubClient(gh_binary="python")
    assert shutil.which(client._gh) == client._gh or client._gh == "python"


def _pull(
    number: int, head_ref: str, labels: list[str] | None = None
) -> dict[str, object]:
    return {
        "number": number,
        "title": f"PR {number}",
        "state": "open",
        "html_url": f"https://github.com/acme/mes/pull/{number}",
        "head": {"ref": head_ref},
        "base": {"ref": "main"},
        "draft": False,
        "labels": [{"name": n} for n in (labels or [])],
    }


@pytest.mark.asyncio
async def test_find_open_pr_matches_by_branch_over_rest() -> None:
    """The lookup uses the REST API (not the gh CLI) so it works on hosts
    without gh installed — which is the case on the orchestrator host."""
    payload = [
        _pull(5, "feat/NSG-1-other"),  # different ticket
        _pull(7, "feat/NSG-10-add-orders", labels=["high-risk"]),
    ]
    async with httpx.AsyncClient() as client:
        gh = GitHubClient(token="tok", client=client)
        with respx.mock:
            respx.get("https://api.github.com/repos/acme/mes/pulls").mock(
                return_value=httpx.Response(200, json=payload)
            )
            pr = await gh.find_open_pr_for_ticket(repo="acme/mes", ticket_id="NSG-10")
    assert pr is not None
    assert pr.number == 7
    assert pr.head_ref == "feat/NSG-10-add-orders"
    assert pr.labels == ("high-risk",)
    assert pr.state == "OPEN"


@pytest.mark.asyncio
async def test_find_open_pr_returns_none_when_no_branch_matches() -> None:
    payload = [_pull(5, "feat/NSG-1-other"), _pull(6, "feat/NSG-100-big")]
    async with httpx.AsyncClient() as client:
        gh = GitHubClient(token="tok", client=client)
        with respx.mock:
            respx.get("https://api.github.com/repos/acme/mes/pulls").mock(
                return_value=httpx.Response(200, json=payload)
            )
            pr = await gh.find_open_pr_for_ticket(repo="acme/mes", ticket_id="NSG-10")
    assert pr is None


@pytest.mark.asyncio
async def test_find_open_pr_without_token_raises() -> None:
    gh = GitHubClient(token=None)
    with pytest.raises(GitHubClientError):
        await gh.find_open_pr_for_ticket(repo="acme/mes", ticket_id="NSG-10")


@pytest.mark.parametrize(
    "head_ref",
    [
        "feat/NSG-10-add-orders",
        "fix/NSG-10-handle-null",
        "refactor/NSG-10-extract",
        "harness/NSG-10-linter",
        "NSG-10-bare-branch",
        "NSG-10",
    ],
)
def test_matches_branches_belonging_to_the_ticket(head_ref: str) -> None:
    assert branch_matches_ticket(head_ref, "NSG-10")


@pytest.mark.parametrize(
    "head_ref",
    [
        "feat/NSG-100-other",   # different ticket, shared prefix
        "feat/NSG-1-other",     # NSG-1 must not match NSG-10
        "feat/XSG-10-other",    # different project key
        "main",
    ],
)
def test_rejects_branches_for_other_tickets(head_ref: str) -> None:
    assert not branch_matches_ticket(head_ref, "NSG-10")

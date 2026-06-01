"""Tests for the Linear client.

Uses ``respx`` to mock the GraphQL endpoint. We never make real network
calls. The tests cover happy paths and error paths for the queries and
mutations the orchestrator actually uses.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from tools.orchestrator.orchestrator.linear_client import (
    LINEAR_GRAPHQL_URL,
    Issue,
    LinearClient,
    LinearClientError,
)


def _ok(data: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def _err(status: int = 401, body: str = "unauthorized") -> httpx.Response:
    return httpx.Response(status, text=body)


# ---------------------------------------------------------------------------
# Counts and lists
# ---------------------------------------------------------------------------


@respx.mock
async def test_count_issues_by_state() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok(
            {"issues": {"nodes": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}}
        )
    )
    async with LinearClient("k", "team") as client:
        n = await client.count_issues_by_state("Backlog")
    assert n == 3


@respx.mock
async def test_count_returns_zero_when_no_issues() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"issues": {"nodes": []}})
    )
    async with LinearClient("k", "team") as client:
        n = await client.count_issues_by_state("Done")
    assert n == 0


@respx.mock
async def test_list_issues_by_state_returns_typed_objects() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok(
            {
                "issues": {
                    "nodes": [
                        {
                            "id": "uuid-1",
                            "identifier": "NSG-1",
                            "title": "Setup Django",
                            "description": "Bootstrap…",
                            "state": {"name": "Backlog"},
                            "labels": {
                                "nodes": [{"name": "module:orders"}, {"name": "low-risk"}]
                            },
                            "parent": {"id": "epic-uuid"},
                        },
                    ]
                }
            }
        )
    )
    async with LinearClient("k", "team") as client:
        issues = await client.list_issues_by_state("Backlog")
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, Issue)
    assert issue.identifier == "NSG-1"
    assert issue.title == "Setup Django"
    assert issue.state == "Backlog"
    assert issue.labels == ("module:orders", "low-risk")
    assert issue.parent_id == "epic-uuid"


@respx.mock
async def test_get_issue_returns_none_when_not_found() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(return_value=_ok({"issue": None}))
    async with LinearClient("k", "team") as client:
        result = await client.get_issue("NSG-NOPE")
    assert result is None


@respx.mock
async def test_get_issue_returns_issue() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok(
            {
                "issue": {
                    "id": "x",
                    "identifier": "NSG-2",
                    "title": "T",
                    "description": "D",
                    "state": {"name": "In Progress"},
                    "labels": {"nodes": []},
                    "parent": None,
                }
            }
        )
    )
    async with LinearClient("k", "team") as client:
        issue = await client.get_issue("NSG-2")
    assert issue is not None
    assert issue.parent_id is None
    assert issue.state == "In Progress"


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@respx.mock
async def test_update_issue_state_succeeds() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"issueUpdate": {"success": True}})
    )
    async with LinearClient("k", "team") as client:
        await client.update_issue_state("uuid", "state-uuid")  # no exception


@respx.mock
async def test_update_issue_state_raises_when_unsuccessful() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"issueUpdate": {"success": False}})
    )
    async with LinearClient("k", "team") as client:
        with pytest.raises(LinearClientError):
            await client.update_issue_state("uuid", "state-uuid")


@respx.mock
async def test_add_comment_succeeds() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"commentCreate": {"success": True}})
    )
    async with LinearClient("k", "team") as client:
        await client.add_comment("uuid", "hello")


@respx.mock
async def test_create_issue_returns_issue() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok(
            {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "new-uuid",
                        "identifier": "NSG-7",
                        "title": "New",
                        "description": "",
                        "state": {"name": "Backlog"},
                        "labels": {"nodes": []},
                        "parent": None,
                    },
                }
            }
        )
    )
    async with LinearClient("k", "team") as client:
        issue = await client.create_issue(title="New", description="")
    assert issue.identifier == "NSG-7"


@respx.mock
async def test_create_issue_with_project_id_includes_it_in_payload() -> None:
    """Regression: seed tickets were landing at team level without a project.
    Verify projectId is forwarded to the GraphQL input when provided."""
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return _ok(
            {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "x",
                        "identifier": "NSG-1",
                        "title": "T",
                        "description": "",
                        "state": {"name": "Backlog"},
                        "labels": {"nodes": []},
                        "parent": None,
                    },
                }
            }
        )

    respx.post(LINEAR_GRAPHQL_URL).mock(side_effect=_capture)
    async with LinearClient("k", "team") as client:
        await client.create_issue(
            title="T",
            description="",
            project_id="proj-uuid-abc",
        )
    payload_input = captured["variables"]["input"]  # type: ignore[index]
    assert payload_input["projectId"] == "proj-uuid-abc"
    assert payload_input["teamId"] == "team"


@respx.mock
async def test_create_issue_without_project_id_omits_field() -> None:
    """If no project_id is passed, projectId must NOT be in the payload
    (Linear treats missing differently from explicit null)."""
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return _ok(
            {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "x",
                        "identifier": "NSG-2",
                        "title": "T",
                        "description": "",
                        "state": {"name": "Backlog"},
                        "labels": {"nodes": []},
                        "parent": None,
                    },
                }
            }
        )

    respx.post(LINEAR_GRAPHQL_URL).mock(side_effect=_capture)
    async with LinearClient("k", "team") as client:
        await client.create_issue(title="T", description="")
    payload_input = captured["variables"]["input"]  # type: ignore[index]
    assert "projectId" not in payload_input


@respx.mock
async def test_attach_file_succeeds() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"attachmentCreate": {"success": True}})
    )
    async with LinearClient("k", "team") as client:
        await client.attach_file("uuid", url="https://x/y.png", title="screenshot")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@respx.mock
async def test_http_error_raises() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(return_value=_err(401))
    async with LinearClient("k", "team") as client:
        with pytest.raises(LinearClientError):
            await client.count_issues_by_state("Backlog")


@respx.mock
async def test_graphql_errors_field_raises() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200, json={"errors": [{"message": "bad query"}]}
        )
    )
    async with LinearClient("k", "team") as client:
        with pytest.raises(LinearClientError):
            await client.count_issues_by_state("Backlog")


@respx.mock
async def test_authorization_header_includes_api_key() -> None:
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        return _ok({"issues": {"nodes": []}})

    respx.post(LINEAR_GRAPHQL_URL).mock(side_effect=_capture)
    async with LinearClient("test-key", "team") as client:
        await client.count_issues_by_state("Backlog")
    assert captured["auth"] == "test-key"


@respx.mock
async def test_post_payload_contains_query_and_variables() -> None:
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return _ok({"issues": {"nodes": []}})

    respx.post(LINEAR_GRAPHQL_URL).mock(side_effect=_capture)
    async with LinearClient("k", "team-xyz") as client:
        await client.count_issues_by_state("Backlog")
    assert "query" in captured
    assert captured["variables"] == {"team": "team-xyz", "state": "Backlog"}

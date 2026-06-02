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
# Workflow states
# ---------------------------------------------------------------------------


@respx.mock
async def test_list_team_states_returns_name_to_uuid_map() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok(
            {
                "team": {
                    "states": {
                        "nodes": [
                            {"id": "state-1", "name": "Backlog"},
                            {"id": "state-2", "name": "Spec Draft"},
                            {"id": "state-3", "name": "Ready for Agent"},
                        ]
                    }
                }
            }
        )
    )
    async with LinearClient("k", "team") as client:
        states = await client.list_team_states()
    assert states == {
        "Backlog": "state-1",
        "Spec Draft": "state-2",
        "Ready for Agent": "state-3",
    }


@respx.mock
async def test_list_team_states_empty_team_returns_empty_dict() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"team": {"states": {"nodes": []}}})
    )
    async with LinearClient("k", "team") as client:
        assert await client.list_team_states() == {}


@respx.mock
async def test_list_team_states_raises_when_team_missing() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(return_value=_ok({"team": None}))
    async with LinearClient("k", "team") as client:
        with pytest.raises(LinearClientError):
            await client.list_team_states()


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@respx.mock
async def test_list_team_labels_returns_name_to_uuid_map() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok(
            {
                "team": {
                    "labels": {
                        "nodes": [
                            {"id": "uuid-a", "name": "type:story"},
                            {"id": "uuid-b", "name": "module:orders"},
                            {"id": "uuid-c", "name": "low-risk"},
                        ]
                    }
                }
            }
        )
    )
    async with LinearClient("k", "team") as client:
        labels = await client.list_team_labels()
    assert labels == {
        "type:story": "uuid-a",
        "module:orders": "uuid-b",
        "low-risk": "uuid-c",
    }


@respx.mock
async def test_list_team_labels_empty_team_returns_empty_dict() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"team": {"labels": {"nodes": []}}})
    )
    async with LinearClient("k", "team") as client:
        labels = await client.list_team_labels()
    assert labels == {}


@respx.mock
async def test_list_team_labels_raises_when_team_missing() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(return_value=_ok({"team": None}))
    async with LinearClient("k", "team") as client:
        with pytest.raises(LinearClientError):
            await client.list_team_labels()


@respx.mock
async def test_create_label_returns_uuid() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok(
            {
                "issueLabelCreate": {
                    "success": True,
                    "issueLabel": {"id": "new-uuid", "name": "module:orders"},
                }
            }
        )
    )
    async with LinearClient("k", "team") as client:
        uuid = await client.create_label("module:orders")
    assert uuid == "new-uuid"


@respx.mock
async def test_create_label_raises_on_non_success() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"issueLabelCreate": {"success": False, "issueLabel": None}})
    )
    async with LinearClient("k", "team") as client:
        with pytest.raises(LinearClientError):
            await client.create_label("module:orders")


@respx.mock
async def test_create_label_sends_team_id_and_optional_color() -> None:
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return _ok(
            {
                "issueLabelCreate": {
                    "success": True,
                    "issueLabel": {"id": "x", "name": "module:orders"},
                }
            }
        )

    respx.post(LINEAR_GRAPHQL_URL).mock(side_effect=_capture)
    async with LinearClient("k", "team-xyz") as client:
        await client.create_label("module:orders", color="#E2E2E2")
    payload_input = captured["variables"]["input"]  # type: ignore[index]
    assert payload_input == {
        "teamId": "team-xyz",
        "name": "module:orders",
        "color": "#E2E2E2",
    }


@respx.mock
async def test_ensure_labels_reuses_existing_and_creates_missing() -> None:
    """Idempotency: known names skip creation, unknown names get created."""
    calls: list[dict[str, object]] = []

    def _route(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        calls.append(body)
        query = str(body.get("query", ""))
        if "TeamLabels" in query:
            return _ok(
                {
                    "team": {
                        "labels": {
                            "nodes": [
                                {"id": "existing-1", "name": "type:story"},
                                {"id": "existing-2", "name": "low-risk"},
                            ]
                        }
                    }
                }
            )
        # else: it's a CreateLabel call
        name = body["variables"]["input"]["name"]
        return _ok(
            {
                "issueLabelCreate": {
                    "success": True,
                    "issueLabel": {"id": f"new-{name}", "name": name},
                }
            }
        )

    respx.post(LINEAR_GRAPHQL_URL).mock(side_effect=_route)
    async with LinearClient("k", "team") as client:
        out = await client.ensure_labels(
            ["type:story", "module:orders", "low-risk", "module:frontend"]
        )
    assert out == {
        "type:story": "existing-1",
        "module:orders": "new-module:orders",
        "low-risk": "existing-2",
        "module:frontend": "new-module:frontend",
    }
    # 1 list call + 2 creates (only the unknown names)
    assert len(calls) == 3
    create_names = sorted(
        c["variables"]["input"]["name"]  # type: ignore[index]
        for c in calls
        if "CreateLabel" in str(c.get("query", ""))
    )
    assert create_names == ["module:frontend", "module:orders"]


@respx.mock
async def test_update_issue_labels_succeeds() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"issueUpdate": {"success": True}})
    )
    async with LinearClient("k", "team") as client:
        await client.update_issue_labels("issue-uuid", ["lbl-1", "lbl-2"])


@respx.mock
async def test_update_issue_labels_raises_on_non_success() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=_ok({"issueUpdate": {"success": False}})
    )
    async with LinearClient("k", "team") as client:
        with pytest.raises(LinearClientError):
            await client.update_issue_labels("issue-uuid", ["lbl-1"])


@respx.mock
async def test_update_issue_labels_sends_label_ids_array() -> None:
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return _ok({"issueUpdate": {"success": True}})

    respx.post(LINEAR_GRAPHQL_URL).mock(side_effect=_capture)
    async with LinearClient("k", "team") as client:
        await client.update_issue_labels("issue-uuid", ["lbl-1", "lbl-2", "lbl-3"])
    assert captured["variables"] == {
        "id": "issue-uuid",
        "labelIds": ["lbl-1", "lbl-2", "lbl-3"],
    }


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

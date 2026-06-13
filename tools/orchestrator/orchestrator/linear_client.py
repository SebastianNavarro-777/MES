"""Async wrapper over Linear's GraphQL API.

Tests live at ``tools/orchestrator/tests/test_linear_client.py`` using
``respx`` to mock the GraphQL endpoint. This module never makes a real
network call inside tests.

The client is intentionally narrow — only the operations the daemons
actually need. Adding a new query is a small, focused PR.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx

__all__ = [
    "Issue",
    "LinearClient",
    "LinearClientError",
]


LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Issue:
    """A Linear issue, projected to the fields the orchestrator uses."""

    id: str  # Linear's UUID
    identifier: str  # human-readable, e.g., "NSG-123"
    title: str
    description: str
    state: str  # state name, e.g., "Backlog"
    labels: tuple[str, ...] = ()
    parent_id: str | None = None  # Epic parent if any
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LinearClientError(RuntimeError):
    """Raised when Linear returns an error or unexpected payload."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LinearClient:
    """Minimal async client for Linear's GraphQL API.

    Construct with the API key (from ``Settings.LINEAR_API_KEY``) and the
    team identifier. The client is safe to share between concurrent
    daemons — ``httpx.AsyncClient`` is itself concurrent-safe.
    """

    def __init__(
        self,
        api_key: str,
        team_id: str,
        *,
        endpoint: str = LINEAR_GRAPHQL_URL,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._team_id = team_id
        self._endpoint = endpoint
        self._timeout = timeout
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> LinearClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    # -- low-level GraphQL helper -------------------------------------------

    async def _post(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {"Authorization": self._api_key, "Content-Type": "application/json"}
        body = {"query": query, "variables": variables or {}}
        response = await self._client.post(
            self._endpoint, json=body, headers=headers, timeout=self._timeout
        )
        if response.status_code >= 400:
            raise LinearClientError(
                f"Linear HTTP {response.status_code}: {response.text[:200]}"
            )
        payload: object = response.json()
        if not isinstance(payload, dict):
            raise LinearClientError(f"Linear returned non-object payload: {payload!r}")
        if payload.get("errors"):
            raise LinearClientError(f"Linear GraphQL errors: {payload['errors']}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise LinearClientError(
                f"Linear payload missing `data`: {list(payload.keys())}"
            )
        return data

    # -- queries -------------------------------------------------------------

    async def count_issues_by_state(self, state_name: str) -> int:
        """Number of issues in this team currently in the given state."""
        query = """
        query Count($team: ID!, $state: String!) {
          issues(
            filter: { team: { id: { eq: $team } }, state: { name: { eq: $state } } }
          ) { nodes { id } }
        }
        """
        data = await self._post(
            query, {"team": self._team_id, "state": state_name}
        )
        nodes = data.get("issues", {}).get("nodes", [])
        if not isinstance(nodes, list):
            raise LinearClientError("issues.nodes is not a list")
        return len(nodes)

    async def count_issues_by_states(self, state_names: Iterable[str]) -> int:
        """Number of issues in this team currently in *any* of the given states.

        Used by the trigger dispatcher to gauge real backlog pressure across
        every in-flight state in a single round-trip, instead of one query
        per state. An empty ``state_names`` returns ``0`` without a request.
        """
        names = list(state_names)
        if not names:
            return 0
        query = """
        query CountMulti($team: ID!, $states: [String!]!) {
          issues(
            filter: { team: { id: { eq: $team } }, state: { name: { in: $states } } }
          ) { nodes { id } }
        }
        """
        data = await self._post(
            query, {"team": self._team_id, "states": names}
        )
        nodes = data.get("issues", {}).get("nodes", [])
        if not isinstance(nodes, list):
            raise LinearClientError("issues.nodes is not a list")
        return len(nodes)

    async def list_issues_by_state(self, state_name: str) -> list[Issue]:
        """All issues in this team currently in the given state."""
        query = """
        query List($team: ID!, $state: String!) {
          issues(
            filter: { team: { id: { eq: $team } }, state: { name: { eq: $state } } }
          ) {
            nodes {
              id
              identifier
              title
              description
              state { name }
              labels { nodes { name } }
              parent { id }
            }
          }
        }
        """
        data = await self._post(
            query, {"team": self._team_id, "state": state_name}
        )
        nodes = data.get("issues", {}).get("nodes", [])
        if not isinstance(nodes, list):
            raise LinearClientError("issues.nodes is not a list")
        return [_node_to_issue(n) for n in nodes if isinstance(n, dict)]

    async def get_issue(self, identifier: str) -> Issue | None:
        """Fetch a single issue by its identifier (e.g., ``NSG-123``)."""
        query = """
        query Get($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            description
            state { name }
            labels { nodes { name } }
            parent { id }
          }
        }
        """
        data = await self._post(query, {"id": identifier})
        node = data.get("issue")
        if node is None:
            return None
        if not isinstance(node, dict):
            raise LinearClientError("issue is not an object")
        return _node_to_issue(node)

    # -- mutations -----------------------------------------------------------

    async def update_issue_state(self, issue_id: str, new_state_id: str) -> None:
        """Move an issue to a different state by state UUID."""
        mutation = """
        mutation UpdateState($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: { stateId: $stateId }) { success }
        }
        """
        data = await self._post(mutation, {"id": issue_id, "stateId": new_state_id})
        if not data.get("issueUpdate", {}).get("success"):
            raise LinearClientError(f"issueUpdate({issue_id}) returned non-success")

    async def add_comment(self, issue_id: str, body: str) -> None:
        """Add a comment to an issue."""
        mutation = """
        mutation Comment($id: String!, $body: String!) {
          commentCreate(input: { issueId: $id, body: $body }) { success }
        }
        """
        data = await self._post(mutation, {"id": issue_id, "body": body})
        if not data.get("commentCreate", {}).get("success"):
            raise LinearClientError(f"commentCreate on {issue_id} returned non-success")

    async def create_issue(
        self,
        *,
        title: str,
        description: str,
        team_id: str | None = None,
        parent_id: str | None = None,
        project_id: str | None = None,
        label_ids: list[str] | None = None,
    ) -> Issue:
        """Create a new issue. Returns the created issue.

        ``project_id``: optional Linear project UUID. If provided, the
        issue lands inside that project (appears in the project view).
        If omitted, the issue lives at team level only.
        """
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue {
              id
              identifier
              title
              description
              state { name }
              labels { nodes { name } }
              parent { id }
            }
          }
        }
        """
        input_payload: dict[str, Any] = {
            "teamId": team_id or self._team_id,
            "title": title,
            "description": description,
        }
        if parent_id:
            input_payload["parentId"] = parent_id
        if project_id:
            input_payload["projectId"] = project_id
        if label_ids:
            input_payload["labelIds"] = label_ids
        data = await self._post(mutation, {"input": input_payload})
        result = data.get("issueCreate", {})
        if not result.get("success"):
            raise LinearClientError("issueCreate returned non-success")
        node = result.get("issue")
        if not isinstance(node, dict):
            raise LinearClientError("issueCreate did not return an issue")
        return _node_to_issue(node)

    async def attach_file(
        self, issue_id: str, *, url: str, title: str
    ) -> None:
        """Attach a remote URL to an issue (e.g., a Playwright artefact)."""
        mutation = """
        mutation Attach($issueId: String!, $url: String!, $title: String!) {
          attachmentCreate(
            input: { issueId: $issueId, url: $url, title: $title }
          ) { success }
        }
        """
        data = await self._post(
            mutation, {"issueId": issue_id, "url": url, "title": title}
        )
        if not data.get("attachmentCreate", {}).get("success"):
            raise LinearClientError(f"attachmentCreate on {issue_id} returned non-success")

    # -- workflow states -----------------------------------------------------

    async def list_team_states(self) -> dict[str, str]:
        """Return ``{name: id}`` for every workflow state on this team.

        Linear's ``issueUpdate(input: { stateId })`` mutation requires a
        state UUID. The orchestrator reads state names from
        ``state_machine.py`` (``"Backlog"``, ``"Spec Draft"``, etc.) so
        any daemon that needs to transition a ticket calls this once and
        caches the result.

        Names are case-sensitive and must match what Sebas created in
        Linear during SETUP step 1.1.
        """
        query = """
        query TeamStates($team: String!) {
          team(id: $team) {
            states { nodes { id name } }
          }
        }
        """
        data = await self._post(query, {"team": self._team_id})
        team = data.get("team")
        if not isinstance(team, dict):
            raise LinearClientError("team payload missing or malformed")
        nodes = team.get("states", {}).get("nodes", [])
        if not isinstance(nodes, list):
            raise LinearClientError("team.states.nodes is not a list")
        result: dict[str, str] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            name = node.get("name")
            uuid = node.get("id")
            if isinstance(name, str) and isinstance(uuid, str):
                result[name] = uuid
        return result

    # -- labels --------------------------------------------------------------

    async def list_team_labels(self) -> dict[str, str]:
        """Return ``{name: id}`` for every label on this team.

        Linear's API requires label UUIDs to attach labels to issues, so
        the orchestrator resolves names locally via this map. Names are
        case-sensitive — Linear treats ``type:story`` and ``Type:Story``
        as different labels.
        """
        query = """
        query TeamLabels($team: String!) {
          team(id: $team) {
            labels { nodes { id name } }
          }
        }
        """
        data = await self._post(query, {"team": self._team_id})
        team = data.get("team")
        if not isinstance(team, dict):
            raise LinearClientError("team payload missing or malformed")
        nodes = team.get("labels", {}).get("nodes", [])
        if not isinstance(nodes, list):
            raise LinearClientError("team.labels.nodes is not a list")
        result: dict[str, str] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            name = node.get("name")
            uuid = node.get("id")
            if isinstance(name, str) and isinstance(uuid, str):
                result[name] = uuid
        return result

    async def create_label(self, name: str, *, color: str | None = None) -> str:
        """Create a label scoped to this team. Returns the UUID.

        ``color`` is a 6-digit hex string like ``"#E2E2E2"``. If omitted,
        Linear picks a default.
        """
        mutation = """
        mutation CreateLabel($input: IssueLabelCreateInput!) {
          issueLabelCreate(input: $input) {
            success
            issueLabel { id name }
          }
        }
        """
        input_payload: dict[str, Any] = {"teamId": self._team_id, "name": name}
        if color:
            input_payload["color"] = color
        data = await self._post(mutation, {"input": input_payload})
        result = data.get("issueLabelCreate", {})
        if not result.get("success"):
            raise LinearClientError(f"issueLabelCreate({name}) returned non-success")
        label = result.get("issueLabel")
        if not isinstance(label, dict):
            raise LinearClientError("issueLabelCreate did not return the label")
        uuid = label.get("id")
        if not isinstance(uuid, str):
            raise LinearClientError("issueLabelCreate returned no id")
        return uuid

    async def ensure_labels(self, names: list[str]) -> dict[str, str]:
        """Return ``{name: id}`` for every requested label, creating missing ones.

        Idempotent: existing labels keep their UUID and color; only the
        truly missing names get a fresh ``issueLabelCreate``. The caller
        does not have to know which labels already existed.
        """
        existing = await self.list_team_labels()
        result: dict[str, str] = {}
        for name in names:
            if name in existing:
                result[name] = existing[name]
                continue
            result[name] = await self.create_label(name)
        return result

    async def update_issue_labels(
        self, issue_id: str, label_ids: list[str]
    ) -> None:
        """Overwrite the label set on an issue.

        Linear's ``issueUpdate(input: {labelIds})`` *replaces* the full
        set — there is no add-only mutation. Callers wanting to merge
        with the existing labels should first fetch the issue and union
        the two lists themselves.
        """
        mutation = """
        mutation UpdateLabels($id: String!, $labelIds: [String!]!) {
          issueUpdate(id: $id, input: { labelIds: $labelIds }) { success }
        }
        """
        data = await self._post(mutation, {"id": issue_id, "labelIds": label_ids})
        if not data.get("issueUpdate", {}).get("success"):
            raise LinearClientError(
                f"issueUpdate({issue_id}) labels returned non-success"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_to_issue(node: dict[str, Any]) -> Issue:
    state_obj = node.get("state") or {}
    parent_obj = node.get("parent")
    labels_obj = node.get("labels", {}).get("nodes", [])
    return Issue(
        id=str(node.get("id", "")),
        identifier=str(node.get("identifier", "")),
        title=str(node.get("title", "")),
        description=str(node.get("description") or ""),
        state=str(state_obj.get("name", "")),
        labels=tuple(
            str(label.get("name", ""))
            for label in labels_obj
            if isinstance(label, dict)
        ),
        parent_id=str(parent_obj["id"]) if isinstance(parent_obj, dict) else None,
    )

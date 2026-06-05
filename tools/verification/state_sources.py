"""External / volatile data sources for ``STATE.md``.

Three sections of the snapshot come from outside the static tree:

* **Recently merged PRs** — parsed from ``git log --merges``.
* **Active exec-plans** — the files under ``docs/exec-plans/active/``.
* **Open Questions** — issues labelled ``needs-human-decision`` in Linear.

The Stop hook runs on every session close, so every source here is wrapped to
**degrade gracefully** (NSG-50 AC-7): a missing ``git``, an offline network, or
absent Linear credentials must never crash the hook. When a source cannot be
reached the function returns ``None`` (rendered as "unavailable"), distinct from
an empty list (rendered as "none"). Failures are logged at ``warning`` — never
silently swallowed.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

__all__ = [
    "MergedPr",
    "OpenQuestion",
    "QuestionsProvider",
    "active_exec_plans",
    "fetch_open_questions_via_http",
    "open_questions",
    "parse_merge_log",
    "recently_merged_prs",
]

log = logging.getLogger(__name__)

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
QUESTION_LABEL = "needs-human-decision"
_GIT_TIMEOUT_SECONDS = 5.0
_LINEAR_TIMEOUT_SECONDS = 5.0

_MERGE_RE = re.compile(r"Merge pull request #(?P<number>\d+) from (?P<source>\S+)")
_FIELD_SEP = "\x1f"


@dataclass(frozen=True)
class MergedPr:
    """A merged pull request parsed from the git merge log."""

    number: int
    source: str
    merged_on: str  # ISO-8601 date (YYYY-MM-DD)


@dataclass(frozen=True)
class OpenQuestion:
    """An open ``Question`` ticket awaiting a human decision."""

    identifier: str
    title: str


# A provider returns the open questions, or raises to signal "unavailable".
QuestionsProvider = Callable[[], "list[OpenQuestion]"]
# A git runner takes (argv, cwd) and returns stdout, or raises on failure.
GitRunner = Callable[[Sequence[str], Path], str]


# ---------------------------------------------------------------------------
# Recently merged PRs (git)
# ---------------------------------------------------------------------------


def parse_merge_log(raw: str) -> list[MergedPr]:
    """Parse the output of the merge-log command into :class:`MergedPr` rows.

    Lines that are merges but not "Merge pull request #N" (e.g. a local
    ``Merge branch 'main'``) are skipped — they carry no PR number.
    """
    prs: list[MergedPr] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split(_FIELD_SEP)
        if len(parts) != 3:
            continue
        _commit, subject, committed_iso = parts
        match = _MERGE_RE.search(subject)
        if match is None:
            continue
        prs.append(
            MergedPr(
                number=int(match.group("number")),
                source=match.group("source"),
                merged_on=committed_iso[:10],
            )
        )
    return prs


def _run_git(argv: Sequence[str], cwd: Path) -> str:
    result = subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=True,
    )
    return result.stdout


def recently_merged_prs(
    root: Path,
    *,
    limit: int = 10,
    runner: GitRunner | None = None,
) -> list[MergedPr] | None:
    """Most recent merged PRs, or ``None`` if git history is unavailable."""
    run = runner or _run_git
    argv = [
        "git",
        "log",
        "--merges",
        f"-n{limit}",
        f"--pretty=format:%H{_FIELD_SEP}%s{_FIELD_SEP}%cI",
    ]
    try:
        raw = run(argv, root)
    except Exception as exc:  # AC-7: any git failure degrades, never crashes.
        log.warning("git merge log unavailable", extra={"error": str(exc)})
        return None
    return parse_merge_log(raw)


# ---------------------------------------------------------------------------
# Active exec-plans (filesystem)
# ---------------------------------------------------------------------------


def active_exec_plans(root: Path) -> list[str]:
    """File names under ``docs/exec-plans/active/`` (excluding ``.gitkeep``)."""
    active_dir = root / "docs" / "exec-plans" / "active"
    if not active_dir.exists():
        return []
    return sorted(
        p.name
        for p in active_dir.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )


# ---------------------------------------------------------------------------
# Open Questions (Linear)
# ---------------------------------------------------------------------------


def fetch_open_questions_via_http(
    api_key: str,
    team_id: str,
    *,
    endpoint: str = LINEAR_GRAPHQL_URL,
    timeout: float = _LINEAR_TIMEOUT_SECONDS,
    client: httpx.Client | None = None,
) -> list[OpenQuestion]:
    """Query Linear for open ``needs-human-decision`` issues.

    Raises on any transport/HTTP/shape error — the caller in
    :func:`open_questions` turns that into graceful "unavailable".
    """
    query = """
    query OpenQuestions($team: ID!, $label: String!) {
      issues(filter: {
        team: { id: { eq: $team } },
        labels: { name: { eq: $label } },
        state: { type: { nin: ["completed", "canceled"] } }
      }) { nodes { identifier title } }
    }
    """
    variables = {"team": team_id, "label": QUESTION_LABEL}
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        response = http.post(
            endpoint, json={"query": query, "variables": variables}, headers=headers
        )
        response.raise_for_status()
        payload: Any = response.json()
    finally:
        if owns_client:
            http.close()
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ValueError(f"Linear returned errors or bad payload: {payload!r}")
    nodes = payload.get("data", {}).get("issues", {}).get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("Linear issues.nodes is not a list")
    questions: list[OpenQuestion] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        questions.append(
            OpenQuestion(
                identifier=str(node.get("identifier", "")),
                title=str(node.get("title", "")),
            )
        )
    return questions


def _default_provider() -> list[OpenQuestion]:
    api_key = os.environ.get("LINEAR_API_KEY", "")
    team_id = os.environ.get("LINEAR_TEAM_ID", "")
    if not api_key or not team_id:
        raise RuntimeError("LINEAR_API_KEY / LINEAR_TEAM_ID not set")
    return fetch_open_questions_via_http(api_key, team_id)


def open_questions(provider: QuestionsProvider | None = None) -> list[OpenQuestion] | None:
    """Open ``Question`` tickets, or ``None`` when Linear is unavailable.

    Per AC-7 the Stop hook must survive a missing/offline/unauthenticated
    Linear, so *any* failure from the provider degrades to ``None`` (the
    section is then rendered as "not refreshed") with a logged warning.
    """
    provide = provider or _default_provider
    try:
        return provide()
    except Exception as exc:  # AC-7: degrade on any Linear failure.
        log.warning("Linear open-questions unavailable", extra={"error": str(exc)})
        return None

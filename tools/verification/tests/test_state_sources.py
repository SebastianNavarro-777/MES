"""Tests for ``tools.verification.state_sources``."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest
import respx

from tools.verification.state_sources import (
    LINEAR_GRAPHQL_URL,
    OpenQuestion,
    active_exec_plans,
    fetch_open_questions_via_http,
    open_questions,
    parse_merge_log,
    recently_merged_prs,
)

_SEP = "\x1f"


def _log_line(commit: str, subject: str, iso: str) -> str:
    return _SEP.join([commit, subject, iso])


def test_parse_merge_log_extracts_pr_number_source_and_date() -> None:
    # AC-3: recently merged PRs are parsed from the git merge log.
    raw = "\n".join(
        [
            _log_line("abc", "Merge pull request #3 from owner/feature-x", "2026-06-02T09:30:54Z"),
            _log_line("def", "Merge branch 'main' of github.com/o/r", "2026-06-02T09:00:00Z"),
            _log_line("ghi", "Merge pull request #1 from owner/dep-bump", "2026-06-01T10:00:00Z"),
        ]
    )
    prs = parse_merge_log(raw)
    assert [p.number for p in prs] == [3, 1]  # non-PR merge is skipped
    assert prs[0].source == "owner/feature-x"
    assert prs[0].merged_on == "2026-06-02"


def test_recently_merged_prs_degrades_to_none_on_git_failure() -> None:
    # AC-7: a git failure must degrade gracefully, never crash.
    def boom(argv: Sequence[str], cwd: Path) -> str:
        raise OSError("git not found")

    assert recently_merged_prs(Path("."), runner=boom) is None


def test_recently_merged_prs_parses_runner_output(tmp_path: Path) -> None:
    raw = _log_line("abc", "Merge pull request #7 from o/b", "2026-06-02T00:00:00Z")

    def runner(argv: Sequence[str], cwd: Path) -> str:
        return raw

    prs = recently_merged_prs(tmp_path, runner=runner)
    assert prs is not None
    assert prs[0].number == 7


def test_active_exec_plans_lists_files_excluding_dotfiles(tmp_path: Path) -> None:
    # AC-3: active exec-plans come from docs/exec-plans/active/.
    active = tmp_path / "docs" / "exec-plans" / "active"
    active.mkdir(parents=True)
    (active / ".gitkeep").write_text("", encoding="utf-8")
    (active / "0001-migrate-orders.md").write_text("plan", encoding="utf-8")
    assert active_exec_plans(tmp_path) == ["0001-migrate-orders.md"]


def test_active_exec_plans_empty_when_dir_absent(tmp_path: Path) -> None:
    assert active_exec_plans(tmp_path) == []


def test_open_questions_returns_provider_list() -> None:
    # AC-3: when Linear is reachable, Open Questions populate the section.
    def provider() -> list[OpenQuestion]:
        return [OpenQuestion(identifier="NSG-99", title="Schema decision")]

    result = open_questions(provider)
    assert result == [OpenQuestion(identifier="NSG-99", title="Schema decision")]


def test_open_questions_degrades_to_none_when_provider_raises() -> None:
    # AC-7: any Linear failure degrades to None (rendered as "unavailable").
    def provider() -> list[OpenQuestion]:
        raise ConnectionError("offline")

    assert open_questions(provider) is None


@respx.mock
def test_fetch_open_questions_via_http_parses_nodes() -> None:
    respx.post(LINEAR_GRAPHQL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "issues": {
                        "nodes": [
                            {"identifier": "NSG-42", "title": "Sign-off needed"},
                            {"identifier": "NSG-43", "title": "PPAP format?"},
                        ]
                    }
                }
            },
        )
    )
    questions = fetch_open_questions_via_http("lin_api_x", "team-uuid")
    assert [q.identifier for q in questions] == ["NSG-42", "NSG-43"]


@respx.mock
def test_fetch_open_questions_via_http_raises_on_http_error() -> None:
    # AC-7: an HTTP error surfaces as an exception, which open_questions catches.
    respx.post(LINEAR_GRAPHQL_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_open_questions_via_http("bad", "team")

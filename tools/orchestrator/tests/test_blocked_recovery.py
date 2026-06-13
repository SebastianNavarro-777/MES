"""Tests for the Blocked-dependency recovery daemon.

Contract:

* A ``Blocked`` ticket whose every ``blockedBy`` ticket is ``Done`` is
  released to ``Ready for Agent``.
* If *any* blocker is not yet ``Done``, the ticket stays ``Blocked`` — this
  is what stops a multi-blocker Story from being let through early.
* A ticket with no ``blockedBy`` relations is left alone (the Consultant
  Resolver or a human owns it).
* ``needs-human`` tickets and Question (``needs-human-decision``) tickets are
  never touched.

Uses a ``FakeLinearClient`` so the daemon runs fully offline.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from tools.orchestrator.orchestrator.blocked_recovery import BlockedRecoveryDaemon
from tools.orchestrator.orchestrator.config import Settings
from tools.orchestrator.orchestrator.db import Database
from tools.orchestrator.orchestrator.linear_client import Issue, LinearClient

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _Transition:
    issue_id: str
    new_state_id: str


@dataclass
class FakeLinearClient:
    issues_by_state: dict[str, list[Issue]] = field(default_factory=dict)
    blockers: dict[str, dict[str, str]] = field(default_factory=dict)
    state_ids: dict[str, str] = field(default_factory=dict)
    transitions: list[_Transition] = field(default_factory=list)
    comments: list[tuple[str, str]] = field(default_factory=list)

    async def list_issues_by_state(self, state: str) -> list[Issue]:
        return list(self.issues_by_state.get(state, []))

    async def list_blocker_states(self, identifier: str) -> dict[str, str]:
        return dict(self.blockers.get(identifier, {}))

    async def list_team_states(self) -> dict[str, str]:
        return dict(self.state_ids)

    async def update_issue_state(self, issue_id: str, new_state_id: str) -> None:
        self.transitions.append(_Transition(issue_id, new_state_id))

    async def add_comment(self, issue_id: str, body: str) -> None:
        self.comments.append((issue_id, body))


def _issue(identifier: str, *, labels: tuple[str, ...] = ()) -> Issue:
    return Issue(
        id=f"uuid-{identifier}",
        identifier=identifier,
        title=f"Title for {identifier}",
        description="",
        state="Blocked",
        labels=labels,
        parent_id=None,
    )


def _state_ids() -> dict[str, str]:
    return {
        "Ready for Agent": "state-ready",
        "Blocked": "state-blocked",
        "Done": "state-done",
    }


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(tmp_path / "queue.db")
    yield d
    d.close()


def _make_daemon(
    settings: Settings, db: Database, linear: FakeLinearClient
) -> BlockedRecoveryDaemon:
    return BlockedRecoveryDaemon(
        settings=settings, db=db, linear=cast(LinearClient, linear)
    )


# ---------------------------------------------------------------------------
# Release behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_releases_when_all_blockers_done(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"Blocked": [_issue("NSG-41")]},
        blockers={"NSG-41": {"NSG-21": "Done", "NSG-42": "Done"}},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == [_Transition("uuid-NSG-41", "state-ready")]
    assert len(linear.comments) == 1
    assert "NSG-21" in linear.comments[0][1] and "NSG-42" in linear.comments[0][1]


@pytest.mark.asyncio
async def test_stays_blocked_when_one_blocker_open(
    tmp_path: Path, db: Database
) -> None:
    """Only one blocker Done is not enough — a sibling dependency still open
    must keep the ticket Blocked (avoids the premature-release churn)."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"Blocked": [_issue("NSG-41")]},
        blockers={"NSG-41": {"NSG-21": "In Review", "NSG-42": "Done"}},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == []
    assert linear.comments == []


@pytest.mark.asyncio
async def test_no_blockers_is_left_alone(tmp_path: Path, db: Database) -> None:
    """A Blocked ticket with no dependency relation (e.g. a Question-block the
    Resolver owns, or a human park) is not ours to release."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"Blocked": [_issue("NSG-50")]},
        blockers={},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == []
    assert linear.comments == []


@pytest.mark.asyncio
async def test_needs_human_ticket_is_skipped(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"Blocked": [_issue("NSG-60", labels=("needs-human",))]},
        blockers={"NSG-60": {"NSG-21": "Done"}},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == []
    assert linear.comments == []


@pytest.mark.asyncio
async def test_question_ticket_is_skipped(tmp_path: Path, db: Database) -> None:
    """A Question parked in Blocked must never be pushed to Ready for Agent,
    even if (spuriously) all its blockers read Done."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={
            "Blocked": [_issue("NSG-44", labels=("needs-human-decision",))]
        },
        blockers={"NSG-44": {"NSG-17": "Done"}},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == []
    assert linear.comments == []


@pytest.mark.asyncio
async def test_release_skipped_when_team_lacks_ready_state(
    tmp_path: Path, db: Database
) -> None:
    """No 'Ready for Agent' state → no transition, no comment (don't claim a
    release we couldn't perform)."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"Blocked": [_issue("NSG-41")]},
        blockers={"NSG-41": {"NSG-21": "Done"}},
        state_ids={"Blocked": "state-blocked"},  # no Ready for Agent
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == []
    assert linear.comments == []

"""Tests for the Failed-ticket recovery daemon.

Contract:

* On each tick, every ``Failed`` ticket is re-queued to ``Ready for
  Agent`` so the recolector + Worker pool re-attempt it.
* Re-queues are bounded by ``Settings.MAX_AUTO_RETRIES`` per ticket
  (stage ``"worker"``); past the budget the ticket is labelled
  ``needs-human`` and left alone.
* A ticket already labelled ``needs-human`` is never touched.

Uses a ``FakeLinearClient`` so the daemon runs fully offline.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from tools.orchestrator.orchestrator.config import Settings
from tools.orchestrator.orchestrator.db import Database
from tools.orchestrator.orchestrator.failed_recovery import FailedRecoveryDaemon
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
    state_ids: dict[str, str] = field(default_factory=dict)
    transitions: list[_Transition] = field(default_factory=list)
    label_updates: list[tuple[str, list[str]]] = field(default_factory=list)
    comments: list[tuple[str, str]] = field(default_factory=list)

    async def list_issues_by_state(self, state: str) -> list[Issue]:
        return list(self.issues_by_state.get(state, []))

    async def list_team_states(self) -> dict[str, str]:
        return dict(self.state_ids)

    async def update_issue_state(self, issue_id: str, new_state_id: str) -> None:
        self.transitions.append(_Transition(issue_id, new_state_id))

    async def add_comment(self, issue_id: str, body: str) -> None:
        self.comments.append((issue_id, body))

    async def ensure_labels(self, names: list[str]) -> dict[str, str]:
        return {name: f"label-{name}" for name in names}

    async def update_issue_labels(
        self, issue_id: str, label_ids: list[str]
    ) -> None:
        self.label_updates.append((issue_id, list(label_ids)))


def _issue(identifier: str, *, labels: tuple[str, ...] = ()) -> Issue:
    return Issue(
        id=f"uuid-{identifier}",
        identifier=identifier,
        title=f"Title for {identifier}",
        description="",
        state="Failed",
        labels=labels,
        parent_id=None,
    )


def _state_ids() -> dict[str, str]:
    return {
        "Ready for Agent": "state-ready",
        "Failed": "state-failed",
    }


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(tmp_path / "queue.db")
    yield d
    d.close()


def _make_daemon(
    settings: Settings, db: Database, linear: FakeLinearClient
) -> FailedRecoveryDaemon:
    return FailedRecoveryDaemon(
        settings=settings, db=db, linear=cast(LinearClient, linear)
    )


# ---------------------------------------------------------------------------
# Re-queue behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_failed_list_is_a_noop(tmp_path: Path, db: Database) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(state_ids=_state_ids())
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == []
    assert linear.comments == []


@pytest.mark.asyncio
async def test_requeues_failed_ticket_to_ready_for_agent(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"Failed": [_issue("NSG-10")]},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == [_Transition("uuid-NSG-10", "state-ready")]
    assert db.get_attempts("NSG-10", "worker") == 1
    assert len(linear.comments) == 1
    assert "Auto-retry 1/2" in linear.comments[0][1]


@pytest.mark.asyncio
async def test_attempt_only_counts_after_successful_transition(
    tmp_path: Path, db: Database
) -> None:
    """If the team has no Ready for Agent state, the daemon must not burn
    a retry on a transition it could not perform."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"Failed": [_issue("NSG-10")]},
        state_ids={"Failed": "state-failed"},  # no Ready for Agent
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == []
    assert db.get_attempts("NSG-10", "worker") == 0


@pytest.mark.asyncio
async def test_escalates_to_human_after_budget(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"), MAX_AUTO_RETRIES=2)
    linear = FakeLinearClient(
        issues_by_state={"Failed": [_issue("NSG-10")]},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    db.bump_attempt("NSG-10", "worker")
    db.bump_attempt("NSG-10", "worker")  # now at the limit

    await daemon.tick()

    assert linear.transitions == []  # not re-queued
    assert len(linear.label_updates) == 1
    issue_id, label_ids = linear.label_updates[0]
    assert issue_id == "uuid-NSG-10"
    assert "label-needs-human" in label_ids


@pytest.mark.asyncio
async def test_needs_human_ticket_is_skipped(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"Failed": [_issue("NSG-10", labels=("needs-human",))]},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == []
    assert linear.label_updates == []
    assert linear.comments == []


@pytest.mark.asyncio
async def test_failed_question_ticket_is_skipped(
    tmp_path: Path, db: Database
) -> None:
    """A Question that somehow landed in Failed must not be re-queued into
    the Worker pipeline — it has no code to implement, so a Worker would only
    churn it back into Blocked (NSG-42/44)."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={
            "Failed": [_issue("NSG-30", labels=("needs-human-decision",))]
        },
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    assert linear.transitions == []
    assert linear.comments == []
    assert db.get_attempts("NSG-30", "worker") == 0


@pytest.mark.asyncio
async def test_multiple_failed_tickets_each_recovered(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"Failed": [_issue("NSG-10"), _issue("NSG-11")]},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    await daemon.tick()
    requeued = sorted(t.issue_id for t in linear.transitions)
    assert requeued == ["uuid-NSG-10", "uuid-NSG-11"]
    assert db.get_attempts("NSG-10", "worker") == 1
    assert db.get_attempts("NSG-11", "worker") == 1


# ---------------------------------------------------------------------------
# Stale In Progress reaping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_in_progress_is_requeued(
    tmp_path: Path, db: Database
) -> None:
    """A ticket stuck in In Progress past the grace window (Worker crashed
    mid-run) is re-queued to Ready for Agent."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"In Progress": [_issue("NSG-20")]},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    # Age the ticket well past IN_PROGRESS_GRACE_SECONDS (default 45 min).
    db.mark_in_progress_seen("NSG-20", now=datetime.now(UTC) - timedelta(hours=2))

    await daemon.tick()

    assert linear.transitions == [_Transition("uuid-NSG-20", "state-ready")]
    assert db.get_attempts("NSG-20", "worker") == 1
    assert len(linear.comments) == 1
    assert "In Progress" in linear.comments[0][1]
    # Clock cleared so a re-entry starts fresh.
    assert db.mark_in_progress_seen("NSG-20") > (
        datetime.now(UTC) - timedelta(minutes=1)
    )


@pytest.mark.asyncio
async def test_fresh_in_progress_is_left_alone(
    tmp_path: Path, db: Database
) -> None:
    """A ticket only recently In Progress might be a live Worker run, so it
    is never yanked."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={"In Progress": [_issue("NSG-21")]},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)

    await daemon.tick()  # first observation → clock starts now

    assert linear.transitions == []
    assert db.get_attempts("NSG-21", "worker") == 0


@pytest.mark.asyncio
async def test_stale_in_progress_escalates_after_budget(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"), MAX_AUTO_RETRIES=2)
    linear = FakeLinearClient(
        issues_by_state={"In Progress": [_issue("NSG-20")]},
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    db.mark_in_progress_seen("NSG-20", now=datetime.now(UTC) - timedelta(hours=2))
    db.bump_attempt("NSG-20", "worker")
    db.bump_attempt("NSG-20", "worker")  # at the limit

    await daemon.tick()

    assert linear.transitions == []  # not re-queued
    assert len(linear.label_updates) == 1
    issue_id, label_ids = linear.label_updates[0]
    assert issue_id == "uuid-NSG-20"
    assert "label-needs-human" in label_ids


@pytest.mark.asyncio
async def test_stale_in_progress_question_is_skipped(
    tmp_path: Path, db: Database
) -> None:
    """Orphan recovery must not yank a Question out of In Progress back into
    Ready for Agent — that is the exact loop that churned resolved Questions
    (NSG-42, NSG-44) into Blocked after the human had already answered."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={
            "In Progress": [_issue("NSG-31", labels=("needs-human-decision",))]
        },
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    db.mark_in_progress_seen("NSG-31", now=datetime.now(UTC) - timedelta(hours=2))

    await daemon.tick()

    assert linear.transitions == []
    assert linear.comments == []
    assert db.get_attempts("NSG-31", "worker") == 0


@pytest.mark.asyncio
async def test_needs_human_in_progress_is_skipped(
    tmp_path: Path, db: Database
) -> None:
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"))
    linear = FakeLinearClient(
        issues_by_state={
            "In Progress": [_issue("NSG-20", labels=("needs-human",))]
        },
        state_ids=_state_ids(),
    )
    daemon = _make_daemon(settings, db, linear)
    db.mark_in_progress_seen("NSG-20", now=datetime.now(UTC) - timedelta(hours=2))

    await daemon.tick()

    assert linear.transitions == []
    assert linear.label_updates == []
    assert linear.comments == []

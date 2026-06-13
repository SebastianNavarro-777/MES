"""Tests for the Spec Writer daemon.

The daemon's contract:

* On each tick, pick at most ONE Backlog ticket of an enrichable type.
* Transition that ticket Backlog → Spec Draft via Linear before spawning
  the agent (so a concurrent recolector / second tick can't double-pick).
* Spawn ``claude --print`` with ``agent_name="spec_writer"`` and the repo
  root as workspace (Spec Writer reads ``docs/`` and edits Linear; it
  does no code work, so no worktree).
* On non-zero exit, record a ``spec_writer_failed`` learning event.
* Filter ``type:epic`` and ``type:question`` out; accept ``type:story``,
  ``type:bug``, ``type:harness-fix``.
* Re-entrance safety: a ticket already in flight isn't re-picked.

Tests use ``FakeLinearClient`` + ``FakeClaudeRunner`` so the daemon runs
fully offline. We don't unit-test the prompt itself; the agent prompt
is exercised by integration runs against the real Claude binary.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from tools.orchestrator.orchestrator.claude_runner import ClaudeRunner, ClaudeRunResult
from tools.orchestrator.orchestrator.config import Settings
from tools.orchestrator.orchestrator.db import Database
from tools.orchestrator.orchestrator.linear_client import Issue, LinearClient
from tools.orchestrator.orchestrator.spec_writer_runner import SpecWriterDaemon

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _Transition:
    issue_id: str
    new_state_id: str


@dataclass
class FakeLinearClient:
    """Minimal stand-in for LinearClient used by SpecWriterDaemon."""

    issues_by_state: dict[str, list[Issue]] = field(default_factory=dict)
    state_ids: dict[str, str] = field(default_factory=dict)
    transitions: list[_Transition] = field(default_factory=list)
    raise_on_transition: bool = False
    label_updates: list[tuple[str, list[str]]] = field(default_factory=list)
    comments: list[tuple[str, str]] = field(default_factory=list)

    async def list_issues_by_state(self, state: str) -> list[Issue]:
        return list(self.issues_by_state.get(state, []))

    async def list_team_states(self) -> dict[str, str]:
        return dict(self.state_ids)

    async def update_issue_state(self, issue_id: str, new_state_id: str) -> None:
        if self.raise_on_transition:
            raise RuntimeError("simulated transition failure")
        self.transitions.append(_Transition(issue_id, new_state_id))

    async def ensure_labels(self, names: list[str]) -> dict[str, str]:
        return {name: f"label-{name}" for name in names}

    async def update_issue_labels(
        self, issue_id: str, label_ids: list[str]
    ) -> None:
        self.label_updates.append((issue_id, list(label_ids)))

    async def add_comment(self, issue_id: str, body: str) -> None:
        self.comments.append((issue_id, body))


@dataclass
class _Spawn:
    agent_name: str
    user_prompt: str
    workspace: Path


@dataclass
class FakeClaudeRunner:
    """Records each .run(...) call; returns a configurable exit code."""

    spawns: list[_Spawn] = field(default_factory=list)
    next_exit_code: int = 0
    next_stderr: str = ""

    async def run(
        self,
        *,
        agent_name: str,
        user_prompt: str,
        workspace: Path,
        timeout: float = 60 * 60,
        extra_args: list[str] | None = None,
    ) -> ClaudeRunResult:
        self.spawns.append(_Spawn(agent_name, user_prompt, workspace))
        return ClaudeRunResult(
            exit_code=self.next_exit_code,
            stdout="",
            stderr=self.next_stderr,
            duration_seconds=0.0,
        )


def _issue(
    identifier: str,
    *,
    labels: tuple[str, ...] = (),
) -> Issue:
    return Issue(
        id=f"uuid-{identifier}",
        identifier=identifier,
        title=f"Title for {identifier}",
        description="",
        state="Backlog",
        labels=labels,
        parent_id=None,
    )


def _spec_draft_state_ids() -> dict[str, str]:
    """The minimum state map the daemon needs to transition tickets."""
    return {
        "Backlog": "state-backlog",
        "Spec Draft": "state-spec-draft",
        "Ready for Agent": "state-ready",
    }


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(WORKTREES_DIR=str(tmp_path / "wt"))


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(tmp_path / "queue.db")
    yield d
    d.close()


def _make_daemon(
    settings: Settings,
    db: Database,
    linear: FakeLinearClient,
    claude: FakeClaudeRunner,
) -> SpecWriterDaemon:
    return SpecWriterDaemon(
        settings=settings,
        db=db,
        linear=cast(LinearClient, linear),
        claude=cast(ClaudeRunner, claude),
    )


# ---------------------------------------------------------------------------
# Picking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_backlog_is_a_noop(
    settings: Settings, db: Database
) -> None:
    linear = FakeLinearClient(state_ids=_spec_draft_state_ids())
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert claude.spawns == []
    assert linear.transitions == []


@pytest.mark.asyncio
async def test_picks_a_story_and_transitions_to_spec_draft(
    settings: Settings, db: Database
) -> None:
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [_issue("NSG-5", labels=("type:story", "module:orders"))],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert linear.transitions == [
        _Transition("uuid-NSG-5", "state-spec-draft")
    ]
    assert len(claude.spawns) == 1
    assert claude.spawns[0].agent_name == "spec_writer"
    assert "NSG-5" in claude.spawns[0].user_prompt


@pytest.mark.asyncio
async def test_skips_epics(settings: Settings, db: Database) -> None:
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [_issue("NSG-1", labels=("type:epic", "module:orders"))],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert claude.spawns == []
    assert linear.transitions == []


@pytest.mark.asyncio
async def test_skips_questions(settings: Settings, db: Database) -> None:
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [
                _issue("NSG-2", labels=("type:question", "needs-human-decision"))
            ],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert claude.spawns == []


@pytest.mark.asyncio
async def test_bugs_and_harness_fixes_are_enrichable(
    settings: Settings, db: Database
) -> None:
    """Spec Writer should treat bugs and harness-fix tickets the same as
    stories — all three need ACs + DoD attached before the Worker can
    pick them up."""
    for label in ("type:bug", "type:harness-fix"):
        linear = FakeLinearClient(
            issues_by_state={
                "Backlog": [_issue("NSG-9", labels=(label,))],
            },
            state_ids=_spec_draft_state_ids(),
        )
        claude = FakeClaudeRunner()
        daemon = _make_daemon(settings, db, linear, claude)
        await daemon.tick()
        assert len(claude.spawns) == 1, f"label={label} should be enrichable"


@pytest.mark.asyncio
async def test_picks_the_first_enrichable_when_mixed(
    settings: Settings, db: Database
) -> None:
    """Epic first in the list shouldn't block the Story behind it."""
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [
                _issue("NSG-1", labels=("type:epic",)),
                _issue("NSG-5", labels=("type:story",)),
            ],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert len(claude.spawns) == 1
    assert "NSG-5" in claude.spawns[0].user_prompt


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_spec_draft_state_skips_and_logs(
    settings: Settings, db: Database
) -> None:
    """If the team never created a 'Spec Draft' workflow state in Linear,
    the daemon must NOT spawn the agent on a half-broken transition."""
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [_issue("NSG-5", labels=("type:story",))],
        },
        state_ids={"Backlog": "state-backlog"},  # no "Spec Draft"
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert linear.transitions == []
    assert claude.spawns == []


@pytest.mark.asyncio
async def test_transition_failure_skips_agent_spawn(
    settings: Settings, db: Database
) -> None:
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [_issue("NSG-5", labels=("type:story",))],
        },
        state_ids=_spec_draft_state_ids(),
        raise_on_transition=True,
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert claude.spawns == []


@pytest.mark.asyncio
async def test_non_zero_agent_exit_records_learning_event(
    settings: Settings, db: Database
) -> None:
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [_issue("NSG-5", labels=("type:story",))],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner(next_exit_code=1, next_stderr="something failed")
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    events = db.list_learning_events()
    assert len(events) == 1
    assert events[0].event_type == "spec_writer_failed"
    assert events[0].ticket_id == "NSG-5"


@pytest.mark.asyncio
async def test_zero_exit_does_not_record_learning_event(
    settings: Settings, db: Database
) -> None:
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [_issue("NSG-5", labels=("type:story",))],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner(next_exit_code=0)
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert db.list_learning_events() == []


# ---------------------------------------------------------------------------
# State cache + in-flight set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_ids_are_cached_across_ticks(
    settings: Settings, db: Database
) -> None:
    """``list_team_states`` should be called at most once, then the
    daemon's internal cache serves subsequent transitions."""
    call_count = {"n": 0}

    class CountingFake(FakeLinearClient):
        async def list_team_states(self) -> dict[str, str]:
            call_count["n"] += 1
            return dict(self.state_ids)

    linear = CountingFake(
        issues_by_state={
            "Backlog": [
                _issue("NSG-5", labels=("type:story",)),
                _issue("NSG-6", labels=("type:story",)),
            ],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    # Tick 2 picks the other ticket; we simulate that by removing NSG-5
    # from Backlog (since the real Linear would have moved it).
    linear.issues_by_state["Backlog"] = [
        _issue("NSG-6", labels=("type:story",))
    ]
    await daemon.tick()
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_in_flight_ticket_is_not_repicked(
    settings: Settings, db: Database
) -> None:
    """Pre-populate the in-flight set and confirm pick_one skips it.

    Simulates the race where a second tick fires before the first tick's
    Linear transition has propagated."""
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [_issue("NSG-5", labels=("type:story",))],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    daemon._in_flight.add("NSG-5")
    await daemon.tick()
    assert claude.spawns == []
    assert linear.transitions == []


# ---------------------------------------------------------------------------
# Orphaned Spec Draft recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redrives_orphaned_spec_draft_without_transitioning(
    settings: Settings, db: Database
) -> None:
    """A ticket stuck in Spec Draft (prior agent run died before reaching
    Ready for Agent) gets the agent re-spawned, with no Backlog → Spec
    Draft transition (it is already there)."""
    linear = FakeLinearClient(
        issues_by_state={
            "Spec Draft": [_issue("NSG-7", labels=("type:story",))],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert linear.transitions == []  # already in Spec Draft
    assert len(claude.spawns) == 1
    assert "NSG-7" in claude.spawns[0].user_prompt
    assert db.get_attempts("NSG-7", "spec") == 1


@pytest.mark.asyncio
async def test_backlog_has_priority_over_orphaned_spec_draft(
    settings: Settings, db: Database
) -> None:
    """Fresh Backlog work drains before we spend a tick re-driving a
    stranded Spec Draft."""
    linear = FakeLinearClient(
        issues_by_state={
            "Backlog": [_issue("NSG-5", labels=("type:story",))],
            "Spec Draft": [_issue("NSG-7", labels=("type:story",))],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert linear.transitions == [_Transition("uuid-NSG-5", "state-spec-draft")]
    assert len(claude.spawns) == 1
    assert "NSG-5" in claude.spawns[0].user_prompt
    assert db.get_attempts("NSG-7", "spec") == 0  # orphan untouched this tick


@pytest.mark.asyncio
async def test_orphaned_spec_draft_escalates_after_budget(
    tmp_path: Path, db: Database
) -> None:
    """Once a Spec Draft has burned its retry budget it is labelled
    needs-human and the agent is not spawned again."""
    settings = Settings(WORKTREES_DIR=str(tmp_path / "wt"), MAX_AUTO_RETRIES=1)
    linear = FakeLinearClient(
        issues_by_state={
            "Spec Draft": [_issue("NSG-7", labels=("type:story",))],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    db.bump_attempt("NSG-7", "spec")  # already at the limit (MAX=1)

    await daemon.tick()

    assert claude.spawns == []  # not re-driven
    assert len(linear.label_updates) == 1
    issue_id, label_ids = linear.label_updates[0]
    assert issue_id == "uuid-NSG-7"
    assert "label-needs-human" in label_ids
    assert len(linear.comments) == 1


@pytest.mark.asyncio
async def test_needs_human_spec_draft_is_not_repicked(
    settings: Settings, db: Database
) -> None:
    """A Spec Draft already escalated to a human is left alone."""
    linear = FakeLinearClient(
        issues_by_state={
            "Spec Draft": [
                _issue("NSG-7", labels=("type:story", "needs-human"))
            ],
        },
        state_ids=_spec_draft_state_ids(),
    )
    claude = FakeClaudeRunner()
    daemon = _make_daemon(settings, db, linear, claude)
    await daemon.tick()
    assert claude.spawns == []
    assert linear.label_updates == []

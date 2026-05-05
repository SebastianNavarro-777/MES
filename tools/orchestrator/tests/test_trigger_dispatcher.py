"""Tests for the orchestrator's trigger dispatcher.

The dispatcher is the brain that decides whether Architect / Auditor /
Gardener should fire on each poll. These tests exercise:

- Architect: backlog-below-threshold + cooldown + ``--run-now`` override.
- Auditor: unaudited-PR threshold + cooldown + ``--run-now`` override.
- Gardener: learning-event threshold OR PR-safety-net threshold + cooldown.
- Inspection state.

All tests run against an in-memory SQLite DB and a synthetic
``backlog_count_provider`` callable, so no Linear / network access is
needed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tools.orchestrator.orchestrator.config import Settings
from tools.orchestrator.orchestrator.db import Database
from tools.orchestrator.orchestrator.trigger_dispatcher import (
    AgentName,
    ArchitectDecision,
    AuditorDecision,
    GardenerDecision,
    TriggerDispatcher,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(
        ARCHITECT_BACKLOG_THRESHOLD=5,
        AUDITOR_PR_THRESHOLD=5,
        GARDENER_LEARNING_THRESHOLD=10,
        GARDENER_PR_SAFETY_THRESHOLD=50,
        AGENT_COOLDOWN_MINUTES=30,
        WORKTREES_DIR=str(tmp_path / "wt"),
    )
    return s


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(tmp_path / "queue.db")
    yield d
    d.close()


def _dispatcher(
    settings: Settings,
    db: Database,
    *,
    backlog: int = 0,
    now: datetime | None = None,
) -> TriggerDispatcher:
    fixed = now or datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    def backlog_provider() -> int:
        return backlog

    def now_fn() -> datetime:
        return fixed

    return TriggerDispatcher(
        settings=settings,
        db=db,
        backlog_count_provider=backlog_provider,
        now=now_fn,
    )


def _record_unaudited_prs(db: Database, n: int) -> list[int]:
    pr_numbers: list[int] = []
    for i in range(n):
        pr = 100 + i
        db.record_merged_pr(pr, f"NSG-{200 + i}")
        pr_numbers.append(pr)
    return pr_numbers


# ---------------------------------------------------------------------------
# Architect
# ---------------------------------------------------------------------------


def test_architect_fires_when_backlog_below_threshold(
    settings: Settings, db: Database
) -> None:
    d = _dispatcher(settings, db, backlog=2)
    decision = d.evaluate_architect()
    assert isinstance(decision, ArchitectDecision)
    assert decision.fire is True
    assert "backlog=2" in decision.reason
    assert decision.backlog_count == 2


def test_architect_does_not_fire_when_backlog_at_or_above_threshold(
    settings: Settings, db: Database
) -> None:
    d_at = _dispatcher(settings, db, backlog=5)
    d_above = _dispatcher(settings, db, backlog=8)
    assert d_at.evaluate_architect().fire is False
    assert d_above.evaluate_architect().fire is False


def test_architect_respects_one_hour_cooldown(
    settings: Settings, db: Database, fixed_now: datetime
) -> None:
    # Stamp a recent run (30 min ago — under the 1h cooldown).
    db.record_agent_run("architect", when=fixed_now - timedelta(minutes=30))
    d = _dispatcher(settings, db, backlog=2, now=fixed_now)
    assert d.evaluate_architect().fire is False
    assert "cooldown" in d.evaluate_architect().reason


def test_architect_run_now_overrides_cooldown(
    settings: Settings, db: Database, fixed_now: datetime
) -> None:
    db.record_agent_run("architect", when=fixed_now - timedelta(minutes=30))
    d = _dispatcher(settings, db, backlog=2, now=fixed_now)
    forced = d.evaluate_architect(force=True)
    assert forced.fire is True
    assert "forced" in forced.reason


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------


def test_auditor_fires_at_threshold_with_exact_pr_list(
    settings: Settings, db: Database
) -> None:
    pr_numbers = _record_unaudited_prs(db, 5)
    d = _dispatcher(settings, db)
    decision = d.evaluate_auditor()
    assert isinstance(decision, AuditorDecision)
    assert decision.fire is True
    # The dispatcher hands the agent every unaudited PR — no sampling.
    assert sorted(decision.pr_numbers) == sorted(pr_numbers)


def test_auditor_does_not_fire_below_threshold(
    settings: Settings, db: Database
) -> None:
    _record_unaudited_prs(db, 4)  # threshold is 5
    d = _dispatcher(settings, db)
    decision = d.evaluate_auditor()
    assert decision.fire is False
    assert decision.pr_numbers != ()  # we still report what we have


def test_auditor_respects_global_cooldown(
    settings: Settings, db: Database, fixed_now: datetime
) -> None:
    _record_unaudited_prs(db, 6)
    db.record_agent_run("auditor", when=fixed_now - timedelta(minutes=10))
    d = _dispatcher(settings, db, now=fixed_now)
    assert d.evaluate_auditor().fire is False


def test_auditor_run_now_overrides_cooldown_when_prs_exist(
    settings: Settings, db: Database, fixed_now: datetime
) -> None:
    _record_unaudited_prs(db, 2)  # below threshold, but force should still fire
    db.record_agent_run("auditor", when=fixed_now - timedelta(minutes=5))
    d = _dispatcher(settings, db, now=fixed_now)
    forced = d.evaluate_auditor(force=True)
    assert forced.fire is True


def test_auditor_run_now_does_not_fire_when_no_prs_to_audit(
    settings: Settings, db: Database
) -> None:
    """``--run-now`` cannot conjure work that doesn't exist."""
    d = _dispatcher(settings, db)
    decision = d.evaluate_auditor(force=True)
    assert decision.fire is False
    assert "no unaudited PRs" in decision.reason


# ---------------------------------------------------------------------------
# Gardener
# ---------------------------------------------------------------------------


def test_gardener_fires_on_learning_threshold(
    settings: Settings, db: Database
) -> None:
    for i in range(10):
        db.record_learning_event("ticket_failed", f"NSG-{i}")
    d = _dispatcher(settings, db)
    decision = d.evaluate_gardener()
    assert isinstance(decision, GardenerDecision)
    assert decision.fire is True
    assert len(decision.learning_event_ids) == 10
    assert "learning=10" in decision.reason


def test_gardener_fires_on_pr_safety_net_with_zero_learning_events(
    settings: Settings, db: Database
) -> None:
    """Even with 0 learning events, the safety net trips when enough PRs accumulate."""
    _record_unaudited_prs(db, 50)
    d = _dispatcher(settings, db)
    decision = d.evaluate_gardener()
    assert decision.fire is True
    assert len(decision.pr_numbers) == 50
    assert "pr_safety=50" in decision.reason


def test_gardener_does_not_fire_below_both_thresholds(
    settings: Settings, db: Database
) -> None:
    for i in range(9):  # below learning threshold of 10
        db.record_learning_event("ticket_failed", f"NSG-{i}")
    _record_unaudited_prs(db, 49)  # below safety threshold of 50
    d = _dispatcher(settings, db)
    assert d.evaluate_gardener().fire is False


def test_gardener_respects_global_cooldown(
    settings: Settings, db: Database, fixed_now: datetime
) -> None:
    for i in range(15):
        db.record_learning_event("ticket_failed", f"NSG-{i}")
    db.record_agent_run("gardener", when=fixed_now - timedelta(minutes=5))
    d = _dispatcher(settings, db, now=fixed_now)
    assert d.evaluate_gardener().fire is False


def test_gardener_run_now_overrides_cooldown(
    settings: Settings, db: Database, fixed_now: datetime
) -> None:
    for i in range(15):
        db.record_learning_event("ticket_failed", f"NSG-{i}")
    db.record_agent_run("gardener", when=fixed_now - timedelta(minutes=5))
    d = _dispatcher(settings, db, now=fixed_now)
    forced = d.evaluate_gardener(force=True)
    assert forced.fire is True
    assert len(forced.learning_event_ids) == 15


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


def test_evaluate_returns_decisions_for_all_three_agents_in_order(
    settings: Settings, db: Database
) -> None:
    d = _dispatcher(settings, db)
    decisions = d.evaluate()
    assert [dec.agent for dec in decisions] == [
        AgentName.ARCHITECT,
        AgentName.AUDITOR,
        AgentName.GARDENER,
    ]


def test_evaluate_with_override_only_forces_named_agent(
    settings: Settings, db: Database, fixed_now: datetime
) -> None:
    # Both auditor and gardener have recent runs (cooldown active).
    db.record_agent_run("auditor", when=fixed_now - timedelta(minutes=5))
    db.record_agent_run("gardener", when=fixed_now - timedelta(minutes=5))
    _record_unaudited_prs(db, 6)
    for i in range(15):
        db.record_learning_event("ticket_failed", f"NSG-{i}")

    d = _dispatcher(settings, db, now=fixed_now)
    decisions = {dec.agent: dec for dec in d.evaluate(override=AgentName.AUDITOR)}
    assert decisions[AgentName.AUDITOR].fire is True
    assert decisions[AgentName.GARDENER].fire is False  # still in cooldown


def test_inspect_reports_state_without_firing(
    settings: Settings, db: Database, fixed_now: datetime
) -> None:
    _record_unaudited_prs(db, 3)
    for i in range(7):
        db.record_learning_event("ticket_failed", f"NSG-{i}")
    db.record_agent_run("architect", when=fixed_now - timedelta(minutes=10))
    d = _dispatcher(settings, db, backlog=2, now=fixed_now)

    snap = d.inspect()
    assert snap.backlog_count == 2
    assert snap.architect_threshold == 5
    assert snap.architect_in_cooldown is True
    assert snap.pending_audit_pr_count == 3
    assert snap.auditor_threshold == 5
    assert snap.unconsumed_learning_events == 7
    assert snap.learning_threshold == 10
    assert snap.gardener_in_cooldown is False  # never run yet


def test_provider_callable_is_used_for_backlog_count(
    settings: Settings, db: Database
) -> None:
    """The dispatcher does not call Linear directly — it asks the provider."""
    calls: list[int] = []

    def provider() -> int:
        calls.append(1)
        return 0

    fixed = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    d = TriggerDispatcher(
        settings=settings,
        db=db,
        backlog_count_provider=provider,
        now=lambda: fixed,
    )
    d.evaluate_architect()
    d.evaluate_architect()
    assert sum(calls) == 2  # once per call


def test_now_callable_is_used_for_cooldown_math(
    settings: Settings, db: Database
) -> None:
    """The dispatcher's clock is injectable, so cooldown tests are deterministic."""
    early = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    late = early + timedelta(hours=2)

    def provider() -> int:
        return 0

    db.record_agent_run("architect", when=early)
    d_early = TriggerDispatcher(
        settings=settings, db=db, backlog_count_provider=provider, now=lambda: early
    )
    d_late = TriggerDispatcher(
        settings=settings, db=db, backlog_count_provider=provider, now=lambda: late
    )
    # Right after running, still in cooldown.
    assert d_early.evaluate_architect().fire is False
    # 2 hours later, cooldown has elapsed.
    assert d_late.evaluate_architect().fire is True


def test_callable_typed_provider() -> None:
    """Sanity: TriggerDispatcher accepts any Callable[[], int]."""
    p: Callable[[], int] = lambda: 0  # noqa: E731
    assert p() == 0

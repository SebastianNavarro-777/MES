"""Trigger dispatcher — fires Architect / Auditor / Gardener on counter thresholds.

The dispatcher is purely *reactive*: it checks SQLite counters every poll
and decides whether each one-shot agent should run. It enforces a
per-agent cooldown plus a global ``AGENT_COOLDOWN_MINUTES`` to prevent
runaway loops if something goes wrong downstream.

Tests cover:

- Architect dispatches when the Linear ``Backlog`` count is below threshold.
- Auditor dispatches when ``pr_events.audited == FALSE`` count crosses threshold.
- Gardener dispatches on either learning-event threshold OR the safety-net
  PR threshold.
- Cooldown logic, including ``--run-now`` overrides.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .config import Settings
from .db import Database, PrEvent

__all__ = [
    "AgentName",
    "ArchitectDecision",
    "AuditorDecision",
    "GardenerDecision",
    "TriggerDecision",
    "TriggerDispatcher",
    "TriggerInspection",
]


class AgentName(enum.StrEnum):
    ARCHITECT = "architect"
    AUDITOR = "auditor"
    GARDENER = "gardener"


# ---------------------------------------------------------------------------
# Decision types — what the dispatcher hands to each agent runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TriggerDecision:
    """Common header — whether to fire and why."""

    agent: AgentName
    fire: bool
    reason: str


@dataclass(frozen=True)
class ArchitectDecision(TriggerDecision):
    # ``backlog_count`` is the count of in-flight (unfinished) Stories — every
    # ticket state except Done and Failed — NOT just the ``Backlog`` state.
    # The field name is retained for backwards compatibility; see NSG-49 and
    # ``state_machine.inflight_states`` for the broadened semantics.
    backlog_count: int = 0


@dataclass(frozen=True)
class AuditorDecision(TriggerDecision):
    pr_numbers: tuple[int, ...] = ()


@dataclass(frozen=True)
class GardenerDecision(TriggerDecision):
    learning_event_ids: tuple[int, ...] = ()
    pr_numbers: tuple[int, ...] = ()


# ---------------------------------------------------------------------------
# Inspection — what `--inspect` prints
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TriggerInspection:
    backlog_count: int
    architect_threshold: int
    architect_last_run: datetime | None
    architect_in_cooldown: bool

    pending_audit_pr_count: int
    auditor_threshold: int
    auditor_last_run: datetime | None
    auditor_in_cooldown: bool

    unconsumed_learning_events: int
    learning_threshold: int
    pr_safety_pending: int
    pr_safety_threshold: int
    gardener_last_run: datetime | None
    gardener_in_cooldown: bool

    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class TriggerDispatcher:
    """Decides which one-shot agents to fire, given DB and Linear state.

    The dispatcher does NOT call Linear or Claude itself — it returns
    typed decisions that callers (the agent runners) act upon. This makes
    it trivially testable.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        db: Database,
        backlog_count_provider: Callable[[], int],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._db = db
        self._backlog_count_provider = backlog_count_provider
        self._now = now

    # -- public API ----------------------------------------------------------

    def evaluate(self, *, override: AgentName | None = None) -> list[TriggerDecision]:
        """Return decisions for all three one-shot agents in a stable order.

        ``override`` corresponds to the ``--run-now`` flag. When set, that
        single agent's cooldown gate is bypassed; the threshold gate is
        still respected (you can't "force" an Auditor when there are no
        unaudited PRs — the agent would have nothing to do).
        """
        out: list[TriggerDecision] = [
            self.evaluate_architect(force=override == AgentName.ARCHITECT),
            self.evaluate_auditor(force=override == AgentName.AUDITOR),
            self.evaluate_gardener(force=override == AgentName.GARDENER),
        ]
        return out

    def inspect(self) -> TriggerInspection:
        """Snapshot the state without firing anything. Used by --inspect."""
        backlog_count = self._backlog_count_provider()
        unaudited = [p.pr_number for p in self._unaudited_prs()]
        learning_ids = [
            e.id
            for e in self._db.list_learning_events(consumed_by_gardener=False)
        ]
        unconsumed_pr_count = len(self._unconsumed_prs_for_gardener())

        notes: list[str] = []
        if not self._settings.is_configured():
            notes.append("Live credentials not configured; orchestrator is in dry mode.")

        return TriggerInspection(
            backlog_count=backlog_count,
            architect_threshold=self._settings.ARCHITECT_BACKLOG_THRESHOLD,
            architect_last_run=self._last_run(AgentName.ARCHITECT),
            architect_in_cooldown=self._in_cooldown(
                AgentName.ARCHITECT, self._architect_cooldown()
            ),
            pending_audit_pr_count=len(unaudited),
            auditor_threshold=self._settings.AUDITOR_PR_THRESHOLD,
            auditor_last_run=self._last_run(AgentName.AUDITOR),
            auditor_in_cooldown=self._in_cooldown(
                AgentName.AUDITOR, self._global_cooldown()
            ),
            unconsumed_learning_events=len(learning_ids),
            learning_threshold=self._settings.GARDENER_LEARNING_THRESHOLD,
            pr_safety_pending=unconsumed_pr_count,
            pr_safety_threshold=self._settings.GARDENER_PR_SAFETY_THRESHOLD,
            gardener_last_run=self._last_run(AgentName.GARDENER),
            gardener_in_cooldown=self._in_cooldown(
                AgentName.GARDENER, self._global_cooldown()
            ),
            notes=notes,
        )

    # -- per-agent evaluators ------------------------------------------------

    def evaluate_architect(self, *, force: bool = False) -> ArchitectDecision:
        backlog = self._backlog_count_provider()
        threshold = self._settings.ARCHITECT_BACKLOG_THRESHOLD
        if backlog >= threshold:
            # `backlog` is the in-flight Story count (see ArchitectDecision).
            # Above threshold means the active phase still has unfinished work
            # in flight — the backlog is NOT exhausted, so do not fire.
            return ArchitectDecision(
                agent=AgentName.ARCHITECT,
                fire=False,
                reason=(
                    f"in-flight work={backlog} ≥ threshold={threshold}; "
                    f"backlog not exhausted"
                ),
                backlog_count=backlog,
            )
        if not force and self._in_cooldown(
            AgentName.ARCHITECT, self._architect_cooldown()
        ):
            return ArchitectDecision(
                agent=AgentName.ARCHITECT,
                fire=False,
                reason="architect in cooldown",
                backlog_count=backlog,
            )
        return ArchitectDecision(
            agent=AgentName.ARCHITECT,
            fire=True,
            reason=(
                f"backlog={backlog} < threshold={threshold}"
                + (" (forced)" if force else "")
            ),
            backlog_count=backlog,
        )

    def evaluate_auditor(self, *, force: bool = False) -> AuditorDecision:
        unaudited = self._unaudited_prs()
        threshold = self._settings.AUDITOR_PR_THRESHOLD
        pr_numbers = tuple(p.pr_number for p in unaudited)

        if not force and len(pr_numbers) < threshold:
            return AuditorDecision(
                agent=AgentName.AUDITOR,
                fire=False,
                reason=f"unaudited={len(pr_numbers)} < threshold={threshold}",
                pr_numbers=pr_numbers,
            )
        if not pr_numbers:
            # Even with --run-now, there's nothing to do.
            return AuditorDecision(
                agent=AgentName.AUDITOR,
                fire=False,
                reason="no unaudited PRs",
                pr_numbers=(),
            )
        if not force and self._in_cooldown(
            AgentName.AUDITOR, self._global_cooldown()
        ):
            return AuditorDecision(
                agent=AgentName.AUDITOR,
                fire=False,
                reason="auditor in global cooldown",
                pr_numbers=pr_numbers,
            )
        return AuditorDecision(
            agent=AgentName.AUDITOR,
            fire=True,
            reason=(
                f"unaudited={len(pr_numbers)} ≥ threshold={threshold}"
                + (" (forced)" if force else "")
            ),
            pr_numbers=pr_numbers,
        )

    def evaluate_gardener(self, *, force: bool = False) -> GardenerDecision:
        learning = self._db.list_learning_events(consumed_by_gardener=False)
        prs = self._unconsumed_prs_for_gardener()

        learning_ids = tuple(e.id for e in learning)
        pr_numbers = tuple(p.pr_number for p in prs)

        learning_hit = len(learning_ids) >= self._settings.GARDENER_LEARNING_THRESHOLD
        safety_hit = len(pr_numbers) >= self._settings.GARDENER_PR_SAFETY_THRESHOLD

        if not force and not (learning_hit or safety_hit):
            return GardenerDecision(
                agent=AgentName.GARDENER,
                fire=False,
                reason=(
                    f"learning={len(learning_ids)}/"
                    f"{self._settings.GARDENER_LEARNING_THRESHOLD}, "
                    f"pr_safety={len(pr_numbers)}/"
                    f"{self._settings.GARDENER_PR_SAFETY_THRESHOLD}"
                ),
                learning_event_ids=learning_ids,
                pr_numbers=pr_numbers,
            )
        if not force and self._in_cooldown(
            AgentName.GARDENER, self._global_cooldown()
        ):
            return GardenerDecision(
                agent=AgentName.GARDENER,
                fire=False,
                reason="gardener in global cooldown",
                learning_event_ids=learning_ids,
                pr_numbers=pr_numbers,
            )

        if not (learning_ids or pr_numbers):
            # Nothing to do, even forced.
            return GardenerDecision(
                agent=AgentName.GARDENER,
                fire=False,
                reason="no learning events or unconsumed PRs",
                learning_event_ids=(),
                pr_numbers=(),
            )

        reason_parts = []
        if learning_hit:
            reason_parts.append(
                f"learning={len(learning_ids)} ≥ "
                f"{self._settings.GARDENER_LEARNING_THRESHOLD}"
            )
        if safety_hit:
            reason_parts.append(
                f"pr_safety={len(pr_numbers)} ≥ "
                f"{self._settings.GARDENER_PR_SAFETY_THRESHOLD}"
            )
        if force and not reason_parts:
            reason_parts.append("forced")
        return GardenerDecision(
            agent=AgentName.GARDENER,
            fire=True,
            reason=", ".join(reason_parts) or "forced",
            learning_event_ids=learning_ids,
            pr_numbers=pr_numbers,
        )

    # -- internal helpers ----------------------------------------------------

    def _unaudited_prs(self) -> list[PrEvent]:
        return self._db.list_pr_events(audited=False)

    def _unconsumed_prs_for_gardener(self) -> list[PrEvent]:
        return self._db.list_pr_events(consumed_by_gardener=False)

    def _last_run(self, agent: AgentName) -> datetime | None:
        state = self._db.get_agent_state(agent.value)
        return state.last_triggered_at if state else None

    def _in_cooldown(self, agent: AgentName, cooldown: timedelta) -> bool:
        last = self._last_run(agent)
        if last is None:
            return False
        return (self._now() - last) < cooldown

    def _architect_cooldown(self) -> timedelta:
        # Architect-specific cooldown is 1 hour per the prompt spec; the
        # global per-agent cooldown still applies but the architect is
        # always at least 1h.
        global_minutes = self._settings.AGENT_COOLDOWN_MINUTES
        return timedelta(minutes=max(60, global_minutes))

    def _global_cooldown(self) -> timedelta:
        return timedelta(minutes=self._settings.AGENT_COOLDOWN_MINUTES)

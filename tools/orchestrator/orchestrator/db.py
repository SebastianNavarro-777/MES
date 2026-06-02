"""SQLite-backed orchestrator state.

The DB is the single source of truth for trigger counters, queued work,
PR audit state, and learning events. Stored under
``.orchestrator-state/queue.db`` at the repo root by default.

Uses the stdlib ``sqlite3`` module — no async driver. Access from daemons
is wrapped in ``asyncio.to_thread`` when called from async code.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "AgentTriggerState",
    "Database",
    "LearningEvent",
    "PrEvent",
    "WorkItem",
]


# ---------------------------------------------------------------------------
# Row types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkItem:
    """A ticket queued for one of the daemons."""

    ticket_id: str
    state: str
    enqueued_at: datetime
    metadata: dict[str, Any]


@dataclass(frozen=True)
class AgentTriggerState:
    """Counter + cooldown for Architect / Auditor / Gardener."""

    agent_name: str
    counter: int
    last_triggered_at: datetime | None
    last_triggered_pr_number: int | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class PrEvent:
    """One row per merged PR. ``audited`` is set TRUE by the Auditor."""

    pr_number: int
    ticket_id: str
    merged_at: datetime
    audited: bool
    consumed_by_gardener: bool


@dataclass(frozen=True)
class LearningEvent:
    """An anomaly the Gardener may turn into a harness change."""

    id: int
    event_type: str
    ticket_id: str
    occurred_at: datetime
    consumed_by_gardener: bool


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_queue (
    ticket_id   TEXT PRIMARY KEY,
    state       TEXT NOT NULL,
    enqueued_at TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS agent_trigger_state (
    agent_name              TEXT PRIMARY KEY,
    counter                 INTEGER NOT NULL DEFAULT 0,
    last_triggered_at       TEXT,
    last_triggered_pr_number INTEGER,
    metadata                TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS pr_events (
    pr_number             INTEGER PRIMARY KEY,
    ticket_id             TEXT NOT NULL,
    merged_at             TEXT NOT NULL,
    audited               INTEGER NOT NULL DEFAULT 0,
    consumed_by_gardener  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS learning_events (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type            TEXT NOT NULL,
    ticket_id             TEXT NOT NULL,
    occurred_at           TEXT NOT NULL,
    consumed_by_gardener  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ticket_attempts (
    ticket_id   TEXT NOT NULL,
    stage       TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ticket_id, stage)
);

CREATE TABLE IF NOT EXISTS in_progress_seen (
    ticket_id     TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _row_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    parsed: object = json.loads(raw)
    if not isinstance(parsed, dict):
        return {}
    return {str(k): v for k, v in parsed.items()}


# ---------------------------------------------------------------------------
# Database wrapper
# ---------------------------------------------------------------------------


class Database:
    """Thin wrapper over the orchestrator's SQLite file.

    Construct once per process. All methods are synchronous; daemons that
    are async should wrap calls in ``asyncio.to_thread``.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # -- transaction helper --------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        cur = self._conn.cursor()
        cur.execute("BEGIN")
        try:
            yield self._conn
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise

    # -- work queue ----------------------------------------------------------

    def enqueue(
        self, ticket_id: str, state: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Insert or update a work-queue entry. Idempotent on ticket_id."""
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO work_queue (ticket_id, state, enqueued_at, metadata)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ticket_id) DO UPDATE SET
                    state = excluded.state,
                    enqueued_at = excluded.enqueued_at,
                    metadata = excluded.metadata
                """,
                (
                    ticket_id,
                    state,
                    _utc_now_iso(),
                    json.dumps(metadata or {}),
                ),
            )

    def list_work_items(self, state: str | None = None) -> list[WorkItem]:
        sql = "SELECT * FROM work_queue"
        params: tuple[Any, ...] = ()
        if state is not None:
            sql += " WHERE state = ?"
            params = (state,)
        sql += " ORDER BY enqueued_at"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            WorkItem(
                ticket_id=row["ticket_id"],
                state=row["state"],
                enqueued_at=_parse_dt(row["enqueued_at"]) or datetime.now(UTC),
                metadata=_row_metadata(row["metadata"]),
            )
            for row in rows
        ]

    def remove_work_item(self, ticket_id: str) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM work_queue WHERE ticket_id = ?", (ticket_id,))

    # -- auto-retry accounting ----------------------------------------------

    def get_attempts(self, ticket_id: str, stage: str) -> int:
        """How many automated re-attempts a ticket has had at ``stage``.

        ``stage`` separates the recovery budgets — e.g. ``"spec"`` for
        Spec Writer re-drives vs. ``"worker"`` for Failed → Ready for
        Agent re-queues — so one stage burning its budget doesn't deny
        the other.
        """
        row = self._conn.execute(
            "SELECT attempts FROM ticket_attempts WHERE ticket_id = ? AND stage = ?",
            (ticket_id, stage),
        ).fetchone()
        return int(row["attempts"]) if row is not None else 0

    def bump_attempt(self, ticket_id: str, stage: str) -> int:
        """Increment and return the attempt counter for ``(ticket, stage)``."""
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO ticket_attempts (ticket_id, stage, attempts)
                VALUES (?, ?, 1)
                ON CONFLICT(ticket_id, stage) DO UPDATE SET
                    attempts = attempts + 1
                """,
                (ticket_id, stage),
            )
        row = self._conn.execute(
            "SELECT attempts FROM ticket_attempts WHERE ticket_id = ? AND stage = ?",
            (ticket_id, stage),
        ).fetchone()
        return int(row["attempts"]) if row is not None else 0

    # -- In Progress staleness tracking -------------------------------------

    def mark_in_progress_seen(
        self, ticket_id: str, *, now: datetime | None = None
    ) -> datetime:
        """Record (once) when a ticket was first observed In Progress.

        Idempotent: the first observation's timestamp is kept on later
        calls so the staleness clock measures continuous time in the
        state, and it survives orchestrator restarts (the row is durable).
        Returns the stored first-seen timestamp. ``now`` overrides the
        recorded timestamp (tests use it to age a ticket deterministically).
        """
        ts_iso = (now or datetime.now(UTC)).isoformat()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO in_progress_seen (ticket_id, first_seen_at)
                VALUES (?, ?)
                ON CONFLICT(ticket_id) DO NOTHING
                """,
                (ticket_id, ts_iso),
            )
        row = self._conn.execute(
            "SELECT first_seen_at FROM in_progress_seen WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()
        if row is None:
            return datetime.now(UTC)
        return _parse_dt(row["first_seen_at"]) or datetime.now(UTC)

    def clear_in_progress_seen(self, ticket_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "DELETE FROM in_progress_seen WHERE ticket_id = ?", (ticket_id,)
            )

    def prune_in_progress_seen(self, keep: Iterable[str]) -> None:
        """Drop staleness rows for tickets no longer In Progress.

        Called each tick with the set of currently-In Progress tickets so
        a ticket that left and later re-enters the state restarts its
        clock instead of inheriting a stale (premature) timestamp.
        """
        keep_set = set(keep)
        existing = self._conn.execute(
            "SELECT ticket_id FROM in_progress_seen"
        ).fetchall()
        to_drop = [r["ticket_id"] for r in existing if r["ticket_id"] not in keep_set]
        if not to_drop:
            return
        with self.transaction() as conn:
            placeholders = ",".join("?" * len(to_drop))
            conn.execute(
                f"DELETE FROM in_progress_seen WHERE ticket_id IN ({placeholders})",
                to_drop,
            )

    # -- PR events -----------------------------------------------------------

    def record_merged_pr(self, pr_number: int, ticket_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO pr_events (pr_number, ticket_id, merged_at,
                                       audited, consumed_by_gardener)
                VALUES (?, ?, ?, 0, 0)
                ON CONFLICT(pr_number) DO NOTHING
                """,
                (pr_number, ticket_id, _utc_now_iso()),
            )

    def list_pr_events(
        self,
        *,
        audited: bool | None = None,
        consumed_by_gardener: bool | None = None,
    ) -> list[PrEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        if audited is not None:
            clauses.append("audited = ?")
            params.append(1 if audited else 0)
        if consumed_by_gardener is not None:
            clauses.append("consumed_by_gardener = ?")
            params.append(1 if consumed_by_gardener else 0)
        sql = "SELECT * FROM pr_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY merged_at"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            PrEvent(
                pr_number=row["pr_number"],
                ticket_id=row["ticket_id"],
                merged_at=_parse_dt(row["merged_at"]) or datetime.now(UTC),
                audited=bool(row["audited"]),
                consumed_by_gardener=bool(row["consumed_by_gardener"]),
            )
            for row in rows
        ]

    def mark_prs_audited(self, pr_numbers: Iterable[int]) -> None:
        ids = list(pr_numbers)
        if not ids:
            return
        with self.transaction() as conn:
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE pr_events SET audited = 1 WHERE pr_number IN ({placeholders})",
                ids,
            )

    def mark_prs_consumed_by_gardener(self, pr_numbers: Iterable[int]) -> None:
        ids = list(pr_numbers)
        if not ids:
            return
        with self.transaction() as conn:
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE pr_events SET consumed_by_gardener = 1 WHERE pr_number IN ({placeholders})",  # noqa: E501
                ids,
            )

    # -- learning events -----------------------------------------------------

    def record_learning_event(self, event_type: str, ticket_id: str) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO learning_events (event_type, ticket_id, occurred_at)
                VALUES (?, ?, ?)
                """,
                (event_type, ticket_id, _utc_now_iso()),
            )
            row_id = cur.lastrowid
        return int(row_id) if row_id is not None else 0

    def record_learning_event_once(self, event_type: str, ticket_id: str) -> int:
        """Idempotent variant for poll-driven sources.

        Inserts a new ``learning_events`` row only if no unconsumed row
        with the same ``(event_type, ticket_id)`` already exists.
        Returns the row id of the newly-inserted row, or ``0`` when a
        duplicate was suppressed.

        Use this from any recurring loop (e.g., ``recolector`` ticks) so
        the Gardener's learning counter isn't inflated by repeated
        observations of the same condition. Once the Gardener consumes
        the row (``consumed_by_gardener = 1``), a future observation of
        the same condition will produce a fresh row — which is the
        correct behaviour: the harness may legitimately need to learn
        from the same ticket twice if circumstances change between
        Gardener cycles.
        """
        row = self._conn.execute(
            """
            SELECT id FROM learning_events
            WHERE event_type = ? AND ticket_id = ? AND consumed_by_gardener = 0
            LIMIT 1
            """,
            (event_type, ticket_id),
        ).fetchone()
        if row is not None:
            return 0
        return self.record_learning_event(event_type, ticket_id)

    def list_learning_events(
        self, *, consumed_by_gardener: bool | None = None
    ) -> list[LearningEvent]:
        sql = "SELECT * FROM learning_events"
        params: tuple[Any, ...] = ()
        if consumed_by_gardener is not None:
            sql += " WHERE consumed_by_gardener = ?"
            params = (1 if consumed_by_gardener else 0,)
        sql += " ORDER BY occurred_at"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            LearningEvent(
                id=row["id"],
                event_type=row["event_type"],
                ticket_id=row["ticket_id"],
                occurred_at=_parse_dt(row["occurred_at"]) or datetime.now(UTC),
                consumed_by_gardener=bool(row["consumed_by_gardener"]),
            )
            for row in rows
        ]

    def mark_learning_events_consumed(self, ids: Iterable[int]) -> None:
        ids_list = list(ids)
        if not ids_list:
            return
        with self.transaction() as conn:
            placeholders = ",".join("?" * len(ids_list))
            conn.execute(
                f"UPDATE learning_events SET consumed_by_gardener = 1 WHERE id IN ({placeholders})",
                ids_list,
            )

    # -- agent trigger state -------------------------------------------------

    def get_agent_state(self, agent_name: str) -> AgentTriggerState | None:
        row = self._conn.execute(
            "SELECT * FROM agent_trigger_state WHERE agent_name = ?",
            (agent_name,),
        ).fetchone()
        if row is None:
            return None
        return AgentTriggerState(
            agent_name=row["agent_name"],
            counter=row["counter"],
            last_triggered_at=_parse_dt(row["last_triggered_at"]),
            last_triggered_pr_number=row["last_triggered_pr_number"],
            metadata=_row_metadata(row["metadata"]),
        )

    def upsert_agent_state(
        self,
        agent_name: str,
        *,
        counter: int | None = None,
        last_triggered_at: datetime | None = None,
        last_triggered_pr_number: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        existing = self.get_agent_state(agent_name)

        def _existing_ts() -> str | None:
            if existing and existing.last_triggered_at is not None:
                return existing.last_triggered_at.isoformat()
            return None

        new_counter = (
            counter
            if counter is not None
            else (existing.counter if existing else 0)
        )
        new_ts = (
            last_triggered_at.isoformat()
            if last_triggered_at is not None
            else _existing_ts()
        )
        new_pr = (
            last_triggered_pr_number
            if last_triggered_pr_number is not None
            else (existing.last_triggered_pr_number if existing else None)
        )
        new_meta = (
            metadata
            if metadata is not None
            else (existing.metadata if existing else {})
        )
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO agent_trigger_state
                    (agent_name, counter, last_triggered_at,
                     last_triggered_pr_number, metadata)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(agent_name) DO UPDATE SET
                    counter = excluded.counter,
                    last_triggered_at = excluded.last_triggered_at,
                    last_triggered_pr_number = excluded.last_triggered_pr_number,
                    metadata = excluded.metadata
                """,
                (
                    agent_name,
                    new_counter,
                    new_ts,
                    new_pr,
                    json.dumps(new_meta),
                ),
            )

    def record_agent_run(
        self,
        agent_name: str,
        *,
        when: datetime | None = None,
        pr_number: int | None = None,
    ) -> None:
        """Stamp the last-triggered-at after the agent finished a run."""
        ts = when or datetime.now(UTC)
        self.upsert_agent_state(
            agent_name,
            last_triggered_at=ts,
            last_triggered_pr_number=pr_number,
        )

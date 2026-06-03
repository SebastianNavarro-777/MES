"""Tests for the orchestrator main process wiring (``run_all``).

Focused on the trigger tick: the per-poll step that asks Linear for the
in-flight Story count, evaluates the dispatcher, and logs why the Architect
did or did not fire. Linear is mocked with ``respx`` — no network access.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from tools.orchestrator.orchestrator.claude_runner import ClaudeRunner
from tools.orchestrator.orchestrator.config import Settings
from tools.orchestrator.orchestrator.db import Database
from tools.orchestrator.orchestrator.linear_client import (
    LINEAR_GRAPHQL_URL,
    LinearClient,
)
from tools.orchestrator.orchestrator.run_all import _trigger_tick


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        ARCHITECT_BACKLOG_THRESHOLD=5,
        AUDITOR_PR_THRESHOLD=5,
        GARDENER_LEARNING_THRESHOLD=10,
        GARDENER_PR_SAFETY_THRESHOLD=50,
        AGENT_COOLDOWN_MINUTES=30,
        WORKTREES_DIR=str(tmp_path / "wt"),
    )


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(tmp_path / "queue.db")
    yield d
    d.close()


def _nodes(n: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": {"issues": {"nodes": [{"id": str(i)} for i in range(n)]}}},
    )


@respx.mock
async def test_trigger_tick_logs_architect_not_firing_with_inflight_work(
    settings: Settings, db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    # AC-4: when the Architect holds back because work is in flight, the tick
    # logs the reason so orchestrator.jsonl distinguishes "work in flight,
    # backlog not exhausted" from a genuinely empty backlog.
    respx.post(LINEAR_GRAPHQL_URL).mock(return_value=_nodes(25))
    log = logging.getLogger("tools.orchestrator.orchestrator.run_all")
    claude = ClaudeRunner()
    async with LinearClient("k", "team") as linear:
        with caplog.at_level(logging.INFO):
            await _trigger_tick(
                settings=settings,
                db=db,
                linear=linear,
                claude=claude,
                log=log,
            )

    architect_logs = [
        rec.getMessage()
        for rec in caplog.records
        if "architect" in rec.getMessage() and "not firing" in rec.getMessage()
    ]
    assert architect_logs, f"no architect non-fire log found in {caplog.records!r}"
    assert "backlog not exhausted" in architect_logs[0]


@respx.mock
async def test_trigger_tick_counts_inflight_via_multi_state_query(
    settings: Settings, db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    # AC-1 wiring: the tick reads the in-flight count from a single multi-state
    # query (the `in` filter), not just `Backlog`. With 25 in flight it does
    # not fire the Architect; the logged reason carries the in-flight count.
    captured: dict[str, object] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return _nodes(25)

    respx.post(LINEAR_GRAPHQL_URL).mock(side_effect=_capture)
    log = logging.getLogger("tools.orchestrator.orchestrator.run_all")
    claude = ClaudeRunner()
    async with LinearClient("k", "team") as linear:
        with caplog.at_level(logging.INFO):
            await _trigger_tick(
                settings=settings,
                db=db,
                linear=linear,
                claude=claude,
                log=log,
            )

    variables = captured["variables"]
    assert isinstance(variables, dict)
    states = variables["states"]
    assert isinstance(states, list)
    # All in-flight states queried at once; Done/Failed never queried.
    assert "Backlog" in states
    assert "In Review" in states
    assert "Done" not in states
    assert "Failed" not in states

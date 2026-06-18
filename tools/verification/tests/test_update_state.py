"""Tests for :mod:`tools.verification.update_state`."""

from __future__ import annotations

import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.verification import update_state
from tools.verification.repo_stats import MergedPR, RepoStats

FIXED_NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)

SEED_STATE = """---
generated_by: tools/verification/update_state.py
last_generated_at: never (seed)
last_updated: 2026-05-04
---

# State snapshot — auto-generated

> **Seed placeholder.**

## Counts

| Item | Count |
|---|---|
| Bounded contexts implemented | 0 |
"""


def _stats() -> RepoStats:
    return RepoStats(
        bounded_contexts_scaffolded=8,
        bounded_contexts_with_code=0,
        domain_entities=0,
        api_endpoints=1,
        domain_events=0,
        test_functions=179,
        contexts=(),
        merged_prs=(
            MergedPR(
                number=7,
                ticket="NSG-21",
                subject="feat: order detail (#7)",
                date="2026-06-04",
            ),
        ),
        active_exec_plans=("plan-x.md",),
    )


# AC-1: the rendered snapshot replaces the seed timestamp with a real tz-aware
# UTC timestamp and drops the "Seed placeholder" notice.
def test_render_removes_seed_and_sets_real_timestamp() -> None:
    text = update_state.render_state(_stats(), generated_at=FIXED_NOW, open_questions=[])
    assert update_state.SEED_MARKER not in text
    assert "Seed placeholder" not in text
    assert "last_generated_at: 2026-06-04T12:00:00+00:00" in text


# AC-1 / GP-003: a naive datetime is rejected at the boundary.
def test_render_rejects_naive_datetime() -> None:
    naive = datetime(2026, 6, 4, 12, 0)  # intentionally tz-naive
    with pytest.raises(ValueError, match="timezone-aware"):
        update_state.render_state(_stats(), generated_at=naive, open_questions=[])


# AC-2: counts are rendered, non-zero where the repo has substance, and the
# n/a coverage cell is explicitly justified.
def test_counts_rendered_with_documented_na() -> None:
    text = update_state.render_state(_stats(), generated_at=FIXED_NOW, open_questions=[])
    assert "| Bounded contexts scaffolded | 8 |" in text
    assert "| API endpoints | 1 |" in text
    assert "| Coverage | n/a |" in text
    # The reason coverage stays n/a must be documented (AC-2).
    assert "too slow for a per-session Stop hook" in text


# AC-3: merged PRs, Open Questions and exec-plans sections are populated from
# real data — the "(none)" placeholders disappear when data exists.
def test_sections_populated_when_data_present() -> None:
    text = update_state.render_state(
        _stats(),
        generated_at=FIXED_NOW,
        open_questions=["NSG-99 — should we sign approvals?"],
    )
    assert "- #7 (NSG-21) 2026-06-04 — feat: order detail (#7)" in text
    assert "- NSG-99 — should we sign approvals?" in text
    assert "- `docs/exec-plans/active/plan-x.md`" in text
    assert "_(none open)_" not in text


# AC-7: when Linear is unavailable the section is marked, not populated, and
# rendering still succeeds.
def test_open_questions_unavailable_is_marked() -> None:
    text = update_state.render_state(_stats(), generated_at=FIXED_NOW, open_questions=None)
    assert "Linear was unavailable" in text
    assert "see AC-7" in text


# AC-7: no token → no network call, returns None (unavailable), never raises.
def test_fetch_returns_none_without_token() -> None:
    assert update_state.fetch_open_questions(token=None) is None


# AC-7: a network error inside the fetch is swallowed and reported as None.
def test_fetch_swallows_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> object:
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    assert update_state.fetch_open_questions(token="secret", timeout=0.1) is None


# AC-7: a well-formed Linear payload is narrowed to "ID — title", excluding
# already-resolved (completed/canceled) issues.
def test_parse_questions_filters_resolved() -> None:
    payload = {
        "data": {
            "issues": {
                "nodes": [
                    {"identifier": "NSG-1", "title": "open one", "state": {"type": "started"}},
                    {"identifier": "NSG-2", "title": "done one", "state": {"type": "completed"}},
                ]
            }
        }
    }
    assert update_state._parse_questions(payload) == ["NSG-1 — open one"]


# AC-1: writing over a seed file rewrites it and clears the seed marker.
def test_write_state_replaces_seed(tmp_path: Path) -> None:
    target = tmp_path / "STATE.md"
    target.write_text(SEED_STATE, encoding="utf-8", newline="\n")
    changed = update_state.write_state(
        target, stats=_stats(), generated_at=FIXED_NOW, open_questions=[]
    )
    assert changed is True
    assert update_state.SEED_MARKER not in target.read_text(encoding="utf-8")


# AC-5 / idempotency: a second run with no substantive change does not rewrite
# the file (avoids timestamp churn on every Stop hook).
def test_write_state_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "STATE.md"
    first_now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    second_now = datetime(2026, 6, 4, 13, 30, tzinfo=UTC)
    assert update_state.write_state(
        target, stats=_stats(), generated_at=first_now, open_questions=[]
    )
    before = target.read_text(encoding="utf-8")
    # Same substantive content, later timestamp → must NOT rewrite.
    changed = update_state.write_state(
        target, stats=_stats(), generated_at=second_now, open_questions=[]
    )
    assert changed is False
    assert target.read_text(encoding="utf-8") == before


# AC-5: the module is invocable exactly as the Stop hook calls it and exits 0.
def test_cli_runs_and_clears_seed(tmp_path: Path) -> None:
    state_path = tmp_path / "docs" / "generated" / "STATE.md"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(SEED_STATE, encoding="utf-8", newline="\n")
    rc = update_state.main(["--root", str(tmp_path), "--no-linear"])
    assert rc == 0
    assert update_state.SEED_MARKER not in state_path.read_text(encoding="utf-8")

"""Tests for ``tools.verification.update_state``."""

from __future__ import annotations

from pathlib import Path

from tools.verification.repo_scan import RepoStats
from tools.verification.state_sources import MergedPr, OpenQuestion
from tools.verification.update_state import build_state_md, main, render_state

_STATS = RepoStats(
    bounded_contexts_scaffolded=8,
    bounded_contexts_implemented=0,
    domain_entities=0,
    api_endpoints=0,
    domain_events=0,
    test_functions=162,
)


def _render(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "stats": _STATS,
        "prs": [MergedPr(number=3, source="owner/x", merged_on="2026-06-02")],
        "questions": [OpenQuestion(identifier="NSG-9", title="Sign-off?")],
        "plans": ["0001-migrate.md"],
        "timestamp": "2026-06-04T12:00:00Z",
    }
    kwargs.update(overrides)
    return render_state(**kwargs)  # type: ignore[arg-type]


def test_render_replaces_seed_with_real_timestamp() -> None:
    # AC-1: the seed marker is gone and a real UTC timestamp is present.
    out = _render()
    assert "never (seed)" not in out
    assert "Seed placeholder" not in out
    assert "last_generated_at: 2026-06-04T12:00:00Z" in out


def test_render_shows_nonzero_coherent_counts() -> None:
    # AC-2: counts coherent with the tree appear, including a non-zero figure.
    out = _render()
    assert "| Test functions | 162 |" in out
    assert "| Bounded contexts (scaffolded) | 8 |" in out
    assert "n/a" in out  # coverage documented as n/a


def test_render_populates_prs_and_questions_and_plans() -> None:
    # AC-3: real data appears; no "(none yet)" placeholder when data exists.
    out = _render()
    assert "#3" in out
    assert "NSG-9 — Sign-off?" in out
    assert "0001-migrate.md" in out
    assert "(none yet)" not in out


def test_render_marks_linear_unavailable_when_questions_none() -> None:
    # AC-7: when Linear is unavailable the section says so, no crash.
    out = _render(questions=None)
    assert "Linear unavailable" in out


def test_render_marks_git_unavailable_when_prs_none() -> None:
    # AC-7: git history unavailable degrades to an explicit note.
    out = _render(prs=None)
    assert "Git history unavailable" in out


def test_build_state_md_degrades_without_git_or_linear(tmp_path: Path) -> None:
    # AC-7: building over a non-git tmp dir with no Linear creds still works.
    out = build_state_md(tmp_path)
    assert "never (seed)" not in out
    assert "# State snapshot" in out


def test_main_writes_state_and_is_idempotent(tmp_path: Path) -> None:
    # AC-1/AC-5: running the generator rewrites STATE.md; a second run is a
    # no-op (no timestamp churn), so the Stop hook does not dirty the tree.
    (tmp_path / "docs" / "generated").mkdir(parents=True)
    assert main(["--root", str(tmp_path)]) == 0
    state = tmp_path / "docs" / "generated" / "STATE.md"
    first = state.read_text(encoding="utf-8")
    assert "never (seed)" not in first
    assert main(["--root", str(tmp_path)]) == 0
    assert state.read_text(encoding="utf-8") == first  # unchanged on re-run

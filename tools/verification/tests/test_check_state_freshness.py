"""Tests for ``tools.verification.check_state_freshness`` (AC-6)."""

from __future__ import annotations

from pathlib import Path

from tools.verification.check_state_freshness import (
    attestation_checked,
    find_problems,
    main,
    state_is_seed,
)

_SEED = (
    "---\nlast_generated_at: never (seed)\n---\n"
    "> **Seed placeholder.** Will be regenerated.\n"
)
_FRESH = "---\nlast_generated_at: 2026-06-04T12:00:00Z\n---\n# State snapshot\nbody\n"

_DOD_CHECKED = (
    "## DoD\n"
    "- [x] docs/generated/STATE.md se actualizó automáticamente vía hook\n"
)
_DOD_UNCHECKED = (
    "## DoD\n"
    "- [ ] docs/generated/STATE.md se actualizó automáticamente vía hook\n"
)


def test_attestation_checked_detects_checked_box() -> None:
    assert attestation_checked(_DOD_CHECKED) is True
    assert attestation_checked("- [x] STATE.md regenerated via hook") is True


def test_attestation_unchecked_box_is_not_attestation() -> None:
    assert attestation_checked(_DOD_UNCHECKED) is False
    assert attestation_checked("- [x] some unrelated box") is False


def test_state_is_seed_detects_placeholder() -> None:
    assert state_is_seed(_SEED) is True
    assert state_is_seed(_FRESH) is False


def test_false_attestation_over_seed_is_a_problem() -> None:
    # AC-6: ticking the box while STATE.md is still the seed is rejected.
    problems = find_problems(body=_DOD_CHECKED, state_text=_SEED)
    assert len(problems) == 1
    assert "seed placeholder" in problems[0]


def test_honest_attestation_passes() -> None:
    # AC-6: ticking the box with a regenerated STATE.md is fine.
    assert find_problems(body=_DOD_CHECKED, state_text=_FRESH) == []


def test_unchecked_box_never_problematic() -> None:
    # AC-6: no attestation, no problem — even over a seed file.
    assert find_problems(body=_DOD_UNCHECKED, state_text=_SEED) == []


def test_noop_rewrite_against_baseline_is_a_problem() -> None:
    # AC-6: "no hubo cambio de contenido" — identical to baseline (ignoring the
    # timestamp) while the box is ticked is also a false attestation.
    baseline = "---\nlast_generated_at: 2026-06-01T00:00:00Z\n---\nsame body\n"
    current = "---\nlast_generated_at: 2026-06-04T00:00:00Z\n---\nsame body\n"
    problems = find_problems(
        body=_DOD_CHECKED, state_text=current, baseline_text=baseline
    )
    assert any("unchanged versus the baseline" in p for p in problems)


def test_main_returns_one_on_false_attestation(tmp_path: Path) -> None:
    # AC-6: the CLI exits non-zero so CI / the Reviewer blocks the merge.
    state = tmp_path / "STATE.md"
    state.write_text(_SEED, encoding="utf-8")
    body = tmp_path / "body.md"
    body.write_text(_DOD_CHECKED, encoding="utf-8")
    rc = main(["--state", str(state), "--body-file", str(body)])
    assert rc == 1


def test_main_returns_zero_on_honest_attestation(tmp_path: Path) -> None:
    state = tmp_path / "STATE.md"
    state.write_text(_FRESH, encoding="utf-8")
    body = tmp_path / "body.md"
    body.write_text(_DOD_CHECKED, encoding="utf-8")
    rc = main(["--state", str(state), "--body-file", str(body)])
    assert rc == 0

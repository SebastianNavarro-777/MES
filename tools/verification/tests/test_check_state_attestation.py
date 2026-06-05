"""Tests for :mod:`tools.verification.check_state_attestation` (AC-6)."""

from __future__ import annotations

from pathlib import Path

from tools.verification import check_state_attestation as check

SEED_STATE = "---\nlast_generated_at: never (seed)\n---\n# State\n"
REAL_STATE = "---\nlast_generated_at: 2026-06-04T12:00:00+00:00\n---\n# State\nendpoints: 1\n"

CHECKED_BODY = "## DoD\n- [x] `docs/generated/STATE.md` se actualizó automáticamente vía hook\n"
UNCHECKED_BODY = "## DoD\n- [ ] `docs/generated/STATE.md` se actualizó automáticamente vía hook\n"


# AC-6: a ticked "STATE.md" box over a still-seed STATE.md is a violation.
def test_checked_box_over_seed_is_violation() -> None:
    violations = check.find_attestation_violations(CHECKED_BODY, SEED_STATE)
    assert violations
    assert any("seed marker" in v for v in violations)


# AC-6: a ticked box over a genuinely regenerated STATE.md is allowed.
def test_checked_box_over_real_state_is_ok() -> None:
    assert check.find_attestation_violations(CHECKED_BODY, REAL_STATE) == []


# AC-6: an unchecked box asserts nothing, so never a violation.
def test_unchecked_box_is_never_a_violation() -> None:
    assert check.find_attestation_violations(UNCHECKED_BODY, SEED_STATE) == []


# AC-6: a ticked box over a no-op (content identical to previous) is rejected.
def test_checked_box_over_noop_is_violation() -> None:
    violations = check.find_attestation_violations(
        CHECKED_BODY, REAL_STATE, previous_state_md=REAL_STATE
    )
    assert any("no-op" in v for v in violations)


# AC-6: detection is robust to checkbox styling and only fires on STATE.md.
def test_box_detection() -> None:
    assert check.box_is_checked("- [x] regenerate STATE.md") is True
    assert check.box_is_checked("* [X] STATE.MD regenerated") is True
    assert check.box_is_checked("- [x] some unrelated box") is False
    assert check.box_is_checked("- [ ] STATE.md") is False


# AC-6: the CLI exits non-zero on a false attestation and zero otherwise.
def test_cli_exit_codes(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    state = tmp_path / "STATE.md"
    body.write_text(CHECKED_BODY, encoding="utf-8")

    state.write_text(SEED_STATE, encoding="utf-8")
    assert check.main(["--pr-body", str(body), "--state", str(state)]) == 1

    state.write_text(REAL_STATE, encoding="utf-8")
    assert check.main(["--pr-body", str(body), "--state", str(state)]) == 0

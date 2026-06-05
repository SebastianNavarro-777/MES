"""Regression test that the Stop hook regenerates the snapshots (AC-5)."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STOP_HOOK = _REPO_ROOT / ".claude" / "hooks" / "stop.sh"


def test_stop_hook_runs_both_generators() -> None:
    # AC-5: the Stop hook invokes both generators, so closing a session that
    # touched the tree regenerates STATE.md and module-map.md with no manual
    # action — making the DoD "STATE.md regenerated via hook" box mechanically
    # true.
    text = _STOP_HOOK.read_text(encoding="utf-8")
    assert "tools.verification.update_state" in text
    assert "tools.verification.dump_module_map" in text


def test_stop_hook_uses_run_step_for_generators() -> None:
    # AC-5: the generators are wired through the existing run_step pattern so
    # they respect the hook's exit-code contract (0 green / 2 feedback).
    text = _STOP_HOOK.read_text(encoding="utf-8")
    assert 'run_step "regenerate STATE.md"' in text
    assert 'run_step "regenerate module-map"' in text

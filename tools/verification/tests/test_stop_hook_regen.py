"""Static contract tests for the Stop hook's regeneration steps (AC-5).

We assert on the committed ``.claude/hooks/stop.sh`` text rather than executing
it (running the full pipeline belongs to the hook itself). The behaviour of the
generators it invokes is covered by ``test_update_state`` / ``test_dump_module_map``.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STOP_HOOK = REPO_ROOT / ".claude" / "hooks" / "stop.sh"


def _hook_text() -> str:
    return STOP_HOOK.read_text(encoding="utf-8")


# AC-5: the Stop hook runs both generators as pipeline steps.
def test_stop_hook_invokes_both_generators() -> None:
    text = _hook_text()
    assert "tools.verification.update_state" in text
    assert "tools.verification.dump_module_map" in text


# AC-5: regeneration happens after the verification steps (it should reflect the
# post-fix tree) and is wired through the existing run_step harness.
def test_generators_run_after_pytest_via_run_step() -> None:
    text = _hook_text()
    pytest_idx = text.index('run_step "pytest"')
    state_idx = text.index("tools.verification.update_state")
    map_idx = text.index("tools.verification.dump_module_map")
    assert pytest_idx < state_idx < map_idx
    assert 'run_step "regenerate STATE.md"' in text
    assert 'run_step "regenerate module-map"' in text


# AC-7: the STATE.md regeneration is given a short Linear timeout so a network
# outage cannot hang or fail the hook.
def test_state_generator_has_short_linear_timeout() -> None:
    assert "--linear-timeout" in _hook_text()

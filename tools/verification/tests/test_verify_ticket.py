"""Contract tests for ``tools/verification/verify_ticket.sh``.

The script wraps the local verification pipeline (ruff, mypy, the architecture
linter, pytest) that CLAUDE.md tells every agent to run before proposing a
ticket as done. We don't run the real tools here — that would re-run the whole
suite recursively. Instead we inject a fake Python interpreter via the script's
``PY`` override hook and assert the script's *contract*: it requires a
ticket-id, runs the four steps in the documented order, surfaces a non-zero
exit when any step fails, and stays green when they all pass.

This mirrors ``test_deploy_staging.py`` (fake-binary injection + static/contract
assertions, skipped when bash is unavailable).
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY_SCRIPT = REPO_ROOT / "tools" / "verification" / "verify_ticket.sh"

BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required to run verify_ticket.sh")

# A fake `python` that logs every invocation's args to $FAKE_LOG and exits 1
# whenever the args contain the token in $FAKE_FAIL_ON (so a test can make a
# single step "fail"); otherwise exits 0.
_FAKE_PY = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_LOG"
if [ -n "${FAKE_FAIL_ON:-}" ]; then
  for arg in "$@"; do
    case "$arg" in
      *"$FAKE_FAIL_ON"*) exit 1 ;;
    esac
  done
fi
exit 0
"""


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run(
    tmp_path: Path, *args: str, fail_on: str | None = None
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run verify_ticket.sh with a fake interpreter; return (result, py_calls)."""
    fake_py = tmp_path / "fake_python"
    _write_exec(fake_py, _FAKE_PY)
    log = tmp_path / "py_calls.log"

    env = {
        "PATH": "/usr/bin:/bin",
        "PY": str(fake_py),
        "REPO_ROOT": str(REPO_ROOT),
        "FAKE_LOG": str(log),
    }
    if fail_on is not None:
        env["FAKE_FAIL_ON"] = fail_on

    assert BASH is not None  # guarded by pytestmark
    result = subprocess.run(
        [BASH, str(VERIFY_SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=60,
        check=False,
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, calls


def test_missing_ticket_id_exits_with_usage(tmp_path: Path) -> None:
    # A bad invocation fails loudly (exit 2) rather than running a useless pass.
    result, _ = _run(tmp_path)
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_all_steps_green_exits_zero_in_order(tmp_path: Path) -> None:
    # Happy path: every step passes -> exit 0, and the four steps run in the
    # documented order (ruff -> mypy -> architecture linter -> pytest).
    result, calls = _run(tmp_path, "NSG-123")
    assert result.returncode == 0, result.stderr
    assert "all checks green" in result.stderr

    joined = "\n".join(calls)
    for token in ("ruff", "mypy", "architecture.py", "pytest"):
        assert token in joined, f"step {token!r} was never invoked: {calls!r}"

    def first_index(token: str) -> int:
        return next(i for i, c in enumerate(calls) if token in c)

    assert (
        first_index("ruff")
        < first_index("mypy")
        < first_index("architecture.py")
        < first_index("pytest")
    ), f"steps ran out of order: {calls!r}"


@pytest.mark.parametrize("failing_step", ["ruff", "mypy", "architecture.py", "pytest"])
def test_any_failing_step_exits_nonzero(tmp_path: Path, failing_step: str) -> None:
    # If any single step fails, the script must exit non-zero and name it —
    # an agent must never get a green verdict over a red check.
    result, _ = _run(tmp_path, "NSG-123", fail_on=failing_step)
    assert result.returncode == 1
    assert "FAILED" in result.stderr
    assert "all checks green" not in result.stderr


def test_ticket_id_is_echoed_for_traceability(tmp_path: Path) -> None:
    # The ticket id appears in the output so the run is attributable.
    result, _ = _run(tmp_path, "NSG-999")
    assert result.returncode == 0, result.stderr
    assert "NSG-999" in result.stderr

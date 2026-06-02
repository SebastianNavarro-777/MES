"""Tests that the local verification pipeline gates on the frontend.

AC-7 (NSG-19): the frontend type-check (strict) + TypeScript lint must be
integrated into the ticket verification pipeline, so verification fails on any
type or lint error under ``frontend/``.
"""

from __future__ import annotations

from pathlib import Path

_VERIFICATION_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (_VERIFICATION_DIR / relative).read_text(encoding="utf-8")


# AC-7: a dedicated frontend verifier exists and runs both strict type-check and lint.
def test_verify_frontend_script_exists() -> None:
    assert (_VERIFICATION_DIR / "verify_frontend.sh").is_file()


# AC-7: the frontend verifier runs the strict type-check and the lint step.
def test_verify_frontend_runs_typecheck_and_lint() -> None:
    script = _read("verify_frontend.sh")
    assert "run typecheck" in script
    assert "run lint" in script


# AC-7: the ticket-level pipeline wires the frontend gate in when a frontend exists.
def test_verify_ticket_invokes_frontend_gate() -> None:
    script = _read("verify_ticket.sh")
    assert "verify_frontend.sh" in script
    assert "frontend/package.json" in script


# AC-7: the frontend package exposes the typecheck + lint scripts the gate calls.
def test_frontend_package_exposes_quality_scripts() -> None:
    import json

    package_json = json.loads(
        (_REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"),
    )
    scripts = package_json["scripts"]
    assert "typecheck" in scripts
    assert "lint" in scripts
    assert "--noEmit" in scripts["typecheck"]

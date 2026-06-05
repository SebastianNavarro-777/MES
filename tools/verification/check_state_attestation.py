"""Regression guard against false "STATE.md regenerated" attestations (AC-6).

The Definition of Done has a box: *"docs/generated/STATE.md se actualizó
automáticamente vía hook"*. Before NSG-50 that box was being ticked on PRs even
though STATE.md was physically still the seed — a false attestation. This check
fails when a PR/ticket body ticks that box while STATE.md still carries the seed
marker (``last_generated_at: never (seed)``) or while the content is provably a
no-op (identical to its previous version).

It is intentionally narrow and text-based so it can run in CI against a PR body
without any Linear/GitHub dependency.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from tools.verification.update_state import SEED_MARKER

__all__ = ["box_is_checked", "find_attestation_violations", "main"]

# A checked markdown checkbox ("- [x] ...") whose text mentions STATE.md.
_CHECKED_BOX_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(?P<text>.+)$")
_STATE_MENTION_RE = re.compile(r"state\.md", re.IGNORECASE)


def box_is_checked(pr_body: str) -> bool:
    """True if the body ticks a checkbox that references ``STATE.md``."""
    for line in pr_body.splitlines():
        match = _CHECKED_BOX_RE.match(line)
        if match and _STATE_MENTION_RE.search(match.group("text")):
            return True
    return False


def find_attestation_violations(
    pr_body: str,
    state_md: str,
    *,
    previous_state_md: str | None = None,
) -> list[str]:
    """Return human-readable violations; empty list means the attestation holds.

    * If the STATE.md box is not checked, nothing is asserted (empty list).
    * If checked while STATE.md still contains the seed marker → violation.
    * If checked while ``previous_state_md`` is byte-identical (a no-op) →
      violation. Pass ``None`` to skip the no-op comparison.
    """
    if not box_is_checked(pr_body):
        return []

    violations: list[str] = []
    if SEED_MARKER in state_md:
        violations.append(
            "PR/ticket ticks the 'STATE.md regenerated' box, but STATE.md still "
            f"contains the seed marker '{SEED_MARKER}'. Run "
            "tools/verification/update_state.py and commit the result."
        )
    if previous_state_md is not None and previous_state_md == state_md:
        violations.append(
            "PR/ticket ticks the 'STATE.md regenerated' box, but STATE.md is "
            "byte-identical to its previous version (a no-op). The box may not "
            "be ticked for a no-op."
        )
    return violations


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_show(repo_root: Path, revision: str, rel_path: str, git_bin: str) -> str | None:
    try:
        result = subprocess.run(
            [git_bin, "show", f"{revision}:{rel_path}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_state_attestation",
        description=(
            "Fail when a PR/ticket body ticks the 'STATE.md regenerated' box "
            "while STATE.md is still the seed or is an unchanged no-op (AC-6)."
        ),
    )
    parser.add_argument("--pr-body", type=Path, required=True, help="File with the PR/ticket body.")
    parser.add_argument(
        "--state",
        type=Path,
        default=Path("docs/generated/STATE.md"),
        help="Path to STATE.md (default: docs/generated/STATE.md).",
    )
    parser.add_argument(
        "--compare-rev",
        default=None,
        help="Git revision to compare STATE.md against for no-op detection (e.g. 'origin/main').",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    args = parser.parse_args(argv)

    pr_body = _read(args.pr_body)
    state_md = _read(args.state)

    previous: str | None = None
    if args.compare_rev is not None:
        rel = args.state.resolve().relative_to(args.root.resolve()).as_posix()
        previous = _git_show(args.root.resolve(), args.compare_rev, rel, "git")

    violations = find_attestation_violations(pr_body, state_md, previous_state_md=previous)
    if violations:
        for violation in violations:
            print(f"[check_state_attestation] {violation}")
        return 1
    print("[check_state_attestation] OK: no false STATE.md attestation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Regression guard against *false* STATE.md attestations (NSG-50 AC-6).

The Definition of Done has a checkbox:

    - [ ] docs/generated/STATE.md se actualizó automáticamente vía hook ...

Before NSG-50 the regeneration step did not exist, yet Workers ticked that box
on PRs #4/#13/#17 — a green box over an action that could not physically happen.
This check makes that impossible to repeat: if a PR/ticket body ticks the box
while ``STATE.md`` is still the seed placeholder (or, given a baseline, was not
actually changed), the check fails.

Used by the Reviewer agent / CI, not by the Stop hook.

Run::

    python -m tools.verification.check_state_freshness --body-file PR_BODY.md
    gh pr view N --json body -q .body | python -m tools.verification.check_state_freshness
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from tools.verification.doc_render import strip_timestamp_line

__all__ = [
    "SEED_MARKERS",
    "attestation_checked",
    "find_problems",
    "main",
    "state_is_seed",
]

# Substrings that prove STATE.md is still the un-regenerated seed.
SEED_MARKERS = ("never (seed)", "Seed placeholder")

# A ticked checkbox line that refers to STATE.md being (re)generated. Matches
# both the Spanish DoD wording ("se actualizó") and an English "regenerated".
_ATTESTATION_RE = re.compile(
    r"^\s*[-*]\s*\[[xX]\].*STATE\.md.*"
    r"(regenerat|se actualiz|actualiz[oó]|auto[- ]?generat)",
    re.IGNORECASE,
)


def attestation_checked(body: str) -> bool:
    """Whether ``body`` ticks the "STATE.md was regenerated" DoD checkbox."""
    return any(_ATTESTATION_RE.search(line) for line in body.splitlines())


def state_is_seed(state_text: str) -> bool:
    """Whether ``state_text`` is still the un-regenerated seed placeholder."""
    return any(marker in state_text for marker in SEED_MARKERS)


def find_problems(
    *,
    body: str,
    state_text: str,
    baseline_text: str | None = None,
) -> list[str]:
    """Return human-readable problems; empty list means the attestation is honest.

    A problem is raised when the box is ticked **and** either:
      * STATE.md is still the seed placeholder, or
      * a ``baseline_text`` is supplied and STATE.md is byte-identical to it
        once the volatile timestamp line is ignored (i.e. a no-op rewrite).
    """
    if not attestation_checked(body):
        return []
    problems: list[str] = []
    if state_is_seed(state_text):
        problems.append(
            "PR/ticket ticks the 'STATE.md regenerated' box, but STATE.md still "
            "contains the seed placeholder (never regenerated). No green box "
            "over a no-op (AC-6)."
        )
    if baseline_text is not None and strip_timestamp_line(state_text) == (
        strip_timestamp_line(baseline_text)
    ):
        problems.append(
            "PR/ticket ticks the 'STATE.md regenerated' box, but STATE.md is "
            "unchanged versus the baseline (only the timestamp differs). No "
            "green box over a no-op (AC-6)."
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-state-freshness",
        description=(
            "Fail when a PR/ticket body attests STATE.md was regenerated while "
            "STATE.md is still the seed placeholder (or unchanged). AC-6."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (default: inferred from this file's location).",
    )
    parser.add_argument(
        "--body-file",
        type=Path,
        help="File with the PR/ticket body. Defaults to reading stdin.",
    )
    parser.add_argument(
        "--state",
        type=Path,
        help="Path to STATE.md (default: <root>/docs/generated/STATE.md).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Optional baseline STATE.md to detect no-op rewrites.",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    body = (
        args.body_file.read_text(encoding="utf-8")
        if args.body_file is not None
        else sys.stdin.read()
    )
    state_path: Path = args.state or (root / "docs" / "generated" / "STATE.md")
    try:
        state_text = state_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[check_state_freshness] cannot read {state_path}: {exc}", file=sys.stderr)
        return 1
    baseline_text = (
        args.baseline.read_text(encoding="utf-8") if args.baseline is not None else None
    )

    problems = find_problems(
        body=body, state_text=state_text, baseline_text=baseline_text
    )
    if problems:
        for problem in problems:
            print(f"[check_state_freshness] {problem}", file=sys.stderr)
        return 1
    print("[check_state_freshness] STATE.md attestation is honest.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

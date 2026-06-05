"""Regenerate ``docs/generated/STATE.md`` from the live working tree.

``STATE.md`` is every agent's "what exists today" reference (``AGENTS.md`` step
4). Before this generator existed it was a frozen seed (``last_generated_at:
never (seed)``) and the Definition-of-Done box claiming it was auto-regenerated
was a false attestation. This script makes that box mechanically true: the Stop
hook (``.claude/hooks/stop.sh``) runs it on every session close.

Design points (see NSG-50):

* **Deterministic except for the timestamp.** The substantive body is a pure
  function of the tree; only ``last_generated_at`` / ``last_updated`` vary. To
  avoid timestamp churn on every commit, the file is rewritten *only* when the
  substantive body changes (:func:`write_state` compares with the volatile
  lines stripped).
* **GP-003.** The generation timestamp is timezone-aware UTC.
* **Graceful degradation (AC-7).** The "Open Questions" section is pulled from
  Linear; if Linear is unreachable or no ``LINEAR_API_KEY`` is set, the section
  is marked unavailable and the generator still exits 0 — the Stop hook never
  fails because of a network outage.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from tools.verification import repo_stats
from tools.verification.repo_stats import RepoStats

__all__ = [
    "SEED_MARKER",
    "fetch_open_questions",
    "main",
    "render_state",
    "strip_volatile",
    "write_state",
]

SEED_MARKER = "last_generated_at: never (seed)"
_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
_LINEAR_QUESTION_LABEL = "needs-human-decision"
_DONE_STATE_TYPES: frozenset[str] = frozenset({"completed", "canceled"})

_OPEN_QUESTIONS_QUERY = """
query OpenQuestions($label: String!) {
  issues(filter: { labels: { name: { eq: $label } } }, first: 50) {
    nodes { identifier title state { type } }
  }
}
"""


# ---------------------------------------------------------------------------
# Linear (best-effort, never raises)
# ---------------------------------------------------------------------------


def _parse_questions(payload: object) -> list[str]:
    """Narrow the GraphQL response to ``["NSG-1 — title", ...]`` (strict-typed)."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    issues = data.get("issues")
    if not isinstance(issues, dict):
        return []
    nodes = issues.get("nodes")
    if not isinstance(nodes, list):
        return []

    questions: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        state = node.get("state")
        state_type = state.get("type") if isinstance(state, dict) else None
        if isinstance(state_type, str) and state_type in _DONE_STATE_TYPES:
            continue
        identifier = node.get("identifier")
        title = node.get("title")
        if isinstance(identifier, str) and isinstance(title, str):
            questions.append(f"{identifier} — {title}")
    return sorted(questions)


def fetch_open_questions(
    *,
    token: str | None,
    timeout: float = 5.0,
    endpoint: str = _LINEAR_ENDPOINT,
) -> list[str] | None:
    """Return open ``needs-human-decision`` issues from Linear, or ``None``.

    ``None`` means "Linear was unavailable" (no token, network failure, bad
    response). The caller renders an explicit "unavailable" note and does NOT
    treat this as an error — satisfying AC-7.
    """
    if not token:
        return None
    body = json.dumps(
        {"query": _OPEN_QUESTIONS_QUERY, "variables": {"label": _LINEAR_QUESTION_LABEL}}
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Authorization": token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        payload: object = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return _parse_questions(payload)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_counts(stats: RepoStats) -> list[str]:
    coverage = "n/a"
    rows = [
        ("Bounded contexts scaffolded", stats.bounded_contexts_scaffolded),
        ("Bounded contexts with code", stats.bounded_contexts_with_code),
        ("Domain entities", stats.domain_entities),
        ("API endpoints", stats.api_endpoints),
        ("Domain events defined", stats.domain_events),
        ("Test functions", stats.test_functions),
    ]
    lines = ["## Counts", "", "| Item | Count |", "|---|---|"]
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    lines.append(f"| Coverage | {coverage} |")
    lines.extend(
        [
            "",
            "> Counts reflect the live working tree. `Domain entities`, "
            "`Domain events defined` and `Bounded contexts with code` are 0 "
            "because the merged work so far is the deployable skeleton "
            "(config + `/healthz` + the React bundle); the `apps/*` contexts "
            "are scaffolded but carry no domain code yet. `Coverage` is `n/a`: "
            "computing it means running the full suite under coverage, which is "
            "too slow for a per-session Stop hook — read it from CI "
            "(`coverage report`) instead.",
        ]
    )
    return lines


def _render_prs(stats: RepoStats) -> list[str]:
    lines = ["## Recently merged PRs", ""]
    if not stats.merged_prs:
        lines.append("_(none yet)_")
        return lines
    for pr in stats.merged_prs:
        ticket = f" ({pr.ticket})" if pr.ticket else ""
        lines.append(f"- #{pr.number}{ticket} {pr.date} — {pr.subject}")
    return lines


def _render_open_questions(open_questions: list[str] | None) -> list[str]:
    lines = ["## Open Questions", ""]
    if open_questions is None:
        lines.append(
            "> _Linear was unavailable when this snapshot was generated "
            "(no `LINEAR_API_KEY`, or the API was unreachable). Section skipped; "
            "the Stop hook does not fail for this — see AC-7._"
        )
        return lines
    if not open_questions:
        lines.append("_(none open)_")
        return lines
    lines.extend(f"- {question}" for question in open_questions)
    return lines


def _render_exec_plans(stats: RepoStats) -> list[str]:
    lines = ["## Active exec-plans", ""]
    if not stats.active_exec_plans:
        lines.append("_(none active)_")
        return lines
    lines.extend(f"- `docs/exec-plans/active/{name}`" for name in stats.active_exec_plans)
    return lines


def render_state(
    stats: RepoStats,
    *,
    generated_at: datetime,
    open_questions: list[str] | None,
) -> str:
    """Render the full ``STATE.md`` text. ``generated_at`` must be tz-aware UTC."""
    if generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware UTC (GP-003)")
    generated_at = generated_at.astimezone(UTC)

    lines = [
        "---",
        "generated_by: tools/verification/update_state.py",
        f"last_generated_at: {generated_at.isoformat()}",
        f"last_updated: {generated_at.date().isoformat()}",
        "---",
        "",
        "# State snapshot — auto-generated",
        "",
        "> Regenerated by `tools/verification/update_state.py` on every `Stop` "
        "hook (`.claude/hooks/stop.sh`). Do not edit by hand — changes are "
        "overwritten.",
        "",
        *_render_counts(stats),
        "",
        *_render_prs(stats),
        "",
        *_render_open_questions(open_questions),
        "",
        *_render_exec_plans(stats),
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Idempotent write
# ---------------------------------------------------------------------------


def strip_volatile(text: str) -> str:
    """Drop volatile front-matter lines so substantive diffs can be compared."""
    kept = [
        line
        for line in text.splitlines()
        if not line.startswith(("last_generated_at:", "last_updated:"))
    ]
    return "\n".join(kept)


def write_state(
    path: Path,
    *,
    stats: RepoStats,
    generated_at: datetime,
    open_questions: list[str] | None,
) -> bool:
    """Write ``STATE.md`` only when the substantive body changed.

    Returns ``True`` if the file was (re)written, ``False`` if it was left
    untouched because nothing but the timestamp would have changed. This keeps
    the Stop hook from churning the file on every session.
    """
    new_text = render_state(stats, generated_at=generated_at, open_questions=open_questions)
    if path.exists():
        old_text = path.read_text(encoding="utf-8")
        if strip_volatile(old_text) == strip_volatile(new_text):
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8", newline="\n")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="update_state",
        description="Regenerate docs/generated/STATE.md from the working tree.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root.")
    parser.add_argument(
        "--no-linear",
        action="store_true",
        help="Skip the Linear query for Open Questions (offline / CI).",
    )
    parser.add_argument(
        "--linear-timeout",
        type=float,
        default=5.0,
        help="Seconds to wait for Linear before giving up (default: 5).",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.root.resolve()
    stats = repo_stats.gather(repo_root)

    if args.no_linear:
        open_questions: list[str] | None = None
    else:
        open_questions = fetch_open_questions(
            token=os.environ.get("LINEAR_API_KEY"),
            timeout=args.linear_timeout,
        )

    target = repo_root / "docs" / "generated" / "STATE.md"
    changed = write_state(
        target,
        stats=stats,
        generated_at=datetime.now(UTC),
        open_questions=open_questions,
    )
    status = "rewritten" if changed else "unchanged (no substantive diff)"
    print(f"[update_state] {target} {status}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

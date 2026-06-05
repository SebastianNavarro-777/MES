"""Shared rendering helpers for the auto-generated docs in ``docs/generated/``.

Both ``update_state.py`` and ``dump_module_map.py`` write a Markdown file with
a YAML front matter that carries a volatile ``last_generated_at`` timestamp.

The Stop hook runs the generators on *every* session close, so a naive
"always rewrite" strategy would churn the timestamp on every commit even when
nothing substantive changed. To keep diffs honest, :func:`write_doc_if_changed`
compares the *substantive* content (everything except the timestamp line) and
only rewrites — bumping the timestamp — when that substantive content actually
changed. Two runs over an unchanged tree therefore produce **zero** diff.

These helpers contain no I/O beyond the single file write in
:func:`write_doc_if_changed`, so the pure pieces are trivially testable.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "TIMESTAMP_KEY",
    "frontmatter_block",
    "strip_timestamp_line",
    "utc_timestamp",
    "write_doc_if_changed",
]

TIMESTAMP_KEY = "last_generated_at"


def utc_timestamp(now: datetime | None = None) -> str:
    """A timezone-aware UTC timestamp string (GP-003).

    ``now`` is injectable so tests stay deterministic. When omitted the
    current UTC time is used. The value is always rendered with a trailing
    ``Z`` to make the UTC offset unambiguous.
    """
    moment = now if now is not None else datetime.now(UTC)
    if moment.tzinfo is None:
        raise ValueError("refusing to render a naive datetime (GP-003)")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def frontmatter_block(*, generated_by: str, timestamp: str, last_updated: str) -> str:
    """Render the YAML front matter common to every generated doc."""
    return (
        "---\n"
        f"generated_by: {generated_by}\n"
        f"{TIMESTAMP_KEY}: {timestamp}\n"
        f"last_updated: {last_updated}\n"
        "---\n"
    )


def strip_timestamp_line(text: str) -> str:
    """Return ``text`` with the ``last_generated_at:`` line removed.

    Used to compare two renderings while ignoring the only volatile field.
    """
    kept = [
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(f"{TIMESTAMP_KEY}:")
    ]
    return "\n".join(kept)


def write_doc_if_changed(
    path: Path,
    render: Callable[[str], str],
    *,
    timestamp: str,
) -> bool:
    """Write the rendered document only if its substantive content changed.

    ``render`` takes the timestamp string and returns the complete document.
    The timestamp is compared out, so an unchanged tree never rewrites the
    file (and never bumps the timestamp). Returns ``True`` when the file was
    written, ``False`` when it was left untouched.
    """
    new_text = render(timestamp)
    if path.exists():
        old_text = path.read_text(encoding="utf-8")
        if strip_timestamp_line(old_text) == strip_timestamp_line(new_text):
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return True

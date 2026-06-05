"""Tests for ``tools.verification.doc_render``."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.verification.doc_render import (
    frontmatter_block,
    strip_timestamp_line,
    utc_timestamp,
    write_doc_if_changed,
)


def test_utc_timestamp_is_timezone_aware_utc() -> None:
    # GP-003: the generated timestamp is timezone-aware UTC, rendered with `Z`.
    aware = datetime(2026, 6, 4, 12, 30, 15, tzinfo=UTC)
    assert utc_timestamp(aware) == "2026-06-04T12:30:15Z"


def test_utc_timestamp_converts_other_offsets_to_utc() -> None:
    # A -06:00 wall-clock time renders as the equivalent UTC instant.
    cst = datetime(2026, 6, 4, 6, 30, 15, tzinfo=timezone(timedelta(hours=-6)))
    assert utc_timestamp(cst) == "2026-06-04T12:30:15Z"


def test_utc_timestamp_rejects_naive_datetime() -> None:
    # GP-003: naive datetimes are refused at the boundary.
    with pytest.raises(ValueError, match="naive"):
        utc_timestamp(datetime(2026, 6, 4, 12, 0, 0))


def test_strip_timestamp_line_removes_only_that_field() -> None:
    text = "---\ngenerated_by: x\nlast_generated_at: 2026-06-04T00:00:00Z\n---\nbody\n"
    stripped = strip_timestamp_line(text)
    assert "last_generated_at" not in stripped
    assert "generated_by: x" in stripped
    assert "body" in stripped


def _render(body: str) -> Callable[[str], str]:
    def render(timestamp: str) -> str:
        return frontmatter_block(
            generated_by="g", timestamp=timestamp, last_updated="2026-06-04"
        ) + f"\n{body}\n"

    return render


def test_write_doc_creates_file_when_absent(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    assert write_doc_if_changed(target, _render("alpha"), timestamp="T1") is True
    assert "alpha" in target.read_text(encoding="utf-8")
    assert "T1" in target.read_text(encoding="utf-8")


def test_write_doc_is_idempotent_across_timestamps(tmp_path: Path) -> None:
    # Determinism: an unchanged body must NOT rewrite (and must NOT bump the
    # timestamp), so the Stop hook does not churn the file every session.
    target = tmp_path / "out.md"
    write_doc_if_changed(target, _render("alpha"), timestamp="T1")
    changed = write_doc_if_changed(target, _render("alpha"), timestamp="T2")
    assert changed is False
    assert "T1" in target.read_text(encoding="utf-8")
    assert "T2" not in target.read_text(encoding="utf-8")


def test_write_doc_rewrites_when_body_changes(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    write_doc_if_changed(target, _render("alpha"), timestamp="T1")
    changed = write_doc_if_changed(target, _render("beta"), timestamp="T2")
    assert changed is True
    body = target.read_text(encoding="utf-8")
    assert "beta" in body
    assert "T2" in body

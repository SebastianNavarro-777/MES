"""Tests for :mod:`tools.verification.dump_module_map`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.verification import dump_module_map
from tools.verification.repo_stats import ContextStats

FIXED_NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)

SEED_MAP = """---
generated_by: tools/verification/dump_module_map.py
last_generated_at: never (seed)
last_updated: 2026-05-04
---

# Module map — auto-generated

| Context | Layers present (D/A/I/X) | LoC | Public symbols |
|---|---|---|---|

_(no modules yet)_
"""


def _contexts() -> list[ContextStats]:
    return [
        ContextStats(name="orders", layers_present=("D", "A", "X"), loc=120, public_symbols=7),
        ContextStats(name="quality", layers_present=(), loc=0, public_symbols=0),
    ]


# AC-4: one row per bounded context, layers ordered D/A/I/X, empty layers as "—".
def test_render_one_row_per_context() -> None:
    text = dump_module_map.render_module_map(_contexts(), generated_at=FIXED_NOW)
    assert "| orders | D/A/X | 120 | 7 |" in text
    assert "| quality | — | 0 | 0 |" in text
    assert "_(no modules yet)_" not in text


# AC-4 / GP-003: the generation timestamp must be timezone-aware UTC.
def test_render_rejects_naive_datetime() -> None:
    naive = datetime(2026, 6, 4, 12, 0)  # tz-naive on purpose
    with pytest.raises(ValueError, match="timezone-aware"):
        dump_module_map.render_module_map(_contexts(), generated_at=naive)


# AC-4: writing over the seed replaces the "(no modules yet)" placeholder.
def test_write_replaces_seed_placeholder(tmp_path: Path) -> None:
    target = tmp_path / "module-map.md"
    target.write_text(SEED_MAP, encoding="utf-8", newline="\n")
    assert dump_module_map.write_module_map(target, contexts=_contexts(), generated_at=FIXED_NOW)
    assert "_(no modules yet)_" not in target.read_text(encoding="utf-8")


# AC-5 / idempotency: a later run with unchanged content does not rewrite.
def test_write_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "module-map.md"
    later = datetime(2026, 6, 4, 18, 0, tzinfo=UTC)
    assert dump_module_map.write_module_map(target, contexts=_contexts(), generated_at=FIXED_NOW)
    before = target.read_text(encoding="utf-8")
    assert not dump_module_map.write_module_map(target, contexts=_contexts(), generated_at=later)
    assert target.read_text(encoding="utf-8") == before


# AC-5: invocable exactly as the Stop hook calls it; exits 0.
def test_cli_runs(tmp_path: Path) -> None:
    (tmp_path / "apps" / "orders").mkdir(parents=True)
    (tmp_path / "apps" / "orders" / ".gitkeep").write_text("", encoding="utf-8")
    rc = dump_module_map.main(["--root", str(tmp_path)])
    assert rc == 0
    written = (tmp_path / "docs" / "generated" / "module-map.md").read_text(encoding="utf-8")
    assert "| orders |" in written

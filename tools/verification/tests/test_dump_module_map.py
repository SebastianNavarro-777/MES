"""Tests for ``tools.verification.dump_module_map``."""

from __future__ import annotations

from pathlib import Path

from tools.verification.dump_module_map import main, render_module_map
from tools.verification.repo_scan import ModuleRow

_TS = "2026-06-04T12:00:00Z"


def test_render_empty_replaces_placeholder() -> None:
    # AC-4: when no context is implemented the seed "(no modules yet)" is gone,
    # replaced by an honest computed note.
    out = render_module_map(rows=[], timestamp=_TS)
    assert "(no modules yet)" not in out
    assert "scaffold-only" in out
    assert f"last_generated_at: {_TS}" in out


def test_render_one_row_per_context() -> None:
    # AC-4: one row per implemented context with layer presence + counts.
    rows = [
        ModuleRow(
            context="orders",
            has_domain=True,
            has_application=True,
            has_infrastructure=False,
            has_interface=True,
            loc=120,
            public_symbols=7,
        )
    ]
    out = render_module_map(rows=rows, timestamp=_TS)
    assert "| orders | D A - X | 120 | 7 |" in out
    assert "(no modules yet)" not in out


def test_main_writes_module_map(tmp_path: Path) -> None:
    # AC-4: end-to-end generation over a synthetic implemented context.
    (tmp_path / "docs" / "generated").mkdir(parents=True)
    orders = tmp_path / "apps" / "orders" / "domain"
    orders.mkdir(parents=True)
    (orders / "order.py").write_text("class Order:\n    pass\n", encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 0
    out = (tmp_path / "docs" / "generated" / "module-map.md").read_text(encoding="utf-8")
    assert "| orders |" in out
    assert "(no modules yet)" not in out

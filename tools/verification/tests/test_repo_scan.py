"""Tests for ``tools.verification.repo_scan`` against synthetic repos."""

from __future__ import annotations

from pathlib import Path

from tools.verification.repo_scan import (
    ModuleRow,
    count_url_patterns,
    gather_module_rows,
    gather_stats,
)


def _write(repo: Path, rel: str, source: str) -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source, encoding="utf-8")
    return p


def _scaffold_empty_contexts(repo: Path, names: list[str]) -> None:
    for name in names:
        _write(repo, f"apps/{name}/.gitkeep", "")


def test_stats_count_scaffolded_vs_implemented_contexts(tmp_path: Path) -> None:
    # AC-2: counts are coherent with the tree — scaffold-only contexts are
    # counted as scaffolded but NOT implemented.
    _scaffold_empty_contexts(tmp_path, ["downtime", "oee", "quality"])
    _write(
        tmp_path,
        "apps/orders/domain/manufacturing_order.py",
        "class ManufacturingOrder:\n    pass\n",
    )
    stats = gather_stats(tmp_path)
    assert stats.bounded_contexts_scaffolded == 4  # 3 empty + orders
    assert stats.bounded_contexts_implemented == 1  # only orders has .py


def test_stats_count_domain_entities_events_and_endpoints(tmp_path: Path) -> None:
    # AC-2: entities, domain events and API endpoints are counted separately.
    _write(
        tmp_path,
        "apps/orders/domain/manufacturing_order.py",
        "class ManufacturingOrder:\n    pass\n\nclass OrderLine:\n    pass\n",
    )
    _write(
        tmp_path,
        "apps/orders/domain/events.py",
        "class OrderReleased:\n    pass\n",
    )
    _write(
        tmp_path,
        "apps/orders/domain/exceptions.py",
        "class OrdersDomainError(Exception):\n    pass\n",
    )
    _write(
        tmp_path,
        "apps/orders/urls.py",
        "from django.urls import path\n"
        "urlpatterns = [path('a', 1), path('b', 2)]\n",
    )
    stats = gather_stats(tmp_path)
    assert stats.domain_entities == 2  # entities only, not events/exceptions
    assert stats.domain_events == 1
    assert stats.api_endpoints == 2


def test_stats_count_test_functions(tmp_path: Path) -> None:
    # AC-2: test functions are a cheap, non-zero count drawn from the tree.
    _write(
        tmp_path,
        "tools/foo/tests/test_foo.py",
        "def test_a():\n    pass\n\ndef test_b():\n    pass\n\ndef helper():\n    pass\n",
    )
    stats = gather_stats(tmp_path)
    assert stats.test_functions == 2


def test_url_patterns_counts_path_and_re_path(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        "apps/orders/urls.py",
        "from django.urls import path, re_path\n"
        "urlpatterns = [path('a', 1), re_path(r'^b$', 2)]\n",
    )
    assert count_url_patterns(p) == 2


def test_gather_module_rows_only_for_implemented_contexts(tmp_path: Path) -> None:
    # AC-4: one row per implemented context, with layer presence and counts.
    _scaffold_empty_contexts(tmp_path, ["empty_ctx"])
    _write(
        tmp_path,
        "apps/orders/domain/manufacturing_order.py",
        "class ManufacturingOrder:\n    pass\n\ndef build_order():\n    return None\n",
    )
    _write(
        tmp_path,
        "apps/orders/interface/views.py",
        "class OrderView:\n    pass\n",
    )
    rows = gather_module_rows(tmp_path)
    assert [r.context for r in rows] == ["orders"]  # empty_ctx excluded
    row = rows[0]
    assert row.has_domain is True
    assert row.has_interface is True
    assert row.has_application is False
    assert row.has_infrastructure is False
    assert row.loc > 0
    assert row.public_symbols == 3  # ManufacturingOrder, build_order, OrderView


def test_module_row_layers_cell_is_ascii() -> None:
    row = ModuleRow(
        context="orders",
        has_domain=True,
        has_application=False,
        has_infrastructure=False,
        has_interface=True,
        loc=10,
        public_symbols=2,
    )
    assert row.layers_cell() == "D - - X"


def test_empty_repo_yields_zero_counts(tmp_path: Path) -> None:
    stats = gather_stats(tmp_path)
    assert stats.bounded_contexts_scaffolded == 0
    assert stats.domain_entities == 0
    assert gather_module_rows(tmp_path) == []

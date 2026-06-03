"""Structural test: the orders bounded context exposes all four layers.

Tests are exempt from the architecture linter's layer rules, so importing the
non-domain layer packages here is allowed and is the cheapest way to assert the
skeleton exists. The linter itself (run by the pipeline) enforces AC-1's
"no warnings" half on these same packages.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "layer",
    ["domain", "application", "infrastructure", "interface"],
)
def test_orders_context_exposes_all_four_layers(layer: str) -> None:
    # AC-1: existe el bounded context apps/orders/ con las cuatro capas
    # (domain/, application/, infrastructure/, interface/).
    module = importlib.import_module(f"apps.orders.{layer}")
    assert module.__name__ == f"apps.orders.{layer}"

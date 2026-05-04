"""Tests for ``tools.linters.architecture``.

Each test creates a synthetic mini-repo under ``tmp_path`` and calls the
linter against it. We never run on the real repo here so the tests stay
hermetic and fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.linters.architecture import (
    RULE_CROSS_CONTEXT,
    RULE_EXTERNAL_IN_PURE_LAYER,
    RULE_LAYER,
    Layer,
    Violation,
    is_exempt_from_layer_rules,
    is_external,
    is_internal,
    is_stdlib,
    lint,
    main,
    path_to_context,
    path_to_layer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(repo: Path, rel: str, source: str) -> Path:
    """Create ``rel`` under ``repo`` with ``source``. Creates parent dirs."""
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source, encoding="utf-8")
    return p


def _rules(violations: list[Violation]) -> set[str]:
    return {v.rule for v in violations}


# ---------------------------------------------------------------------------
# 1. path_to_layer / path_to_context — pure functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("packages/domain/money.py", Layer.DOMAIN),
        ("packages/shared/ids.py", Layer.DOMAIN),
        ("packages/infrastructure/event_bus.py", Layer.INFRASTRUCTURE),
        ("apps/orders/domain/entities.py", Layer.DOMAIN),
        ("apps/orders/application/use_cases.py", Layer.APPLICATION),
        ("apps/orders/infrastructure/repository.py", Layer.INFRASTRUCTURE),
        ("apps/orders/interface/serializers.py", Layer.INTERFACE),
        ("apps/orders/views.py", Layer.INTERFACE),
        ("apps/orders/admin.py", Layer.INTERFACE),
        ("apps/orders/urls.py", Layer.INTERFACE),
    ],
)
def test_path_to_layer_recognises_layered_paths(rel: str, expected: Layer) -> None:
    assert path_to_layer(Path(rel)) == expected


@pytest.mark.parametrize(
    "rel",
    [
        "tools/orchestrator/run_all.py",
        "tools/linters/architecture.py",
        "frontend/src/main.tsx",
        "apps/orders/__init__.py",
        "apps/orders/apps.py",
        "apps/orders/celery_tasks.py",
        "apps/orders/migrations/0001_initial.py",
        "README.md",
    ],
)
def test_path_to_layer_returns_none_outside_layered_tree(rel: str) -> None:
    assert path_to_layer(Path(rel)) is None


def test_path_to_context_returns_apps_subname() -> None:
    assert path_to_context(Path("apps/orders/domain/entities.py")) == "orders"
    assert path_to_context(Path("apps/wip/views.py")) == "wip"


def test_path_to_context_returns_none_outside_apps() -> None:
    assert path_to_context(Path("packages/domain/money.py")) is None
    assert path_to_context(Path("tools/orchestrator/worker.py")) is None


def test_is_exempt_from_layer_rules() -> None:
    assert is_exempt_from_layer_rules(("tools", "linters", "architecture.py")) is True
    assert (
        is_exempt_from_layer_rules(
            ("apps", "orders", "domain", "tests", "test_order.py")
        )
        is True
    )
    assert (
        is_exempt_from_layer_rules(
            ("apps", "orders", "migrations", "0001_initial.py")
        )
        is True
    )
    assert is_exempt_from_layer_rules(("apps", "orders", "conftest.py")) is True
    assert (
        is_exempt_from_layer_rules(("apps", "orders", "domain", "entities.py"))
        is False
    )


def test_module_classification() -> None:
    assert is_stdlib("dataclasses") is True
    assert is_stdlib("datetime.timezone") is True
    assert is_stdlib("__future__") is True
    assert is_internal("apps.orders.domain") is True
    assert is_internal("packages.shared") is True
    assert is_internal("tools.orchestrator") is True
    assert is_external("django") is True
    assert is_external("httpx") is True
    assert is_external("dataclasses") is False
    assert is_external("apps.orders") is False


# ---------------------------------------------------------------------------
# 2. End-to-end: real linting against synthetic repos
# ---------------------------------------------------------------------------


def test_clean_repo_yields_no_violations(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "packages/domain/money.py",
        "from dataclasses import dataclass\n@dataclass\nclass Money: cents: int\n",
    )
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "from dataclasses import dataclass\n"
        "from packages.shared.ids import OrderId\n"
        "@dataclass\nclass Order: id: OrderId\n",
    )
    _write(tmp_path, "packages/shared/ids.py", "OrderId = str\n")
    _write(
        tmp_path,
        "apps/orders/application/use_cases.py",
        "from apps.orders.domain.entities import Order\n"
        "def create(): return Order('x')\n",
    )

    assert lint(tmp_path) == []


def test_domain_importing_external_package_is_violation(tmp_path: Path) -> None:
    """ARCH003 — domain may not import a third-party package."""
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "import django\n",  # GP-001 violation
    )
    violations = lint(tmp_path)
    assert any(v.rule == RULE_EXTERNAL_IN_PURE_LAYER for v in violations)
    assert any("django" in v.message for v in violations)


def test_application_importing_external_package_is_violation(tmp_path: Path) -> None:
    """ARCH003 — application is also a pure layer."""
    _write(
        tmp_path,
        "apps/orders/application/use_cases.py",
        "import httpx\n",
    )
    violations = lint(tmp_path)
    assert RULE_EXTERNAL_IN_PURE_LAYER in _rules(violations)


def test_domain_importing_application_is_layer_violation(tmp_path: Path) -> None:
    """ARCH001 — domain (L0) cannot import application (L1)."""
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "from apps.orders.application import use_cases\n",
    )
    violations = lint(tmp_path)
    assert RULE_LAYER in _rules(violations)


def test_application_importing_infrastructure_is_layer_violation(
    tmp_path: Path,
) -> None:
    """ARCH001 — application (L1) cannot import infrastructure (L2)."""
    _write(
        tmp_path,
        "apps/orders/application/use_cases.py",
        "from apps.orders.infrastructure import repository\n",
    )
    violations = lint(tmp_path)
    assert RULE_LAYER in _rules(violations)


def test_infrastructure_importing_interface_is_layer_violation(
    tmp_path: Path,
) -> None:
    """ARCH001 — infrastructure (L2) cannot import interface (L3)."""
    _write(
        tmp_path,
        "apps/orders/infrastructure/repository.py",
        "from apps.orders.interface import serializers\n",
    )
    violations = lint(tmp_path)
    assert RULE_LAYER in _rules(violations)


def test_cross_context_import_is_violation(tmp_path: Path) -> None:
    """ARCH002 — apps/orders cannot import apps/wip."""
    _write(
        tmp_path,
        "apps/orders/application/use_cases.py",
        "from apps.wip.domain.entities import WipPosition\n",
    )
    violations = lint(tmp_path)
    rules = _rules(violations)
    assert RULE_CROSS_CONTEXT in rules


def test_stdlib_in_pure_layers_is_allowed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "import dataclasses\nimport datetime\nfrom enum import StrEnum\n",
    )
    _write(
        tmp_path,
        "apps/orders/application/use_cases.py",
        "import dataclasses\n",
    )
    assert lint(tmp_path) == []


def test_external_package_in_infrastructure_is_allowed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/orders/infrastructure/http_client.py",
        "import httpx\nimport asyncua\n",
    )
    assert lint(tmp_path) == []


def test_lower_layer_imports_are_allowed(tmp_path: Path) -> None:
    """L≥N may import L≤N. Verifies the table direction explicitly."""
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "from packages.shared.ids import OrderId\n",
    )
    _write(
        tmp_path,
        "apps/orders/application/use_cases.py",
        "from apps.orders.domain.entities import Order\n"
        "from packages.shared.ids import OrderId\n",
    )
    _write(
        tmp_path,
        "apps/orders/infrastructure/repository.py",
        "from apps.orders.application.use_cases import Order\n"
        "from apps.orders.domain.entities import Order as O\n",
    )
    _write(tmp_path, "packages/shared/ids.py", "OrderId = str\n")
    _write(tmp_path, "apps/orders/domain/__init__.py", "")
    _write(tmp_path, "apps/orders/application/__init__.py", "")

    assert lint(tmp_path) == []


def test_tools_directory_is_exempt_from_layer_rules(tmp_path: Path) -> None:
    """tools/ may import third-party packages freely; layer rules don't apply."""
    _write(
        tmp_path,
        "tools/orchestrator/worker.py",
        "import httpx\nimport asyncio\nimport django\n",
    )
    assert lint(tmp_path) == []


def test_tests_subdirectory_is_exempt_from_layer_rules(tmp_path: Path) -> None:
    """A test in a domain/tests/ may import infrastructure for fixtures."""
    _write(
        tmp_path,
        "apps/orders/domain/tests/test_entities.py",
        "from apps.orders.infrastructure.repository import OrderRepo\n"
        "import httpx\n",
    )
    assert lint(tmp_path) == []


def test_tools_still_subject_to_cross_context_rule(tmp_path: Path) -> None:
    """tools/ doesn't have a context, so this is a no-op for tools, but the
    cross-context rule still triggers when a file in apps/X imports apps/Y
    via a tools-located helper. Here we verify the symmetric case: a file
    in apps/wip should not be importable from apps/orders, even from a
    layer-exempt path. We test this by placing a layer-exempt file (tests/)
    under apps/orders importing apps/wip.
    """
    _write(
        tmp_path,
        "apps/orders/application/tests/test_xs.py",  # layer-exempt
        "from apps.wip.domain.entities import WipPosition\n",
    )
    violations = lint(tmp_path)
    assert RULE_CROSS_CONTEXT in _rules(violations)


def test_relative_import_is_resolved_and_checked(tmp_path: Path) -> None:
    """Relative imports must still be checked. ``from ..application import x``
    inside ``apps/orders/domain/entities.py`` is a domain→application breach.
    """
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "from ..application import use_cases\n",
    )
    violations = lint(tmp_path)
    assert RULE_LAYER in _rules(violations)


def test_conditional_import_inside_function_is_caught(tmp_path: Path) -> None:
    """Hiding an import inside a function does NOT bypass the linter."""
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "def make_order():\n"
        "    import django\n"  # ARCH003: still a violation
        "    return django\n",
    )
    violations = lint(tmp_path)
    assert RULE_EXTERNAL_IN_PURE_LAYER in _rules(violations)


def test_violation_includes_file_line_and_rule(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "import dataclasses\nimport django\n",  # django on line 2
    )
    [v] = lint(tmp_path)
    assert v.rule == RULE_EXTERNAL_IN_PURE_LAYER
    assert v.line == 2
    assert v.path.name == "entities.py"


def test_main_returns_zero_on_clean_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "import dataclasses\n",
    )
    rc = main(["--root", str(tmp_path)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "OK" in err


def test_main_returns_one_on_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "import django\n",
    )
    rc = main(["--root", str(tmp_path)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "ARCH003" in out
    assert "django" in out


def test_fix_flag_prints_suggestion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        tmp_path,
        "apps/orders/application/use_cases.py",
        "from apps.orders.infrastructure import repository\n",
    )
    rc = main(["--root", str(tmp_path), "--fix"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "ARCH001" in out
    assert "suggestion:" in out


def test_lint_with_specific_paths_argument(tmp_path: Path) -> None:
    """Passing explicit paths overrides the default scan roots."""
    _write(
        tmp_path,
        "apps/orders/domain/entities.py",
        "import django\n",
    )
    _write(
        tmp_path,
        "apps/orders/infrastructure/repository.py",
        "import django\n",  # OK — infrastructure may import external
    )
    only_infra = lint(tmp_path, paths=[tmp_path / "apps" / "orders" / "infrastructure"])
    assert only_infra == []
    only_domain = lint(tmp_path, paths=[tmp_path / "apps" / "orders" / "domain"])
    assert RULE_EXTERNAL_IN_PURE_LAYER in _rules(only_domain)


def test_packages_shared_layer_constraints(tmp_path: Path) -> None:
    """packages/shared is L0 — same rules as domain."""
    _write(
        tmp_path,
        "packages/shared/ids.py",
        "import django\n",  # ARCH003
    )
    violations = lint(tmp_path)
    assert RULE_EXTERNAL_IN_PURE_LAYER in _rules(violations)


def test_packages_shared_can_import_packages_domain(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "packages/shared/ids.py",
        "from packages.domain.money import Money\n",
    )
    _write(tmp_path, "packages/domain/money.py", "class Money: pass\n")
    assert lint(tmp_path) == []

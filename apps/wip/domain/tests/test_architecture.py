"""Structural tests for the wip bounded context (GP-011).

These cover the *structural* acceptance criteria that the per-entity test files
do not: the four-layer package layout (AC-1), the stdlib-only purity of the
domain layer (AC-2, GP-001), and the AC-annotation contract itself (AC-7,
GP-011). They lean on the architecture linter's own importable API
(``tools.linters.architecture``) so the checks match exactly what the linter
enforces in CI — no subprocess, fully deterministic.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

from tools.linters.architecture import (
    Layer,
    is_stdlib,
    lint,
    path_to_context,
    path_to_layer,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_WIP_DIR = _REPO_ROOT / "apps" / "wip"
_DOMAIN_DIR = _WIP_DIR / "domain"
_TESTS_DIR = _DOMAIN_DIR / "tests"

_LAYERS: dict[str, Layer] = {
    "domain": Layer.DOMAIN,
    "application": Layer.APPLICATION,
    "infrastructure": Layer.INFRASTRUCTURE,
    "interface": Layer.INTERFACE,
}

# Entity / value-object module -> expected test file (AC-7, GP-011).
_ENTITY_TEST_FILES: dict[str, str] = {
    "Quantity": "test_quantity.py",
    "RouteStepRef": "test_route_step_ref.py",
    "WipBalance": "test_wip_balance.py",
}

_AC_PATTERN = re.compile(r"#\s*AC-(\d+)\b")


def _domain_modules() -> list[Path]:
    return sorted(p for p in _DOMAIN_DIR.glob("*.py") if p.name != "__init__.py")


def test_wip_exposes_four_importable_layer_packages() -> None:
    # AC-1: apps/wip/ has the four layers (domain/application/infrastructure/
    # interface), each an importable Python package living under apps/wip/.
    for layer in _LAYERS:
        module = importlib.import_module(f"apps.wip.{layer}")
        # A package has __path__; a plain module does not.
        assert hasattr(module, "__path__"), f"apps.wip.{layer} is not a package"
        module_file = Path(module.__file__ or "").resolve()
        assert module_file.name == "__init__.py"
        assert _WIP_DIR in module_file.parents


def test_linter_recognises_wip_context_and_layers() -> None:
    # AC-1: the architecture linter recognises `wip` as a bounded context and
    # maps each sublayer to the right architectural layer.
    for layer_name, expected in _LAYERS.items():
        rel = Path("apps") / "wip" / layer_name / "__init__.py"
        assert path_to_context(rel) == "wip"
        assert path_to_layer(rel) == expected


def test_wip_context_passes_architecture_linter_with_zero_violations() -> None:
    # AC-1: the architecture linter passes over apps/wip/ with 0 violations.
    violations = lint(_REPO_ROOT, [_WIP_DIR])
    assert violations == [], "\n".join(
        v.format_line(_REPO_ROOT) for v in violations
    )


def test_domain_layer_imports_stdlib_only() -> None:
    # AC-2 (GP-001): apps/wip/domain/ imports only the standard library and its
    # own internal modules — never Django, DRF or any third-party package.
    offenders: list[str] = []
    for module_path in _domain_modules():
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # Relative imports (level > 0) are internal to apps.wip.domain.
                if node.level and node.level > 0:
                    continue
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                if not is_stdlib(name):
                    offenders.append(f"{module_path.name}: import {name}")
    assert offenders == [], "domain layer must import stdlib only (GP-001): " + ", ".join(
        offenders
    )


def test_every_entity_and_value_object_has_an_annotated_test_file() -> None:
    # AC-7 (GP-011): each new entity/VO has a test_<entity>.py whose tests carry
    # `# AC-N:` annotations linking them back to acceptance criteria.
    for entity, test_filename in _ENTITY_TEST_FILES.items():
        test_file = _TESTS_DIR / test_filename
        assert test_file.is_file(), f"missing test file for {entity}: {test_filename}"
        annotations = _AC_PATTERN.findall(test_file.read_text(encoding="utf-8"))
        assert annotations, f"{test_filename} has no `# AC-N:` annotation for {entity}"


def test_all_seven_acceptance_criteria_have_an_annotated_test() -> None:
    # AC-7 (GP-011): every AC of this Story (AC-1..AC-7) is covered by at least
    # one `# AC-N:` annotated test somewhere in the domain test suite.
    covered: set[int] = set()
    for test_file in _TESTS_DIR.glob("test_*.py"):
        covered.update(int(n) for n in _AC_PATTERN.findall(test_file.read_text(encoding="utf-8")))
    missing = set(range(1, 8)) - covered
    assert not missing, f"acceptance criteria without an annotated test: {sorted(missing)}"

"""Architecture linter for the NSG MES repository.

Enforces the layer rules and bounded-context isolation defined in
``/ARCHITECTURE.md`` by parsing imports with ``ast`` (no regex).

Rules
-----
ARCH001  Layer rule. A file at layer ``N`` may only import from layers ``≤ N``
         (closer to ``domain``). Order: domain (0) < application (1)
         < infrastructure (2) < interface (3).

ARCH002  Cross-context rule. ``apps/X/`` may not import from ``apps/Y/`` when
         ``X != Y``. Cross-context communication goes through the event bus.

ARCH003  External-package-in-pure-layer rule. The domain (L0) and application
         (L1) layers may only import the standard library and other internal
         layered modules. External third-party packages (Django, httpx,
         asyncua, etc.) are forbidden in those layers.

Files exempt from layer rules (cross-context still applies):
    - Anything under ``tools/``.
    - Any path containing a ``tests/`` directory.
    - Any path containing a ``migrations/`` directory.
    - Files named ``conftest.py``.

CLI usage
---------
    python -m tools.linters.architecture [--fix] [--root PATH] [paths ...]
    python tools/linters/architecture.py  [--fix] [--root PATH] [paths ...]

Exit code: 0 if clean, 1 if any violation is found.

The ``--fix`` flag does NOT modify any file. It only prints a refactor
suggestion next to each violation.
"""

from __future__ import annotations

import argparse
import ast
import enum
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "RULE_CROSS_CONTEXT",
    "RULE_EXTERNAL_IN_PURE_LAYER",
    "RULE_LAYER",
    "Layer",
    "Violation",
    "check_source",
    "is_exempt_from_layer_rules",
    "is_external",
    "is_internal",
    "is_stdlib",
    "lint",
    "main",
    "path_to_context",
    "path_to_layer",
]


# ---------------------------------------------------------------------------
# Layer model
# ---------------------------------------------------------------------------


class Layer(enum.IntEnum):
    """Architectural layer. Lower values are deeper (closer to domain)."""

    DOMAIN = 0
    APPLICATION = 1
    INFRASTRUCTURE = 2
    INTERFACE = 3


_LAYER_NAMES: dict[Layer, str] = {
    Layer.DOMAIN: "domain",
    Layer.APPLICATION: "application",
    Layer.INFRASTRUCTURE: "infrastructure",
    Layer.INTERFACE: "interface",
}


RULE_LAYER = "ARCH001"
RULE_CROSS_CONTEXT = "ARCH002"
RULE_EXTERNAL_IN_PURE_LAYER = "ARCH003"


@dataclass(frozen=True)
class Violation:
    """A single rule violation found in source code."""

    path: Path
    line: int
    rule: str
    message: str
    suggestion: str = ""

    def format_line(self, repo_root: Path, *, with_fix: bool = False) -> str:
        try:
            shown_path: Path | str = self.path.relative_to(repo_root)
        except ValueError:
            shown_path = self.path
        out = f"{shown_path}:{self.line}: {self.rule}: {self.message}"
        if with_fix and self.suggestion:
            out += f"\n    suggestion: {self.suggestion}"
        return out


# ---------------------------------------------------------------------------
# Path → layer / context resolution
# ---------------------------------------------------------------------------


def path_to_layer(rel_path: Path) -> Layer | None:
    """Resolve a path (relative to the repo root) to its architectural layer.

    Returns ``None`` if the path is outside the layered tree.
    """
    parts = rel_path.parts

    # packages/{domain,shared}/** → L0
    if len(parts) >= 2 and parts[0] == "packages" and parts[1] in ("domain", "shared"):
        return Layer.DOMAIN

    # packages/infrastructure/** → L2
    if len(parts) >= 2 and parts[:2] == ("packages", "infrastructure"):
        return Layer.INFRASTRUCTURE

    # apps/<X>/<sublayer>/** → layer determined by sublayer
    if len(parts) >= 3 and parts[0] == "apps":
        sublayer = parts[2]
        if sublayer == "domain":
            return Layer.DOMAIN
        if sublayer == "application":
            return Layer.APPLICATION
        if sublayer == "infrastructure":
            return Layer.INFRASTRUCTURE
        if sublayer == "interface":
            return Layer.INTERFACE

    # apps/<X>/{views,admin,urls}.py → L3
    if (
        len(parts) == 3
        and parts[0] == "apps"
        and parts[2] in ("views.py", "admin.py", "urls.py")
    ):
        return Layer.INTERFACE

    return None


def path_to_context(rel_path: Path) -> str | None:
    """Return the bounded-context name for ``apps/<X>/...``, else ``None``."""
    parts = rel_path.parts
    if len(parts) >= 2 and parts[0] == "apps":
        return parts[1]
    return None


def is_exempt_from_layer_rules(rel_parts: tuple[str, ...]) -> bool:
    """Layer rules are skipped for these files. Cross-context still applies."""
    if rel_parts[:1] == ("tools",):
        return True
    if "tests" in rel_parts or "migrations" in rel_parts:
        return True
    return bool(rel_parts and rel_parts[-1] == "conftest.py")


# ---------------------------------------------------------------------------
# Module classification
# ---------------------------------------------------------------------------


_STDLIB_NAMES: frozenset[str] = frozenset(sys.stdlib_module_names) | {"__future__"}
_INTERNAL_TOPS: frozenset[str] = frozenset({"apps", "packages", "tools"})


def _module_top(module: str) -> str:
    """Top-level component of a dotted module path."""
    return module.split(".", 1)[0]


def is_stdlib(module: str) -> bool:
    """Whether ``module`` is from the standard library."""
    return _module_top(module) in _STDLIB_NAMES


def is_internal(module: str) -> bool:
    """Whether ``module`` lives under ``apps/``, ``packages/``, or ``tools/``."""
    return _module_top(module) in _INTERNAL_TOPS


def is_external(module: str) -> bool:
    """Whether ``module`` is a third-party package (not stdlib, not internal)."""
    return not is_stdlib(module) and not is_internal(module)


def _imported_module_to_layer(module: str) -> Layer | None:
    """Best-effort: map a dotted module to the layer it would live in."""
    parts = module.split(".")
    if not parts or not parts[0]:
        return None
    # Try as a package first (e.g., apps.orders.domain → apps/orders/domain/__init__.py)
    layer = path_to_layer(Path(*parts, "__init__.py"))
    if layer is not None:
        return layer
    # Try as a single file (e.g., apps.orders.views → apps/orders/views.py)
    synthetic = Path(f"{parts[0]}.py") if len(parts) == 1 else Path(*parts[:-1], f"{parts[-1]}.py")
    return path_to_layer(synthetic)


def _imported_module_to_context(module: str) -> str | None:
    """Top-level apps context, or ``None``."""
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "apps":
        return parts[1]
    return None


# ---------------------------------------------------------------------------
# Per-file checking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FileContext:
    path: Path
    rel_path: Path
    layer: Layer | None
    context: str | None
    exempt: bool


def _resolve_relative(rel_path: Path, level: int, module: str | None) -> str | None:
    """Convert a relative import to an absolute dotted module name."""
    parts = rel_path.parts
    if not parts:
        return None
    pkg_parts = parts[:-1]  # strip the importing file's own filename
    drop = level - 1
    if drop > len(pkg_parts):
        return None
    base_parts = pkg_parts[: len(pkg_parts) - drop] if drop > 0 else pkg_parts
    if module:
        return ".".join((*base_parts, module))
    return ".".join(base_parts) or None


def _layer_suggestion(from_layer: Layer, to_layer: Layer) -> str:
    pairs: dict[tuple[Layer, Layer], str] = {
        (Layer.DOMAIN, Layer.APPLICATION): (
            "Move the dependency to application/, or define a Protocol in "
            "domain/ and inject the application function as a parameter."
        ),
        (Layer.DOMAIN, Layer.INFRASTRUCTURE): (
            "Domain has no dependencies on infrastructure. Define a Protocol "
            "in application/ and inject the infrastructure adapter at the "
            "interface composition root."
        ),
        (Layer.DOMAIN, Layer.INTERFACE): (
            "Domain entities should not depend on interface adapters. Move "
            "shared logic to domain/ and let interface code call domain "
            "entities, not the other way around."
        ),
        (Layer.APPLICATION, Layer.INFRASTRUCTURE): (
            "Define a Protocol in application/ that abstracts the "
            "infrastructure operation, and inject the concrete implementation "
            "from interface/."
        ),
        (Layer.APPLICATION, Layer.INTERFACE): (
            "Application use cases should not call into interface code. Move "
            "shared helpers to application/, or invert the dependency."
        ),
        (Layer.INFRASTRUCTURE, Layer.INTERFACE): (
            "Infrastructure adapters should not depend on the interface "
            "layer. The composition root in interface/ wires infrastructure "
            "to application."
        ),
    }
    return pairs.get(
        (from_layer, to_layer),
        "Move the import target down to a lower layer, or invert the dependency.",
    )


def _check_import(ctx: _FileContext, module: str, line: int) -> list[Violation]:
    violations: list[Violation] = []

    # Cross-context check applies even to exempt files (tools/, tests/, etc.).
    imported_ctx = _imported_module_to_context(module)
    if (
        imported_ctx is not None
        and ctx.context is not None
        and imported_ctx != ctx.context
    ):
        violations.append(
            Violation(
                path=ctx.path,
                line=line,
                rule=RULE_CROSS_CONTEXT,
                message=(
                    f"`apps/{ctx.context}/` cannot import from `apps/{imported_ctx}/`. "
                    f"Bounded contexts communicate only via the event bus."
                ),
                suggestion=(
                    f"Define an event in `apps/{imported_ctx}/domain/events.py` "
                    f"and subscribe to it from `apps/{ctx.context}/infrastructure/`. "
                    f"See docs/architecture/event-bus.md."
                ),
            )
        )

    if ctx.exempt or ctx.layer is None:
        return violations

    if is_stdlib(module):
        return violations

    imported_layer = _imported_module_to_layer(module)
    if imported_layer is not None:
        if imported_layer > ctx.layer:
            violations.append(
                Violation(
                    path=ctx.path,
                    line=line,
                    rule=RULE_LAYER,
                    message=(
                        f"{_LAYER_NAMES[ctx.layer]} layer cannot import from "
                        f"{_LAYER_NAMES[imported_layer]} layer (`{module}`)."
                    ),
                    suggestion=_layer_suggestion(ctx.layer, imported_layer),
                )
            )
        return violations

    # Not stdlib, not in our layered tree → external third-party package.
    if is_external(module) and ctx.layer < Layer.INFRASTRUCTURE:
        top = _module_top(module)
        violations.append(
            Violation(
                path=ctx.path,
                line=line,
                rule=RULE_EXTERNAL_IN_PURE_LAYER,
                message=(
                    f"{_LAYER_NAMES[ctx.layer]} layer cannot import external "
                    f"package `{top}`. Only stdlib is allowed in pure layers "
                    f"(domain, application)."
                ),
                suggestion=(
                    f"Wrap `{top}` behind a Protocol defined in application/, "
                    f"with the concrete implementation living in infrastructure/."
                ),
            )
        )

    return violations


def check_source(rel_path: Path, abs_path: Path, source: str) -> list[Violation]:
    """Check a single source file. Used by tests; ``lint`` calls this."""
    try:
        tree = ast.parse(source, filename=str(abs_path))
    except SyntaxError:
        # Let ruff / mypy report syntax errors. We refuse to guess.
        return []

    ctx = _FileContext(
        path=abs_path,
        rel_path=rel_path,
        layer=path_to_layer(rel_path),
        context=path_to_context(rel_path),
        exempt=is_exempt_from_layer_rules(rel_path.parts),
    )

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                violations.extend(_check_import(ctx, alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                resolved = _resolve_relative(rel_path, node.level, node.module)
                if resolved is None:
                    continue
                module = resolved
            else:
                if node.module is None:
                    continue
                module = node.module
            violations.extend(_check_import(ctx, module, node.lineno))

    return violations


# ---------------------------------------------------------------------------
# Discovery and CLI
# ---------------------------------------------------------------------------


_DEFAULT_SCAN_ROOTS: tuple[str, ...] = (
    "apps",
    "packages",
    "tools/orchestrator",
    "tools/linters",
)


def _iter_python_files(repo_root: Path, paths: list[Path] | None) -> Iterator[Path]:
    if paths:
        for p in paths:
            if p.is_file() and p.suffix == ".py":
                yield p
            elif p.is_dir():
                yield from sorted(p.rglob("*.py"))
        return
    for tree in _DEFAULT_SCAN_ROOTS:
        root = repo_root / tree
        if root.exists():
            yield from sorted(root.rglob("*.py"))


def lint(repo_root: Path, paths: Iterable[Path] | None = None) -> list[Violation]:
    """Run the linter against ``repo_root``. Returns a list of violations."""
    repo_root = repo_root.resolve()
    paths_list = [p.resolve() for p in paths] if paths is not None else None

    violations: list[Violation] = []
    for f in _iter_python_files(repo_root, paths_list):
        try:
            rel = f.resolve().relative_to(repo_root)
        except ValueError:
            continue
        try:
            source = f.read_text(encoding="utf-8")
        except OSError:
            continue
        violations.extend(check_source(rel, f, source))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="architecture-linter",
        description=(
            "Enforce NSG MES layer rules and bounded-context isolation. "
            "See /ARCHITECTURE.md."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Print a refactor suggestion next to each violation. Does NOT "
        "modify any file.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to lint. Default: scan the standard tree.",
    )
    args = parser.parse_args(argv)

    repo_root = args.root.resolve()
    paths = list(args.paths) if args.paths else None

    violations = lint(repo_root, paths)

    if not violations:
        print(f"OK: 0 architecture violations under {repo_root}.", file=sys.stderr)
        return 0

    for v in violations:
        print(v.format_line(repo_root, with_fix=args.fix))

    print(
        f"\n{len(violations)} architecture violation(s) found.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

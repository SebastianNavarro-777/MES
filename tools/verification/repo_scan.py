"""Static scan of the repository tree for the ``docs/generated/`` snapshots.

Everything here is **pure with respect to the repo root passed in**: no
network, no git, no Django import. Counts are derived with :mod:`ast`, never
regex, so renamed symbols and comments never fool them. This keeps the Stop
hook fast and deterministic — two runs over the same tree return identical
results (the determinism requirement in the NSG-50 notas técnicas).

What it measures
----------------
* Bounded contexts — ``apps/<context>/`` directories, split into *scaffolded*
  (the directory exists) and *implemented* (it carries at least one ``.py``).
* Domain entities — top-level classes in domain-layer modules, excluding the
  ``events.py`` / ``exceptions.py`` modules which are counted (or skipped)
  separately.
* Domain events — top-level classes declared in any domain ``events.py``.
* API endpoints — ``path(...)`` / ``re_path(...)`` calls in any ``urls.py``.
* Test functions — ``def test_*`` across ``apps/``, ``packages/`` and
  ``tools/``.

It also builds the per-context rows for ``module-map.md``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ModuleRow",
    "RepoStats",
    "context_dirs",
    "count_classes",
    "count_domain_entities",
    "count_domain_events",
    "count_public_symbols",
    "count_test_functions",
    "count_url_patterns",
    "gather_module_rows",
    "gather_stats",
]

# Directory names that never carry production source we want to measure.
_SKIP_DIR_PARTS = frozenset({"__pycache__", "migrations"})
# Domain modules that are not "entities" in the headline count.
_NON_ENTITY_DOMAIN_FILES = frozenset({"__init__.py", "events.py", "exceptions.py"})
_URL_CALLEES = frozenset({"path", "re_path"})


@dataclass(frozen=True)
class RepoStats:
    """Headline counts shown in ``STATE.md``."""

    bounded_contexts_scaffolded: int
    bounded_contexts_implemented: int
    domain_entities: int
    api_endpoints: int
    domain_events: int
    test_functions: int


@dataclass(frozen=True)
class ModuleRow:
    """One row of ``module-map.md`` for an implemented bounded context."""

    context: str
    has_domain: bool
    has_application: bool
    has_infrastructure: bool
    has_interface: bool
    loc: int
    public_symbols: int

    def layers_cell(self) -> str:
        """Render the ``D/A/I/X`` presence cell, e.g. ``D A - X``."""
        flags = (
            ("D", self.has_domain),
            ("A", self.has_application),
            ("I", self.has_infrastructure),
            ("X", self.has_interface),
        )
        return " ".join(letter if present else "-" for letter, present in flags)


# ---------------------------------------------------------------------------
# Low-level file helpers
# ---------------------------------------------------------------------------


def _parse(path: Path) -> ast.Module | None:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


def _is_skipped(path: Path, root: Path, *, exclude_tests: bool) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    if any(part in _SKIP_DIR_PARTS for part in parts):
        return True
    return exclude_tests and "tests" in parts


def _iter_py_files(base: Path, root: Path, *, exclude_tests: bool) -> list[Path]:
    if not base.exists():
        return []
    return sorted(
        p
        for p in base.rglob("*.py")
        if p.is_file() and not _is_skipped(p, root, exclude_tests=exclude_tests)
    )


# ---------------------------------------------------------------------------
# AST counters (pure, file-level)
# ---------------------------------------------------------------------------


def count_classes(path: Path) -> int:
    """Top-level class definitions in ``path``."""
    tree = _parse(path)
    if tree is None:
        return 0
    return sum(isinstance(node, ast.ClassDef) for node in tree.body)


def count_public_symbols(path: Path) -> int:
    """Top-level classes/functions not prefixed with ``_``."""
    tree = _parse(path)
    if tree is None:
        return 0
    public = 0
    for node in tree.body:
        if isinstance(
            node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ) and not node.name.startswith("_"):
            public += 1
    return public


def count_test_functions(path: Path) -> int:
    """Functions named ``test_*`` anywhere in ``path`` (incl. methods)."""
    tree = _parse(path)
    if tree is None:
        return 0
    return sum(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def count_url_patterns(path: Path) -> int:
    """Number of ``path(...)`` / ``re_path(...)`` calls in ``path``."""
    tree = _parse(path)
    if tree is None:
        return 0
    return sum(
        isinstance(node, ast.Call) and _callee_name(node.func) in _URL_CALLEES
        for node in ast.walk(tree)
    )


# ---------------------------------------------------------------------------
# Tree-level aggregation
# ---------------------------------------------------------------------------


def context_dirs(root: Path) -> list[Path]:
    """Sorted ``apps/<context>/`` directories (the bounded contexts)."""
    apps = root / "apps"
    if not apps.exists():
        return []
    return sorted(p for p in apps.iterdir() if p.is_dir())


def _context_is_implemented(ctx_dir: Path, root: Path) -> bool:
    return bool(_iter_py_files(ctx_dir, root, exclude_tests=False))


def _domain_dirs(root: Path) -> list[Path]:
    dirs = [root / "packages" / "domain", root / "packages" / "shared"]
    dirs.extend(ctx / "domain" for ctx in context_dirs(root))
    return [d for d in dirs if d.exists()]


def count_domain_entities(root: Path) -> int:
    """Top-level classes in domain modules, excluding events/exceptions."""
    total = 0
    for base in _domain_dirs(root):
        for path in _iter_py_files(base, root, exclude_tests=True):
            if path.name in _NON_ENTITY_DOMAIN_FILES:
                continue
            total += count_classes(path)
    return total


def count_domain_events(root: Path) -> int:
    """Top-level classes declared in any domain ``events.py``."""
    total = 0
    for base in _domain_dirs(root):
        for path in _iter_py_files(base, root, exclude_tests=True):
            if path.name == "events.py":
                total += count_classes(path)
    return total


def _count_api_endpoints(root: Path) -> int:
    total = 0
    for ctx in context_dirs(root):
        for path in _iter_py_files(ctx, root, exclude_tests=True):
            if path.name == "urls.py":
                total += count_url_patterns(path)
    return total


def _count_test_functions(root: Path) -> int:
    total = 0
    for top in ("apps", "packages", "tools"):
        base = root / top
        for path in _iter_py_files(base, root, exclude_tests=False):
            if path.name.startswith("test_"):
                total += count_test_functions(path)
    return total


def gather_stats(root: Path) -> RepoStats:
    """Compute the headline counts for ``STATE.md``."""
    root = root.resolve()
    contexts = context_dirs(root)
    implemented = [c for c in contexts if _context_is_implemented(c, root)]
    return RepoStats(
        bounded_contexts_scaffolded=len(contexts),
        bounded_contexts_implemented=len(implemented),
        domain_entities=count_domain_entities(root),
        api_endpoints=_count_api_endpoints(root),
        domain_events=count_domain_events(root),
        test_functions=_count_test_functions(root),
    )


def _module_row(ctx_dir: Path, root: Path) -> ModuleRow:
    impl_files = _iter_py_files(ctx_dir, root, exclude_tests=True)
    loc = 0
    public = 0
    for path in impl_files:
        try:
            loc += len(path.read_text(encoding="utf-8").splitlines())
        except OSError:
            continue
        public += count_public_symbols(path)
    return ModuleRow(
        context=ctx_dir.name,
        has_domain=(ctx_dir / "domain").exists()
        and bool(_iter_py_files(ctx_dir / "domain", root, exclude_tests=True)),
        has_application=(ctx_dir / "application").exists()
        and bool(_iter_py_files(ctx_dir / "application", root, exclude_tests=True)),
        has_infrastructure=(ctx_dir / "infrastructure").exists()
        and bool(_iter_py_files(ctx_dir / "infrastructure", root, exclude_tests=True)),
        has_interface=_has_interface_layer(ctx_dir, root),
        loc=loc,
        public_symbols=public,
    )


def _has_interface_layer(ctx_dir: Path, root: Path) -> bool:
    if (ctx_dir / "interface").exists() and _iter_py_files(
        ctx_dir / "interface", root, exclude_tests=True
    ):
        return True
    # Django-convention top-level interface modules.
    return any((ctx_dir / name).exists() for name in ("views.py", "urls.py", "admin.py"))


def gather_module_rows(root: Path) -> list[ModuleRow]:
    """One :class:`ModuleRow` per *implemented* bounded context."""
    root = root.resolve()
    rows = [
        _module_row(ctx, root)
        for ctx in context_dirs(root)
        if _context_is_implemented(ctx, root)
    ]
    return rows

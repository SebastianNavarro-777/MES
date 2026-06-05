"""Repository scanner for the auto-generated docs (``STATE.md``, ``module-map.md``).

This module is **pure**: it reads the working tree and ``git`` history and
returns dataclasses. It performs no writes and has no network dependency, so
the rendering/CLI layers (``update_state.py``, ``dump_module_map.py``) stay
trivial to test deterministically.

It lives under ``tools/`` and is therefore exempt from the layer rules in
``ARCHITECTURE.md`` (it is not a bounded context), but it still passes
``ruff check`` and ``mypy --strict`` with no bypass.

Counting heuristics (kept deliberately cheap so the Stop hook stays fast):

* **Bounded contexts** are the directories under ``apps/``. A context "has
  code" when it contains at least one non-trivial ``.py`` file (more than an
  empty ``__init__``/``.gitkeep`` placeholder).
* **Domain entities / events** are top-level classes declared under a context's
  ``domain/`` package (events are the classes in a ``events.py`` module; every
  other domain class counts as an entity).
* **API endpoints** are ``path()`` / ``re_path()`` / ``router.register()`` calls
  found in ``urls.py`` modules under ``config/`` and ``apps/``.
* **Tests** are ``test_*`` functions in ``test_*.py`` files (cheap via ``ast``).
  Coverage is intentionally *not* computed here — running the suite under
  coverage is too slow for a per-session write step.
"""

from __future__ import annotations

import ast
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ContextStats",
    "MergedPR",
    "RepoStats",
    "active_exec_plans",
    "collect_context_stats",
    "count_api_endpoints",
    "count_domain_entities",
    "count_domain_events",
    "count_test_functions",
    "gather",
    "merged_prs",
]

# Layer short codes used in the module map (D=domain, A=application,
# I=infrastructure, X=interface).
_LAYER_DIRS: tuple[tuple[str, str], ...] = (
    ("domain", "D"),
    ("application", "A"),
    ("infrastructure", "I"),
    ("interface", "X"),
)

# Files that do not represent real code when scanning a scaffolded context.
_PLACEHOLDER_NAMES: frozenset[str] = frozenset({".gitkeep"})

_PR_NUMBER_RE = re.compile(r"\(#(\d+)\)")
_TICKET_RE = re.compile(r"\b(NSG-\d+)\b")


@dataclass(frozen=True)
class ContextStats:
    """Per-bounded-context metrics for the module map."""

    name: str
    layers_present: tuple[str, ...]
    loc: int
    public_symbols: int


@dataclass(frozen=True)
class MergedPR:
    """A merged pull request parsed from ``git log``."""

    number: int
    ticket: str | None
    subject: str
    date: str


@dataclass(frozen=True)
class RepoStats:
    """Aggregate snapshot of the repository for ``STATE.md``."""

    bounded_contexts_scaffolded: int
    bounded_contexts_with_code: int
    domain_entities: int
    api_endpoints: int
    domain_events: int
    test_functions: int
    contexts: tuple[ContextStats, ...]
    merged_prs: tuple[MergedPR, ...]
    active_exec_plans: tuple[str, ...]


# ---------------------------------------------------------------------------
# Low-level file helpers
# ---------------------------------------------------------------------------


def _iter_py_files(directory: Path) -> Iterator[Path]:
    """Yield ``.py`` files under ``directory``, skipping caches and tests dirs."""
    if not directory.exists():
        return
    for path in sorted(directory.rglob("*.py")):
        parts = path.parts
        if "__pycache__" in parts or ".venv" in parts:
            continue
        yield path


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None


def _is_trivial_module(path: Path) -> bool:
    """True when a ``.py`` file has no real code (empty or docstring-only)."""
    tree = _parse(path)
    if tree is None:
        return True
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # bare string/constant (module docstring)
        return False
    return True


def _count_code_lines(path: Path) -> int:
    """Count non-blank, non-comment-only lines in a ``.py`` file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    total = 0
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            total += 1
    return total


def _count_top_level_classes(tree: ast.Module) -> int:
    return sum(1 for node in tree.body if isinstance(node, ast.ClassDef))


def _count_public_symbols(tree: ast.Module) -> int:
    """Top-level classes and functions whose name does not start with ``_``."""
    total = 0
    for node in tree.body:
        if isinstance(
            node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ) and not node.name.startswith("_"):
            total += 1
    return total


# ---------------------------------------------------------------------------
# Context scanning
# ---------------------------------------------------------------------------


def _context_dirs(repo_root: Path) -> list[Path]:
    apps = repo_root / "apps"
    if not apps.exists():
        return []
    return sorted(p for p in apps.iterdir() if p.is_dir())


def _context_has_code(context_dir: Path) -> bool:
    for py in _iter_py_files(context_dir):
        if py.name == "__init__.py" and _is_trivial_module(py):
            continue
        if not _is_trivial_module(py):
            return True
    return False


def _layers_present(context_dir: Path) -> tuple[str, ...]:
    present: list[str] = []
    for dir_name, code in _LAYER_DIRS:
        layer_dir = context_dir / dir_name
        if layer_dir.is_dir() and any(
            not _is_trivial_module(py) for py in _iter_py_files(layer_dir)
        ):
            present.append(code)
    # Django-convention interface files at the context root also count as X.
    if "X" not in present and any(
        (context_dir / name).exists() and not _is_trivial_module(context_dir / name)
        for name in ("views.py", "urls.py", "admin.py")
    ):
        present.append("X")
    return tuple(present)


def collect_context_stats(repo_root: Path) -> list[ContextStats]:
    """One :class:`ContextStats` per directory under ``apps/`` (sorted)."""
    stats: list[ContextStats] = []
    for context_dir in _context_dirs(repo_root):
        loc = 0
        symbols = 0
        for py in _iter_py_files(context_dir):
            loc += _count_code_lines(py)
            tree = _parse(py)
            if tree is not None and "tests" not in py.parts:
                symbols += _count_public_symbols(tree)
        stats.append(
            ContextStats(
                name=context_dir.name,
                layers_present=_layers_present(context_dir),
                loc=loc,
                public_symbols=symbols,
            )
        )
    return stats


# ---------------------------------------------------------------------------
# Aggregate counters
# ---------------------------------------------------------------------------


def _domain_dirs(repo_root: Path) -> list[Path]:
    dirs: list[Path] = []
    for context_dir in _context_dirs(repo_root):
        domain = context_dir / "domain"
        if domain.is_dir():
            dirs.append(domain)
    for shared in ("packages/domain", "packages/shared"):
        path = repo_root / shared
        if path.is_dir():
            dirs.append(path)
    return dirs


def count_domain_entities(repo_root: Path) -> int:
    """Top-level domain classes, excluding events and test modules."""
    total = 0
    for domain in _domain_dirs(repo_root):
        for py in _iter_py_files(domain):
            if py.name == "events.py" or "tests" in py.parts:
                continue
            tree = _parse(py)
            if tree is not None:
                total += _count_top_level_classes(tree)
    return total


def count_domain_events(repo_root: Path) -> int:
    """Top-level classes declared in ``domain/events.py`` modules."""
    total = 0
    for domain in _domain_dirs(repo_root):
        events = domain / "events.py"
        if events.is_file() and "tests" not in events.parts:
            tree = _parse(events)
            if tree is not None:
                total += _count_top_level_classes(tree)
    return total


def _count_url_calls(tree: ast.Module) -> int:
    total = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_path = isinstance(func, ast.Name) and func.id in ("path", "re_path")
        is_register = isinstance(func, ast.Attribute) and func.attr == "register"
        if is_path or is_register:
            total += 1
    return total


def _url_modules(repo_root: Path) -> Iterator[Path]:
    config_urls = repo_root / "config" / "urls.py"
    if config_urls.is_file():
        yield config_urls
    for context_dir in _context_dirs(repo_root):
        for py in _iter_py_files(context_dir):
            if py.name == "urls.py":
                yield py


def count_api_endpoints(repo_root: Path) -> int:
    """Count URL route declarations across ``config/`` and ``apps/``."""
    total = 0
    for module in _url_modules(repo_root):
        tree = _parse(module)
        if tree is not None:
            total += _count_url_calls(tree)
    return total


def count_test_functions(repo_root: Path) -> int:
    """Count ``test_*`` functions in ``test_*.py`` files across the repo."""
    total = 0
    for root in ("apps", "packages", "tools"):
        base = repo_root / root
        for py in _iter_py_files(base):
            if not py.name.startswith("test_"):
                continue
            tree = _parse(py)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(
                    node, ast.FunctionDef | ast.AsyncFunctionDef
                ) and node.name.startswith("test_"):
                    total += 1
    return total


def active_exec_plans(repo_root: Path) -> tuple[str, ...]:
    """Names of plans under ``docs/exec-plans/active/`` (``.md`` files)."""
    active = repo_root / "docs" / "exec-plans" / "active"
    if not active.is_dir():
        return ()
    return tuple(sorted(p.name for p in active.glob("*.md")))


# ---------------------------------------------------------------------------
# git history
# ---------------------------------------------------------------------------


def merged_prs(
    repo_root: Path,
    *,
    limit: int = 15,
    git_bin: str = "git",
) -> tuple[MergedPR, ...]:
    """Parse recently merged PRs from ``git log`` subjects (``(#N)`` markers).

    Network-free and best-effort: any ``git`` failure yields an empty tuple so
    the caller degrades gracefully rather than raising.
    """
    try:
        result = subprocess.run(
            [git_bin, "log", "--max-count=200", "--pretty=format:%cI%x1f%s"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()

    prs: list[MergedPR] = []
    seen: set[int] = set()
    for line in result.stdout.splitlines():
        date, _, subject = line.partition("\x1f")
        match = _PR_NUMBER_RE.search(subject)
        if match is None:
            continue
        number = int(match.group(1))
        if number in seen:
            continue
        seen.add(number)
        ticket_match = _TICKET_RE.search(subject)
        prs.append(
            MergedPR(
                number=number,
                ticket=ticket_match.group(1) if ticket_match else None,
                subject=subject.strip(),
                date=date[:10],
            )
        )
        if len(prs) >= limit:
            break
    return tuple(prs)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def gather(repo_root: Path, *, git_bin: str = "git") -> RepoStats:
    """Build the full :class:`RepoStats` snapshot for ``repo_root``."""
    contexts = tuple(collect_context_stats(repo_root))
    with_code = sum(1 for c in _context_dirs(repo_root) if _context_has_code(c))
    return RepoStats(
        bounded_contexts_scaffolded=len(contexts),
        bounded_contexts_with_code=with_code,
        domain_entities=count_domain_entities(repo_root),
        api_endpoints=count_api_endpoints(repo_root),
        domain_events=count_domain_events(repo_root),
        test_functions=count_test_functions(repo_root),
        contexts=contexts,
        merged_prs=merged_prs(repo_root, git_bin=git_bin),
        active_exec_plans=active_exec_plans(repo_root),
    )

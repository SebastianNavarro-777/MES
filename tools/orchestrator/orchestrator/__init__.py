"""NSG MES orchestrator.

Single-process reactive orchestrator that drives the harness:
- polls Linear for actionable tickets,
- spawns Claude Code (headless) with the right system prompt,
- bridges results back to Linear and to GitHub,
- fires Architect / Auditor / Gardener on counter thresholds.

See ``tools/orchestrator/README.md`` for the lay of the land and
``tools/orchestrator/orchestrator/__main__.py`` for the CLI surface.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]

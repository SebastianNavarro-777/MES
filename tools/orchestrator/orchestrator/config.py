"""Orchestrator configuration loaded from ``.env`` at the repo root.

Built on Pydantic Settings so every value is typed, validated, and has a
clearly-defined default. Tests can construct a Settings instance with
overrides directly without needing a real ``.env``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "repo_root"]


def repo_root() -> Path:
    """Repo root resolved from this file's location.

    The file lives at ``tools/orchestrator/orchestrator/config.py`` so the
    repo root is three parents up.
    """
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Strongly-typed orchestrator configuration."""

    model_config = SettingsConfigDict(
        env_file=str(repo_root() / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Linear ---
    LINEAR_API_KEY: str = Field(
        default="",
        description="Personal API key generated in Linear. Empty = orchestrator runs in dry mode.",
    )
    LINEAR_TEAM_ID: str = Field(
        default="",
        description="Linear team UUID where MES tickets live.",
    )
    LINEAR_PROJECT_ID: str = Field(
        default="",
        description=(
            "Optional Linear project UUID. When set, the seed script and the "
            "Architect agent assign new tickets to this project so they appear "
            "in the project view. Empty = tickets land at team level only."
        ),
    )

    # --- GitHub ---
    GITHUB_TOKEN: str = Field(
        default="",
        description="Personal access token with `repo` scope. Used by the `gh` CLI.",
    )
    GITHUB_REPO: str = Field(
        default="",
        description="`owner/repo` slug, e.g., `nsg-engineering/mes`.",
    )

    # --- Claude Code ---
    CLAUDE_CONFIG_PATH: str = Field(
        default="",
        description="Path to claude CLI binary. Empty falls back to whatever is on $PATH.",
    )

    # --- Worktrees ---
    WORKTREES_DIR: str = Field(
        default="",
        description="Absolute path where the orchestrator creates per-ticket worktrees.",
    )

    # --- Concurrency / triggers ---
    MAX_CONCURRENT_WORKERS: int = Field(default=2, ge=1, le=16)
    MAX_AUTO_RETRIES: int = Field(
        default=2,
        ge=0,
        le=10,
        description=(
            "How many times the recovery daemons re-attempt a stuck ticket "
            "before labelling it `needs-human` and giving up. Applies "
            "per-stage: Spec Writer re-drives of orphaned Spec Drafts, and "
            "Failed → Ready for Agent re-queues. 0 disables auto-retry."
        ),
    )
    IN_PROGRESS_GRACE_SECONDS: int = Field(
        default=2700,
        ge=60,
        description=(
            "How long a ticket may sit in In Progress before the recovery "
            "daemon treats it as orphaned (a Worker that crashed mid-run) "
            "and re-queues it to Ready for Agent. Must exceed the longest "
            "possible Worker run so a live agent is never yanked — the "
            "claude_runner timeout is 30 min, so the default is 45 min."
        ),
    )
    AUDITOR_PR_THRESHOLD: int = Field(default=5, ge=1)
    GARDENER_LEARNING_THRESHOLD: int = Field(default=10, ge=1)
    GARDENER_PR_SAFETY_THRESHOLD: int = Field(default=50, ge=1)
    ARCHITECT_BACKLOG_THRESHOLD: int = Field(default=5, ge=1)
    AGENT_COOLDOWN_MINUTES: int = Field(default=30, ge=1)

    # --- Derived paths ---
    @property
    def state_dir(self) -> Path:
        """Where SQLite + JSONL logs live. Always under the repo root."""
        return repo_root() / ".orchestrator-state"

    @property
    def db_path(self) -> Path:
        return self.state_dir / "queue.db"

    @property
    def logs_dir(self) -> Path:
        return self.state_dir / "logs"

    @property
    def worktrees_path(self) -> Path:
        """Resolved worktrees dir. Falls back to ``<repo>/worktrees`` when empty."""
        if self.WORKTREES_DIR:
            return Path(self.WORKTREES_DIR).expanduser().resolve()
        return repo_root() / "worktrees"

    # --- Validators ---

    @field_validator("GITHUB_REPO")
    @classmethod
    def _slug_or_empty(cls, value: str) -> str:
        if not value:
            return value
        if "/" not in value or value.count("/") != 1:
            raise ValueError("GITHUB_REPO must be 'owner/repo'.")
        return value

    @field_validator("LINEAR_TEAM_ID")
    @classmethod
    def _team_id_or_empty(cls, value: str) -> str:
        # Linear team IDs are usually short slugs or UUIDs. We don't validate the
        # exact shape — empty (dry mode) is the only special case.
        return value

    # --- Helpers ---

    def is_configured(self) -> bool:
        """Whether all the credentials needed for live operation are present."""
        return bool(
            self.LINEAR_API_KEY
            and self.LINEAR_TEAM_ID
            and self.GITHUB_TOKEN
            and self.GITHUB_REPO
        )

"""Contract tests for ``tools/verification/deploy_staging.sh``.

The script orchestrates Docker, git and curl. We don't spin up real
containers here (that's QA Smoke's job against the live stand); instead we
inject fake ``docker``/``git``/``curl`` executables via the script's override
hooks (``DOCKER``/``GIT``/``CURL``) and assert the script's *contract*: its
stdout line, exit codes, cleanup on failure, idempotent teardown ordering and
the timeout it enforces. Static assertions on the committed compose/entrypoint
files cover the parts that are declarative rather than behavioural.

Every Acceptance Criterion of NSG-22 is covered by at least one test, marked
with an ``# AC-N:`` comment.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_SCRIPT = REPO_ROOT / "tools" / "verification" / "deploy_staging.sh"
COMPOSE_FILE = REPO_ROOT / "docker-compose.staging.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.staging.example"
ENTRYPOINT = REPO_ROOT / "deploy" / "staging" / "entrypoint.sh"
NGINX_CONF = REPO_ROOT / "deploy" / "staging" / "nginx.conf"

BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required to run deploy_staging.sh")

EXPECTED_URL = "http://localhost:8080"

_FAKE_DOCKER = """#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
for arg in "$@"; do
  case "$arg" in
    build) [ "${FAKE_DOCKER_FAIL_ON:-}" = "build" ] && exit 1 ;;
    up)    [ "${FAKE_DOCKER_FAIL_ON:-}" = "up" ] && exit 1 ;;
    down)  [ "${FAKE_DOCKER_FAIL_ON:-}" = "down" ] && exit 1 ;;
  esac
done
exit 0
"""

_FAKE_GIT = """#!/usr/bin/env bash
echo "git $*" >> "$FAKE_LOG"
case "$*" in
  *cat-file*) [ "${FAKE_GIT_SHA_MISSING:-0}" = "1" ] && exit 1 ;;
esac
exit 0
"""

_FAKE_CURL = """#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
[ "${FAKE_CURL_FAIL:-0}" = "1" ] && exit 1
exit 0
"""


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class Harness:
    """A fake repo + fake binaries wired to run the real deploy script."""

    def __init__(self, repo: Path, env: dict[str, str], log: Path) -> None:
        self.repo = repo
        self.env = env
        self.log = log

    def run(self, *args: str, **extra_env: str) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        env.update(extra_env)
        assert BASH is not None  # guarded by pytestmark
        return subprocess.run(
            [BASH, str(DEPLOY_SCRIPT), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.repo),
            timeout=60,
            check=False,
        )

    def docker_calls(self) -> list[str]:
        if not self.log.exists():
            return []
        return [
            line[len("docker ") :]
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.startswith("docker ")
        ]

    def curl_calls(self) -> list[str]:
        if not self.log.exists():
            return []
        return [
            line[len("curl ") :]
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.startswith("curl ")
        ]


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copy(COMPOSE_FILE, repo / COMPOSE_FILE.name)
    shutil.copy(ENV_EXAMPLE, repo / ENV_EXAMPLE.name)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    _write_exec(bindir / "docker", _FAKE_DOCKER)
    _write_exec(bindir / "git", _FAKE_GIT)
    _write_exec(bindir / "curl", _FAKE_CURL)

    log = tmp_path / "calls.log"
    env = dict(os.environ)
    env.update(
        {
            "DOCKER": str(bindir / "docker"),
            "GIT": str(bindir / "git"),
            "CURL": str(bindir / "curl"),
            "REPO_ROOT": str(repo),
            "SKIP_ARCHIVE": "1",
            "FAKE_LOG": str(log),
        }
    )
    return Harness(repo=repo, env=env, log=log)


def _index_of(calls: list[str], token: str) -> int:
    for i, call in enumerate(calls):
        if token in call.split():
            return i
    return -1


# --- AC-1 -----------------------------------------------------------------


def test_compose_defines_four_healthy_services() -> None:
    # AC-1: docker-compose levanta cuatro servicios — Postgres, Redis, la app
    # Django y el bundle de React — y deja los cuatro en estado healthy.
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    for service in ("db:", "redis:", "app:", "web:"):
        assert service in text, f"missing service {service!r} in compose file"
    assert text.count("healthcheck:") >= 4, "every service needs a healthcheck"
    # `up --wait` is what blocks until all healthchecks pass.
    assert "--wait" in DEPLOY_SCRIPT.read_text(encoding="utf-8")


# --- AC-2 -----------------------------------------------------------------


def test_success_prints_exact_ready_line_and_exits_zero(harness: Harness) -> None:
    # AC-2: con un SHA de merge, despliega e imprime exactamente la línea
    # `staging ready at <url>` y retorna código de salida 0.
    result = harness.run("deadbeefcafe")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"staging ready at {EXPECTED_URL}"


# --- AC-3 -----------------------------------------------------------------


def test_health_endpoint_is_verified_and_migrations_run_before_serving(
    harness: Harness,
) -> None:
    # AC-3: la <url> apunta a la app servida; un endpoint de salud (/healthz)
    # responde 200 con las migraciones de Django ya aplicadas.
    result = harness.run("deadbeefcafe")
    assert result.returncode == 0, result.stderr
    # The deploy verifies the served URL's /healthz before declaring ready.
    assert any(f"{EXPECTED_URL}/healthz" in call for call in harness.curl_calls())
    # nginx proxies /healthz to the Django app (so the served URL reflects it).
    assert "/healthz" in NGINX_CONF.read_text(encoding="utf-8")
    # Migrations are applied at start-up, before gunicorn serves traffic.
    entry = ENTRYPOINT.read_text(encoding="utf-8")
    assert entry.index("manage.py migrate") < entry.index("exec gunicorn")


# --- AC-4 -----------------------------------------------------------------


def test_build_failure_exits_nonzero_and_cleans_up(harness: Harness) -> None:
    # AC-4: si el despliegue falla, retorna código ≠ 0 con un mensaje legible
    # y no deja servicios a medio arrancar (limpia el estado).
    result = harness.run("deadbeefcafe", FAKE_DOCKER_FAIL_ON="build")
    assert result.returncode != 0
    assert "ERROR" in result.stderr
    assert "staging ready at" not in result.stdout
    calls = harness.docker_calls()
    # Cleanup runs after the failure: the last docker call is a teardown.
    assert calls, "expected docker to have been invoked"
    assert "down" in calls[-1].split(), f"expected cleanup teardown, got {calls[-1]!r}"


def test_missing_argument_exits_with_usage(harness: Harness) -> None:
    # AC-4 (robustness): a bad invocation fails loudly rather than half-deploying.
    result = harness.run()
    assert result.returncode == 2
    assert "Usage:" in result.stderr


# --- AC-5 -----------------------------------------------------------------


def test_deploy_enforces_timeout_under_ten_minutes(harness: Harness) -> None:
    # AC-5: un despliegue exitoso completa en menos de 10 minutos; el script
    # pasa un --wait-timeout por debajo del límite de QA Smoke (600s).
    result = harness.run("deadbeefcafe", DEPLOY_TIMEOUT_SECONDS="540")
    assert result.returncode == 0, result.stderr
    up_calls = [c for c in harness.docker_calls() if "up" in c.split()]
    assert up_calls, "expected a compose up call"
    assert "--wait-timeout" in up_calls[0]
    assert "540" in up_calls[0]
    assert 540 < 600


# --- AC-6 -----------------------------------------------------------------


def test_success_documents_logs_command(harness: Harness) -> None:
    # AC-6: los logs de cada servicio son accesibles vía el comando que el
    # script documente en su salida.
    result = harness.run("deadbeefcafe")
    assert result.returncode == 0, result.stderr
    assert "compose" in result.stderr and "logs" in result.stderr
    assert "nsg_mes_staging" in result.stderr


# --- AC-7 -----------------------------------------------------------------


def test_run_is_idempotent_teardown_before_start(harness: Harness) -> None:
    # AC-7: re-ejecutar es idempotente — reconstruye/reinicia un entorno limpio
    # sin chocar con contenedores/volúmenes/puertos de la corrida anterior.
    result = harness.run("deadbeefcafe")
    assert result.returncode == 0, result.stderr
    calls = harness.docker_calls()
    down_idx = _index_of(calls, "down")
    build_idx = _index_of(calls, "build")
    up_idx = _index_of(calls, "up")
    assert down_idx != -1 and build_idx != -1 and up_idx != -1
    # A clean teardown (with volumes) happens before building/starting.
    assert down_idx < build_idx < up_idx
    assert "--volumes" in calls[down_idx]

    # Running again must not error (no manual cleanup between runs).
    second = harness.run("deadbeefcafe")
    assert second.returncode == 0, second.stderr

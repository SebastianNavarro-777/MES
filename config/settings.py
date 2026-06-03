"""Minimal Django settings for the MES staging skeleton.

Scope is deliberately small: enough to build a deployable image, run
migrations, and answer ``/healthz``. It does **not** define any bounded
context — those arrive with later Stories under ``apps/``.

Configuration is read from the environment (12-factor) so the same image
runs in staging with values supplied by ``docker-compose.staging.yml`` /
``.env.staging``. No secrets are committed.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Core -----------------------------------------------------------------

# Staging uses a throwaway key supplied via the environment. Never a real
# production secret (see .env.staging.example).
SECRET_KEY = _env("DJANGO_SECRET_KEY", "insecure-staging-key-change-me")

DEBUG = _env_bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,app,web")

# nginx terminates HTTP in front of the app; trust its forwarded host/proto
# for the staging origin so CSRF checks pass behind the reverse proxy.
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:8080")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

# --- Database (Postgres in staging) ---------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _env("POSTGRES_DB", "mes_staging"),
        "USER": _env("POSTGRES_USER", "mes"),
        "PASSWORD": _env("POSTGRES_PASSWORD", "mes"),
        "HOST": _env("POSTGRES_HOST", "db"),
        "PORT": _env("POSTGRES_PORT", "5432"),
    }
}

# --- Event bus (Redis Streams) --------------------------------------------

# The event bus (ARCHITECTURE.md) is Redis Streams. No context publishes yet,
# but the connection string is wired so the stand mirrors later phases.
REDIS_URL = _env("REDIS_URL", "redis://redis:6379/0")

# --- I18N / TZ (GP-003: timezone-aware UTC) -------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files ---------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

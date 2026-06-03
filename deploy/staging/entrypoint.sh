#!/usr/bin/env bash
# Entrypoint for the staging Django app container.
#
# Order matters for AC-3 (health endpoint must report 200 only once the DB is
# reachable AND migrations are applied):
#   1. wait for Postgres to accept connections,
#   2. apply migrations,
#   3. hand off to gunicorn.
#
# `exec` replaces the shell so gunicorn receives signals (clean shutdown).

set -Eeuo pipefail

DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
APP_BIND="${APP_BIND:-0.0.0.0:8000}"
APP_WORKERS="${GUNICORN_WORKERS:-3}"

echo "entrypoint: waiting for Postgres at ${DB_HOST}:${DB_PORT} ..."
for attempt in $(seq 1 60); do
    if python -c "import socket,sys; s=socket.socket(); s.settimeout(1); \
sys.exit(0 if s.connect_ex(('${DB_HOST}', ${DB_PORT})) == 0 else 1)"; then
        echo "entrypoint: Postgres is reachable (attempt ${attempt})."
        break
    fi
    if [ "${attempt}" -eq 60 ]; then
        echo "entrypoint: Postgres never became reachable; aborting." >&2
        exit 1
    fi
    sleep 1
done

echo "entrypoint: applying database migrations ..."
python manage.py migrate --noinput

echo "entrypoint: starting gunicorn on ${APP_BIND} ..."
exec gunicorn config.wsgi:application \
    --bind "${APP_BIND}" \
    --workers "${APP_WORKERS}" \
    --access-logfile - \
    --error-logfile -

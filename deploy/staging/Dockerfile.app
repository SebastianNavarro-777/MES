# Staging image for the MES Django app (gunicorn).
# Built from a merge-SHA snapshot by tools/verification/deploy_staging.sh.
FROM python:3.12-slim

# GP-003: containers run in UTC so staging matches production behaviour.
ENV TZ=UTC \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# System deps: libpq for psycopg runtime. Build kept slim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching.
COPY deploy/staging/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Application code (minimal skeleton: project package + manage.py).
COPY manage.py /app/manage.py
COPY config /app/config

COPY deploy/staging/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

# Container-level health: the app is healthy only when /healthz returns 200,
# which requires DB connectivity + applied migrations.
HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=12 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]

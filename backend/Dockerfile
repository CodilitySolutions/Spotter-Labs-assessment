# syntax=docker/dockerfile:1

# ---------- base: Python + uv, non-root user ----------
FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app

# ---------- dev: all deps (incl. test/lint), source is bind-mounted ----------
FROM base AS dev

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen

COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---------- prod: runtime deps only, served by gunicorn ----------
FROM base AS prod

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev

COPY --chown=app:app . .
USER app
EXPOSE 8000
# One process, several threads: without Redis the cache lives in process memory, and a plan
# must be found by the heatmap request that follows it. Hosts (e.g. Render) set $PORT.
ENV WEB_CONCURRENCY=1 GUNICORN_THREADS=8
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY} --threads ${GUNICORN_THREADS} --timeout 60 --access-logfile -"]

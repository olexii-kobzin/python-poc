FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable

#   docker build -f cicd/docker/Dockerfile --target test -t statement:test .
#   docker run --rm --env-file .env.test --network backend statement:test
FROM builder AS test

ENV PATH="/app/.venv/bin:$PATH"

RUN uv sync --locked --no-editable

COPY tests ./tests
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

CMD ["pytest"]

FROM python:3.14-slim-trixie AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /app/.venv ./.venv
COPY --chown=appuser:appgroup alembic.ini ./alembic.ini
COPY --chown=appuser:appgroup migrations ./migrations

USER appuser

ENTRYPOINT []

Python PoC project.

Technologies used: uv, ruff, mypy, fastapi, faststream, sqlalchemy (postgresql), alembic, pgqueuer, docker.

PoC includes but not limited to: layered architecture (anemic domain), outbox, park-and-process, dlx, async retries with last attempt, versioning, ledger validation/verification, jwt/w permissions, complex cursor pagination, routers/w validation.

## Running locally

Three processes share one image: `api` (FastAPI), `consumers` (pgqueuer jobs and schedulers) and `subscribers` (RabbitMQ, via FastStream).

### Prerequisites

- Docker with compose.
- An **external docker network named `backend`** with PostgreSQL and RabbitMQ already running on it. `compose.yaml` does not start them. Create the network with `docker network create backend` if it does not exist.
- A `.env` file: `cp .env.example .env` and fill in the values. `Settings` reads the real environment only, so the processes must be started through compose (which loads `.env`).

### First start

```sh
docker compose build
# pgqueuer owns its own tables; alembic does not create them
docker compose run --rm api pgq install
docker compose run --rm api alembic upgrade head
docker compose up
```

The API is on `http://localhost:8000` (OpenAPI at `/docs`). Health: `/livez` (process only) and `/readyz` (also checks Postgres).

Migrations are manual on purpose: the database is shared between services, so no single service's deploy migrates it. Keep migrations backward compatible.

### Local auth

With `APP_ENV=local` and `JWT_LOCAL_PRIVATE_KEY` set, mint a dev token (admin role by default):

```sh
docker compose run --rm api statement-token
```

`JWT_LOCAL_PRIVATE_KEY` is refused outside `APP_ENV=local`, and `JWT_AUDIENCE` is required in `dev` and `prod`.

## Checks

```sh
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

### Tests

Tests need the same Postgres and RabbitMQ, with migrations applied. Use a separate database, configured in `.env.test`:

```sh
docker build -f cicd/docker/Dockerfile --target test -t statement:test .
docker run --rm --env-file .env.test --network backend statement:test
```

Add `--cov` to the pytest run for a coverage report (`pytest --cov`).

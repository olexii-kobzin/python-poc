from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Protocol
from unittest.mock import AsyncMock

import anyio
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from faststream.rabbit import RabbitBroker, TestRabbitBroker
from httpx import ASGITransport, AsyncClient
from pgqueuer import PgQueuer
from pgqueuer.models import Context, Job, Schedule, ScheduleContext
from pgqueuer.types import JobId, ScheduleId
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from statement import deps, fast_deps
from statement.app.consumers.entrypoints.main import register_entrypoints
from statement.app.consumers.schedulers.main import register_jobs
from statement.conf import settings
from statement.db import VersionedSession
from statement.infra.auth import TokenVerifier
from statement.main import app
from tests.utils.auth import TEST_ISSUER, AuthHeaders, TokenTestVerifier, make_token


class RunEntrypoint(Protocol):
    def __call__(
        self,
        entrypoint: str,
        payload: bytes | None,
        *,
        attempts: int = 0,
    ) -> Awaitable[None]: ...


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def rsa_private_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def token_verifier(rsa_private_key: RSAPrivateKey) -> TokenVerifier:
    return TokenTestVerifier(
        public_key=rsa_private_key.public_key(),
        trusted_issuers={TEST_ISSUER: ["statement."]},
    )


@pytest.fixture
def auth_headers(rsa_private_key: RSAPrivateKey) -> AuthHeaders:
    def _make(scopes: Sequence[str], sub: str | None = None) -> dict[str, str]:
        token = make_token(rsa_private_key, scopes=scopes, sub=sub)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
# TestRabbitBroker is only the patching context manager; entering it
# yields the passed-in RabbitBroker itself, patched for in-memory delivery
async def broker() -> AsyncIterator[RabbitBroker]:
    real_broker = deps.get_broker()
    original_publish = real_broker.publish
    real_broker.publish = AsyncMock()  # type: ignore[method-assign]

    try:
        async with TestRabbitBroker(real_broker) as test_broker:
            yield test_broker
    finally:
        real_broker.publish = original_publish  # type: ignore[method-assign]


@pytest.fixture(scope="session")
def db_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_async_url,
        echo=False,
        poolclass=NullPool,
    )


@pytest.fixture
async def session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as connection:
        outer_tx = await connection.begin()

        factory = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            sync_session_class=VersionedSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        session = factory()
        try:
            yield session
        finally:
            await session.close()
            await outer_tx.rollback()


@pytest.fixture
async def pg_queuer(
    session: AsyncSession,
    broker: RabbitBroker,
) -> AsyncIterator[PgQueuer]:
    @asynccontextmanager
    async def session_scope() -> AsyncIterator[AsyncSession]:
        yield session

    pgq = PgQueuer.in_memory(
        resources={"session_scope": session_scope, "broker": broker},
    )
    register_entrypoints(pgq)
    register_jobs(pgq)
    yield pgq


@pytest.fixture
async def run_entrypoint(pg_queuer: PgQueuer) -> RunEntrypoint:
    async def _run(
        entrypoint: str,
        payload: bytes | None,
        *,
        attempts: int = 0,
    ) -> None:
        executor = pg_queuer.qm.entrypoint_registry.get(entrypoint)
        if executor is None:
            raise AssertionError(f"no entrypoint registered for {entrypoint!r}")

        now = datetime.now(UTC)
        job = Job(
            id=JobId(1),
            priority=0,
            created=now,
            updated=now,
            heartbeat=now,
            execute_after=now,
            status="picked",
            entrypoint=entrypoint,
            payload=payload,
            attempts=attempts,
            queue_manager_id=None,
            headers=None,
        )

        await executor.execute(
            job,
            Context(
                cancellation=anyio.CancelScope(),
                resources=pg_queuer.qm.resources,
            ),
        )

    return _run


@pytest.fixture
async def run_schedule(pg_queuer: PgQueuer) -> Callable[[str], Awaitable[None]]:
    async def _run(entrypoint: str) -> None:
        for key, executor in pg_queuer.sm.registry.items():
            if key.entrypoint != entrypoint:
                continue

            now = datetime.now(UTC)
            await executor.execute(
                Schedule(
                    id=ScheduleId(1),
                    expression=key.expression,
                    entrypoint=key.entrypoint,
                    heartbeat=now,
                    created=now,
                    updated=now,
                    next_run=now,
                    last_run=None,
                    status="picked",
                ),
                ScheduleContext(resources=pg_queuer.sm.resources),
            )
            return

        raise AssertionError(f"no schedule registered for {entrypoint!r}")

    return _run


@pytest.fixture
async def client(
    session: AsyncSession,
    token_verifier: TokenVerifier,
) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield session

    def override_get_token_verifier() -> TokenVerifier:
        return token_verifier

    app.dependency_overrides[fast_deps.get_session] = override_get_session
    app.dependency_overrides[fast_deps.get_token_verifier] = override_get_token_verifier

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(fast_deps.get_session, None)
        app.dependency_overrides.pop(fast_deps.get_token_verifier, None)

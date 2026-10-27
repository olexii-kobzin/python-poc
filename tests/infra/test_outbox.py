from uuid import uuid7

import pytest
import sqlalchemy as sa
from pgqueuer.domain.settings import DBSettings
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from statement import deps

pytestmark = pytest.mark.anyio

QUEUE_TABLE = DBSettings().queue_table


async def count_jobs(connection: AsyncConnection, entrypoint: str) -> int:
    result = await connection.execute(
        sa.text(f"SELECT count(*) FROM {QUEUE_TABLE} WHERE entrypoint = :entrypoint"),
        {"entrypoint": entrypoint},
    )
    return int(result.scalar_one())


async def test_enqueue_is_rolled_back_with_the_session_transaction(
    db_engine: AsyncEngine,
) -> None:
    """The outbox guarantee: ``enqueue`` rides the SQLAlchemy transaction.

    ``deps.make_queries`` hands pgqueuer the session's own asyncpg connection.
    If that ever stops being true, the job is written on a separate connection,
    survives the rollback, and an event is published for a write that never
    happened.
    """
    entrypoint = f"test_outbox_{uuid7()}"

    async with (db_engine.connect() as connection,
                AsyncSession(bind=connection) as session):
        tx = await session.begin()
        await session.execute(sa.text("SELECT 1"))
        queries = await deps.make_job_queries(await session.connection())
        await queries.enqueue(entrypoint, b"{}")

        # control: the job is visible inside the transaction, so the
        # assertion below cannot pass just because enqueue did nothing
        assert await count_jobs(await session.connection(), entrypoint) == 1

        await tx.rollback()

    async with db_engine.connect() as other:
        assert await count_jobs(other, entrypoint) == 0

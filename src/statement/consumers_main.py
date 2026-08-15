from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from pgqueuer import PgQueuer

from statement import deps
from statement.app.consumers.entrypoints.main import register_entrypoints
from statement.app.consumers.schedulers.main import register_jobs
from statement.conf import settings
from statement.db import Session
from statement.infra.observability import setup_logging

setup_logging("statement-consumers")


@asynccontextmanager
async def main() -> AsyncIterator[PgQueuer]:
    broker = deps.get_broker()

    resources = {
        "session_scope": Session,
        "broker": broker,
    }

    connection = await asyncpg.connect(dsn=settings.database_pgq_url)
    pgq = PgQueuer.from_asyncpg_connection(connection, resources=resources)

    register_entrypoints(pgq)
    register_jobs(pgq)

    try:
        await broker.start()
        yield pgq
    finally:
        await broker.stop()
        await connection.close()

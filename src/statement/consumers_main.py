from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from pgqueuer import PgQueuer

from statement import deps
from statement.app.consumers.entrypoints.main import register_entrypoints
from statement.app.consumers.schedulers.main import register_jobs
from statement.conf import settings
from statement.db import Session, sa_engine
from statement.infra.heartbeat import start_heartbeat, stop_heartbeat
from statement.infra.observability import setup_logging

setup_logging("statement-consumers")

HEARTBEAT_FILE = Path("/tmp/consumers.alive")


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

    heartbeat = None
    try:
        await broker.start()
        heartbeat = start_heartbeat(HEARTBEAT_FILE, broker)
        yield pgq
    finally:
        if heartbeat is not None:
            await stop_heartbeat(heartbeat)
        await broker.stop()
        await connection.close()
        await sa_engine.dispose()

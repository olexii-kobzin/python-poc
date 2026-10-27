import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog
from faststream.rabbit import RabbitBroker
from sqlalchemy import text

from statement.db import Session

logger = structlog.get_logger()

AMQP_PING_TIMEOUT_SECONDS = 2


async def check_dependencies(broker: RabbitBroker) -> None:
    async with Session() as session:
        await session.execute(text("SELECT 1"))

    if not await broker.ping(AMQP_PING_TIMEOUT_SECONDS):
        raise RuntimeError("amqp unavailable")


async def run_heartbeat(
    path: Path,
    check: Callable[[], Awaitable[object]],
    interval: float,
) -> None:
    while True:
        try:
            await check()
            path.touch()
        except Exception:
            logger.exception("heartbeat_check_failed", path=str(path))

        await asyncio.sleep(interval)


def start_heartbeat(
    path: Path,
    broker: RabbitBroker,
    interval: float = 10,
) -> asyncio.Task[None]:
    return asyncio.create_task(
        run_heartbeat(path, lambda: check_dependencies(broker), interval)
    )


async def stop_heartbeat(task: asyncio.Task[None]) -> None:
    task.cancel()
    #  the same as try: await task / except asyncio.CancelledError: pass
    with contextlib.suppress(asyncio.CancelledError):
        await task

import asyncio
from pathlib import Path

from faststream import FastStream

from statement.app.subscribers import main
from statement.app.subscribers.base import (
    build_broker,
    commands_dlx,
    commands_exchange,
    events_dlx,
    events_exchange,
)
from statement.db import sa_engine
from statement.infra.heartbeat import start_heartbeat, stop_heartbeat
from statement.infra.observability import setup_logging

setup_logging("statement-subscribers")

HEARTBEAT_FILE = Path("/tmp/subscribers.alive")

broker = build_broker()
broker.include_router(main.router)

app = FastStream(broker)

heartbeat: asyncio.Task[None] | None = None


@app.after_startup
async def after_startup_hook() -> None:
    global heartbeat

    await broker.declare_exchange(commands_exchange)
    await broker.declare_exchange(commands_dlx)
    await broker.declare_exchange(events_exchange)
    await broker.declare_exchange(events_dlx)

    heartbeat = start_heartbeat(HEARTBEAT_FILE, broker)


@app.on_shutdown
async def before_shutdown_hook() -> None:
    if heartbeat is not None:
        await stop_heartbeat(heartbeat)

    await sa_engine.dispose()

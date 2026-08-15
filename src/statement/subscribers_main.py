from faststream import FastStream

from statement.app.subscribers import main
from statement.app.subscribers.base import (
    build_broker,
    commands_dlx,
    commands_exchange,
    events_dlx,
    events_exchange,
)
from statement.infra.observability import setup_logging

setup_logging("statement-subscribers")

broker = build_broker()
broker.include_router(main.router)

app = FastStream(broker)


@app.after_startup
async def after_startup_hook():
    await broker.declare_exchange(commands_exchange)
    await broker.declare_exchange(commands_dlx)
    await broker.declare_exchange(events_exchange)
    await broker.declare_exchange(events_dlx)

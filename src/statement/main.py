from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from structlog.contextvars import bind_contextvars, clear_contextvars

from statement.app.routers.admin import account
from statement.db import sa_engine
from statement.infra.observability import setup_logging

setup_logging("statement-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("statement-api")  # re-apply after uvicorn boots
    try:
        yield
    finally:
        await sa_engine.dispose()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def logging_ctx(request: Request, call_next):
    clear_contextvars()
    bind_contextvars(request_id=request.headers.get("x-request-id"))
    return await call_next(request)


app.include_router(account.router)

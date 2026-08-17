from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError
from structlog.contextvars import bind_contextvars, clear_contextvars

from statement.app.routers.admin import account
from statement.db import sa_engine
from statement.infra.observability import setup_logging

setup_logging("statement-api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging("statement-api")  # re-apply after uvicorn boots
    try:
        yield
    finally:
        await sa_engine.dispose()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def logging_ctx(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    clear_contextvars()
    bind_contextvars(request_id=request.headers.get("x-request-id"))
    return await call_next(request)


@app.exception_handler(StaleDataError)
async def stale_data_conflict(request: Request, exc: StaleDataError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Resource was modified concurrently; reload and retry"},
    )


app.include_router(account.router)

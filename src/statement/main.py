from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError
from structlog.contextvars import bind_contextvars, clear_contextvars

from statement.app.routers.admin import account
from statement.app.routers.system import health
from statement.db import sa_engine
from statement.infra.observability import setup_logging
from statement.infra.request_id import REQUEST_ID_HEADER, resolve_request_id

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

    request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))

    bind_contextvars(request_id=request_id)

    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id

    return response


@app.exception_handler(StaleDataError)
async def stale_data_conflict(request: Request, exc: StaleDataError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Resource was modified concurrently; reload and retry"},
    )


app.include_router(account.router)
app.include_router(health.router)

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from fastapi import status
from httpx import AsyncClient

from statement import fast_deps
from statement.app.routers.system import health
from statement.main import app


class BrokenSession:
    def __init__(self, error: Callable[[], Exception]) -> None:
        self._error = error

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        raise self._error()


class HangingSession:
    async def execute(self, *args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(10)


def override_session(session: object) -> None:
    async def _get_session() -> AsyncIterator[object]:
        yield session

    app.dependency_overrides[fast_deps.get_session] = _get_session


@pytest.mark.anyio
async def test_livez_does_not_touch_the_database(client: AsyncClient) -> None:
    override_session(BrokenSession(lambda: RuntimeError("db is down")))

    response = await client.get("/livez")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_readyz_ok_when_database_answers(client: AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        lambda: ConnectionRefusedError("refused"),
        lambda: RuntimeError("anything"),
    ],
)
async def test_readyz_503_on_any_database_error(
    client: AsyncClient,
    error: Callable[[], Exception],
) -> None:
    override_session(BrokenSession(error))

    response = await client.get("/readyz")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"detail": "database unavailable"}


@pytest.mark.anyio
async def test_readyz_503_when_database_hangs(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health, "READY_TIMEOUT_SECONDS", 0.01)
    override_session(HangingSession())

    response = await client.get("/readyz")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

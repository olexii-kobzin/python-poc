import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from statement.infra.request_id import REQUEST_ID_HEADER
from statement.main import app


def make_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_incoming_request_id_is_returned() -> None:
    raw = str(uuid.uuid7())

    async with make_client() as client:
        response = await client.get("/livez", headers={REQUEST_ID_HEADER: raw})

    assert response.headers[REQUEST_ID_HEADER] == raw


@pytest.mark.anyio
async def test_missing_request_id_is_generated() -> None:
    async with make_client() as client:
        response = await client.get("/livez")

    generated = response.headers[REQUEST_ID_HEADER]
    assert str(uuid.UUID(generated)) == generated


@pytest.mark.anyio
async def test_invalid_request_id_is_replaced() -> None:
    async with make_client() as client:
        response = await client.get("/livez", headers={REQUEST_ID_HEADER: "bad id"})

    returned = response.headers[REQUEST_ID_HEADER]
    assert returned != "bad id"
    assert str(uuid.UUID(returned)) == returned

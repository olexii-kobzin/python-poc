import json
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.orm.exc import StaleDataError
from starlette.requests import Request

from statement.infra.request_id import REQUEST_ID_HEADER
from statement.main import stale_data_conflict


@pytest.mark.anyio
async def test_stale_data_error_becomes_a_409() -> None:
    request = Request({"type": "http", "method": "PATCH", "path": "/", "headers": []})

    response = await stale_data_conflict(request, StaleDataError("row changed"))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert json.loads(bytes(response.body)) == {
        "detail": "Resource was modified concurrently; reload and retry"
    }


@pytest.mark.anyio
async def test_response_carries_a_generated_request_id(client: AsyncClient) -> None:
    response = await client.get("/livez")

    assert str(uuid.UUID(response.headers[REQUEST_ID_HEADER]))


@pytest.mark.anyio
async def test_response_echoes_a_valid_incoming_request_id(
    client: AsyncClient,
) -> None:
    incoming = str(uuid.uuid7())

    response = await client.get("/livez", headers={REQUEST_ID_HEADER: incoming})

    assert response.headers[REQUEST_ID_HEADER] == incoming


@pytest.mark.anyio
async def test_invalid_incoming_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/livez", headers={REQUEST_ID_HEADER: "not-a-uuid"})

    returned = response.headers[REQUEST_ID_HEADER]
    assert returned != "not-a-uuid"
    assert str(uuid.UUID(returned))

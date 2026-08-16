from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from statement.app.permissions import Permission
from statement.domain.entities.account import CustomerAccount, CustomerAccountStatus
from statement.domain.entities.customer import Customer
from statement.domain.enum import Currency
from tests.utils.auth import AuthHeaders

BASE_TIME = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


async def add_accounts(
    session: AsyncSession,
    specs: list[dict[str, Any]],
) -> tuple[str, list[CustomerAccount]]:
    now = datetime.now(UTC)
    customer = Customer(
        id=uuid7(),
        email=f"{uuid7()}@mail.com",
        name="customer",
        created_at=now,
        updated_at=now,
    )
    session.add(customer)

    token = uuid7().hex[:8]
    accounts: list[CustomerAccount] = []
    for index, spec in enumerate(specs):
        account = CustomerAccount(
            id=uuid7(),
            customer_id=customer.id,
            currency=spec.get("currency", "EUR"),
            name=f"{token}-{spec.get('name', index)}",
            status=spec.get("status", CustomerAccountStatus.ACTIVE),
            created_at=spec.get("created_at", BASE_TIME + timedelta(minutes=index)),
            updated_at=now,
            updated_by=uuid7(),
        )
        accounts.append(account)
        session.add(account)

    await session.flush()

    return token, accounts


async def list_accounts(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    **params: Any,
) -> dict[str, Any]:
    response = await client.get(
        "/v1/accounts",
        params=params,
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_GET]),
    )
    assert response.status_code == status.HTTP_200_OK, response.text

    payload: dict[str, Any] = response.json()
    return payload


def ids_of(payload: dict[str, Any]) -> list[UUID]:
    return [UUID(row["id"]) for row in payload["data"]]


@pytest.mark.anyio
async def test_list_sorts_by_created_at_desc(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    token, accounts = await add_accounts(
        session,
        [
            {
                "currency": "EUR",
            },
            {
                "currency": "USD",
            },
            {
                "currency": "GBP",
            },
        ],
    )

    payload = await list_accounts(
        client,
        auth_headers,
        sort="created_at:desc",
        name=token,
    )

    assert ids_of(payload) == [a.id for a in reversed(accounts)]

    account = accounts[2]
    row = payload["data"][0]
    assert row == {
        "id": str(account.id),
        "customer_id": str(account.customer_id),
        "currency": "GBP",
        "name": account.name,
        "status": CustomerAccountStatus.ACTIVE.value,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat(),
        "updated_by": str(account.updated_by),
    }


@pytest.mark.anyio
async def test_list_not_requires_sort(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    response = await client.get(
        "/v1/accounts",
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_GET]),
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.anyio
async def test_list_rejects_malformed_sort(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    response = await client.get(
        "/v1/accounts",
        params={"sort": "created_at"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_GET]),
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.anyio
async def test_list_sorts_by_created_at_asc(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    token, accounts = await add_accounts(
        session,
        [
            {
                "currency": "EUR",
            },
            {
                "currency": "USD",
            },
            {
                "currency": "GBP",
            },
        ],
    )

    payload = await list_accounts(
        client,
        auth_headers,
        sort="created_at:asc",
        name=token,
    )

    assert ids_of(payload) == [a.id for a in accounts]


@pytest.mark.anyio
async def test_list_sorts_by_currency(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    token, accounts = await add_accounts(
        session,
        [
            {"currency": "EUR"},
            {"currency": "USD"},
            {"currency": "GBP"},
        ],
    )
    eur, usd, gbp = accounts

    payload = await list_accounts(
        client,
        auth_headers,
        sort="currency:asc",
        name=token,
    )

    assert ids_of(payload) == [eur.id, gbp.id, usd.id]


@pytest.mark.anyio
async def test_list_pages_through_with_cursor(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    token, accounts = await add_accounts(
        session,
        [
            {
                "currency": "EUR",
            },
            {
                "currency": "USD",
            },
            {
                "currency": "GBP",
            },
            {
                "currency": "UAH",
            },
            {
                "currency": "JPY",
            },
        ],
    )
    expected = [a.id for a in reversed(accounts)]

    first = await list_accounts(
        client,
        auth_headers,
        sort="created_at:desc",
        name=token,
        count=2,
    )
    assert ids_of(first) == expected[:2]
    assert first["meta"]["next_cursor"] is not None

    second = await list_accounts(
        client,
        auth_headers,
        sort="created_at:desc",
        name=token,
        count=2,
        cursor=first["meta"]["next_cursor"],
    )
    assert ids_of(second) == expected[2:4]

    third = await list_accounts(
        client,
        auth_headers,
        sort="created_at:desc",
        name=token,
        count=2,
        cursor=second["meta"]["next_cursor"],
    )
    assert ids_of(third) == expected[4:]
    # a short page means there is nothing left to hand back
    assert third["meta"]["next_cursor"] is None


@pytest.mark.anyio
async def test_list_rejects_garbage_cursor(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    response = await client.get(
        "/v1/accounts",
        params={"sort": "created_at:desc", "cursor": "not-base64"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_GET]),
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.anyio
async def test_list_filters_by_currency(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    token, accounts = await add_accounts(
        session,
        [{"currency": "USD"}, {"currency": "EUR"}],
    )
    usd, _ = accounts

    payload = await list_accounts(
        client,
        auth_headers,
        sort="created_at:desc",
        name=token,
        currency="USD",
    )

    assert ids_of(payload) == [usd.id]


@pytest.mark.anyio
async def test_list_filters_by_status(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    token, accounts = await add_accounts(
        session,
        [
            {
                "currency": Currency.JPY,
                "status": CustomerAccountStatus.DISABLED,
            },
            {
                "currency": Currency.EUR,
                "status": CustomerAccountStatus.ACTIVE,
            },
        ],
    )
    disabled, _ = accounts

    payload = await list_accounts(
        client,
        auth_headers,
        sort="created_at:desc",
        name=token,
        status=CustomerAccountStatus.DISABLED,
    )

    assert ids_of(payload) == [disabled.id]


@pytest.mark.anyio
async def test_list_filters_by_name_substring(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    token, accounts = await add_accounts(
        session,
        [
            {
                "currency": Currency.EUR,
                "name": "savings",
            },
            {
                "currency": Currency.USD,
                "name": "current",
            },
        ],
    )
    savings, _ = accounts

    payload = await list_accounts(
        client,
        auth_headers,
        sort="created_at:desc",
        name=f"{token}-sav",
    )

    assert ids_of(payload) == [savings.id]


@pytest.mark.anyio
async def test_list_filters_by_created_at_range(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    token, accounts = await add_accounts(
        session,
        [
            {
                "currency": Currency.EUR,
            },
            {
                "currency": Currency.USD,
            },
            {
                "currency": Currency.GBP,
            },
        ],
    )
    first, second, third = accounts

    payload = await list_accounts(
        client,
        auth_headers,
        sort="created_at:asc",
        name=token,
        created_at_from=first.created_at.isoformat(),
        created_at_to=third.created_at.isoformat(),
    )

    assert ids_of(payload) == [first.id, second.id]


@pytest.mark.anyio
async def test_list_without_token(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    response = await client.get("/v1/accounts", params={"sort": "created_at:desc"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_list_without_permission(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    response = await client.get(
        "/v1/accounts",
        params={"sort": "created_at:desc"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_CREATE]),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

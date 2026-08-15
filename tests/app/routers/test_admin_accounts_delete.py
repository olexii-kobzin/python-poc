from datetime import UTC, datetime
from uuid import uuid7

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from statement.app.permissions import Permission
from statement.domain.entities.account import CustomerAccount, CustomerAccountStatus
from statement.domain.entities.customer import Customer
from tests.utils.auth import AuthHeaders
from tests.utils.db import DbTestUtil


async def add_account(session: AsyncSession) -> CustomerAccount:
    now = datetime.now(UTC)
    customer = Customer(
        id=uuid7(),
        email=f"{uuid7()}@mail.com",
        name="customer",
        created_at=now,
        updated_at=now,
    )
    account = CustomerAccount(
        id=uuid7(),
        customer_id=customer.id,
        currency="EUR",
        name="main",
        status=CustomerAccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        updated_by=uuid7(),
    )
    session.add_all([customer, account])
    await session.flush()

    return account


@pytest.mark.anyio
async def test_delete_flips_status_to_deleted(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account(session)

    sub = uuid7()
    response = await client.delete(
        f"/v1/accounts/{account.id}",
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_DELETE], str(sub)),
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {
            "id": account.id,
            "status": CustomerAccountStatus.DELETED,
            "updated_by": str(sub),
        },
    )


@pytest.mark.anyio
async def test_delete_unknown_account(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    response = await client.delete(
        f"/accounts/{uuid7()}",
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_DELETE]),
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_delete_without_token(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    account = await add_account(session)

    response = await client.delete(f"/v1/accounts/{account.id}")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {"id": account.id, "status": CustomerAccountStatus.ACTIVE},
    )


@pytest.mark.anyio
async def test_delete_without_permission(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account(session)

    response = await client.delete(
        f"/v1/accounts/{account.id}",
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {"id": account.id, "status": CustomerAccountStatus.ACTIVE},
    )

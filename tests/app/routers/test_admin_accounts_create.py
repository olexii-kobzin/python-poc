from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid7

import pytest
import sqlalchemy as sa
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from statement.app.permissions import Permission
from statement.domain.entities.account import (
    CustomerAccount,
    CustomerAccountLedger,
    LedgerOperationType,
)
from statement.domain.entities.customer import Customer
from tests.utils.auth import AuthHeaders
from tests.utils.db import DbTestUtil


async def add_customer(session: AsyncSession) -> Customer:
    customer = Customer(
        id=uuid7(),
        email="customer1@mail.com",
        name="customer1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(customer)
    await session.flush()

    return customer


async def add_account(
    session: AsyncSession, customer: Customer
) -> CustomerAccount:
    account = CustomerAccount(
        id=uuid7(),
        customer_id=customer.id,
        currency="EUR",
        name="main",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        updated_by=uuid7(),
    )
    session.add(account)
    await session.flush()

    return account


@pytest.mark.anyio
async def test_create_account_with_permission(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    customer = await add_customer(session)

    response = await client.post(
        "/v1/accounts",
        json={
            "customer_id": str(customer.id),
            "currency": "EUR",
            "name": "main",
        },
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_CREATE]),
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {
            "customer_id": customer.id,
            "currency": "EUR",
            "name": "main",
        },
    )

    # the account creates with a zero row, so no 1 always exists to chain onto
    account_id = (
        await session.execute(
            sa.select(CustomerAccount.id).where(
                CustomerAccount.customer_id == customer.id
            )
        )
    ).scalar_one()

    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedger.__tablename__,
        {
            "account_id": str(account_id),
            "no": 1,
            "amount": Decimal("0.00"),
            "balance": Decimal("0.00"),
            "operation_type": LedgerOperationType.CREATE,
        }
    )

@pytest.mark.anyio
async def test_create_account_without_token(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    customer_id = uuid7()

    response = await client.post(
        "/v1/accounts",
        json={"customer_id": str(customer_id), "currency": "EUR", "name": "main"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert await DbTestUtil.missing(
        session,
        CustomerAccount.__tablename__,
        {
            "customer_id": customer_id,
        },
    )


@pytest.mark.anyio
async def test_create_account_with_garbage_token(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    customer_id = uuid7()

    response = await client.post(
        "/v1/accounts",
        json={"customer_id": str(customer_id), "currency": "EUR", "name": "main"},
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await DbTestUtil.missing(
        session,
        CustomerAccount.__tablename__,
        {
            "customer_id": customer_id,
        },
    )


@pytest.mark.anyio
async def test_create_account_without_permission(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    customer_id = uuid7()

    response = await client.post(
        "/v1/accounts",
        json={"customer_id": str(customer_id), "currency": "EUR", "name": "main"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert await DbTestUtil.missing(
        session,
        CustomerAccount.__tablename__,
        {
            "customer_id": customer_id,
        },
    )

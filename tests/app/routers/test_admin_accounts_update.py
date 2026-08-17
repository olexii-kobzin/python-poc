from datetime import UTC, datetime
from uuid import uuid7

import pytest
import sqlalchemy as sa
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from statement.app import version_token
from statement.app.permissions import Permission
from statement.domain.entities.account import CustomerAccount, CustomerAccountStatus
from statement.domain.entities.customer import Customer
from tests.utils.auth import AuthHeaders
from tests.utils.db import DbTestUtil


async def set_up_customer(session: AsyncSession) -> Customer:
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


async def set_up_account(
    session: AsyncSession,
    customer: Customer,
    status: CustomerAccountStatus = CustomerAccountStatus.ACTIVE,
) -> CustomerAccount:
    account = CustomerAccount(
        id=uuid7(),
        customer_id=customer.id,
        currency="EUR",
        name="main",
        status=status,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        updated_by=uuid7(),
    )
    session.add(account)
    await session.flush()

    return account


def current_version(account: CustomerAccount) -> str:
    """The token a client would have received from a read of this account."""
    return version_token.issue(account.id, account.version)


@pytest.mark.anyio
async def test_update_account_with_permission(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    customer = await set_up_customer(session)
    account = await set_up_account(session, customer)

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={"version": current_version(account), "name": "renamed"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {
            "id": account.id,
            "name": "renamed",
            "status": account.status,
        },
    )


@pytest.mark.anyio
async def test_update_account_deactivates(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    customer = await set_up_customer(session)
    account = await set_up_account(session, customer)

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={
            "version": current_version(account),
            "status": CustomerAccountStatus.DISABLED,
        },
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {
            "id": account.id,
            "name": account.name,
            "status": CustomerAccountStatus.DISABLED,
        },
    )


@pytest.mark.anyio
async def test_update_account_reactivates(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    customer = await set_up_customer(session)
    account = await set_up_account(
        session,
        customer,
        status=CustomerAccountStatus.DISABLED,
    )

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={
            "version": current_version(account),
            "status": CustomerAccountStatus.ACTIVE,
        },
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {
            "id": account.id,
            "name": account.name,
            "status": CustomerAccountStatus.ACTIVE,
        },
    )


@pytest.mark.anyio
async def test_update_account_without_status_leaves_it_alone(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    """Omitting status must not silently reactivate a disabled account."""
    customer = await set_up_customer(session)
    account = await set_up_account(
        session,
        customer,
        status=CustomerAccountStatus.DISABLED,
    )

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={"version": current_version(account), "name": "renamed"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {
            "id": account.id,
            "name": "renamed",
            "status": CustomerAccountStatus.DISABLED,
        },
    )


@pytest.mark.anyio
async def test_update_account_cannot_set_deleted(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    """Deleting has its own route; the schema must not accept it here."""
    customer = await set_up_customer(session)
    account = await set_up_account(session, customer)

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={
            "version": current_version(account),
            "name": "main",
            "status": CustomerAccountStatus.DELETED,
        },
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {"id": account.id, "status": CustomerAccountStatus.ACTIVE},
    )


@pytest.mark.anyio
async def test_update_deleted_account_is_rejected(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    """Without this, a status update would resurrect a deleted account."""
    customer = await set_up_customer(session)
    account = await set_up_account(
        session,
        customer,
        status=CustomerAccountStatus.DELETED,
    )

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={
            "version": current_version(account),
            "name": "renamed",
            "status": CustomerAccountStatus.ACTIVE,
        },
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {
            "id": account.id,
            "name": "main",
            "status": CustomerAccountStatus.DELETED,
        },
    )


@pytest.mark.anyio
async def test_update_account_not_found(
    client: AsyncClient,
    auth_headers: AuthHeaders,
) -> None:
    response = await client.patch(
        f"/v1/accounts/{uuid7()}",
        json={"version": version_token.issue(uuid7(), 1), "name": "renamed"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_update_account_with_stale_version_is_rejected(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    """Admin A holds a token from before admin B's write."""
    customer = await set_up_customer(session)
    account = await set_up_account(session, customer)
    stale = version_token.issue(account.id, account.version - 1)

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={"version": stale, "name": "renamed"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {"id": account.id, "name": "main"},
    )


@pytest.mark.anyio
async def test_update_account_loses_race_after_version_check(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    """
    Simulates a writer committing between the handler's read and its commit by
    moving the row forward underneath the loaded instance
    """
    customer = await set_up_customer(session)
    account = await set_up_account(session, customer)
    token = current_version(account)

    await session.execute(
        sa.text(
            "UPDATE customer_account SET version = version + 1 WHERE id = :id",
        ),
        {"id": account.id},
    )

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={"version": token, "name": "renamed"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_UPDATE]),
    )

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.anyio
async def test_update_account_without_token(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    customer = await set_up_customer(session)
    account = await set_up_account(session, customer)

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={"version": current_version(account), "name": "renamed"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {
            "id": account.id,
            "name": "main",
        },
    )


@pytest.mark.anyio
async def test_update_account_without_permission(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    customer = await set_up_customer(session)
    account = await set_up_account(session, customer)

    response = await client.patch(
        f"/v1/accounts/{account.id}",
        json={"version": current_version(account), "name": "renamed"},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_CREATE]),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert await DbTestUtil.exists(
        session,
        CustomerAccount.__tablename__,
        {
            "id": account.id,
            "name": "main",
        },
    )

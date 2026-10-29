from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid7

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from statement.app.enums.account import LedgerDiscrepancyKind
from statement.app.permissions import Permission
from statement.domain.entities.account import (
    CustomerAccount,
    CustomerAccountLedger,
    CustomerAccountStatus,
    LedgerOperationType,
)
from statement.domain.entities.customer import Customer
from statement.infra.models.account import (
    CustomerAccountLedgerDiscrepancy,
    CustomerAccountLedgerVerified,
)
from tests.utils.auth import AuthHeaders
from tests.utils.db import DbTestUtil


async def add_account_with_ledger(
    session: AsyncSession,
    movements: int = 2,
) -> CustomerAccount:
    """An account whose ledger is no=1 (genesis), then ``movements`` deposits of 10."""
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

    row = CustomerAccountLedger.create(account.id, created_by=None)
    session.add(row)
    for _ in range(movements):
        row = CustomerAccountLedger.follow(
            row,
            amount=Decimal("10.00"),
            operation_type=LedgerOperationType.DEPOSIT,
            operation_id=uuid7(),
            created_by=None,
        )
        session.add(row)
    await session.flush()

    return account


async def add_discrepancy(
    session: AsyncSession,
    account_id: UUID,
    *,
    no: int,
    kind: LedgerDiscrepancyKind = LedgerDiscrepancyKind.BALANCE,
) -> CustomerAccountLedgerDiscrepancy:
    discrepancy = CustomerAccountLedgerDiscrepancy(
        account_id=account_id,
        no=no,
        kind=kind,
        prev_no=no - 1,
        expected_balance=Decimal("20.00"),
        actual_balance=Decimal("25.00"),
    )
    session.add(discrepancy)
    await session.flush()

    return discrepancy


async def add_checkpoint(
    session: AsyncSession,
    account_id: UUID,
    through_no: int,
    balance: str,
) -> None:
    session.add(
        CustomerAccountLedgerVerified(
            account_id=account_id,
            through_no=through_no,
            balance=Decimal(balance),
        )
    )
    await session.flush()


def discrepancy_url(account_id: UUID) -> str:
    return f"/v1/admin/accounts/{account_id}/ledger/discrepancy"


def resolve_url(account_id: UUID) -> str:
    return f"{discrepancy_url(account_id)}/resolve"


@pytest.mark.anyio
async def test_get_open_discrepancy(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session, movements=3)
    discrepancy = await add_discrepancy(session, account.id, no=3)

    response = await client.get(
        discrepancy_url(account.id),
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_GET]),
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["id"] == str(account.id)
    assert body["no"] == discrepancy.no
    assert body["kind"] == LedgerDiscrepancyKind.BALANCE
    assert body["prev_no"] == 2
    assert Decimal(body["expected_balance"]) == Decimal("20.00")
    assert Decimal(body["actual_balance"]) == Decimal("25.00")
    assert body["verified_through_no"] == 0


@pytest.mark.anyio
async def test_get_discrepancy_reports_the_latest_checkpoint(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session, movements=3)
    await add_checkpoint(session, account.id, through_no=2, balance="10.00")
    await add_discrepancy(session, account.id, no=3)

    response = await client.get(
        discrepancy_url(account.id),
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_GET]),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["verified_through_no"] == 2


@pytest.mark.anyio
async def test_get_discrepancy_ignores_resolved_ones(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session)
    discrepancy = await add_discrepancy(session, account.id, no=2)
    discrepancy.resolved_at = datetime.now(UTC)
    await session.flush()

    response = await client.get(
        discrepancy_url(account.id),
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_GET]),
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_get_discrepancy_when_there_is_none(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session)

    response = await client.get(
        discrepancy_url(account.id),
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_GET]),
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_get_discrepancy_without_token(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    account = await add_account_with_ledger(session)

    response = await client.get(discrepancy_url(account.id))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.anyio
async def test_get_discrepancy_without_permission(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session)
    await add_discrepancy(session, account.id, no=2)

    response = await client.get(
        discrepancy_url(account.id),
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_GET]),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.anyio
async def test_resolve_defaults_to_the_broken_row(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session, movements=3)
    discrepancy = await add_discrepancy(session, account.id, no=3)

    sub = uuid7()
    response = await client.post(
        resolve_url(account.id),
        json={},
        headers=auth_headers(
            [Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_RESOLVE],
            str(sub),
        ),
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    # the ledger's own balance at row 3 (genesis 0, then 10, 20) is the new anchor
    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedgerVerified.__tablename__,
        {"account_id": account.id, "through_no": 3, "balance": Decimal("20.00")},
    )
    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedgerDiscrepancy.__tablename__,
        {
            "discrepancy_id": discrepancy.discrepancy_id,
            "resolved_by": sub,
            "resolved_at__isnull": False,
        },
    )


@pytest.mark.anyio
async def test_resolve_with_explicit_through_no(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session, movements=4)
    await add_discrepancy(session, account.id, no=3)

    response = await client.post(
        resolve_url(account.id),
        json={"through_no": 5},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_RESOLVE]),
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedgerVerified.__tablename__,
        {"account_id": account.id, "through_no": 5, "balance": Decimal("40.00")},
    )


@pytest.mark.anyio
async def test_resolve_anchor_balance_requires_through_no(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session, movements=3)
    await add_checkpoint(session, account.id, through_no=2, balance="10.00")
    await add_discrepancy(
        session,
        account.id,
        no=2,
        kind=LedgerDiscrepancyKind.ANCHOR_BALANCE,
    )

    response = await client.post(
        resolve_url(account.id),
        json={},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_RESOLVE]),
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedgerDiscrepancy.__tablename__,
        {"account_id": account.id, "resolved_at__isnull": True},
    )


@pytest.mark.anyio
async def test_resolve_cannot_move_the_checkpoint_backwards(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session, movements=3)
    await add_checkpoint(session, account.id, through_no=3, balance="20.00")
    await add_discrepancy(session, account.id, no=4)

    response = await client.post(
        resolve_url(account.id),
        json={"through_no": 3},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_RESOLVE]),
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.anyio
async def test_resolve_rejects_a_ledger_row_that_does_not_exist(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session, movements=2)
    await add_discrepancy(session, account.id, no=2)

    response = await client.post(
        resolve_url(account.id),
        json={"through_no": 99},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_RESOLVE]),
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.anyio
async def test_resolve_when_there_is_no_open_discrepancy(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session)

    response = await client.post(
        resolve_url(account.id),
        json={},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_RESOLVE]),
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.anyio
async def test_resolve_without_permission(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers: AuthHeaders,
) -> None:
    account = await add_account_with_ledger(session)
    await add_discrepancy(session, account.id, no=2)

    response = await client.post(
        resolve_url(account.id),
        json={},
        headers=auth_headers([Permission.ADMIN_ACCOUNTS_LEDGER_DISCREPANCY_GET]),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert await DbTestUtil.exists(
        session,
        CustomerAccountLedgerDiscrepancy.__tablename__,
        {"account_id": account.id, "resolved_at__isnull": True},
    )

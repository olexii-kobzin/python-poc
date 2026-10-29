from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from statement.domain.entities.account import CustomerAccount, CustomerAccountStatus
from statement.domain.entities.customer import Customer

# the generated CustomerAccountHistory class; it only exists at runtime
History: Any = CustomerAccount.__history_mapper__.class_


async def add_account(
    session: AsyncSession,
    customer_id: UUID | None = None,
    currency: str = "EUR",
    name: str = "main",
) -> CustomerAccount:
    now = datetime.now(UTC)
    if customer_id is None:
        customer_id = uuid7()
        session.add(
            Customer(
                id=customer_id,
                email=f"{uuid7()}@mail.com",
                name="customer",
                created_at=now,
                updated_at=now,
            )
        )
    account = CustomerAccount(
        id=uuid7(),
        customer_id=customer_id,
        currency=currency,
        name=name,
        status=CustomerAccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        updated_by=uuid7(),
    )
    session.add(account)
    await session.flush()

    return account


async def history_of(
    session: AsyncSession,
    account: CustomerAccount,
) -> list[tuple[int, str | None]]:
    stmt = (
        sa.select(History.version, History.name)
        .where(History.id == account.id)
        .order_by(History.version)
    )
    return [(row.version, row.name) for row in (await session.execute(stmt)).all()]


@pytest.mark.anyio
async def test_insert_starts_at_version_one_without_history(
    session: AsyncSession,
) -> None:
    account = await add_account(session)

    assert account.version == 1
    assert await history_of(session, account) == []


@pytest.mark.anyio
async def test_update_archives_the_previous_state(session: AsyncSession) -> None:
    account = await add_account(session, name="before")

    account.name = "after"
    await session.flush()

    assert account.version == 2
    assert await history_of(session, account) == [(1, "before")]


@pytest.mark.anyio
async def test_each_update_adds_one_history_row(session: AsyncSession) -> None:
    account = await add_account(session, name="first")

    account.name = "second"
    await session.flush()
    account.name = "third"
    await session.flush()

    assert account.version == 3
    assert await history_of(session, account) == [(1, "first"), (2, "second")]


@pytest.mark.anyio
async def test_flush_without_changes_writes_no_history(session: AsyncSession) -> None:
    account = await add_account(session)

    await session.flush()

    assert account.version == 1
    assert await history_of(session, account) == []


@pytest.mark.anyio
async def test_new_rows_start_at_one_regardless_of_other_rows(
    session: AsyncSession,
) -> None:
    """The version default is a literal 1, not max(version)+1 over the table."""
    first = await add_account(session, currency="EUR")
    first.name = "bumped"
    await session.flush()

    second = await add_account(session, customer_id=first.customer_id, currency="USD")

    assert first.version == 2
    assert second.version == 1
